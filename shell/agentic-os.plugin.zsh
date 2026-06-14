# Agentic OS — Oh My Zsh plugin (FR-09, TR-09)
#
# Emits structured JSON events to the Agentic OS Unix socket on every
# command execution and directory change.  The backend routes these events
# to the shell agent (FR-10, FR-11).
#
# Install:
#   1. mkdir -p ~/.oh-my-zsh/custom/plugins/agentic-os
#   2. cp agentic-os.plugin.zsh ~/.oh-my-zsh/custom/plugins/agentic-os/
#   3. Add "agentic-os" to plugins=() in ~/.zshrc
#   4. reload: source ~/.zshrc
#
# TR-09: socket is at ~/.agentic-os/shell.sock (chmod 600, server-side).
# Reconnection: the plugin retries the socket on every event (socat's
# one-shot mode naturally handles this — no persistent connection to lose).
#
# The plugin is deliberately minimal: no subshells in hot paths, no
# background processes, no eval.  socat is used for IPC because it is
# available on macOS via Homebrew and handles the AF_UNIX framing cleanly.

# ---- configuration -------------------------------------------------------
AGENTIC_OS_SOCKET="${HOME}/.agentic-os/shell.sock"
AGENTIC_OS_TIMEOUT=0.1          # seconds socat waits for socket (non-blocking)
AGENTIC_OS_ENABLED=${AGENTIC_OS_ENABLED:-1}   # set to 0 to silence the plugin

# ---- internal helpers ----------------------------------------------------

# _aos_send: emit a single JSON line to the socket, silently.
# Uses socat in one-shot mode (each call opens, sends, closes).
# Drops the event if the socket is absent or the server is not running.
_aos_send() {
  [[ "${AGENTIC_OS_ENABLED}" == "0" ]] && return
  local payload="$1"
  [[ ! -S "${AGENTIC_OS_SOCKET}" ]] && return
  if command -v socat &>/dev/null; then
    # preferred: socat one-shot (brew install socat)
    printf '%s\n' "${payload}" \
      | socat -t "${AGENTIC_OS_TIMEOUT}" - \
          "UNIX-CONNECT:${AGENTIC_OS_SOCKET}" 2>/dev/null &!
  else
    # fallback: python3 Unix socket (available on all macOS)
    printf '%s\n' "${payload}" \
      | python3 -c "
import socket, sys
s = socket.socket(socket.AF_UNIX)
try:
    s.connect(sys.argv[1])
    s.sendall(sys.stdin.buffer.read())
    s.close()
except Exception:
    pass
" "${AGENTIC_OS_SOCKET}" 2>/dev/null &!
  fi
}

# _aos_json_escape: minimal JSON string escaping (backslash and double-quote)
_aos_json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"   # \ → \\
  s="${s//\"/\\\"}"   # " → \"
  printf '%s' "${s}"
}

# ---- hooks ---------------------------------------------------------------

# preexec: fires before each command is executed (ZSH built-in hook)
agentic_os_preexec() {
  local cmd
  cmd="$(_aos_json_escape "$1")"
  local cwd
  cwd="$(_aos_json_escape "${PWD}")"
  _aos_send "{\"event\":\"preexec\",\"command\":\"${cmd}\",\"cwd\":\"${cwd}\"}"
  # Remember timestamp for duration tracking in precmd
  _AOS_CMD_START="${EPOCHREALTIME:-$(date +%s)}"
}

# precmd: fires after each command completes, before the next prompt
agentic_os_precmd() {
  local code=$?
  local cwd
  cwd="$(_aos_json_escape "${PWD}")"
  local duration=""
  if [[ -n "${_AOS_CMD_START}" ]]; then
    # EPOCHREALTIME is available in ZSH 5.8+
    local now="${EPOCHREALTIME:-$(date +%s)}"
    duration=$(printf '%.3f' $(( now - _AOS_CMD_START )) 2>/dev/null || echo "")
    unset _AOS_CMD_START
  fi
  _aos_send "{\"event\":\"precmd\",\"exit_code\":${code},\"cwd\":\"${cwd}\",\"duration_s\":\"${duration}\"}"
}

# chpwd: fires when the working directory changes (cd, pushd, popd, etc.)
agentic_os_chpwd() {
  local cwd
  cwd="$(_aos_json_escape "${PWD}")"
  _aos_send "{\"event\":\"chpwd\",\"cwd\":\"${cwd}\"}"
}

# ---- register hooks -------------------------------------------------------
autoload -Uz add-zsh-hook
add-zsh-hook preexec agentic_os_preexec
add-zsh-hook precmd  agentic_os_precmd
add-zsh-hook chpwd   agentic_os_chpwd

# ---- optional: helper functions visible in the shell ---------------------

# aos-status: show whether the socket server is reachable
aos-status() {
  if [[ -S "${AGENTIC_OS_SOCKET}" ]]; then
    echo "agentic-os: socket present at ${AGENTIC_OS_SOCKET} ✓"
  else
    echo "agentic-os: socket not found (server not running?)"
  fi
}

# aos-off / aos-on: temporarily suspend / resume event emission
aos-off() { export AGENTIC_OS_ENABLED=0; echo "agentic-os: events paused"; }
aos-on()  { export AGENTIC_OS_ENABLED=1; echo "agentic-os: events resumed"; }
