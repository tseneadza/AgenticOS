import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Environment from '../components/Environment';

// Mock the api module
vi.mock('../api', () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

import { get, post } from '../api';

describe('Environment Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default mock responses
    get.mockResolvedValue({
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
  });

  it('renders without crashing', async () => {
    render(<Environment />);
    await waitFor(() => {
      expect(screen.queryByText('LLM Configuration')).toBeInTheDocument();
    });
  });

  it('loads config on mount', async () => {
    render(<Environment />);
    await waitFor(() => {
      expect(get).toHaveBeenCalledWith('/api/config');
    });
  });

  it('displays loading state initially', () => {
    render(<Environment />);
    expect(screen.getByText('Loading configuration...')).toBeInTheDocument();
  });

  it('renders Ollama settings when Ollama is selected', async () => {
    render(<Environment />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('http://localhost:11434')).toBeInTheDocument();
    });
  });

  it('switches to Anthropic settings when Anthropic radio is clicked', async () => {
    const user = userEvent.setup();
    render(<Environment />);

    await waitFor(() => {
      expect(screen.getByLabelText('Anthropic (Cloud)')).toBeInTheDocument();
    });

    const anthropicRadio = screen.getByLabelText('Anthropic (Cloud)');
    await user.click(anthropicRadio);

    await waitFor(() => {
      expect(screen.getByDisplayValue('https://api.anthropic.com/v1')).toBeInTheDocument();
      expect(screen.getByPlaceholderText('sk-ant-...')).toBeInTheDocument();
    });
  });

  it('tests connection and shows success status', async () => {
    post.mockResolvedValueOnce({ status: 'connected' });
    const user = userEvent.setup();

    render(<Environment />);
    await waitFor(() => {
      expect(screen.getByText(/Test Connection/)).toBeInTheDocument();
    });

    const testButton = screen.getByText(/Test Connection/);
    await user.click(testButton);

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/api/config/test', expect.any(Object));
      expect(screen.getByText(/Connected to ollama/i)).toBeInTheDocument();
    });
  });

  it('shows error on connection test failure', async () => {
    post.mockResolvedValueOnce({
      status: 'error',
      details: 'Connection refused'
    });
    const user = userEvent.setup();

    render(<Environment />);
    await waitFor(() => {
      expect(screen.getByText(/Test Connection/)).toBeInTheDocument();
    });

    const testButton = screen.getByText(/Test Connection/);
    await user.click(testButton);

    await waitFor(() => {
      expect(screen.getByText(/Connection refused/)).toBeInTheDocument();
    });
  });

  it('saves configuration', async () => {
    post.mockResolvedValueOnce({ status: 'saved' });
    const user = userEvent.setup();

    render(<Environment />);
    await waitFor(() => {
      expect(screen.getByText('Save Configuration')).toBeInTheDocument();
    });

    const saveButton = screen.getByText('Save Configuration');
    await user.click(saveButton);

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith('/api/config', expect.any(Object));
      expect(screen.getByText(/Configuration saved/)).toBeInTheDocument();
    });
  });

  it('disables save button when config is unchanged', async () => {
    render(<Environment />);
    await waitFor(() => {
      expect(screen.getByText('Save Configuration')).toBeDisabled();
    });
  });

  it('enables save button when config changes', async () => {
    const user = userEvent.setup();
    render(<Environment />);

    await waitFor(() => {
      expect(screen.getByLabelText('Ollama (Local)')).toBeInTheDocument();
    });

    const hostInput = screen.getByDisplayValue('http://localhost:11434');
    await user.clear(hostInput);
    await user.type(hostInput, 'http://localhost:9999');

    await waitFor(() => {
      expect(screen.getByText('Save Configuration')).not.toBeDisabled();
    });
  });

  it('cancels changes and restores original config', async () => {
    const user = userEvent.setup();
    render(<Environment />);

    await waitFor(() => {
      expect(screen.getByLabelText('Ollama (Local)')).toBeInTheDocument();
    });

    const hostInput = screen.getByDisplayValue('http://localhost:11434');
    await user.clear(hostInput);
    await user.type(hostInput, 'http://localhost:9999');

    const cancelButton = screen.getByText('Cancel');
    await user.click(cancelButton);

    await waitFor(() => {
      expect(screen.getByDisplayValue('http://localhost:11434')).toBeInTheDocument();
    });
  });

  it('toggles feature flags', async () => {
    const user = userEvent.setup();
    render(<Environment />);

    await waitFor(() => {
      expect(screen.getByLabelText(/Shell Commands/)).toBeInTheDocument();
    });

    const shellCommandsCheckbox = screen.getByLabelText(/Shell Commands/);
    expect(shellCommandsCheckbox).toBeChecked();

    await user.click(shellCommandsCheckbox);

    await waitFor(() => {
      expect(shellCommandsCheckbox).not.toBeChecked();
    });
  });

  it('validates Anthropic API key requirement', async () => {
    post.mockResolvedValueOnce({
      status: 'error',
      details: 'API key is required for Anthropic'
    });
    const user = userEvent.setup();

    render(<Environment />);

    // Switch to Anthropic
    await waitFor(() => {
      expect(screen.getByLabelText('Anthropic (Cloud)')).toBeInTheDocument();
    });

    const anthropicRadio = screen.getByLabelText('Anthropic (Cloud)');
    await user.click(anthropicRadio);

    // Try to test without API key
    const testButton = screen.getByText(/Test Connection/);
    await user.click(testButton);

    await waitFor(() => {
      expect(screen.getByText(/API key is required/)).toBeInTheDocument();
    });
  });
});
