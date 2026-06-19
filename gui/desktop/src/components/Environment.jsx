import { useState, useEffect } from 'react';
import { get, post } from '../api';

/**
 * Environment Tab / Configuration View
 *
 * Allows users to:
 * - Select LLM model (Ollama local or Anthropic cloud)
 * - Configure model-specific settings (host, API key)
 * - Test connection to the LLM
 * - Toggle feature flags
 * - Save configuration to ~/.agentic-os/config.yaml
 */
export default function Environment() {
  // Current config state
  const [config, setConfig] = useState({
    llm: {
      activeModel: 'ollama',
      ollama: { host: 'http://localhost:11434' },
      anthropic: { baseUrl: 'https://api.anthropic.com/v1', apiKey: '' }
    },
    flags: {
      shellCommands: true,
      brain2Integration: true,
      hubAbsorption: false
    }
  });

  // Form state
  const [original, setOriginal] = useState(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [saved, setSaved] = useState(false);

  // Load config on mount
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const data = await get('/api/config');
      if (data) {
        setConfig(data);
        setOriginal(JSON.parse(JSON.stringify(data)));
      }
    } catch (e) {
      console.error('Failed to load config:', e);
    } finally {
      setLoading(false);
    }
  };

  const testConnection = async () => {
    try {
      setTesting(true);
      setTestResult(null);

      const testPayload = config.llm.activeModel === 'ollama'
        ? { model: 'ollama', host: config.llm.ollama.host }
        : { model: 'anthropic', baseUrl: config.llm.anthropic.baseUrl, apiKey: config.llm.anthropic.apiKey };

      const result = await post('/api/config/test', testPayload);
      setTestResult(result);
    } catch (e) {
      setTestResult({ status: 'error', details: e.message });
    } finally {
      setTesting(false);
    }
  };

  const saveConfig = async () => {
    try {
      setSaveError(null);
      setSaved(false);
      const result = await post('/api/config', config);
      if (result?.status === 'saved') {
        setSaved(true);
        setOriginal(JSON.parse(JSON.stringify(config)));
        setTimeout(() => setSaved(false), 3000);
      }
    } catch (e) {
      setSaveError(e.message || 'Failed to save config');
    }
  };

  const cancel = () => {
    if (original) {
      setConfig(JSON.parse(JSON.stringify(original)));
      setTestResult(null);
    }
  };

  const isDirty = JSON.stringify(config) !== JSON.stringify(original);
  const isOllama = config.llm.activeModel === 'ollama';
  const isAnthropicSelected = config.llm.activeModel === 'anthropic';

  if (loading) {
    return <div className="env-loading">Loading configuration...</div>;
  }

  return (
    <div className="environment-panel">
      <div className="env-section">
        <h3>LLM Configuration</h3>

        <div className="env-group">
          <label className="env-label">Active Model</label>
          <div className="env-radio-group">
            <label className="env-radio">
              <input
                type="radio"
                name="model"
                value="ollama"
                checked={isOllama}
                onChange={() => setConfig({
                  ...config,
                  llm: { ...config.llm, activeModel: 'ollama' }
                })}
              />
              Ollama (Local)
            </label>
            <label className="env-radio">
              <input
                type="radio"
                name="model"
                value="anthropic"
                checked={isAnthropicSelected}
                onChange={() => setConfig({
                  ...config,
                  llm: { ...config.llm, activeModel: 'anthropic' }
                })}
              />
              Anthropic (Cloud)
            </label>
          </div>
        </div>

        {/* Ollama Settings */}
        {isOllama && (
          <div className="env-group">
            <label className="env-label">Ollama Host URL</label>
            <input
              type="text"
              className="env-input"
              value={config.llm.ollama.host}
              onChange={(e) => setConfig({
                ...config,
                llm: {
                  ...config.llm,
                  ollama: { ...config.llm.ollama, host: e.target.value }
                }
              })}
              placeholder="http://localhost:11434"
            />
            <span className="env-hint">Default: http://localhost:11434</span>
          </div>
        )}

        {/* Anthropic Settings */}
        {isAnthropicSelected && (
          <>
            <div className="env-group">
              <label className="env-label">Base URL</label>
              <input
                type="text"
                className="env-input"
                value={config.llm.anthropic.baseUrl}
                onChange={(e) => setConfig({
                  ...config,
                  llm: {
                    ...config.llm,
                    anthropic: { ...config.llm.anthropic, baseUrl: e.target.value }
                  }
                })}
                placeholder="https://api.anthropic.com/v1"
              />
              <span className="env-hint">Default: https://api.anthropic.com/v1</span>
            </div>

            <div className="env-group">
              <label className="env-label">API Key</label>
              <input
                type="password"
                className="env-input"
                value={config.llm.anthropic.apiKey}
                onChange={(e) => setConfig({
                  ...config,
                  llm: {
                    ...config.llm,
                    anthropic: { ...config.llm.anthropic, apiKey: e.target.value }
                  }
                })}
                placeholder="sk-ant-..."
              />
              <span className="env-hint">Stored locally in ~/.agentic-os/config.yaml</span>
            </div>
          </>
        )}

        <div className="env-actions">
          <button
            className={`btn test-btn ${testing ? 'loading' : ''}`}
            onClick={testConnection}
            disabled={testing}
          >
            {testing ? 'Testing…' : '🔌 Test Connection'}
          </button>
        </div>

        {testResult && (
          <div className={`env-test-result ${testResult.status === 'connected' ? 'success' : 'error'}`}>
            {testResult.status === 'connected' ? (
              <>
                <span className="status-icon">🟢</span> Connected to {config.llm.activeModel}
              </>
            ) : (
              <>
                <span className="status-icon">🔴</span> {testResult.details || 'Connection failed'}
              </>
            )}
          </div>
        )}
      </div>

      <div className="env-section">
        <h3>Feature Flags</h3>

        <div className="env-flags">
          {Object.entries(config.flags).map(([key, value]) => (
            <label key={key} className="env-flag-item">
              <input
                type="checkbox"
                checked={value}
                onChange={(e) => setConfig({
                  ...config,
                  flags: { ...config.flags, [key]: e.target.checked }
                })}
              />
              <span className="flag-name">{formatFlagName(key)}</span>
            </label>
          ))}
        </div>
      </div>

      <div className="env-footer">
        <div className="env-status">
          {saved && <span className="save-success">✓ Configuration saved</span>}
          {saveError && <span className="save-error">✕ {saveError}</span>}
          {isDirty && <span className="unsaved-hint">Unsaved changes</span>}
        </div>

        <div className="env-buttons">
          <button
            className="btn cancel-btn"
            onClick={cancel}
            disabled={!isDirty}
          >
            Cancel
          </button>
          <button
            className="btn save-btn"
            onClick={saveConfig}
            disabled={!isDirty}
          >
            Save Configuration
          </button>
        </div>
      </div>
    </div>
  );
}

function formatFlagName(key) {
  return key
    .split(/(?=[A-Z])/)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
