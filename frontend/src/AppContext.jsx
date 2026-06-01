import { createContext, useContext, useState, useEffect, useRef, useCallback, useMemo } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
if (!import.meta.env.VITE_API_URL && import.meta.env.PROD) {
  throw new Error("VITE_API_URL is required in production builds");
}

const AppContext = createContext(null);

function exportDateSuffix() {
  const d = new Date();
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const yyyy = d.getFullYear();
  return `${dd}${mm}${yyyy}`;
}

function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

function detectSourceFromFile(file) {
  if (!file) return "file";
  const name = file.name.toLowerCase();
  if (file.type === "application/pdf") return "pdf";
  if (name.includes("screenshot") || name.includes("screen shot")) return "screenshot";
  if (file.type.startsWith("image/")) return "image";
  return "file";
}

function getSourceIcon(source) {
  switch (source) {
    case "text": return { icon: "⌨️", label: "text" };
    case "audio": return { icon: "🎤", label: "audio" };
    case "pdf": return { icon: "📄", label: "PDF" };
    case "screenshot": return { icon: "🖼️", label: "screenshot" };
    case "image": return { icon: "🖼️", label: "image" };
    default: return { icon: "📎", label: "file" };
  }
}

function parseItemDate(dateStr, timeStr) {
  if (!dateStr) return null;
  let d = null;

  // dd.mm.yyyy (European, from backend normalize_date) — MUST check first
  // because new Date("01.06.2026") wrongly parses as Jan 6 in US locale
  const euMatch = dateStr.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (euMatch) {
    const [, day, month, year] = euMatch.map(Number);
    d = new Date(year, month - 1, day);
    if (!isNaN(d.getTime())) {
      if (timeStr) {
        const [h, m] = timeStr.split(':').map(Number);
        d.setHours(h || 0, m || 0, 0, 0);
      } else {
        d.setHours(23, 59, 59, 999);
      }
      return d;
    }
  }

  // dd/mm/yyyy or dd-mm-yyyy
  const sepMatch = dateStr.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
  if (sepMatch) {
    const [, day, month, year] = sepMatch.map(Number);
    d = new Date(year, month - 1, day);
    if (!isNaN(d.getTime())) {
      if (timeStr) {
        const [h, m] = timeStr.split(':').map(Number);
        d.setHours(h || 0, m || 0, 0, 0);
      } else {
        d.setHours(23, 59, 59, 999);
      }
      return d;
    }
  }

  // ISO / native parse (yyyy-mm-dd, etc.)
  d = new Date(dateStr);
  if (!isNaN(d.getTime())) {
    if (timeStr) {
      const [h, m] = timeStr.split(':').map(Number);
      d.setHours(h || 0, m || 0, 0, 0);
    } else {
      d.setHours(23, 59, 59, 999);
    }
    return d;
  }

  return null;
}

function isItemExpired(item) {
  const now = new Date();
  const dateStr = item.type === "task" ? item.due_date : item.date;
  const timeStr = item.type === "task" ? null : item.time;
  const d = parseItemDate(dateStr, timeStr);
  if (!d) return false;
  return d < now;
}

async function fetchWithTimeout(url, options = {}, { timeout = 15000, retries = 1 } = {}) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(id);
    return response;
  } catch (err) {
    clearTimeout(id);
    if (retries > 0 && err.name !== "AbortError") {
      await new Promise((r) => setTimeout(r, 1000));
      return fetchWithTimeout(url, options, { timeout, retries: retries - 1 });
    }
    throw err;
  }
}

