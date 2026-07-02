---
name: mysql-recovery
description: |
  Diagnose and resolve MySQL connection issues, fix data directory permissions, and implement automatic recovery infrastructure using launchd. Use this skill whenever MySQL crashes, Keno telemetry panel shows connection errors (2003 HY000), or when setting up persistent database services. Includes health check monitoring, startup procedures, and end-to-end verification for database-dependent applications like AgenticOS.
compatibility: macOS with MySQL 9.4+, requires sudo access for permission fixes
---

# MySQL Recovery & Auto-Restart Infrastructure

## Overview

This skill provides a complete diagnostic and recovery workflow for MySQL connection issues on macOS. It handles permission problems, implements automatic restart infrastructure via launchd, and verifies the complete database stack end-to-end.

**When to use this:**
- MySQL crashes and won't restart
- Dashboard shows "Can't connect to MySQL server on 'localhost:3306' (2003 HY000)"
- Need to set up automatic recovery (health check monitoring every 5 minutes)
- Permission errors prevent MySQL startup: "Permission denied: /usr/local/mysql/data/*"

## Quick Start (5 minutes)

If MySQL is already partially installed, follow this minimal path:

```bash
# 1. Fix permissions (requires sudo)
sudo chown -R _mysql:_mysql /usr/local/mysql/data
sudo chmod 777 /usr/local/mysql/data

# 2. Start MySQL
sudo /usr/local/mysql/support-files/mysql.server start

# 3. Verify connection
/usr/local/mysql/bin/mysql -h 127.0.0.1 -u root -pNatasha1785 -e "SELECT VERSION();"

# 4. Set up auto-recovery (one-time)
bash ~/Codehome/AgenticOS/scripts/setup-mysql-recovery.sh
```

If MySQL is not installed or these fail, follow the full diagnostic process below.

## Diagnostic Flowchart

### Phase 1: Identify the Actual Problem

Many "MySQL won't start" issues have distinct root causes. Diagnosis first, fix second.

**Q1: Is MySQL installed?**
```bash
ls -la /usr/local/mysql/bin/mysqld
```
- If found: Go to Q2
- If not found: MySQL not installed (see "Installation" section)

**Q2: Is the MySQL process running?**
```bash
ps aux | grep mysqld | grep -v grep
```
- If yes: Go to Q3 (connection issue)
- If no: Go to Q4 (startup failure)

**Q3: Is MySQL accepting connections?**
```bash
/usr/local/mysql/bin/mysql -h 127.0.0.1 -u root -pNatasha1785 -e "SELECT 1;"
```
- If works: MySQL is healthy, problem is elsewhere (check application connection string)
- If "2003 (HY000)": Process exists but socket/port not responding (see "Fix: Port/Socket Issues")
- If "2002 (HY000)": Socket file missing (see "Fix: Missing Socket")

**Q4: Why won't MySQL start?**

Run mysqld directly to see the actual error (not filtered by mysql.server script):
```bash
/usr/local/mysql/bin/mysqld --user=_mysql --datadir=/usr/local/mysql/data 2>&1 | head -50
```

