import { useState, useEffect, useMemo } from 'react';

/**
 * Diagnostics Sidebar Panel
 *
 * Collapsible panel showing system health metrics.
 *
 * Collapsed view: 3-line summary (CPU%, RAM%, Net)
 * Expanded view: Full system details (per-core CPU, memory, disk, network, load, top processes)
 *
 * State persists to localStorage["agentic-os.diagExpanded"]
 * Data updates every 2 seconds via usePoll hook
 */
export default function DiagnosticsPanel({ data, forceExpanded = false }) {
  // Expanded state (persisted to localStorage)
  const [expanded, setExpanded] = useState(() => {
    const saved = localStorage.getItem('agentic-os.diagExpanded');
    return saved ? JSON.parse(saved) : false;
  });

  // Update localStorage when expanded state changes
  useEffect(() => {
    localStorage.setItem('agentic-os.diagExpanded', JSON.stringify(expanded));
  }, [expanded]);

  if (!data || data.available === false) {
    return (
      <div className="diag-panel diag-error">
        <button
          className="diag-header"
          onClick={() => setExpanded(!expanded)}
          title="System diagnostics unavailable"
        >
          <span className="diag-toggle">{expanded ? '⊟' : '⊞'}</span>
          <span className="diag-title">Diagnostics</span>
        </button>
        <div className="diag-error-msg">Data unavailable</div>
      </div>
    );
  }

  const cpuPercent = Math.round(data.cpu_percent || 0);
  const ramUsedGb = (data.ram?.used_gb || 0).toFixed(1);
  const ramTotalGb = (data.ram?.total_gb || 0).toFixed(1);
  const ramPercent = data.ram?.percent || 0;
  const netIn = formatBytes(data.network?.bytes_in || 0);
  const netOut = formatBytes(data.network?.bytes_out || 0);

  const toggle = () => setExpanded(!expanded);
  const showExpanded = forceExpanded || expanded;

  if (!showExpanded) {
    // Collapsed view: 3-line summary
    return (
      <div className="diag-panel diag-collapsed">
        <button className="diag-header" onClick={toggle}>
          <span className="diag-toggle">⊞</span>
          <span className="diag-title">Diagnostics</span>
        </button>
        <div className="diag-summary">
          <div className="diag-metric">
            <span className="label">CPU</span>
            <span className="value">{cpuPercent}%</span>
          </div>
          <div className="diag-metric">
            <span className="label">RAM</span>
            <span className="value">{ramPercent}%</span>
          </div>
          <div className="diag-metric">
            <span className="label">Net</span>
            <span className="value">{netIn}</span>
          </div>
        </div>
      </div>
    );
  }

  // Expanded view: Full details
  const cores = data.cpu_per_core || [];
  const uptime = formatUptime(data.uptime_s || 0);
  const loadAvg = (data.load_avg || []).map(x => x.toFixed(2)).join(' / ');
  const rootDisk = data.disks?.find(d => d.mount === '/') || data.disks?.[0];
  const diskUsedGb = (rootDisk?.used_gb || 0).toFixed(1);
  const diskTotalGb = (rootDisk?.total_gb || 0).toFixed(1);
  const diskPercent = rootDisk?.percent || 0;

  return (
    <div className="diag-panel diag-expanded">
      <button className="diag-header" onClick={forceExpanded ? undefined : toggle}>
        <span className="diag-toggle">⊟</span>
        <span className="diag-title">Diagnostics</span>
      </button>

      <div className="diag-content">
        {/* CPU Section */}
        <div className="diag-section">
          <h4 className="diag-section-title">CPU</h4>
          <div className="diag-metric-row">
            <span className="label">Overall</span>
            <div className="value-with-bar">
              <span className="value">{cpuPercent}%</span>
              <div className="bar">
                <div className="bar-fill" style={{ width: `${cpuPercent}%` }} />
              </div>
            </div>
          </div>

          {cores.length > 0 && (
            <>
              <div className="diag-section-subtitle">Per Core</div>
              <div className="core-bars">
                {cores.map((pct, i) => (
                  <div key={i} className="core-bar-group" title={`Core ${i}: ${pct}%`}>
                    <div className="core-bar-container">
                      <div
                        className="core-bar"
                        style={{
                          height: `${Math.max(Math.min(pct, 100), 2)}%`
                        }}
                      />
                    </div>
                    <span className="core-label">{i}</span>
                  </div>
                ))}
              </div>
            </>
          )}

          <div className="diag-metric-row">
            <span className="label">Load Avg</span>
            <span className="value mono">{loadAvg}</span>
          </div>
          <div className="diag-metric-row">
            <span className="label">Uptime</span>
            <span className="value">{uptime}</span>
          </div>
        </div>

        {/* Memory Section */}
        <div className="diag-section">
          <h4 className="diag-section-title">Memory</h4>
          <div className="diag-metric-row">
            <span className="label">RAM</span>
            <div className="value-with-bar">
              <span className="value">
                {ramUsedGb} / {ramTotalGb} GB ({Math.round(ramPercent)}%)
              </span>
              <div className="bar">
                <div
                  className="bar-fill"
                  style={{ width: `${Math.min(ramPercent, 100)}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Disk Section */}
        {rootDisk && (
          <div className="diag-section">
            <h4 className="diag-section-title">Disk {rootDisk.mount}</h4>
            <div className="diag-metric-row">
              <span className="label">Used</span>
              <div className="value-with-bar">
                <span className="value">
                  {diskUsedGb} / {diskTotalGb} GB ({Math.round(diskPercent)}%)
                </span>
                <div className="bar">
                  <div
                    className="bar-fill"
                    style={{ width: `${Math.min(diskPercent, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Network Section */}
        <div className="diag-section">
          <h4 className="diag-section-title">Network</h4>
          <div className="diag-metric-row">
            <span className="label">In / Out</span>
            <span className="value">
              ↓ {netIn} · ↑ {netOut}
            </span>
          </div>
        </div>

        {/* Top Processes */}
        {(data.top_cpu?.length > 0 || data.top_memory?.length > 0) && (
          <div className="diag-section">
            <h4 className="diag-section-title">Top Processes</h4>
            <table className="diag-process-table">
              <thead>
                <tr>
                  <th>Top CPU</th>
                  <th>%</th>
                  <th>Top Mem</th>
                  <th>%</th>
                </tr>
              </thead>
              <tbody>
                {[0, 1, 2].map((i) => (
                  <tr key={i}>
                    <td>{data.top_cpu?.[i]?.name || '—'}</td>
                    <td>{data.top_cpu?.[i]?.cpu_percent || '—'}</td>
                    <td>{data.top_memory?.[i]?.name || '—'}</td>
                    <td>{data.top_memory?.[i]?.memory_percent || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return (bytes / Math.pow(k, i)).toFixed(1) + ' ' + sizes[i];
}

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const mins = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}
