import { useEffect, useMemo, useRef, useState } from "react";
import { useAppContext } from "../AppContext";

function getSortKey(item) {
  const dateStr = item.type === "task" ? item.due_date : item.date;
  const timeStr = item.type === "task" ? null : item.time;
  if (!dateStr) return Infinity;

  let d;

  // dd.mm.yyyy (European — MUST be first because native Date() mis-parses dots as mm.dd.yyyy)
  const euMatch = dateStr.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (euMatch) {
    const [, day, month, year] = euMatch.map(Number);
    d = new Date(year, month - 1, day);
  }

  // dd/mm/yyyy or dd-mm-yyyy
  if (!d) {
    const sepMatch = dateStr.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
    if (sepMatch) {
      const [, day, month, year] = sepMatch.map(Number);
      d = new Date(year, month - 1, day);
    }
  }

  // ISO / native parse (yyyy-mm-dd, etc.)
  if (!d) {
    d = new Date(dateStr);
    if (isNaN(d.getTime())) d = null;
  }

  if (!d) return Infinity;

  // Apply time — handle ranges like "15:00-16:00" by taking the start
  if (timeStr) {
    const startTime = timeStr.split('-')[0];
    const [h, m] = startTime.split(':').map(Number);
    d.setHours(h || 0, m || 0, 0, 0);
  } else {
    d.setHours(0, 0, 0, 0);
  }
  return d.getTime();
}

