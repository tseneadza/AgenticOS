import EnvironmentPanel from "../components/EnvironmentPanel";

/**
 * SettingsView — Settings page (reworked from the Phase 9 shell).
 * Renders EnvironmentPanel as a full-page view in the main dashboard.
 * Navigation: Sidebar link "Settings" → setActiveView('settings')
 *
 * Every setting is wired to real behavior — see settings.js (registry +
 * pollMs/sidecarUrl helpers) and theme.js (Appearance section).
 */
export default function SettingsView() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <EnvironmentPanel />
    </div>
  );
}
