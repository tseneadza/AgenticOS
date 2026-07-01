# Web News Management & API Reference

Complete guide for managing Web News feeds and categories, including API registration, health monitoring, and troubleshooting.

---

## 🚀 Quick Start: Add a Feed or Category

1. **Open Web News** → Click ⚙ settings button (far right toolbar)
2. **Add Feed**:
   - Enter feed name (e.g., "Nature Physics")
   - Enter RSS URL (e.g., `https://example.com/feed`)
   - Select category dropdown
   - Click "+ Add" button
   - Click "Apply & Fetch"
3. **Add Category**:
   - Enter category name (e.g., "Quantum Computing")
   - Pick a color
   - Click "+ Add" button

---

## 📡 Registered API Endpoints

All endpoints are **registered in HubApiExplorer** and available via the sidecar (port 5130).

### Categories Management

| Method | Endpoint | Purpose | Example |
|--------|----------|---------|---------|
| GET | `/api/news/categories` | List all categories | Returns: `{categories: [{id, name, color, ...}]}` |
| POST | `/api/news/categories` | Create new category | Body: `{name: "Robotics", color: "#7fb069"}` |
| PATCH | `/api/news/categories/{id}` | Update category | Body: `{color: "#d97b4f"}` |
| DELETE | `/api/news/categories/{id}` | Delete category + feeds | Removes category and all associated feeds |

### Feeds Management

| Method | Endpoint | Purpose | Example |
|--------|----------|---------|---------|
| GET | `/api/news/feeds` | List all feeds | Query params: `?enabled_only=true` `?category_id=physics-space` |
| POST | `/api/news/feeds` | Create new feed | Body: `{label: "New Scientist", url: "https://...", category_id: "physics-space"}` |
| PATCH | `/api/news/feeds/{id}` | Update feed | Body: `{enabled: false}` or `{label: "New name", url: "https://..."}` |
| DELETE | `/api/news/feeds/{id}` | Delete feed | Removes feed from database |

### Article Processing

| Method | Endpoint | Purpose | Example |
|--------|----------|---------|---------|
| POST | `/api/news/fetch` | Fetch + keyword-filter RSS items | Body: `{urls: ["https://..."], keywords: ["quantum"]}` |
| POST | `/api/news/rank` | AI-rank articles by relevance | Body: `{articles: [{title: "…"}], domains: [], keywords: []}` |

---

## 🗄️ Database: MySQL + SQLite Seeds

**Schema**: `AgenticOS` (MySQL)  
**Tables**: `news_categories`, `news_feeds`  
**Seeding**: Automatic on first connection (8 categories + 30 RSS feeds)

### Seed Data Included

- **8 Science Categories**:
  - Physics & Space, Biology & Life Sciences, AI & Machine Learning
  - Neuroscience, Mathematics, Engineering & Technology
  - Chemistry & Materials, Climate & Earth Science

- **30 RSS Feeds** (from authoritative sources):
  - arXiv (Physics, ML, Neuroscience)
  - Science News, ScienceDaily, Quanta Magazine
  - New Scientist, Chemistry World, Phys.org
  - And more academic + science sources

**Source file**: `gui/sidecar/routes/news_db.py` (lines 127–170)

---

## ✅ Health Monitoring

### Automatic Daily Health Check

**What it does:**
- Verifies MySQL is running every 24 hours
- Auto-restarts MySQL if it crashes
- Logs all checks to `~/.agentic-os/mysql_health.log`
- Alerts on failures (check log for details)

**Status**: ✅ ACTIVE in launchd
```bash
launchctl list | grep mysql
# Should show: com.agenticos.mysql-health-check
```

**Files**:
- Script: `/Users/tonyseneadza/Codehome/AgenticOS/scripts/check_mysql_health.sh`
- Scheduler: `~/Library/LaunchAgents/com.agenticos.mysql-health-check.plist`
- Logs: `~/.agentic-os/mysql_health.log`

### Manual Health Check

```bash
# Is MySQL running?
ps aux | grep mysqld | grep -v grep

# Test connection
/usr/local/mysql/bin/mysql -u root -e "SELECT VERSION();"

# Check health log
tail -20 ~/.agentic-os/mysql_health.log

# Restart if needed
sudo /usr/local/mysql/support-files/mysql.server start
```

---

## 🔧 Troubleshooting Feed Creation Issues

**Problem**: Added a feed but it doesn't appear in the list

**Solution checklist**:

1. **Is MySQL running?**
   ```bash
   ps aux | grep mysqld
   ```
   If not: `sudo /usr/local/mysql/support-files/mysql.server start`

2. **Check health log for errors:**
   ```bash
   tail -50 ~/.agentic-os/mysql_health.log
   ```

3. **Verify category exists:**
   - Go to Settings ⚙
   - Scroll to "Manage Categories"
   - Confirm the category you selected exists

4. **Try adding again:**
   - Fill in all fields (name, URL, category)
   - Click "+ Add"
   - Click "Apply & Fetch"
   - Wait 2-3 seconds
   - Close settings and reopen to refresh

5. **Check sidecar logs:**
   ```bash
   tail -50 /tmp/sidecar.log  # if running manually
   ```

6. **Browser cache issue?**
   - Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows/Linux)
   - Close and reopen Web News view

---

## 📋 Related Documentation

- **MySQL Setup**: `docs/MYSQL_SETUP.md` — Installation & troubleshooting
- **MySQL Maintenance**: `docs/MYSQL_MAINTENANCE.md` — Health checks, auto-restart, scheduling
- **MySQL Quick Reference**: `docs/MYSQL_QUICK_REFERENCE.md` — Fast commands & verification
- **API Registration**: `docs/api-registry.md` — All registered endpoints & requirements

---

## 🎯 Key Learnings (Session 8)

**What went wrong before:**
- MySQL stopped running after years of operation
- Feed creation silently failed due to database unavailability
- One category creation worked, so issue wasn't obvious

**What's fixed now:**
- ✅ MySQL auto-starts on system boot
- ✅ Health check runs daily and auto-restarts if needed
- ✅ All 10 API endpoints properly registered
- ✅ Web News UI fully functional with create/read/update/delete

**Prevention going forward:**
- Automatic daily MySQL health monitoring
- Auto-restart on crash (no manual intervention needed)
- Graceful error handling in Web News UI
- Comprehensive documentation for troubleshooting

---

## ⚡ One-Minute Verification

```bash
# Everything working?
echo "1. MySQL running:" && (ps aux | grep mysqld | grep -v grep && echo "✅ YES" || echo "❌ NO")
echo "2. Health check active:" && (launchctl list | grep mysql | grep -q "com.agenticos" && echo "✅ YES" || echo "❌ NO")
echo "3. Health log:" && tail -5 ~/.agentic-os/mysql_health.log
```

---

**Last verified**: June 30, 2026  
**Status**: All systems operational ✅