Common errors and fixes:
- **"Permission denied: ./binlog.index"** → See "Fix: File Permissions"
- **"Can't remove the pid file"** → Stale PID file (see "Fix: Stale PID")
- **"One can only use the --user switch if running as root"** → Use sudo: `sudo /usr/local/mysql/bin/mysqld_safe`
- **Other errors** → Check /usr/local/mysql/data/*.err log file

## Fixes by Error Type

### Fix: File Permissions

**Error**: `Permission denied: /usr/local/mysql/data/Tonys-MacBook-Air.local.err`

MySQL data directory is owned by `_mysql:_mysql` but current user can't write. Root cause: previous user ran MySQL startup as a different user.

```bash
# 1. Check current permissions
ls -la /usr/local/mysql/data/ | head -10

# 2. Fix ownership and permissions (requires sudo)
sudo chown -R _mysql:_mysql /usr/local/mysql/data
sudo chmod 777 /usr/local/mysql/data

# 3. Remove stale files
sudo rm -f /usr/local/mysql/data/*.pid*
sudo rm -f /usr/local/mysql/data/*.err

# 4. Try starting again
/usr/local/mysql/support-files/mysql.server start
```

**Why this works**: The `_mysql` user owns the MySQL process. Files created by MySQL must be writable by that user. `chmod 777` temporarily opens permissions; in production you'd use `chmod 750` and verify group membership.

### Fix: Stale PID File

**Error**: `Can't remove the pid file: /usr/local/mysql/data/Tonys-MacBook-Air.local.pid`

Previous MySQL process crashed or was killed ungracefully, leaving a stale PID file.

```bash
# 1. Remove all PID-related files
sudo rm -f /usr/local/mysql/data/*.pid*

# 2. Remove error log
sudo rm -f /usr/local/mysql/data/*.err

# 3. Restart
/usr/local/mysql/support-files/mysql.server start
```

### Fix: Missing Socket

**Error**: `Can't connect to local MySQL server through socket '/tmp/mysql.sock' (2)`

MySQL is running but the socket file isn't being created at the expected location.

```bash
# 1. Check where the socket actually is
find /tmp -name "mysql.sock" 2>/dev/null

# 2. Check MySQL config for socket location
grep socket /usr/local/mysql/my.cnf 2>/dev/null || grep socket /etc/my.cnf 2>/dev/null

# 3. Connect via TCP port instead (bypasses socket)
/usr/local/mysql/bin/mysql -h 127.0.0.1 -u root -pNatasha1785 -e "SELECT 1;"
```

If TCP works but socket doesn't, the application connection string might need updating to use TCP: `mysql -h 127.0.0.1` instead of `mysql` (which tries socket first).

### Fix: Port Not Listening

**Error**: `Can't connect to MySQL server on '127.0.0.1:3306' (61)`

Process exists but port 3306 not listening. Usually means startup failed silently.

```bash
# 1. Check if port is actually listening
lsof -i :3306

# 2. Check if process is zombie or hung
ps aux | grep mysqld | grep -v grep

# 3. Run mysqld directly to see actual error
/usr/local/mysql/bin/mysqld --user=_mysql --datadir=/usr/local/mysql/data 2>&1 | head -100

# 4. Kill any stuck processes
pkill -9 mysqld
sleep 1

# 5. Retry with sudo
sudo /usr/local/mysql/bin/mysqld_safe &
sleep 3
ps aux | grep mysqld | grep -v grep
```

## Setting Up Auto-Recovery (Launchd)

Once MySQL starts successfully, implement automatic restart so it recovers from crashes within 5 minutes.

### Step 1: Verify Setup Script Exists

```bash
ls -la ~/Codehome/AgenticOS/scripts/setup-mysql-recovery.sh
ls -la ~/Codehome/AgenticOS/scripts/check_mysql_health.sh
ls -la ~/Codehome/AgenticOS/scripts/mysql-health-check.plist
```

These should be committed in the repo. If missing, create them (see "Reference Files" section).

### Step 2: Run Setup Script

```bash
bash ~/Codehome/AgenticOS/scripts/setup-mysql-recovery.sh
```

This script:
1. Creates `~/Library/LaunchAgents/com.tonyseneadza.mysql-health-check.plist`
2. Fixes MySQL data directory permissions via sudo
3. Loads the launchd service
4. Runs initial health check to verify setup

**Expected output:**
```
Step 1: Creating LaunchAgents directory...
✓ Directory created/verified

Step 2: Copying launchd plist...
✓ Plist installed to: /Users/tonyseneadza/Library/LaunchAgents/...

Step 3: Fixing MySQL data directory permissions...
✓ MySQL data directory permissions updated

Step 4: Unloading any existing health check service...
✓ Previous service unloaded

Step 5: Loading launchd service...
✓ Launchd service loaded successfully

Setup Complete!
```

### Step 3: Verify Service is Active

```bash
# Check if service is loaded
launchctl list | grep mysql-health-check

# Should show output like:
# PID    Status  Label
# 12345  -       com.tonyseneadza.mysql-health-check
```

### Step 4: Monitor Health Checks

```bash
# View recent health check logs
tail -20 ~/.agentic-os/mysql_health.log

# Watch real-time (Ctrl+C to exit)
tail -f ~/.agentic-os/mysql_health.log
```

Expected log output:
```
[2026-07-02 03:35:00] [INFO] MySQL Health Check started
[2026-07-02 03:35:00] [OK] MySQL is running and healthy
```

## End-to-End Verification

After MySQL is running and auto-recovery is set up, verify the complete stack:

### Checklist

- [ ] MySQL process is running: `ps aux | grep mysqld | grep -v grep` returns the mysqld process
- [ ] Port 3306 is listening: `/usr/local/mysql/bin/mysql -h 127.0.0.1 -u root -pNatasha1785 -e "SELECT 1;"` succeeds
- [ ] Database exists: `mysql -h 127.0.0.1 -u root -pNatasha1785 -e "SHOW DATABASES LIKE 'keno_georgia';"` shows the database
- [ ] Launchd service is loaded: `launchctl list | grep mysql-health-check` shows the service
- [ ] Application (e.g., Agentic OS) reconnects: Dashboard Keno Telemetry panel shows data (no error message)

### Restart Application to Trigger Reconnection

If the application cached a connection failure before MySQL restarted, it won't reconnect until restarted:

```bash
# Kill existing application and sidecar
pkill -f "gui.sidecar"
pkill -f "Agentic OS"

# Restart application (example)
open /Applications/"Agentic OS.app"
```

The sidecar will spawn fresh and establish a new connection to MySQL.

## Troubleshooting

### "Launchd service loaded but health check never runs"

Launchd service might not be able to find the bash script. Verify:
1. Script path in plist matches reality: `ls -la /Users/tonyseneadza/Codehome/AgenticOS/scripts/check_mysql_health.sh`
2. Script is executable: `chmod +x /Users/tonyseneadza/Codehome/AgenticOS/scripts/check_mysql_health.sh`
3. Reload service: `launchctl unload ~/Library/LaunchAgents/com.tonyseneadza.mysql-health-check.plist && launchctl load ~/Library/LaunchAgents/com.tonyseneadza.mysql-health-check.plist`

### "Application still shows MySQL error after restart"

The application might have cached the error in memory. Fully restart the application:
```bash
# Kill all related processes
pkill -f "gui.sidecar"
pkill -f "Agentic OS"
sleep 2

# Restart
open /Applications/"Agentic OS.app"
```

### "Permission denied" errors persist after chmod 777

macOS ACLs might be blocking access. Check:
```bash
ls -l@ /usr/local/mysql/data/
```

If you see `@` symbols, ACLs are set:
```bash
# Remove ACLs (requires sudo)
sudo chmod -N /usr/local/mysql/data
sudo chmod 777 /usr/local/mysql/data
```

### MySQL starts but then crashes after 10 seconds

Check the error log for configuration or resource issues:
```bash
tail -50 /usr/local/mysql/data/*.err
```

Common causes:
- Insufficient disk space: `df -h /usr/local/mysql/data/`
- Corrupted innodb files: check `#ib*` files in data directory
- MySQL too old/new vs. data format version

## Key Learnings

1. **Permissions are critical**: MySQL runs as `_mysql:_mysql` user. All data files must be owned by that user and writable.

2. **Error messages are in multiple places**: Check `/usr/local/mysql/data/*.err` not just stdout.

3. **Direct mysqld output shows real errors**: Run `/usr/local/mysql/bin/mysqld` directly (not via mysql.server script) to see startup errors that get hidden.

4. **Socket vs TCP**: Applications can connect via Unix socket (faster, local only) or TCP (works remotely, more portable). The health check script uses TCP internally.

5. **Auto-recovery needs monitoring**: The launchd service will restart MySQL, but it can't fix all problems. Log monitoring is important.

## Session Context

This skill was created after a complete MySQL recovery session on 2026-07-02:
- **Problem**: MySQL crashed, Keno telemetry panel showed "Can't connect" error
- **Root cause**: File permissions in /usr/local/mysql/data prevented startup
- **Solution**: Fixed permissions, implemented launchd auto-restart service
- **Outcome**: MySQL running stably, Keno telemetry showing data, auto-recovery active
- **Related doc**: See `docs/CONTINUATION.md` for session notes
