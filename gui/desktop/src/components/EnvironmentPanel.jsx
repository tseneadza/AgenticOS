import { useState, useEffect, useCallback } from "react";

// ─────────────────────────────────────────────────────────────────────────
// EnvironmentPanel Component
// Manages API keys, feature toggles, and system settings
// Persists to localStorage
// ─────────────────────────────────────────────────────────────────────────

const API_KEYS = [
  {
    id: "anthropic_api_key",
    label: "Anthropic API Key",
    description: "For Claude API calls",
    required: true,
    secured: true,
  },
  {
    id: "github_token",
    label: "GitHub Personal Access Token",
    description: "For git operations",
    required: false,
    secured: true,
  },
];

const FEATURE_FLAGS = [
  {
    id: "dark_mode",
    label: "Dark Mode Enabled",
    description: "Enable dark theme",
    default: true,
  },
  {
    id: "animations",
    label: "Animations Enabled",
    description: "Enable smooth transitions",
    default: true,
  },
  {
    id: "auto_refresh",
    label: "Auto-refresh Logs",
    description: "Automatically refresh log display",
    default: true,
  },
];

const SYSTEM_SETTINGS = [
  {
    id: "log_refresh_interval",
    label: "Log Refresh Interval (seconds)",
    description: "How often to check for new logs",
    type: "number",
    default: 5,
    min: 1,
    max: 60,
  },
  {
    id: "api_timeout",
    label: "API Timeout (seconds)",
    description: "Maximum time to wait for API responses",
    type: "number",
    default: 30,
    min: 5,
    max: 300,
  },
];

const DEFAULT_SETTINGS = {
  anthropic_api_key: "",
  github_token: "",
  dark_mode: true,
  animations: true,
  auto_refresh: true,
  log_refresh_interval: 5,
  api_timeout: 30,
};

// ─────────────────────────────────────────────────────────────────────────
// ApiKeyInput Sub-component
// ─────────────────────────────────────────────────────────────────────────

