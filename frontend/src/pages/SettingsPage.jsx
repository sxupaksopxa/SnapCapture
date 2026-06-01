import { useMemo } from "react";
import { useAppContext } from "../AppContext";

export default function SettingsPage() {
  const {
    provider, setProvider,
    customApiKey, setCustomApiKey,
    showApiKey, setShowApiKey,
    quota,
    navigateTo,
  } = useAppContext();

  const quotaPercent = useMemo(() => {
    if (!quota) return 0;
    return Math.min(100, ((quota.used_today ?? (quota.limit - quota.remaining)) / quota.limit) * 100);
  }, [quota]);

  const quotaColor = useMemo(() => {
    if (!quota) return "#3b82f6";
    if (quota.remaining <= 0) return "#ef4444";
    if (quota.remaining <= 5) return "#f59e0b";
    return "#3b82f6";
  }, [quota]);

  return (
    <div className="page-content settings-page">
      <button className="page-back" onClick={() => navigateTo("capture")}>
        ← Go back
      </button>
      <h2>Settings</h2>

      <div className="settings-section">
        <h3>Select Provider</h3>
        <p className="settings-desc">Choose the AI model used for extraction and enhancement.</p>
        <div className="settings-radio-group">
          <label className="settings-radio">
            <input
              type="radio"
              name="provider"
              value="gemini"
              checked={provider === "gemini"}
              onChange={(e) => setProvider(e.target.value)}
            />
            <span className="radio-label">Gemini 2.5 Flash Lite (Google)</span>
          </label>
          <label className="settings-radio">
            <input
              type="radio"
              name="provider"
              value="openai"
              checked={provider === "openai"}
              onChange={(e) => setProvider(e.target.value)}
            />
            <span className="radio-label">GPT-4o-mini (OpenAI)</span>
          </label>
        </div>
      </div>

      <div className="settings-section">
        <h3>Bring Your Own API Key</h3>
        <p className="settings-desc">
          Optional. Leave empty to use the default shared key. Your key is stored only in your browser.
        </p>
        <div className="settings-input-wrap">
          <input
            type={showApiKey ? "text" : "password"}
            value={customApiKey}
            onChange={(e) => setCustomApiKey(e.target.value)}
            placeholder="Paste your API key here"
            className="settings-input"
          />
          <button
            className="btn-toggle-visibility"
            onClick={() => setShowApiKey((v) => !v)}
            type="button"
          >
            {showApiKey ? "🙈" : "👁️"}
          </button>
        </div>
        {customApiKey.trim() && (
          <p className="settings-hint">
            Active: {provider === "openai" ? "OpenAI" : "Gemini 2.5 Flash Lite"} key set
          </p>
        )}
      </div>

      <div className="settings-section">
        <h3>API Daily Limits</h3>
        {quota ? (
          <div className="quota-detail">
            <div className="quota-row">
              <span className="quota-label">Remaining today</span>
              <span className={`quota-value ${quota.remaining <= 0 ? "exhausted" : quota.remaining <= 5 ? "low" : ""}`}>
                {quota.remaining}
              </span>
            </div>
            <div className="quota-row">
              <span className="quota-label">Daily limit</span>
              <span className="quota-value">{quota.limit}</span>
            </div>
            <div className="quota-row">
              <span className="quota-label">Used today</span>
              <span className="quota-value">{quota.used_today ?? (quota.limit - quota.remaining)}</span>
            </div>
            <div className="quota-bar-bg">
              <div
                className="quota-bar-fill"
                style={{
                  width: `${quotaPercent}%`,
                  backgroundColor: quotaColor,
                }}
              />
            </div>
          </div>
        ) : (
          <p className="settings-desc">Loading quota...</p>
        )}
      </div>
    </div>
  );
}
