# MySQL Quick Reference — AgenticOS

## ⚡ Quick Checks

**Is MySQL running?**
```bash
ps aux | grep mysqld | grep -v grep
```

**Test MySQL connection:**
```bash
/usr/local/mysql/bin/mysql -u root -e "SELECT VERSION();"
```

**Check health monitoring status:**
```bash
launchctl list | grep mysql
```

---

## 🚀 If MySQL Is Down

**Quick restart:**
```bash
sudo /usr/local/mysql/support-files/mysql.server start
```

**Check what's wrong:**
```bash
tail -20 /usr/local/mysql/data/*.err
```

**View health check log:**
```bash
tail -50 ~/.agentic-os/mysql_health.log
```

---

## 📋 Automated Safety Measures (Already Installed)

✅ **Daily health check**: Runs every 24 hours via launchd  
✅ **Auto-restart**: Restarts MySQL if it crashes  
✅ **Logging**: All checks logged to `~/.agentic-os/mysql_health.log`  
✅ **Graceful degradation**: Web News shows "No feeds selected" if MySQL is down (app doesn't crash)

---

## 🔧 Maintenance Tasks

| Task | Command |
|------|---------|
| Restart MySQL now | `sudo /usr/local/mysql/support-files/mysql.server start` |
| Stop MySQL | `sudo /usr/local/mysql/support-files/mysql.server stop` |
| Check current status | `ps aux \| grep mysqld` |
| View recent health checks | `tail -20 ~/.agentic-os/mysql_health.log` |
| View MySQL error log | `tail -50 /usr/local/mysql/data/*.err` |
| Reload health check scheduler | `launchctl unload ~/Library/LaunchAgents/com.agenticos.mysql-health-check.plist && launchctl load ~/Library/LaunchAgents/com.agenticos.mysql-health-check.plist` |

---

## 📍 Important Locations

- **MySQL binary**: `/usr/local/mysql/bin/mysqld`
- **Data directory**: `/usr/local/mysql/data/`
- **Health check script**: `~/Codehome/AgenticOS/scripts/check_mysql_health.sh`
- **Health log**: `~/.agentic-os/mysql_health.log`
- **Scheduler plist**: `~/Library/LaunchAgents/com.agenticos.mysql-health-check.plist`

---

## ✅ Verification Checklist

After restart, verify:
- [ ] MySQL process running: `ps aux | grep mysqld | grep -v grep`
- [ ] Can connect: `/usr/local/mysql/bin/mysql -u root -e "SELECT 1;"`
- [ ] Web News shows articles (not "No feeds selected")
- [ ] Health log updated: `tail -5 ~/.agentic-os/mysql_health.log`

---

## 🚨 If Problems Persist

1. **Check MySQL error log**: `tail -100 /usr/local/mysql/data/*.err`
2. **Check permissions**: `ls -la /usr/local/mysql/data/`
3. **Restart your Mac**: May clear stale locks
4. **Reinstall MySQL**: If corruption suspected

---

## 📚 Full Documentation

See `MYSQL_MAINTENANCE.md` for detailed setup and troubleshooting.