function ApiKeyInput({ label, description, value, onChange, masked = true, required = false, id }) {
  const [showValue, setShowValue] = useState(false);
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value || "");
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (e) {
      console.error("Failed to copy:", e);
    }
  };

  return (
    <div style={{ marginBottom: "16px" }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: "4px" }}>
        <label
          htmlFor={id}
          style={{
            fontSize: "12px",
            fontWeight: "500",
            color: "var(--text)",
          }}
        >
          {label}
          {required && <span style={{ color: "var(--red)" }}> *</span>}
        </label>
      </div>
      {description && (
        <div style={{ fontSize: "11px", color: "var(--text-dim)", marginBottom: "4px" }}>
          {description}
        </div>
      )}
      <div style={{ display: "flex", gap: "4px" }}>
        <input
          id={id}
          data-testid={`api-key-input-${id}`}
          type={showValue ? "text" : "password"}
          value={value || ""}
          onChange={(e) => onChange(e.target.value)}
          style={{
            flex: 1,
            padding: "6px 8px",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            background: "var(--bg-inset)",
            color: "var(--text)",
            fontSize: "12px",
            fontFamily: "var(--mono)",
          }}
        />
        {value && (
          <>
            <button
              data-testid={`toggle-show-${id}`}
              onClick={() => setShowValue(!showValue)}
              aria-label={showValue ? "Hide" : "Show"}
              style={{
                padding: "6px 8px",
                border: "1px solid var(--border)",
                borderRadius: "4px",
                background: "transparent",
                color: "var(--text-dim)",
                cursor: "pointer",
                fontSize: "11px",
                transition: "all 100ms",
              }}
            >
              {showValue ? "Hide" : "Show"}
            </button>
            <button
              data-testid={`copy-btn-${id}`}
              onClick={handleCopy}
              aria-label="Copy"
              style={{
                padding: "6px 8px",
                border: "1px solid var(--border)",
                borderRadius: "4px",
                background: "transparent",
                color: copied ? "var(--green)" : "var(--text-dim)",
                cursor: "pointer",
                fontSize: "11px",
                transition: "all 100ms",
              }}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// FeatureToggle Sub-component
// ─────────────────────────────────────────────────────────────────────────

function FeatureToggle({ id, label, description, value, onChange }) {
  return (
    <div
      style={{
        marginBottom: "12px",
        padding: "8px",
        borderRadius: "4px",
        background: "var(--bg-inset)",
        border: "1px solid var(--border-soft)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <input
          id={`toggle-${id}`}
          data-testid={`toggle-${id}`}
          type="checkbox"
          checked={value || false}
          onChange={(e) => onChange(e.target.checked)}
          style={{
            cursor: "pointer",
            width: "16px",
            height: "16px",
          }}
        />
        <label htmlFor={`toggle-${id}`} style={{ flex: 1, cursor: "pointer" }}>
          <div style={{ fontSize: "12px", fontWeight: "500", color: "var(--text)" }}>
            {label}
          </div>
          {description && (
            <div style={{ fontSize: "11px", color: "var(--text-dim)" }}>
              {description}
            </div>
          )}
        </label>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// NumberSetting Sub-component
// ─────────────────────────────────────────────────────────────────────────

function NumberSetting({ id, label, description, value, onChange, min, max }) {
  const [error, setError] = useState("");

  const handleChange = (newValue) => {
    const num = parseInt(newValue, 10);
    if (isNaN(num)) {
      setError("Must be a number");
      return;
    }
    if (num < min) {
      setError(`Minimum value is ${min}`);
      return;
    }
    if (num > max) {
      setError(`Maximum value is ${max}`);
      return;
    }
    setError("");
    onChange(num);
  };

  return (
    <div style={{ marginBottom: "16px" }}>
      <label
        htmlFor={id}
        style={{
          display: "block",
          fontSize: "12px",
          fontWeight: "500",
          color: "var(--text)",
          marginBottom: "4px",
        }}
      >
        {label}
      </label>
      {description && (
        <div style={{ fontSize: "11px", color: "var(--text-dim)", marginBottom: "4px" }}>
          {description}
        </div>
      )}
      <input
        id={id}
        data-testid={`number-input-${id}`}
        type="number"
        value={value || ""}
        onChange={(e) => handleChange(e.target.value)}
        min={min}
        max={max}
        style={{
          width: "100%",
          padding: "6px 8px",
          border: error ? "2px solid var(--red)" : "1px solid var(--border)",
          borderRadius: "4px",
          background: "var(--bg-inset)",
          color: "var(--text)",
          fontSize: "12px",
          fontFamily: "var(--mono)",
          boxSizing: "border-box",
        }}
      />
      {error && (
        <div
          data-testid={`error-${id}`}
          style={{
            marginTop: "4px",
            fontSize: "11px",
            color: "var(--red)",
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// SettingRow Sub-component
// ─────────────────────────────────────────────────────────────────────────

function SettingRow({ title, children }) {
  return (
    <div style={{ marginBottom: "24px" }}>
      <div
        style={{
          fontSize: "13px",
          fontWeight: "600",
          color: "var(--accent)",
          marginBottom: "12px",
          paddingBottom: "8px",
          borderBottom: "1px solid var(--border-soft)",
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Main EnvironmentPanel Component
// ─────────────────────────────────────────────────────────────────────────

export default function EnvironmentPanel({ onClose }) {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [requiredKeysWarning, setRequiredKeysWarning] = useState("");

  // Load settings from localStorage on mount
  useEffect(() => {
    const stored = localStorage.getItem("agentic-os.settings");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setSettings({ ...DEFAULT_SETTINGS, ...parsed });
      } catch (e) {
        console.error("Failed to parse settings:", e);
      }
    }

    // Check for required keys
    const anthropicKey = stored ? JSON.parse(stored).anthropic_api_key : "";
    if (!anthropicKey) {
      setRequiredKeysWarning("Anthropic API Key is required for Claude API calls");
    }
  }, []);

  // Auto-save to localStorage with debouncing (500ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        setIsSaving(true);
        localStorage.setItem("agentic-os.settings", JSON.stringify(settings));
        setSaveSuccess(true);
        setIsSaving(false);
        setTimeout(() => setSaveSuccess(false), 1500);
      } catch (e) {
        console.error("Failed to auto-save settings:", e);
        setIsSaving(false);
      }
    }, 500); // 500ms debounce to avoid excessive writes

    return () => clearTimeout(timer);
  }, [settings]);

  // Update setting value
  const updateSetting = useCallback((key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Manual save trigger (for explicit validation)
  const handleSave = useCallback(() => {
    // Validate required fields
    let isValid = true;
    if (!settings.anthropic_api_key) {
      setRequiredKeysWarning("Anthropic API Key is required");
      isValid = false;
    } else {
      setRequiredKeysWarning("");
    }

    if (!isValid) return;

    // Force immediate save
    try {
      setIsSaving(true);
      localStorage.setItem("agentic-os.settings", JSON.stringify(settings));
      setSaveSuccess(true);
      setIsSaving(false);
      setTimeout(() => setSaveSuccess(false), 1500);
    } catch (e) {
      console.error("Failed to save settings:", e);
      setIsSaving(false);
    }
  }, [settings]);

  // Reset to defaults
  const handleReset = useCallback(() => {
    if (confirm("Reset all settings to defaults?")) {
      // Auto-save effect persists the reset; no manual dirty flag needed.
      setSettings(DEFAULT_SETTINGS);
      setSaveSuccess(false);
    }
  }, []);

  // Clear a specific API key
  const handleClearKey = useCallback((key) => {
    updateSetting(key, "");
  }, [updateSetting]);

  return (
    <div
      data-testid="environment-panel"
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        background: "var(--bg)",
        color: "var(--text)",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "14px", fontWeight: "600" }}>
          Settings
        </h2>
        {onClose && (
          <button
            data-testid="close-settings"
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-dim)",
              cursor: "pointer",
              fontSize: "16px",
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Content */}
      <div
        data-testid="settings-content"
        style={{
          flex: 1,
          overflow: "auto",
          padding: "16px",
        }}
      >
        {/* Warnings */}
        {requiredKeysWarning && (
          <div
            data-testid="required-warning"
            style={{
              marginBottom: "16px",
              padding: "8px 12px",
              background: "rgba(255, 107, 107, 0.1)",
              border: "1px solid var(--red)",
              borderRadius: "4px",
              color: "var(--red)",
              fontSize: "12px",
            }}
          >
            ⚠ {requiredKeysWarning}
          </div>
        )}

        {/* API Keys Section */}
        <SettingRow title="API Keys">
          {API_KEYS.map((key) => (
            <div key={key.id}>
              <ApiKeyInput
                id={key.id}
                label={key.label}
                description={key.description}
                value={settings[key.id]}
                onChange={(value) => updateSetting(key.id, value)}
                masked={key.secured}
                required={key.required}
              />
              {settings[key.id] && (
                <button
                  data-testid={`clear-${key.id}`}
                  onClick={() => handleClearKey(key.id)}
                  style={{
                    fontSize: "11px",
                    color: "var(--red)",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    marginBottom: "12px",
                  }}
                >
                  Clear {key.label}
                </button>
              )}
            </div>
          ))}
        </SettingRow>

        {/* Feature Flags Section */}
        <SettingRow title="Features">
          {FEATURE_FLAGS.map((flag) => (
            <FeatureToggle
              key={flag.id}
              id={flag.id}
              label={flag.label}
              description={flag.description}
              value={settings[flag.id]}
              onChange={(value) => updateSetting(flag.id, value)}
            />
          ))}
        </SettingRow>

        {/* System Settings Section */}
        <SettingRow title="System Settings">
          {SYSTEM_SETTINGS.map((setting) => (
            <NumberSetting
              key={setting.id}
              id={setting.id}
              label={setting.label}
              description={setting.description}
              value={settings[setting.id]}
              onChange={(value) => updateSetting(setting.id, value)}
              min={setting.min}
              max={setting.max}
            />
          ))}
        </SettingRow>
      </div>

      {/* Footer */}
      <div
        style={{
          padding: "12px 16px",
          borderTop: "1px solid var(--border)",
          display: "flex",
          gap: "8px",
          justifyContent: "flex-end",
          alignItems: "center",
        }}
      >
        {isSaving && (
          <div style={{ color: "var(--text-dim)", fontSize: "12px" }}>
            Saving...
          </div>
        )}
        {saveSuccess && !isSaving && (
          <div style={{ color: "var(--green)", fontSize: "12px" }}>
            ✓ Saved
          </div>
        )}
        <button
          data-testid="reset-settings"
          onClick={handleReset}
          style={{
            padding: "6px 12px",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            background: "transparent",
            color: "var(--text-dim)",
            cursor: "pointer",
            fontSize: "12px",
            transition: "all 100ms",
          }}
        >
          Reset to Defaults
        </button>
      </div>
    </div>
  );
}
