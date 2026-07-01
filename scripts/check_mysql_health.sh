#!/bin/bash
# MySQL Health Check Script for AgenticOS
# Verifies MySQL is running, restarts if needed, logs results
# Usage: Run manually or schedule via cron/launchd

set -e

MYSQL_PATH="/usr/local/mysql/bin/mysql"
MYSQL_START="/usr/local/mysql/support-files/mysql.server"
LOG_DIR="$HOME/.agentic-os"
LOG_FILE="$LOG_DIR/mysql_health.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Function to log messages with timestamp
log_message() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
    # Also echo to stdout for manual runs
    echo "[$timestamp] [$level] $message"
}

# Function to check if MySQL is running
check_mysql() {
    if command -v "$MYSQL_PATH" &> /dev/null; then
        $MYSQL_PATH -u root -e "SELECT 1" > /dev/null 2>&1
        return $?
    else
        log_message "ERROR" "MySQL binary not found at $MYSQL_PATH"
        return 1
    fi
}

# Main logic
log_message "INFO" "MySQL Health Check started"

if check_mysql; then
    log_message "OK" "MySQL is running and healthy"
    exit 0
else
    log_message "WARN" "MySQL is not responding - attempting restart"

    # Attempt restart
    if sudo "$MYSQL_START" start >> "$LOG_FILE" 2>&1; then
        # Wait a moment for MySQL to start
        sleep 2

        # Verify restart was successful
        if check_mysql; then
            log_message "OK" "MySQL restarted successfully"
            exit 0
        else
            log_message "ERROR" "MySQL started but still not responding"
            exit 1
        fi
    else
        log_message "ERROR" "Failed to restart MySQL - manual intervention required"
        log_message "ERROR" "Run: sudo /usr/local/mysql/support-files/mysql.server start"
        exit 1
    fi
fi