export function AppProvider({ children }) {
  // ── State ──
  const [text, setText] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [savedTasks, setSavedTasks] = useState([]);
  const [savedEvents, setSavedEvents] = useState([]);
  const [error, setError] = useState(null);
  const [dashLoading, setDashLoading] = useState(true);
  const [selectedTasks, setSelectedTasks] = useState(new Set());
  const [selectedEvents, setSelectedEvents] = useState(new Set());
  const [hasAnalyzed, setHasAnalyzed] = useState(false);
  const [captureSource, setCaptureSource] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioMimeType, setAudioMimeType] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [isHoveringFile, setIsHoveringFile] = useState(false);
  const [openMenuId, setOpenMenuId] = useState(null);
  const [openMenuType, setOpenMenuType] = useState(null);
  const [editingNoteId, setEditingNoteId] = useState(null);
  const [editingNoteType, setEditingNoteType] = useState(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [editingItemId, setEditingItemId] = useState(null);
  const [editingItemType, setEditingItemType] = useState(null);
  const [editDraft, setEditDraft] = useState({ title: "", due_date: "", date: "", time: "" });
  const [page, setPage] = useState("capture");
  const [hamburgerOpen, setHamburgerOpen] = useState(false);
  const [deviceId, setDeviceId] = useState("");
  const [quota, setQuota] = useState(null);
  const [originalInputText, setOriginalInputText] = useState("");
  const [enhancingItemId, setEnhancingItemId] = useState(null);
  const [enhancingAllType, setEnhancingAllType] = useState(null);
  const [provider, setProvider] = useState(() => localStorage.getItem("snapcapture_provider") || "gemini");
  const [customApiKey, setCustomApiKey] = useState(() => localStorage.getItem("snapcapture_api_key") || "");
  const [showApiKey, setShowApiKey] = useState(false);
  const [feedback, setFeedback] = useState(null);

  const showFeedback = useCallback((message) => {
    setFeedback(message);
    setTimeout(() => setFeedback(null), 2500);
  }, []);

  // ── Refs ──
  const fileInputRef = useRef(null);
  const abortRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recordingTimerRef = useRef(null);
  const itemsRef = useRef(items);
  const selectedFileRef = useRef(selectedFile);
  const originalInputTextRef = useRef(originalInputText);
  const quotaRef = useRef(quota);

  useEffect(() => { itemsRef.current = items; }, [items]);
  useEffect(() => { selectedFileRef.current = selectedFile; }, [selectedFile]);
  useEffect(() => { originalInputTextRef.current = originalInputText; }, [originalInputText]);
  useEffect(() => { quotaRef.current = quota; }, [quota]);

  // ── Effects ──
  useEffect(() => {
    localStorage.setItem("snapcapture_provider", provider);
  }, [provider]);

  useEffect(() => {
    localStorage.setItem("snapcapture_api_key", customApiKey);
  }, [customApiKey]);

  useEffect(() => {
    let id = localStorage.getItem("snapcapture_device_id");
    if (!id) {
      id = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem("snapcapture_device_id", id);
    }
    setDeviceId(id);
  }, []);

  useEffect(() => {
    if (!deviceId) return;
    loadQuota();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  // Cleanup recording on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    function handleClickOutside(e) {
      if (!e.target.closest(".item-menu-wrap")) {
        setOpenMenuId(null);
        setOpenMenuType(null);
      }
    }
    if (openMenuId !== null) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [openMenuId]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (!e.target.closest(".hamburger-wrap")) {
        setHamburgerOpen(false);
      }
    }
    if (hamburgerOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [hamburgerOpen]);

  // ── Handlers (dependency-ordered) ──
  const buildHeaders = useCallback((extra = {}) => {
    return { "X-Device-ID": deviceId, ...extra };
  }, [deviceId]);

  const buildAiHeaders = useCallback((extra = {}) => {
    const h = buildHeaders(extra);
    if (provider) h["X-Provider"] = provider;
    if (customApiKey.trim()) h["X-API-Key"] = customApiKey.trim();
    return h;
  }, [buildHeaders, provider, customApiKey]);

  const clearInputs = useCallback(() => {
    setText("");
    setSelectedFile(null);
    setAudioBlob(null);
    setAudioMimeType("");
    setHasAnalyzed(false);
    setItems([]);
    setCaptureSource("");
    setOriginalInputText("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    if (!window.MediaRecorder) {
      setError("Audio recording is not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/wav";
      const mediaRecorder = new MediaRecorder(stream, { mimeType });
      const chunks = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: mimeType });
        setAudioBlob(blob);
        setAudioMimeType(mimeType);
        stream.getTracks().forEach((track) => track.stop());
      };
      mediaRecorder.start();
      mediaRecorderRef.current = mediaRecorder;
      setIsRecording(true);
      setRecordingTime(0);
      recordingTimerRef.current = setInterval(() => {
        setRecordingTime((t) => t + 1);
      }, 1000);
    } catch {
      setError("Microphone access denied or not available.");
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (recordingTimerRef.current) {
      clearInterval(recordingTimerRef.current);
      recordingTimerRef.current = null;
    }
    setIsRecording(false);
  }, []);

  const loadDashboard = useCallback(async () => {
    try {
      // Enforce temporary-buffer design: auto-delete items older than 1 hour
      await fetchWithTimeout(`${API_URL}/cleanup`, {
        method: "POST",
        headers: buildHeaders(),
      });

      const [tasksRes, eventsRes] = await Promise.all([
        fetchWithTimeout(`${API_URL}/tasks`, { headers: buildHeaders() }),
        fetchWithTimeout(`${API_URL}/events`, { headers: buildHeaders() }),
      ]);
      if (!tasksRes.ok || !eventsRes.ok) return;
      const [tasksData, eventsData] = await Promise.all([
        tasksRes.json(),
        eventsRes.json(),
      ]);
      let tasks = tasksData.items || [];
      let events = eventsData.items || [];

      // Mark past-due items as expired
      const expiredTaskIds = tasks
        .filter((t) => t.status !== "expired" && isItemExpired(t))
        .map((t) => t.id);
      const expiredEventIds = events
        .filter((e) => e.status !== "expired" && isItemExpired(e))
        .map((e) => e.id);

      if (expiredTaskIds.length > 0) {
        await fetchWithTimeout(`${API_URL}/tasks/bulk-update`, {
          method: "POST",
          headers: buildHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ ids: expiredTaskIds, status: "expired" }),
        });
        tasks = tasks.map((t) =>
          expiredTaskIds.includes(t.id) ? { ...t, status: "expired" } : t
        );
      }
      if (expiredEventIds.length > 0) {
        await fetchWithTimeout(`${API_URL}/events/bulk-update`, {
          method: "POST",
          headers: buildHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ ids: expiredEventIds, status: "expired" }),
        });
        events = events.map((e) =>
          expiredEventIds.includes(e.id) ? { ...e, status: "expired" } : e
        );
      }

      setSavedTasks(tasks);
      setSavedEvents(events);
    } catch {
      // silent
    }
  }, [buildHeaders]);

  const loadQuota = useCallback(async () => {
    try {
      const res = await fetchWithTimeout(`${API_URL}/quota`, { headers: buildHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      setQuota(data);
    } catch {
      // silent
    }
  }, [buildHeaders]);

  const saveItem = useCallback(async (item) => {
    setError(null);
    const endpoint = item.type === "task" ? "tasks" : "events";
    try {
      const response = await fetchWithTimeout(`${API_URL}/${endpoint}`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(item),
      });
      if (!response.ok) throw new Error(`Save failed (${response.status})`);
      const updatedItems = items.filter((x) => x !== item);
      setItems(updatedItems);
      if (updatedItems.length === 0) clearInputs();
      await loadDashboard();
      showFeedback(`${item.type === "task" ? "Task" : "Event"} saved`);
    } catch (err) {
      setError(err.message);
    }
  }, [items, buildHeaders, clearInputs, loadDashboard, showFeedback]);

  const rejectItem = useCallback((item) => {
    const updatedItems = items.filter((x) => x !== item);
    setItems(updatedItems);
    if (updatedItems.length === 0) clearInputs();
  }, [items, clearInputs]);

  const saveAllOfType = useCallback(async (type) => {
    setError(null);
    const toSave = items.filter((item) => item.type === type);
    if (toSave.length === 0) return;
    try {
      const res = await fetchWithTimeout(`${API_URL}/items/bulk-save`, {
        method: "POST",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ items: toSave }),
      });
      if (!res.ok) throw new Error(`Bulk save failed (${res.status})`);
      const updatedItems = items.filter((item) => item.type !== type);
      setItems(updatedItems);
      if (updatedItems.length === 0) clearInputs();
      await loadDashboard();
      showFeedback(`${toSave.length} ${type}${toSave.length > 1 ? "s" : ""} saved`);
    } catch (err) {
      setError(err.message);
    }
  }, [items, buildHeaders, clearInputs, loadDashboard, showFeedback]);

  const rejectAll = useCallback(() => {
    setItems([]);
    clearInputs();
  }, [clearInputs]);

  const rejectAllOfType = useCallback((type) => {
    const updatedItems = items.filter((item) => item.type !== type);
    setItems(updatedItems);
    if (updatedItems.length === 0) clearInputs();
  }, [items, clearInputs]);

  const toggleTask = useCallback(async (task) => {
    setError(null);
    try {
      const newStatus = task.status === "done" ? "open" : "done";
      const res = await fetchWithTimeout(`${API_URL}/tasks/${task.id}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(`Toggle failed (${res.status})`);
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [buildHeaders, loadDashboard]);

  const toggleEvent = useCallback(async (eventItem) => {
    setError(null);
    try {
      const newStatus = eventItem.status === "done" ? "open" : "done";
      const res = await fetchWithTimeout(`${API_URL}/events/${eventItem.id}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ status: newStatus }),
      });
      if (!res.ok) throw new Error(`Toggle failed (${res.status})`);
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [buildHeaders, loadDashboard]);

  const toggleTaskSelection = useCallback((id) => {
    setSelectedTasks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleEventSelection = useCallback((id) => {
    setSelectedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAllItems = useCallback(() => {
    const allSelected =
      selectedTasks.size === savedTasks.length &&
      selectedEvents.size === savedEvents.length;
    if (allSelected) {
      setSelectedTasks(new Set());
      setSelectedEvents(new Set());
    } else {
      setSelectedTasks(new Set(savedTasks.map((t) => t.id)));
      setSelectedEvents(new Set(savedEvents.map((e) => e.id)));
    }
  }, [selectedTasks, selectedEvents, savedTasks, savedEvents]);

  const clearAllSelections = useCallback(() => {
    setSelectedTasks(new Set());
    setSelectedEvents(new Set());
  }, []);

  const totalSelected = useMemo(() => selectedTasks.size + selectedEvents.size, [selectedTasks, selectedEvents]);

  const bulkMarkDone = useCallback(async () => {
    setError(null);
    try {
      await Promise.all([
        selectedTasks.size > 0
          ? fetchWithTimeout(`${API_URL}/tasks/bulk-update`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: Array.from(selectedTasks), status: "done" }),
            })
          : Promise.resolve(),
        selectedEvents.size > 0
          ? fetchWithTimeout(`${API_URL}/events/bulk-update`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: Array.from(selectedEvents), status: "done" }),
            })
          : Promise.resolve(),
      ]);
      clearAllSelections();
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [selectedTasks, selectedEvents, buildHeaders, clearAllSelections, loadDashboard]);

  const bulkMarkUndone = useCallback(async () => {
    setError(null);
    try {
      await Promise.all([
        selectedTasks.size > 0
          ? fetchWithTimeout(`${API_URL}/tasks/bulk-update`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: Array.from(selectedTasks), status: "open" }),
            })
          : Promise.resolve(),
        selectedEvents.size > 0
          ? fetchWithTimeout(`${API_URL}/events/bulk-update`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: Array.from(selectedEvents), status: "open" }),
            })
          : Promise.resolve(),
      ]);
      clearAllSelections();
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [selectedTasks, selectedEvents, buildHeaders, clearAllSelections, loadDashboard]);

  const bulkDelete = useCallback(async () => {
    const count = selectedTasks.size + selectedEvents.size;
    if (count === 0) return;
    if (!window.confirm(`Delete ${count} selected item${count > 1 ? "s" : ""}?`)) return;
    setError(null);
    try {
      const [tasksRes, eventsRes] = await Promise.all([
        selectedTasks.size > 0
          ? fetchWithTimeout(`${API_URL}/tasks/bulk-delete`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: Array.from(selectedTasks) }),
            })
          : Promise.resolve(null),
        selectedEvents.size > 0
          ? fetchWithTimeout(`${API_URL}/events/bulk-delete`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: Array.from(selectedEvents) }),
            })
          : Promise.resolve(null),
      ]);
      if (tasksRes && !tasksRes.ok) throw new Error(`Task bulk-delete failed (${tasksRes.status})`);
      if (eventsRes && !eventsRes.ok) throw new Error(`Event bulk-delete failed (${eventsRes.status})`);
      clearAllSelections();
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [selectedTasks, selectedEvents, buildHeaders, clearAllSelections, loadDashboard]);

  const clearAll = useCallback(async () => {
    const total = savedTasks.length + savedEvents.length;
    if (total === 0) return;
    if (!window.confirm(`Clear all ${total} item${total > 1 ? "s" : ""} from the dashboard?`)) return;
    setError(null);
    try {
      const [tasksRes, eventsRes] = await Promise.all([
        savedTasks.length > 0
          ? fetchWithTimeout(`${API_URL}/tasks/bulk-delete`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: savedTasks.map((t) => t.id) }),
            })
          : Promise.resolve(null),
        savedEvents.length > 0
          ? fetchWithTimeout(`${API_URL}/events/bulk-delete`, {
              method: "POST",
              headers: buildHeaders({ "Content-Type": "application/json" }),
              body: JSON.stringify({ ids: savedEvents.map((e) => e.id) }),
            })
          : Promise.resolve(null),
      ]);
      if (tasksRes && !tasksRes.ok) throw new Error(`Task clear failed (${tasksRes.status})`);
      if (eventsRes && !eventsRes.ok) throw new Error(`Event clear failed (${eventsRes.status})`);
      clearAllSelections();
      await loadDashboard();
      showFeedback("Dashboard cleared");
    } catch (err) {
      setError(err.message);
    }
  }, [savedTasks, savedEvents, buildHeaders, clearAllSelections, loadDashboard, showFeedback]);

  const analyzeCapture = useCallback(async () => {
    if (!text.trim() && !selectedFile && !audioBlob) return;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setItems([]);
    try {
      let response;
      if (audioBlob) {
        const formData = new FormData();
        const ext = audioMimeType.split(";")[0].replace("audio/", "") || "webm";
        formData.append("file", audioBlob, `recording.${ext}`);
        response = await fetch(`${API_URL}/analyze-audio`, {
          method: "POST",
          headers: buildAiHeaders(),
          body: formData,
          signal: controller.signal,
        });
      } else if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        response = await fetch(`${API_URL}/analyze-file`, {
          method: "POST",
          headers: buildAiHeaders(),
          body: formData,
          signal: controller.signal,
        });
      } else {
        response = await fetch(`${API_URL}/analyze`, {
          method: "POST",
          headers: buildAiHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ text }),
          signal: controller.signal,
        });
      }
      if (!response.ok) {
        if (response.status === 429) throw new Error("Daily API quota exceeded. Local extraction only.");
        throw new Error(`Analysis failed (${response.status})`);
      }
      const data = await response.json();
      // DEBUG: console.log("[SnapCapture] analysis response:", data);
      if (data.quota_remaining !== undefined && data.quota_remaining !== null) {
        setQuota((prev) =>
          prev
            ? { ...prev, remaining: data.quota_remaining, used_today: prev.limit - data.quota_remaining }
            : { remaining: data.quota_remaining, limit: data.quota_remaining + 1, used_today: 1, date: "" }
        );
      }
      if (data.quota_exceeded) {
        setError("Daily AI quota exhausted — showing local extraction results. Upgrade for more calls.");
      }
      let source = "text";
      let sourceLabel = "text";
      if (audioBlob) {
        source = "audio";
        sourceLabel = "audio recording";
      } else if (selectedFile) {
        source = detectSourceFromFile(selectedFile);
        sourceLabel = selectedFile.name;
      }
      const itemsWithSource = (data.items || []).map((item) => ({ ...item, source, id: item.id || `${item.type}-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}` }));
      setItems(itemsWithSource);
      setCaptureSource(sourceLabel);
      setHasAnalyzed(true);
      if (audioBlob) {
        setOriginalInputText(`[Audio recording: ${formatTime(recordingTime)}]`);
      } else if (selectedFile) {
        setOriginalInputText(`[File: ${selectedFile.name}]`);
      } else {
        setOriginalInputText(text);
      }
    } catch (err) {
      // DEBUG: console.error("[SnapCapture] analysis error:", err);
      if (err.name === "AbortError") setError("Request cancelled.");
      else setError(err.message);
    } finally {
      setLoading(false);
      if (abortRef.current === controller) abortRef.current = null;
    }
  }, [text, selectedFile, audioBlob, audioMimeType, recordingTime, buildAiHeaders]);

  const enhanceItem = useCallback(async (item) => {
    if (!quota || quota.remaining <= 0) {
      setError("Daily AI quota exhausted. Cannot enhance items.");
      return;
    }
    setError(null);
    setEnhancingItemId(item.id);
    const isFileSource = ["pdf", "image", "screenshot", "file"].includes(item.source);
    const hasFile = selectedFile && isFileSource;
    try {
      let res;
      if (hasFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("item_json", JSON.stringify(item));
        res = await fetch(`${API_URL}/enhance-item-file`, {
          method: "POST",
          headers: buildAiHeaders(),
          body: formData,
        });
      } else {
        let sourceText = originalInputText;
        if (!sourceText || sourceText.startsWith("[")) {
          sourceText = [item.title, item.original_date, item.due_date, item.date, item.time, item.location, item.note]
            .filter(Boolean)
            .join(" ");
        }
        res = await fetch(`${API_URL}/enhance-item`, {
          method: "POST",
          headers: buildAiHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ item, source_text: sourceText }),
        });
      }
      if (!res.ok) {
        if (res.status === 429) throw new Error("Daily API quota exceeded.");
        throw new Error(`Enhance failed (${res.status})`);
      }
      const data = await res.json();
      const refined = { ...data.item, source: item.source, id: item.id };
      const updatedItems = items.map((it) => (it === item ? refined : it));
      setItems(updatedItems);
      if (data.quota_remaining !== undefined && data.quota_remaining !== null) {
        setQuota((prev) =>
          prev
            ? { ...prev, remaining: data.quota_remaining, used_today: prev.limit - data.quota_remaining }
            : { remaining: data.quota_remaining, limit: data.quota_remaining + 1, used_today: 1, date: "" }
        );
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setEnhancingItemId(null);
    }
  }, [quota, selectedFile, originalInputText, items, buildAiHeaders]);

  const enhanceAllOfType = useCallback(async (type) => {
    const latestQuota = quotaRef.current;
    const latestItems = itemsRef.current;
    const latestFile = selectedFileRef.current;
    const latestSourceText = originalInputTextRef.current;

    console.log("[enhanceAllOfType] called type=", type, "items.length=", latestItems.length, "quota=", latestQuota);

    if (!latestQuota || latestQuota.remaining <= 0) {
      setError("Daily AI quota exhausted. Cannot enhance items.");
      return;
    }
    const toEnhance = latestItems.filter((i) => i.type === type);
    console.log("[enhanceAllOfType] toEnhance.length=", toEnhance.length);
    if (toEnhance.length === 0) {
      console.warn("[enhanceAllOfType] no items of type", type, "found in", latestItems);
      return;
    }
    if (toEnhance.length > latestQuota.remaining) {
      setError(`Not enough quota to enhance all ${type}s. Need ${toEnhance.length}, have ${latestQuota.remaining}.`);
      return;
    }
    setError(null);
    setEnhancingAllType(type);
    let currentItems = latestItems;
    for (const item of toEnhance) {
      setEnhancingItemId(item.id);
      try {
        const isFileSource = ["pdf", "image", "screenshot", "file"].includes(item.source);
        const hasFile = latestFile && isFileSource;
        let res;
        if (hasFile) {
          const formData = new FormData();
          formData.append("file", latestFile);
          formData.append("item_json", JSON.stringify(item));
          res = await fetch(`${API_URL}/enhance-item-file`, {
            method: "POST",
            headers: buildAiHeaders(),
            body: formData,
          });
        } else {
          let sourceText = latestSourceText;
          if (!sourceText || sourceText.startsWith("[")) {
            sourceText = [item.title, item.original_date, item.due_date, item.date, item.time, item.location, item.note]
              .filter(Boolean)
              .join(" ");
          }
          res = await fetch(`${API_URL}/enhance-item`, {
            method: "POST",
            headers: buildAiHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify({ item, source_text: sourceText }),
          });
        }
        if (!res.ok) {
          if (res.status === 429) throw new Error("Daily API quota exceeded.");
          throw new Error(`Enhance failed (${res.status})`);
        }
        const data = await res.json();
        if (data.quota_exceeded) {
          setError("Daily API quota exceeded.");
          break;
        }
        const refined = { ...data.item, source: item.source, id: item.id };
        currentItems = currentItems.map((it) => (it === item || it.id === item.id ? refined : it));
        setItems(currentItems);
        if (data.quota_remaining !== undefined && data.quota_remaining !== null) {
          setQuota((prev) =>
            prev
              ? { ...prev, remaining: data.quota_remaining, used_today: prev.limit - data.quota_remaining }
              : { remaining: data.quota_remaining, limit: data.quota_remaining + 1, used_today: 1, date: "" }
          );
        }
      } catch (err) {
        console.error("[enhanceAllOfType] item error:", err);
        setError(err.message);
        break;
      }
    }
    setEnhancingItemId(null);
    setEnhancingAllType(null);
  }, [buildAiHeaders]);

  const exportSelected = useCallback(async () => {
    setError(null);
    try {
      if (selectedTasks.size > 0) {
        const params = new URLSearchParams();
        selectedTasks.forEach((id) => params.append("ids", id));
        const res = await fetch(`${API_URL}/export/tasks/csv?${params}`, { headers: buildHeaders() });
        if (!res.ok) throw new Error(`Task export failed (${res.status})`);
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `snapcapture_tasks_${exportDateSuffix()}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
      if (selectedEvents.size > 0) {
        const params = new URLSearchParams();
        selectedEvents.forEach((id) => params.append("ids", id));
        const win = window.open(`${API_URL}/export/events/ics?${params}`, "_blank");
        if (win) win.opener = null;
      }
      const total = selectedTasks.size + selectedEvents.size;
      showFeedback(`${total} item${total > 1 ? "s" : ""} exported`);
    } catch (err) {
      setError(err.message);
    }
  }, [selectedTasks, selectedEvents, buildHeaders, showFeedback]);

  const toggleMenu = useCallback((id, type) => {
    if (openMenuId === id && openMenuType === type) {
      setOpenMenuId(null);
      setOpenMenuType(null);
    } else {
      setOpenMenuId(id);
      setOpenMenuType(type);
    }
  }, [openMenuId, openMenuType]);

  const startEditNote = useCallback((item, type) => {
    setEditingNoteId(item.id);
    setEditingNoteType(type);
    setNoteDraft(item.note || "");
    setOpenMenuId(null);
    setOpenMenuType(null);
  }, []);

  const startEditItem = useCallback((item, type) => {
    setEditingItemId(item.id);
    setEditingItemType(type);
    setEditDraft({ title: item.title || "", due_date: item.due_date || "", date: item.date || "", time: item.time || "" });
    setOpenMenuId(null);
    setOpenMenuType(null);
  }, []);

  const saveItemEdit = useCallback(async () => {
    if (!editingItemId || !editingItemType) return;
    setError(null);
    const endpoint = editingItemType === "task" ? "tasks" : "events";
    const body = { title: editDraft.title.trim() };
    if (editingItemType === "task") {
      body.due_date = editDraft.due_date.trim() || null;
    } else {
      body.date = editDraft.date.trim() || null;
      body.time = editDraft.time.trim() || null;
    }
    try {
      const res = await fetch(`${API_URL}/${endpoint}/${editingItemId}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Save failed (${res.status})`);
      setEditingItemId(null);
      setEditingItemType(null);
      setEditDraft({ title: "", due_date: "", date: "", time: "" });
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [editingItemId, editingItemType, editDraft, buildHeaders, loadDashboard]);

  const cancelEditItem = useCallback(() => {
    setEditingItemId(null);
    setEditingItemType(null);
    setEditDraft({ title: "", due_date: "", date: "", time: "" });
  }, []);

  const saveNote = useCallback(async () => {
    if (!editingNoteId || !editingNoteType) return;
    setError(null);
    const endpoint = editingNoteType === "task" ? "tasks" : "events";
    try {
      const res = await fetch(`${API_URL}/${endpoint}/${editingNoteId}`, {
        method: "PATCH",
        headers: buildHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ note: noteDraft.trim() || null }),
      });
      if (!res.ok) throw new Error(`Save note failed (${res.status})`);
      setEditingNoteId(null);
      setEditingNoteType(null);
      setNoteDraft("");
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [editingNoteId, editingNoteType, noteDraft, buildHeaders, loadDashboard]);

  const cancelEditNote = useCallback(() => {
    setEditingNoteId(null);
    setEditingNoteType(null);
    setNoteDraft("");
  }, []);

  const exportSingleItem = useCallback(async (item, type, taskFormat = "csv") => {
    setError(null);
    try {
      if (type === "task") {
        const endpoint = taskFormat === "ics" ? `/export/tasks/ics?ids=${item.id}` : `/export/tasks/csv?ids=${item.id}`;
        const ext = taskFormat === "ics" ? "ics" : "csv";
        const res = await fetch(`${API_URL}${endpoint}`, { headers: buildHeaders() });
        if (!res.ok) throw new Error(`Export failed (${res.status})`);
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `snapcapture_task_${item.id}_${exportDateSuffix()}.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        const res = await fetch(`${API_URL}/export/events/ics?ids=${item.id}`, { headers: buildHeaders() });
        if (!res.ok) throw new Error(`Export failed (${res.status})`);
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `snapcapture_event_${item.id}_${exportDateSuffix()}.ics`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      }
      showFeedback(`${type === "task" ? "Task" : "Event"} exported`);
    } catch (err) {
      setError(err.message);
    }
    setOpenMenuId(null);
    setOpenMenuType(null);
  }, [buildHeaders, showFeedback]);

  const deleteSingleItem = useCallback(async (item, type) => {
    if (!window.confirm("Delete this item?")) {
      setOpenMenuId(null);
      setOpenMenuType(null);
      return;
    }
    setError(null);
    setOpenMenuId(null);
    setOpenMenuType(null);
    const endpoint = type === "task" ? "tasks" : "events";
    try {
      const res = await fetch(`${API_URL}/${endpoint}/${item.id}`, {
        method: "DELETE",
        headers: buildHeaders(),
      });
      if (!res.ok) throw new Error(`Delete failed (${res.status})`);
      await loadDashboard();
    } catch (err) {
      setError(err.message);
    }
  }, [buildHeaders, loadDashboard]);

  const navigateTo = useCallback((newPage) => {
    setPage(newPage);
    setHamburgerOpen(false);
    window.scrollTo(0, 0);
  }, []);

  const handleKeyDown = useCallback((e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      analyzeCapture();
    }
  }, [analyzeCapture]);

  // ── Context value ──
  const value = useMemo(() => ({
    API_URL,
    text, setText,
    items, setItems,
    loading, setLoading,
    savedTasks, setSavedTasks,
    savedEvents, setSavedEvents,
    error, setError,
    dashLoading, setDashLoading,
    selectedTasks, setSelectedTasks,
    selectedEvents, setSelectedEvents,
    hasAnalyzed, setHasAnalyzed,
    captureSource, setCaptureSource,
    selectedFile, setSelectedFile,
    audioBlob, setAudioBlob,
    audioMimeType, setAudioMimeType,
    isRecording, setIsRecording,
    recordingTime, setRecordingTime,
    isHoveringFile, setIsHoveringFile,
    openMenuId, setOpenMenuId,
    openMenuType, setOpenMenuType,
    editingNoteId, setEditingNoteId,
    editingNoteType, setEditingNoteType,
    noteDraft, setNoteDraft,
    editingItemId, setEditingItemId,
    editingItemType, setEditingItemType,
    editDraft, setEditDraft,
    page, setPage,
    hamburgerOpen, setHamburgerOpen,
    deviceId,
    quota, setQuota,
    originalInputText, setOriginalInputText,
    enhancingItemId, setEnhancingItemId,
    enhancingAllType, setEnhancingAllType,
    provider, setProvider,
    customApiKey, setCustomApiKey,
    showApiKey, setShowApiKey,
    feedback,
    fileInputRef,
    buildHeaders,
    buildAiHeaders,
    clearInputs,
    formatTime,
    detectSourceFromFile,
    getSourceIcon,
    startRecording,
    stopRecording,
    saveItem,
    rejectItem,
    saveAllOfType,
    rejectAll,
    rejectAllOfType,
    loadDashboard,
    loadQuota,
    toggleTask,
    toggleEvent,
    toggleTaskSelection,
    toggleEventSelection,
    selectAllItems,
    clearAllSelections,
    totalSelected,
    bulkMarkDone,
    bulkMarkUndone,
    bulkDelete,
    clearAll,
    analyzeCapture,
    enhanceItem,
    enhanceAllOfType,
    exportSelected,
    toggleMenu,
    startEditNote,
    startEditItem,
    saveItemEdit,
    cancelEditItem,
    saveNote,
    cancelEditNote,
    exportSingleItem,
    deleteSingleItem,
    navigateTo,
    handleKeyDown,
    exportDateSuffix,
  }), [
    text, items, loading, savedTasks, savedEvents, error, dashLoading,
    selectedTasks, selectedEvents, hasAnalyzed, captureSource,
    selectedFile, audioBlob, audioMimeType, isRecording, recordingTime,
    isHoveringFile, openMenuId, openMenuType, editingNoteId, editingNoteType,
    noteDraft, editingItemId, editingItemType, editDraft,
    page, hamburgerOpen, deviceId, quota, originalInputText, enhancingItemId,
    enhancingAllType,
    provider, customApiKey, showApiKey, feedback,
    buildHeaders, buildAiHeaders, clearInputs, startRecording, stopRecording,
    saveItem, rejectItem, saveAllOfType, rejectAll, rejectAllOfType, loadDashboard, loadQuota,
    toggleTask, toggleEvent, toggleTaskSelection, toggleEventSelection,
    selectAllItems, clearAllSelections, totalSelected, bulkMarkDone,
    bulkMarkUndone, bulkDelete, clearAll, analyzeCapture, enhanceItem, enhanceAllOfType, exportSelected,
    toggleMenu, startEditNote, startEditItem, saveItemEdit, cancelEditItem,
    saveNote, cancelEditNote, exportSingleItem, deleteSingleItem,
    navigateTo, handleKeyDown,
  ]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppContext() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppContext must be used within AppProvider");
  return ctx;
}
