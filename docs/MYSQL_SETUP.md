# MySQL Setup for AgenticOS Web News

## Installation (macOS)

### Option 1: Homebrew (Recommended)

```bash
# Install MySQL
brew install mysql

# Start MySQL service
brew services start mysql

# Verify installation
mysql --version
mysql -u root -e "SELECT VERSION();"
```

### Option 2: Download DMG
Visit https://dev.mysql.com/downloads/mysql/ and follow the installer.

---

## Verification

Test that AgenticOS can connect:

```bash
# Check if MySQL is running
lsof -i :3306

# Connect as root (no password initially)
mysql -u root -e "SELECT 1;"
```

---

## First Run — Automatic Setup

Once MySQL is running, the AgenticOS sidecar will automatically:
1. Create the `AgenticOS` database
2. Create `news_categories` and `news_feeds` tables
3. Seed 8 categories + 30 RSS feeds (Science, Physics, AI/ML, etc.)

This happens on the **first API call** to `/api/news/feeds` (when you click Refresh in Web News).

---

## Configuration

If you need to use non-default credentials, create `~/.agentic-os/.env`:

```env
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASS=your_password
MYSQL_DB=AgenticOS
```

---

## Troubleshooting

**MySQL still won't start:**
```bash
# Check if port 3306 is already in use
sudo lsof -i :3306

# Restart MySQL
brew services restart mysql
```

**Permission denied when connecting:**
```bash
# Set a password for root
mysql -u root -e "ALTER USER 'root'@'localhost' IDENTIFIED BY 'yourpassword';"
```

Then add to `~/.agentic-os/.env`:
```env
MYSQL_PASS=yourpassword
```

---

## Next Steps

1. Install & start MySQL
2. Restart the AgenticOS app (or just the sidecar)
3. Go to **Web News** and click **Refresh**
4. You should see ~30 articles from science feeds

---

## References

- Seed data: `gui/sidecar/routes/news_db.py` (lines 127-170)
- API routes: `gui/sidecar/routes/api_news.py`
- Sidecar startup: `gui/sidecar/app.py` line 57 (`_ensure_news_schema`)
