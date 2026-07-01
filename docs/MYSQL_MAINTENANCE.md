# MySQL Maintenance & Auto-Start

## Problem
MySQL stopped running after years of operation, causing Web News to show "No feeds selected." We need to:
1. Prevent MySQL from stopping
2. Automatically restart it if it crashes
3. Monitor its health

---

## Solution 1: Enable Auto-Start (Manual Setup)

Run this **once** to make MySQL start automatically on system boot:

```bash
sudo /usr/local/mysql/support-files/mysql.server start --enable
```

This creates a launchd service that starts MySQL at boot time.

**Verify it worked:**
```bash
launchctl list | grep mysql
```

You should see `com.mysql.mysqld` in the output.

---

## Solution 2: Health Check Script (Automated Monitoring)

Create a daily health check script that:
- Verifies MySQL is running
- Restarts it if needed
- Logs issues for review

**File: `/Users/tonyseneadza/Codehome/AgenticOS/scripts/check_mysql_health.sh`**

```bash
#!/bin/bash

# MySQL Health Check Script
# Runs daily via cron to ensure MySQL stays running

MYSQL_PATH="/usr/local/mysql/bin/mysql"
LOG_FILE="$HOME/.agentic-os/mysql_health.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Test MySQL connection
if ! $MYSQL_PATH -u root -e "SELECT 1" > /dev/null 2>&1; then
    log_message "⚠️  MySQL is DOWN - attempting restart..."
    
    # Try to start MySQL
    if sudo /usr/local/mysql/support-files/mysql.server start > /dev/null 2>&1; then
        log_message "✅ MySQL restarted successfully"
    else
        log_message "❌ ERROR: Failed to restart MySQL - manual intervention required"
    fi
else
    log_message "✅ MySQL is healthy"
fi
```

**Save the script:**
```bash
mkdir -p ~/Codehome/AgenticOS/scripts
cat > ~/Codehome/AgenticOS/scripts/check_mysql_health.sh << 'EOF'
#!/bin/bash
MYSQL_PATH="/usr/local/mysql/bin/mysql"
LOG_FILE="$HOME/.agentic-os/mysql_health.log"
mkdir -p "$(dirname "$LOG_FILE")"
if ! $MYSQL_PATH -u root -e "SELECT 1" > /dev/null 2>&1; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] MySQL DOWN - restarting..." >> "$LOG_FILE"
    sudo /usr/local/mysql/support-files/mysql.server start >> "$LOG_FILE" 2>&1
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] MySQL OK" >> "$LOG_FILE"
fi
EOF
chmod +x ~/Codehome/AgenticOS/scripts/check_mysql_health.sh
```

---

## Solution 3: Schedule Daily Health Checks

**Option A: Using cron (Terminal)**

```bash
crontab -e
```

Add this line to run the health check every morning at 6 AM:

```cron
0 6 * * * /Users/tonyseneadza/Codehome/AgenticOS/scripts/check_mysql_health.sh
```

**Option B: Using launchd (Recommended for macOS)**

Create: `~/Library/LaunchAgents/com.agenticos.mysql-health-check.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agenticos.mysql-health-check</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/tonyseneadza/Codehome/AgenticOS/scripts/check_mysql_health.sh</string>
    </array>
    <key>StartInterval</key>
    <integer>86400</integer>
    <key>StandardErrorPath</key>
    <string>/tmp/mysql-health-check.err</string>
    <key>StandardOutPath</key>
    <string>/tmp/mysql-health-check.out</string>
</dict>
</plist>
```

Load it:
```bash
launchctl load ~/Library/LaunchAgents/com.agenticos.mysql-health-check.plist
```

---

## Solution 4: Sidecar Health Check

The AgenticOS sidecar already has a startup handler that detects MySQL unavailability. If MySQL is down, you'll see:
- Web News shows "No feeds selected" (graceful degradation)
- Logs show MySQL connection errors
- The app continues running (no crash)

**Check sidecar logs:**
```bash
tail -f ~/.agentic-os/sidecar.log
```

---

## Troubleshooting

**Check if MySQL is running:**
```bash
ps aux | grep mysqld | grep -v grep
```

**Manual restart:**
```bash
sudo /usr/local/mysql/support-files/mysql.server start
```

**Check launchd status:**
```bash
launchctl list | grep mysql
```

**View MySQL error log:**
```bash
tail -50 /usr/local/mysql/data/*.err
```

**Test MySQL connection:**
```bash
/usr/local/mysql/bin/mysql -u root -e "SELECT VERSION();"
```

---

## Recommended Maintenance Schedule

| Task | Frequency | Command |
|------|-----------|---------|
| Health check | Daily | Automated via launchd/cron |
| Verify auto-start enabled | Monthly | `launchctl list \| grep mysql` |
| Review health log | Weekly | `tail -20 ~/.agentic-os/mysql_health.log` |
| Restart system | Quarterly | Automatic MySQL restart on reboot |

---

## Files & Locations

- **MySQL binary**: `/usr/local/mysql/bin/mysqld`
- **MySQL startup script**: `/usr/local/mysql/support-files/mysql.server`
- **Data directory**: `/usr/local/mysql/data/`
- **Config**: `~/.agentic-os/.env` (optional MySQL credentials)
- **Health log**: `~/.agentic-os/mysql_health.log`
- **Launchd plist**: `~/Library/LaunchAgents/com.mysql.mysqld.plist` (official installer)

---

## Next Steps

1. Run `sudo /usr/local/mysql/support-files/mysql.server start --enable` to enable auto-start
2. Create the health check script
3. Load the launchd plist to schedule daily checks
4. Verify setup: `launchctl list | grep mysql` should show both services

---

## Questions?

If MySQL stops again:
1. Check the health log: `cat ~/.agentic-os/mysql_health.log`
2. Manually restart: `sudo /usr/local/mysql/support-files/mysql.server start`
3. Check sidecar logs for connection errors