export default function HomePage() {
  const {
    text, setText,
    items,
    loading,
    hasAnalyzed,
    captureSource,
    selectedFile, setSelectedFile,
    audioBlob, setAudioBlob,
    audioMimeType, setAudioMimeType,
    isRecording,
    recordingTime,
    isHoveringFile, setIsHoveringFile,
    savedTasks, savedEvents,
    dashLoading, setDashLoading,
    selectedTasks, selectedEvents,
    openMenuId, openMenuType,
    editingNoteId, editingNoteType, noteDraft, setNoteDraft,
    editingItemId, editingItemType, editDraft, setEditDraft,
    quota,
    provider,
    hamburgerOpen, setHamburgerOpen,
    fileInputRef,
    getSourceIcon,
    clearInputs,
    formatTime,
    detectSourceFromFile,
    startRecording,
    stopRecording,
    saveItem,
    rejectItem,
    saveAllOfType,
    rejectAll,
    rejectAllOfType,
    loadDashboard,
    toggleTask,
    toggleEvent,
    toggleTaskSelection,
    toggleEventSelection,
    selectAllItems,
    totalSelected,
    bulkMarkDone,
    bulkMarkUndone,
    bulkDelete,
    exportSelected,
    clearAll,
    analyzeCapture,
    enhanceItem,
    enhancingItemId,
    enhanceAllOfType,
    enhancingAllType,
    toggleMenu,
    startEditNote,
    startEditItem,
    saveItemEdit,
    cancelEditItem,
    saveNote,
    cancelEditNote,
    exportSingleItem,
    deleteSingleItem,
    deviceId,
    setOpenMenuId,
    setOpenMenuType,
    handleKeyDown,
    navigateTo,
    feedback,
  } = useAppContext();

  const [exportSubmenuId, setExportSubmenuId] = useState(null);

  useEffect(() => {
    setExportSubmenuId(null);
  }, [openMenuId, openMenuType]);

  const suggestedTasks = useMemo(() => items.filter((i) => i.type === "task"), [items]);
  const suggestedEvents = useMemo(() => items.filter((i) => i.type === "event"), [items]);

  const sortedTasks = useMemo(() => {
    return [...savedTasks].sort((a, b) => {
      const aExpired = a.status === "expired" ? 1 : 0;
      const bExpired = b.status === "expired" ? 1 : 0;
      if (aExpired !== bExpired) return aExpired - bExpired;
      const keyDiff = getSortKey(a) - getSortKey(b);
      if (keyDiff !== 0) return keyDiff;
      return (a.id || 0) - (b.id || 0);
    });
  }, [savedTasks]);

  const sortedEvents = useMemo(() => {
    return [...savedEvents].sort((a, b) => {
      const aExpired = a.status === "expired" ? 1 : 0;
      const bExpired = b.status === "expired" ? 1 : 0;
      if (aExpired !== bExpired) return aExpired - bExpired;
      const keyDiff = getSortKey(a) - getSortKey(b);
      if (keyDiff !== 0) return keyDiff;
      return (a.id || 0) - (b.id || 0);
    });
  }, [savedEvents]);

  const allSelected = useMemo(() =>
    (savedTasks.length > 0 || savedEvents.length > 0) &&
    selectedTasks.size === savedTasks.length &&
    selectedEvents.size === savedEvents.length,
  [selectedTasks, selectedEvents, savedTasks, savedEvents]);

  const someSelected = useMemo(() =>
    (selectedTasks.size > 0 || selectedEvents.size > 0) && !allSelected,
  [selectedTasks, selectedEvents, allSelected]);

  const allCheckboxRef = useRef(null);

  useEffect(() => {
    if (allCheckboxRef.current) {
      allCheckboxRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  useEffect(() => {
    if (!deviceId) return; // Wait for deviceId to initialize before loading
    let cancelled = false;
    async function init() {
      setDashLoading(true);
      try {
        await loadDashboard();
      } finally {
        if (!cancelled) setDashLoading(false);
      }
    }
    init();
    return () => { cancelled = true; };
  }, [loadDashboard, setDashLoading, deviceId]);

  return (
    <>
      {/* ── Capture Header ── */}
      <div className="capture-header">
        <div className="hamburger-wrap">
          <button
            className="hamburger-btn"
            onClick={() => setHamburgerOpen(!hamburgerOpen)}
            aria-label="Menu"
          >
            &#9776;
          </button>
          {hamburgerOpen && (
            <div className="hamburger-dropdown">
              <button className="hamburger-item" onClick={() => navigateTo("about")}>
                About
              </button>
              <button className="hamburger-item" onClick={() => navigateTo("manual")}>
                Manual
              </button>
              <button className="hamburger-item" onClick={() => navigateTo("privacy")}>
                Privacy
              </button>
              <button className="hamburger-item" onClick={() => navigateTo("settings")}>
                Settings
              </button>
            </div>
          )}
        </div>
        <div className="capture-brand">
          <span className="capture-title">SnapCapture</span>
          <span className="capture-model">
            Engine: {provider === "openai" ? "GPT-4o-mini" : "Gemini 2.5 Flash Lite"}
          </span>
        </div>
        {quota && (
          <span
            className={`quota-badge ${quota.remaining <= 0 ? "quota-exhausted" : quota.remaining <= 5 ? "quota-low" : ""}`}
            title={`${quota.remaining} AI calls remaining today`}
          >
            {quota.remaining <= 0 ? "⚠️ Quota exhausted" : `🚀 ${quota.remaining}/${quota.limit}`}
          </span>
        )}
      </div>

      {/* ── Capture Input ── */}
      <div className="capture-section">
        <textarea
          autoFocus
          placeholder="Paste email, message, note..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={4}
          disabled={isRecording || !!audioBlob || !!selectedFile}
          maxLength={1000}
        />
        <div className="char-counter">{text.length}/1000</div>

        <div className="capture-toolbar">
          <div
            className="file-btn-wrap"
            onMouseEnter={() => setIsHoveringFile(true)}
            onMouseLeave={() => setIsHoveringFile(false)}
          >
            <button
              className="toolbar-btn choose-file-btn"
              disabled={loading || isRecording || !!audioBlob}
            >
              Choose File
            </button>
            {!(loading || isRecording || !!audioBlob) && (
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png, image/jpeg, image/jpg, application/pdf"
                onChange={(e) => {
                  setSelectedFile(e.target.files[0]);
                  setAudioBlob(null);
                  setAudioMimeType("");
                  setRecordingTime(0);
                }}
                className="file-input-overlay"
              />
            )}
          </div>

          {!isRecording && !audioBlob && (
            <button
              className="toolbar-btn"
              onClick={() => {
                setSelectedFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
                startRecording();
              }}
              disabled={loading || !!selectedFile}
            >
              🎤 Record
            </button>
          )}

          {isRecording && (
            <button className="toolbar-btn recording" onClick={stopRecording}>
              <span className="recording-dot" />
              Stop {formatTime(recordingTime)}
            </button>
          )}

          {audioBlob && !isRecording && (
            <button
              className="toolbar-btn"
              onClick={() => {
                setAudioBlob(null);
                setAudioMimeType("");
                setRecordingTime(0);
              }}
            >
              🗑 Clear
            </button>
          )}

          <div className="analyze-btn-wrap">
            <button
              className="btn-primary toolbar-btn-primary"
              onClick={analyzeCapture}
              disabled={loading || (!text.trim() && !selectedFile && !audioBlob)}
            >
              {loading ? "Analyzing..." : "Analyze"}
            </button>
            <span className="analyze-tooltip">Ctrl + Enter to analyze</span>
          </div>
        </div>
        <div className="capture-status">
          {isHoveringFile && (
            <span className="status-hint">images, PDF, screenshots</span>
          )}
          {!isHoveringFile && selectedFile && (
            <span>
              Selected: {selectedFile.name}
              <button
                className="status-clear"
                onClick={() => {
                  setSelectedFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = "";
                }}
              >
                ×
              </button>
            </span>
          )}
          {!isHoveringFile && isRecording && <span>Recording...</span>}
          {!isHoveringFile && audioBlob && !isRecording && (
            <span>Audio recorded ({formatTime(recordingTime)})</span>
          )}
        </div>
      </div>

      {/* ── Suggested Items ── */}
      {items.length > 0 && (
        <section className="suggested-section">
          <h2 className="suggested-heading">Suggested Items</h2>
          {captureSource && (
            <p className="suggested-source">
              Extracted from: <strong>{captureSource}</strong>
            </p>
          )}

          <div className="suggested-bulk-bar">
            {suggestedTasks.length > 0 && (
              <>
                <button
                  className="bulk-btn bulk-btn-enhance"
                  onClick={() => enhanceAllOfType("task")}
                  disabled={enhancingAllType === "task" || (quota && quota.remaining <= 0)}
                  title={quota && quota.remaining <= 0 ? "Quota exhausted" : `Refine all tasks with AI (${suggestedTasks.length} calls)`}
                >
                  {enhancingAllType === "task" ? "Enhancing..." : `✨ Enhance All Tasks (${suggestedTasks.length})`}
                </button>
                <button
                  className="bulk-btn bulk-btn-tasks"
                  onClick={() => saveAllOfType("task")}
                >
                  Save All Tasks ({suggestedTasks.length})
                </button>
                <button
                  className="bulk-btn bulk-btn-reject"
                  onClick={() => rejectAllOfType("task")}
                >
                  Reject All Tasks
                </button>
              </>
            )}
            {suggestedEvents.length > 0 && (
              <>
                <button
                  className="bulk-btn bulk-btn-enhance"
                  onClick={() => enhanceAllOfType("event")}
                  disabled={enhancingAllType === "event" || (quota && quota.remaining <= 0)}
                  title={quota && quota.remaining <= 0 ? "Quota exhausted" : `Refine all events with AI (${suggestedEvents.length} calls)`}
                >
                  {enhancingAllType === "event" ? "Enhancing..." : `✨ Enhance All Events (${suggestedEvents.length})`}
                </button>
                <button
                  className="bulk-btn bulk-btn-events"
                  onClick={() => saveAllOfType("event")}
                >
                  Save All Events ({suggestedEvents.length})
                </button>
                <button
                  className="bulk-btn bulk-btn-reject"
                  onClick={() => rejectAllOfType("event")}
                >
                  Reject All Events
                </button>
              </>
            )}
            {suggestedTasks.length === 0 && suggestedEvents.length === 0 && (
              <button className="bulk-btn bulk-btn-reject" onClick={rejectAll}>
                Reject All
              </button>
            )}
          </div>

          {suggestedTasks.length > 0 && (
            <div className="suggested-group">
              <h3 className="suggested-group-heading">Tasks ({suggestedTasks.length})</h3>
              {suggestedTasks.map((item, index) => (
                <div key={`task-${index}`} className="suggested-item">
                  <div className="suggested-item-row">
                    <div className="suggested-item-content">
                      <div className="suggested-item-header">
                        <div className="item-title-wrap">
                          <img className="item-icon-img" src="/task.png" alt="Task" title="Task" />
                          <strong>{item.title}</strong>
                        </div>
                      </div>
                      {item.due_date && (
                        <p>
                          {item.source && (
                            <span className="item-source-inline" title={getSourceIcon(item.source).label}>
                              {getSourceIcon(item.source).icon}
                            </span>
                          )}
                          Due: {item.due_date}
                        </p>
                      )}
                      {item.original_date && (
                        <p className="item-note">Original: {item.original_date}</p>
                      )}
                    </div>
                  </div>
                  <div className="suggested-actions">
                    <button
                      className="btn-enhance"
                      onClick={() => enhanceItem(item)}
                      disabled={enhancingItemId === item.id || (quota && quota.remaining <= 0)}
                      title={quota && quota.remaining <= 0 ? "Quota exhausted" : "Refine with AI (1 call)"}
                    >
                      {enhancingItemId === item.id ? "Enhancing..." : "✨ Enhance extraction"}
                    </button>
                    <button className="btn-save" onClick={() => saveItem(item)}>Save</button>
                    <button className="btn-reject" onClick={() => rejectItem(item)}>Reject</button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {suggestedEvents.length > 0 && (
            <div className="suggested-group">
              <h3 className="suggested-group-heading">Events ({suggestedEvents.length})</h3>
              {suggestedEvents.map((item, index) => (
                <div key={`event-${index}`} className="suggested-item">
                  <div className="suggested-item-row">
                    <div className="suggested-item-content">
                      <div className="suggested-item-header">
                        <div className="item-title-wrap">
                          <span className="item-icon" title="Event">📅</span>
                          <strong>{item.title}</strong>
                        </div>
                      </div>
                      {(item.date || item.time) && (
                        <p>
                          {item.source && (
                            <span className="item-source-inline" title={getSourceIcon(item.source).label}>
                              {getSourceIcon(item.source).icon}
                            </span>
                          )}
                          {item.date && `Date: ${item.date}`}
                          {item.date && item.time && ", "}
                          {item.time && `Time: ${item.time}`}
                        </p>
                      )}
                      {item.original_date && (
                        <p className="item-note">Original: {item.original_date}</p>
                      )}
                    </div>
                  </div>
                  <div className="suggested-actions">
                    <button
                      className="btn-enhance"
                      onClick={() => enhanceItem(item)}
                      disabled={enhancingItemId === item.id || (quota && quota.remaining <= 0)}
                      title={quota && quota.remaining <= 0 ? "Quota exhausted" : "Refine with AI (1 call)"}
                    >
                      {enhancingItemId === item.id ? "Enhancing..." : "✨ Enhance extraction"}
                    </button>
                    <button className="btn-save" onClick={() => saveItem(item)}>Save</button>
                    <button className="btn-reject" onClick={() => rejectItem(item)}>Reject</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {!loading && hasAnalyzed && items.length === 0 && (
        <p className="no-items">🔍 No actionable items found.</p>
      )}

      {/* ── Dashboard ── */}
      {dashLoading ? (
        <p className="loading-text">Loading dashboard...</p>
      ) : (
        <section className="dashboard-panel">
          <div className="dashboard-bar">
            <label className="dashboard-bar-label">
              <input
                ref={allCheckboxRef}
                type="checkbox"
                checked={allSelected}
                onChange={selectAllItems}
              />
              <span>All ({savedTasks.length + savedEvents.length})</span>
            </label>
            <span className="dashboard-ttl-hint">Items expire in 1 hour · Sorted by date</span>
            <div className="dashboard-bar-actions">
              <button
                className="dash-btn dash-btn-done"
                onClick={bulkMarkDone}
                disabled={totalSelected === 0}
              >
                Done
              </button>
              <button
                className="dash-btn dash-btn-undone"
                onClick={bulkMarkUndone}
                disabled={totalSelected === 0}
              >
                Undo
              </button>
              <button
                className="dash-btn dash-btn-delete"
                onClick={bulkDelete}
                disabled={totalSelected === 0}
              >
                Delete
              </button>
              <button
                className="dash-btn dash-btn-clear"
                onClick={clearAll}
                disabled={savedTasks.length + savedEvents.length === 0}
              >
                Clear All
              </button>
              <button
                className="dash-btn dash-btn-export"
                onClick={exportSelected}
                disabled={totalSelected === 0}
              >
                Export
              </button>
            </div>
          </div>

          {feedback && (
            <div className="feedback-toast">{feedback}</div>
          )}

          {savedTasks.length === 0 && savedEvents.length === 0 && (
            <p className="dashboard-empty">📤 No saved items yet.</p>
          )}

          {sortedTasks.map((task) => (
            <div
              key={`task-${task.id}`}
              className={`dashboard-item ${task.status === "done" ? "completed" : ""} ${task.status === "expired" ? "expired" : ""}`}
            >
              <div className="dashboard-item-row">
                <input
                  type="checkbox"
                  className="item-checkbox"
                  checked={selectedTasks.has(task.id)}
                  onChange={() => toggleTaskSelection(task.id)}
                />
                <div className="dashboard-item-content">
                  <div className="dashboard-item-header">
                    <div className="item-title-wrap">
                      <img className="item-icon-img" src="/task.png" alt="Task" title="Task" />
                      <strong>{task.title}</strong>
                    </div>
                    {task.status === "done" && (
                      <span className="badge badge-done">Done</span>
                    )}
                    {task.status === "expired" && (
                      <span className="badge badge-expired">Expired</span>
                    )}
                  </div>
                  {editingItemId === task.id && editingItemType === "task" ? (
                    <div className="item-editor">
                      <input
                        type="text"
                        value={editDraft.title}
                        onChange={(e) => setEditDraft((d) => ({ ...d, title: e.target.value }))}
                        placeholder="Title"
                      />
                      <input
                        type="text"
                        value={editDraft.due_date}
                        onChange={(e) => setEditDraft((d) => ({ ...d, due_date: e.target.value }))}
                        placeholder="Due date"
                      />
                      <div className="note-editor-actions">
                        <button className="btn-save-note" onClick={saveItemEdit}>Save</button>
                        <button className="btn-cancel-note" onClick={cancelEditItem}>Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {task.due_date && (
                        <p>
                          {task.source && (
                            <span className="item-source-inline" title={getSourceIcon(task.source).label}>
                              {getSourceIcon(task.source).icon}
                            </span>
                          )}
                          Due: {task.due_date}
                        </p>
                      )}
                      {task.note && <p className="item-note">📝 {task.note}</p>}
                      {editingNoteId === task.id && editingNoteType === "task" && (
                        <div className="note-editor">
                          <textarea
                            placeholder="Add a note..."
                            value={noteDraft}
                            onChange={(e) => setNoteDraft(e.target.value)}
                            rows={2}
                          />
                          <div className="note-editor-actions">
                            <button className="btn-save-note" onClick={saveNote}>Save</button>
                            <button className="btn-cancel-note" onClick={cancelEditNote}>Cancel</button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="item-menu-wrap">
                  <button className="item-menu-btn" onClick={() => toggleMenu(task.id, "task")}>
                    ⋮
                  </button>
                  {openMenuId === task.id && openMenuType === "task" && (
                    <div className="item-menu-dropdown">
                      {task.original_date && (
                        <div className="menu-info">Original: {task.original_date}</div>
                      )}
                      <button
                        className={`menu-item ${task.status !== "done" ? "menu-item-done" : ""}`}
                        onClick={() => { toggleTask(task); setOpenMenuId(null); }}
                      >
                        {task.status === "done" ? "Mark Undone" : "Mark Done"}
                      </button>
                      <button className="menu-item" onClick={() => startEditItem(task, "task")}>
                        Edit
                      </button>
                      <button className="menu-item" onClick={() => startEditNote(task, "task")}>
                        Add Note
                      </button>
                      <div className="menu-item-submenu-wrap">
                        <button className="menu-item" onClick={() => setExportSubmenuId(task.id)}>
                          Export ►
                        </button>
                        {exportSubmenuId === task.id && (
                          <div className="menu-dropright">
                            <button
                              className="menu-item"
                              onClick={() => { setExportSubmenuId(null); exportSingleItem(task, "task", "csv"); }}
                            >
                              as .csv
                            </button>
                            <button
                              className="menu-item"
                              onClick={() => { setExportSubmenuId(null); exportSingleItem(task, "task", "ics"); }}
                            >
                              as .ics
                            </button>
                          </div>
                        )}
                      </div>
                      <button
                        className="menu-item menu-item-danger"
                        onClick={() => deleteSingleItem(task, "task")}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}

          {sortedEvents.map((event) => (
            <div
              key={`event-${event.id}`}
              className={`dashboard-item ${event.status === "done" ? "completed" : ""} ${event.status === "expired" ? "expired" : ""}`}
            >
              <div className="dashboard-item-row">
                <input
                  type="checkbox"
                  className="item-checkbox"
                  checked={selectedEvents.has(event.id)}
                  onChange={() => toggleEventSelection(event.id)}
                />
                <div className="dashboard-item-content">
                  <div className="dashboard-item-header">
                    <div className="item-title-wrap">
                      <span className="item-icon" title="Event">📅</span>
                      <strong>{event.title}</strong>
                    </div>
                    {event.status === "done" && (
                      <span className="badge badge-done">Done</span>
                    )}
                    {event.status === "expired" && (
                      <span className="badge badge-expired">Expired</span>
                    )}
                  </div>
                  {editingItemId === event.id && editingItemType === "event" ? (
                    <div className="item-editor">
                      <input
                        type="text"
                        value={editDraft.title}
                        onChange={(e) => setEditDraft((d) => ({ ...d, title: e.target.value }))}
                        placeholder="Title"
                      />
                      <input
                        type="text"
                        value={editDraft.date}
                        onChange={(e) => setEditDraft((d) => ({ ...d, date: e.target.value }))}
                        placeholder="Date"
                      />
                      <input
                        type="text"
                        value={editDraft.time}
                        onChange={(e) => setEditDraft((d) => ({ ...d, time: e.target.value }))}
                        placeholder="Time"
                      />
                      <div className="note-editor-actions">
                        <button className="btn-save-note" onClick={saveItemEdit}>Save</button>
                        <button className="btn-cancel-note" onClick={cancelEditItem}>Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      {(event.date || event.time) && (
                        <p>
                          {event.source && (
                            <span className="item-source-inline" title={getSourceIcon(event.source).label}>
                              {getSourceIcon(event.source).icon}
                            </span>
                          )}
                          {event.date && `Date: ${event.date}`}
                          {event.date && event.time && ", "}
                          {event.time && `Time: ${event.time}`}
                        </p>
                      )}
                      {event.note && <p className="item-note">📝 {event.note}</p>}
                      {editingNoteId === event.id && editingNoteType === "event" && (
                        <div className="note-editor">
                          <textarea
                            placeholder="Add a note..."
                            value={noteDraft}
                            onChange={(e) => setNoteDraft(e.target.value)}
                            rows={2}
                          />
                          <div className="note-editor-actions">
                            <button className="btn-save-note" onClick={saveNote}>Save</button>
                            <button className="btn-cancel-note" onClick={cancelEditNote}>Cancel</button>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div className="item-menu-wrap">
                  <button className="item-menu-btn" onClick={() => toggleMenu(event.id, "event")}>
                    ⋮
                  </button>
                  {openMenuId === event.id && openMenuType === "event" && (
                    <div className="item-menu-dropdown">
                      {event.original_date && (
                        <div className="menu-info">Original: {event.original_date}</div>
                      )}
                      <button
                        className={`menu-item ${event.status !== "done" ? "menu-item-done" : ""}`}
                        onClick={() => { toggleEvent(event); setOpenMenuId(null); }}
                      >
                        {event.status === "done" ? "Mark Undone" : "Mark Done"}
                      </button>
                      <button className="menu-item" onClick={() => startEditItem(event, "event")}>
                        Edit
                      </button>
                      <button className="menu-item" onClick={() => startEditNote(event, "event")}>
                        Add Note
                      </button>
                      <button className="menu-item" onClick={() => exportSingleItem(event, "event")}>
                        Export
                      </button>
                      <button
                        className="menu-item menu-item-danger"
                        onClick={() => deleteSingleItem(event, "event")}
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </section>
      )}
    </>
  );
}
