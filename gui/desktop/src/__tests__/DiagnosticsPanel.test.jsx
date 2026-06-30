import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import DiagnosticsPanel from '../components/DiagnosticsPanel';

const mockData = {
  available: true,
  cpu_percent: 35,
  cpu_per_core: [25, 40, 35, 30],
  ram: {
    used_gb: 8.2,
    total_gb: 16,
    percent: 51
  },
  disk: null,
  disks: [
    {
      mount: '/',
      used_gb: 200,
      total_gb: 500,
      free_gb: 300,
      percent: 40
    }
  ],
  network: {
    bytes_in: 1048576,  // 1 MB
    bytes_out: 524288   // 512 KB
  },
  uptime_s: 86400 + 3600 + 600,  // 1d 1h 10m
  load_avg: [1.2, 1.4, 0.8],
  top_cpu: [
    { name: 'python3', cpu_percent: 15 },
    { name: 'node', cpu_percent: 8 },
    { name: 'chrome', cpu_percent: 5 }
  ],
  top_memory: [
    { name: 'chrome', memory_percent: 25 },
    { name: 'python3', memory_percent: 12 },
    { name: 'node', memory_percent: 8 }
  ]
};

describe('DiagnosticsPanel Component', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('renders without crashing', () => {
    render(<DiagnosticsPanel data={mockData} />);
    expect(screen.getByText('Diagnostics')).toBeInTheDocument();
  });

  it('renders in collapsed state by default', () => {
    render(<DiagnosticsPanel data={mockData} />);
    expect(screen.getByText('⊞')).toBeInTheDocument();
    expect(screen.getByText('CPU')).toBeInTheDocument(); // Summary line
  });

  it('shows collapsed view with 3 metrics', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const summary = screen.getByText('Diagnostics').closest('.diag-panel');
    expect(summary.textContent).toContain('35%'); // CPU
    expect(summary.textContent).toContain('51%'); // RAM
    expect(summary.textContent).toContain('1.0 MB'); // Network
  });

  it('expands to show full details on toggle', async () => {
    const { rerender } = render(<DiagnosticsPanel data={mockData} />);

    // Click to expand
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    // Should show expanded icon
    expect(screen.getByText('⊟')).toBeInTheDocument();

    // Should show full details
    await waitFor(() => {
      expect(screen.getByText('Per Core')).toBeInTheDocument();
      expect(screen.getByText('Memory')).toBeInTheDocument();
      expect(screen.getByText('Network')).toBeInTheDocument();
    });
  });

  it('persists expanded state to localStorage', () => {
    const { rerender } = render(<DiagnosticsPanel data={mockData} />);

    // Expand
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    // Check localStorage
    const stored = localStorage.getItem('agentic-os.diagExpanded');
    expect(stored).toBe('true');

    // Re-render and verify it stays expanded
    rerender(<DiagnosticsPanel data={mockData} />);
    expect(screen.getByText('⊟')).toBeInTheDocument();
  });

  it('loads expanded state from localStorage', () => {
    localStorage.setItem('agentic-os.diagExpanded', 'true');
    render(<DiagnosticsPanel data={mockData} />);
    expect(screen.getByText('⊟')).toBeInTheDocument();
  });

  it('formats bytes correctly', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    expect(screen.getByText(/1.0 MB/)).toBeInTheDocument(); // bytes_in
    expect(screen.getByText(/512.0 KB/)).toBeInTheDocument(); // bytes_out
  });

  it('formats uptime correctly', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    // uptime_s = 86400 + 3600 + 600 = 1d 1h 10m
    expect(screen.getByText(/1d 1h/)).toBeInTheDocument();
  });

  it('displays per-core CPU bars when expanded', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    expect(screen.getByText('Per Core')).toBeInTheDocument();
    // Check that core indices are displayed
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('displays load average correctly', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    expect(screen.getByText(/1.20.*1.40.*0.80/)).toBeInTheDocument();
  });

  it('displays top processes in table format', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    expect(screen.getByText('Top Processes')).toBeInTheDocument();
    expect(screen.getAllByText('python3').length).toBeGreaterThan(0);
    expect(screen.getAllByText('chrome').length).toBeGreaterThan(0);
    expect(screen.getAllByText('node').length).toBeGreaterThan(0);
  });

  it('displays disk information', () => {
    render(<DiagnosticsPanel data={mockData} />);
    const header = screen.getByText('Diagnostics').closest('.diag-header');
    fireEvent.click(header);

    expect(screen.getByText(/Disk \//)).toBeInTheDocument();
    expect(screen.getByText(/200.0.*500.0.*GB/)).toBeInTheDocument();
  });

  it('handles unavailable data gracefully', () => {
    render(<DiagnosticsPanel data={{ available: false }} />);
    expect(screen.getByText('Data unavailable')).toBeInTheDocument();
  });

  it('handles null data gracefully', () => {
    render(<DiagnosticsPanel data={null} />);
    expect(screen.getByText('Data unavailable')).toBeInTheDocument();
  });

  it('displays RAM percentage in collapsed view', () => {
    render(<DiagnosticsPanel data={mockData} />);
    // In collapsed view, RAM shows percentage
    const ramSection = screen.getByText('RAM').parentElement;
    expect(ramSection.textContent).toContain('51');
  });

  it('toggles collapse and expand multiple times', () => {
    render(<DiagnosticsPanel data={mockData} />);

    const header = screen.getByText('Diagnostics').closest('.diag-header');

    // Initial: collapsed
    expect(screen.getByText('⊞')).toBeInTheDocument();

    // Expand
    fireEvent.click(header);
    expect(screen.getByText('⊟')).toBeInTheDocument();

    // Collapse
    fireEvent.click(header);
    expect(screen.getByText('⊞')).toBeInTheDocument();

    // Expand again
    fireEvent.click(header);
    expect(screen.getByText('⊟')).toBeInTheDocument();
  });
});
