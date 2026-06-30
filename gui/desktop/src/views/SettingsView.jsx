import EnvironmentPanel from "../components/EnvironmentPanel";

/**
 * SettingsView — Phase 9 Settings Page
 * Renders EnvironmentPanel as a full-page view in the main dashboard
 * Navigation: Sidebar link "Settings" → setActiveView('settings')
 * State: EnvironmentPanel handles all localStorage persistence internally
 */
export default function SettingsView() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <EnvironmentPanel />
    </div>
  );
}
