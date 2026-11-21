"""SQLite storage for the all-in-one bot.
Ratings, tickets, levels, economy and warns all live here.
No fake data - everything starts empty.
"""
import sqlite3, time, os

DB_PATH = os.getenv("BOT_DB_PATH") or os.path.join(os.path.dirname(__file__), "bot.db")

def _conn():
    # timeout=30: writers wait instead of instantly failing with
    # "database is locked" when the scan and live counting write at once.
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = _conn(); cur = c.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS settings (
        guild_id INTEGER PRIMARY KEY,
        ticket_category_id INTEGER,
        staff_role_id INTEGER,
        rating_log_channel_id INTEGER,
        welcome_channel_id INTEGER,
        log_channel_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS tickets (
        channel_id INTEGER PRIMARY KEY,
        guild_id INTEGER,
        owner_id INTEGER,
        staff_id INTEGER,
        created_at INTEGER,
        status TEXT DEFAULT 'open'
    );
    CREATE TABLE IF NOT EXISTS ratings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        ticket_channel_id INTEGER,
        user_id INTEGER,
        staff_id INTEGER,
        stars INTEGER,
        feedback TEXT,
        created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS levels (
        guild_id INTEGER, user_id INTEGER,
        xp INTEGER DEFAULT 0, level INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS economy (
        guild_id INTEGER, user_id INTEGER,
        balance INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS censored_words (
        guild_id INTEGER, word TEXT,
        PRIMARY KEY (guild_id, word)
    );
    CREATE TABLE IF NOT EXISTS warns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER, user_id INTEGER,
        mod_id INTEGER, reason TEXT, created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS loa (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER, user_id INTEGER,
        days INTEGER, reason TEXT, status TEXT DEFAULT 'pending',
        decided_by INTEGER, created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS strikes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER, user_id INTEGER,
        mod_id INTEGER, reason TEXT, created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER, user_id INTEGER,
        answers TEXT, status TEXT DEFAULT 'pending', created_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS ticket_menus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        title TEXT,
        placeholder TEXT,
        position INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS ticket_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        name TEXT,
        description TEXT,
        staff_role_id INTEGER,
        panel_channel_id INTEGER,
        category_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS application_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        name TEXT,
        description TEXT,
        role_id INTEGER,
        review_channel_id INTEGER,
        questions TEXT
    );
    CREATE TABLE IF NOT EXISTS message_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        name TEXT,
        title TEXT,
        content TEXT,
        channel_id INTEGER
    );
    CREATE TABLE IF NOT EXISTS auto_replies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        trigger TEXT,
        response TEXT
    );
    CREATE TABLE IF NOT EXISTS message_days (
        guild_id INTEGER, user_id INTEGER,
        day TEXT, -- YYYY-MM-DD (UTC)
        count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, day)
    );
    CREATE TABLE IF NOT EXISTS scan_progress (
        guild_id INTEGER, channel_id INTEGER,
        oldest_id INTEGER, -- oldest message id already counted; -1 = channel fully scanned
        PRIMARY KEY (guild_id, channel_id)
    );
    """)
    c.commit()
    try: cur.execute("ALTER TABLE applications ADD COLUMN template_id INTEGER")
    except Exception: pass
    for _t, _c in [("ticket_templates", "menu_id INTEGER"), ("ticket_templates", "emoji TEXT"),
                  ("ticket_templates", "ticket_prefix TEXT"), ("application_templates", "color INTEGER"),
                  ("application_templates", "cooldown_days INTEGER")]:
        try: cur.execute(f"ALTER TABLE {_t} ADD COLUMN {_c}")
        except Exception: pass
    c.commit()
    # Migrations for older bot.db files (new columns)
    for col in ["faith_channel_id INTEGER", "faith_verse_channel_id INTEGER", "faith_prayer_channel_id INTEGER", "faith_verse_role_id INTEGER", "faith_prayer_role_id INTEGER", "faith_hour INTEGER", "faith_last_posted TEXT", "messages_backfilled TEXT", "starboard_channel_id INTEGER", "app_channel_id INTEGER", "app_role_id INTEGER", "app_panel_channel_id INTEGER", "prefix TEXT DEFAULT '!'", "autorole_id INTEGER", "panel_channel_id INTEGER", "ticket_log_channel_id INTEGER", "welcome_message TEXT", "ticket_panel_title TEXT", "ticket_panel_description TEXT", "ticket_panel_color INTEGER"]:
        try: cur.execute(f"ALTER TABLE settings ADD COLUMN {col}")
        except Exception: pass
    c.commit(); c.close()

# --- settings ---
def set_setting(guild_id, key, value):
    c=_conn(); cur=c.cursor()
    cur.execute("INSERT INTO settings (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,))
    cur.execute(f"UPDATE settings SET {key}=? WHERE guild_id=?", (value, guild_id))
    c.commit(); c.close()

def get_settings(guild_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM settings WHERE guild_id=?", (guild_id,))
    row=cur.fetchone(); c.close()
    return dict(row) if row else {}

# --- tickets ---
def create_ticket(channel_id, guild_id, owner_id):
    c=_conn(); c.execute("INSERT OR REPLACE INTO tickets (channel_id,guild_id,owner_id,created_at) VALUES (?,?,?,?)",
        (channel_id, guild_id, owner_id, int(time.time()))); c.commit(); c.close()

def claim_ticket(channel_id, staff_id):
    c=_conn(); c.execute("UPDATE tickets SET staff_id=? WHERE channel_id=?", (staff_id, channel_id)); c.commit(); c.close()

def get_ticket(channel_id):
    c=_conn(); cur=c.cursor(); cur.execute("SELECT * FROM tickets WHERE channel_id=?", (channel_id,))
    row=cur.fetchone(); c.close(); return dict(row) if row else None

def close_ticket(channel_id):
    c=_conn(); c.execute("UPDATE tickets SET status='closed' WHERE channel_id=?", (channel_id,)); c.commit(); c.close()

# --- ratings (the ticket-close rating system) ---
def add_rating(guild_id, ticket_channel_id, user_id, staff_id, stars, feedback=""):
    c=_conn(); cur=c.cursor()
    # one rating per ticket per user
    cur.execute("SELECT id FROM ratings WHERE ticket_channel_id=? AND user_id=?", (ticket_channel_id, user_id))
    if cur.fetchone():
        c.close(); return False
    cur.execute("INSERT INTO ratings (guild_id,ticket_channel_id,user_id,staff_id,stars,feedback,created_at) VALUES (?,?,?,?,?,?,?)",
        (guild_id, ticket_channel_id, user_id, staff_id, stars, feedback, int(time.time())))
    c.commit(); c.close(); return True

def has_rated(ticket_channel_id, user_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT id FROM ratings WHERE ticket_channel_id=? AND user_id=?", (ticket_channel_id, user_id))
    r=cur.fetchone(); c.close(); return r is not None

def staff_ratings(guild_id, staff_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT stars, feedback, user_id, created_at FROM ratings WHERE guild_id=? AND staff_id=? ORDER BY created_at DESC", (guild_id, staff_id))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

def staff_average(guild_id, staff_id):
    rows=staff_ratings(guild_id, staff_id)
    if not rows: return 0.0, 0
    return round(sum(r["stars"] for r in rows)/len(rows), 2), len(rows)

def top_staff(guild_id, limit=10):
    c=_conn(); cur=c.cursor()
    cur.execute("""SELECT staff_id, AVG(stars) as avg, COUNT(*) as n
        FROM ratings WHERE guild_id=? AND staff_id IS NOT NULL
        GROUP BY staff_id ORDER BY avg DESC, n DESC LIMIT ?""", (guild_id, limit))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

def recent_ratings(guild_id, limit=10):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM ratings WHERE guild_id=? ORDER BY created_at DESC LIMIT ?", (guild_id, limit))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

# --- levels / economy ---
def add_xp(guild_id, user_id, amount):
    c=_conn(); cur=c.cursor()
    cur.execute("INSERT INTO levels (guild_id,user_id,xp) VALUES (?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET xp=xp+?",
        (guild_id, user_id, amount, amount))
    cur.execute("SELECT xp FROM levels WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    xp=cur.fetchone()["xp"]
    level=int((xp/100) ** 0.5)
    cur.execute("UPDATE levels SET level=? WHERE guild_id=? AND user_id=?", (level, guild_id, user_id))
    c.commit(); c.close(); return xp, level

def get_level(guild_id, user_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT xp, level FROM levels WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    r=cur.fetchone(); c.close(); return (r["xp"], r["level"]) if r else (0,0)

def top_levels(guild_id, limit=10):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT user_id, xp, level FROM levels WHERE guild_id=? ORDER BY xp DESC LIMIT ?", (guild_id, limit))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

def get_balance(guild_id, user_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT balance FROM economy WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    r=cur.fetchone(); c.close(); return r["balance"] if r else 0

def set_balance(guild_id, user_id, amount):
    c=_conn(); c.execute("INSERT INTO economy (guild_id,user_id,balance) VALUES (?,?,?) ON CONFLICT(guild_id,user_id) DO UPDATE SET balance=?",
        (guild_id, user_id, amount, amount)); c.commit(); c.close()

def add_balance(guild_id, user_id, amount):
    set_balance(guild_id, user_id, get_balance(guild_id, user_id)+amount)

def add_warn(guild_id, user_id, mod_id, reason):
    c=_conn(); c.execute("INSERT INTO warns (guild_id,user_id,mod_id,reason,created_at) VALUES (?,?,?,?,?)",
        (guild_id, user_id, mod_id, reason, int(time.time()))); c.commit(); c.close()

# --- LOA ---
def add_loa(guild_id, user_id, days, reason):
    c=_conn(); c.execute("INSERT INTO loa (guild_id,user_id,days,reason,created_at) VALUES (?,?,?,?,?)",
        (guild_id, user_id, days, reason, int(time.time()))); c.commit(); c.close()

def get_loa(guild_id, user_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM loa WHERE guild_id=? AND user_id=? AND status IN ('pending','approved') ORDER BY created_at DESC LIMIT 1", (guild_id, user_id))
    r=cur.fetchone(); c.close(); return dict(r) if r else None

def list_loa(guild_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM loa WHERE guild_id=? AND status IN ('pending','approved') ORDER BY created_at DESC", (guild_id,))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

def set_loa_status(guild_id, user_id, status, decided_by):
    c=_conn(); cur=c.cursor()
    cur.execute("UPDATE loa SET status=?, decided_by=? WHERE guild_id=? AND user_id=? AND status='pending'", (status, decided_by, guild_id, user_id))
    ok = cur.rowcount > 0; c.commit(); c.close(); return ok

def end_loa(guild_id, user_id):
    c=_conn(); cur=c.cursor()
    cur.execute("UPDATE loa SET status='ended' WHERE guild_id=? AND user_id=? AND status IN ('pending','approved')", (guild_id, user_id))
    ok = cur.rowcount > 0; c.commit(); c.close(); return ok

# --- Strikes ---
def add_strike(guild_id, user_id, mod_id, reason):
    c=_conn(); c.execute("INSERT INTO strikes (guild_id,user_id,mod_id,reason,created_at) VALUES (?,?,?,?,?)",
        (guild_id, user_id, mod_id, reason, int(time.time()))); c.commit(); c.close()

def list_strikes(guild_id, user_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM strikes WHERE guild_id=? AND user_id=? ORDER BY created_at DESC", (guild_id, user_id))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

def clear_strikes(guild_id, user_id):
    c=_conn(); c.execute("DELETE FROM strikes WHERE guild_id=? AND user_id=?", (guild_id, user_id)); c.commit(); c.close()

# --- applications (/apply in Discord) ---
def add_application(guild_id, user_id, answers):
    c=_conn(); cur=c.cursor()
    cur.execute("INSERT INTO applications (guild_id,user_id,answers,created_at) VALUES (?,?,?,?)",
                (guild_id, user_id, answers, int(time.time())))
    app_id = cur.lastrowid; c.commit(); c.close(); return app_id

def list_applications(guild_id, status="pending"):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM applications WHERE guild_id=? AND status=? ORDER BY created_at DESC", (guild_id, status))
    rows=[dict(r) for r in cur.fetchall()]; c.close(); return rows

def get_application(app_id):
    c=_conn(); cur=c.cursor()
    cur.execute("SELECT * FROM applications WHERE id=?", (app_id,))
    r=cur.fetchone(); c.close(); return dict(r) if r else None

def set_application_status(app_id, status):
    c=_conn(); cur=c.cursor()
    cur.execute("UPDATE applications SET status=? WHERE id=? AND status='pending'", (status, app_id))
    ok = cur.rowcount > 0; c.commit(); c.close(); return ok

def last_application_time(guild_id, user_id, template_id):
    """Unix time of this user's most recent application for this template (0 = never)."""
    c=_conn(); cur=c.cursor()
    r = cur.execute("SELECT MAX(created_at) FROM applications WHERE guild_id=? AND user_id=? AND template_id=?",
                    (guild_id, user_id, template_id)).fetchone()
    c.close(); return r[0] or 0

# --- message counts (/messages) ---
# One row per user per day (UTC). Counting starts when the bot is
# running and sees a message - it cannot count messages sent before
# the bot was added / before tracking started.
def record_message(guild_id, user_id, when=None):
    from datetime import datetime, timezone
    day = (when or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    c=_conn()
    c.execute("INSERT INTO message_days (guild_id,user_id,day,count) VALUES (?,?,?,1) "
              "ON CONFLICT(guild_id,user_id,day) DO UPDATE SET count=count+1",
              (guild_id, user_id, day))
    c.commit(); c.close()

def record_messages_bulk(guild_id, entries):
    """Count many messages at once (history scan): entries are
    (user_id, day) pairs. Aggregates per user/day and commits once,
    so a full-history scan is fast instead of one commit per message."""
    from collections import Counter
    counts = Counter(entries)
    if not counts:
        return
    c = _conn()
    c.executemany(
        "INSERT INTO message_days (guild_id,user_id,day,count) VALUES (?,?,?,?) "
        "ON CONFLICT(guild_id,user_id,day) DO UPDATE SET count=count+excluded.count",
        [(guild_id, uid, day, n) for (uid, day), n in counts.items()])
    c.commit(); c.close()

# --- history scan progress (resumable, no double-counting) ---
def get_scan_progress(guild_id, channel_id):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT oldest_id FROM scan_progress WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
    row = cur.fetchone(); c.close()
    return row[0] if row else None

def set_scan_progress(guild_id, channel_id, oldest_id):
    c = _conn()
    c.execute("INSERT INTO scan_progress VALUES (?,?,?) "
              "ON CONFLICT(guild_id,channel_id) DO UPDATE SET oldest_id=excluded.oldest_id",
              (guild_id, channel_id, oldest_id))
    c.commit(); c.close()

def clear_messages_before(guild_id, day):
    """Drop counted rows older than `day` (YYYY-MM-DD) for a guild — used
    before a clean re-scan so interrupted scans can't double-count."""
    c = _conn()
    c.execute("DELETE FROM message_days WHERE guild_id=? AND day<?", (guild_id, day))
    c.commit(); c.close()

def has_scan_progress(guild_id):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT 1 FROM scan_progress WHERE guild_id=? LIMIT 1", (guild_id,))
    row = cur.fetchone(); c.close()
    return row is not None

def clear_messages(guild_id):
    """Wipe all counted rows for a guild (used once, before the first
    clean scan, to drop counts polluted by older scan versions)."""
    c = _conn()
    c.execute("DELETE FROM message_days WHERE guild_id=?", (guild_id,))
    c.commit(); c.close()

def get_message_stats(guild_id, user_id, now=None):
    from datetime import datetime, timezone, timedelta
    now = now or datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    # This week = Monday-Sunday calendar week (UTC)
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")
    year_start = now.strftime("%Y-01-01")
    c=_conn(); cur=c.cursor()
    def _sum(day_from):
        cur.execute("SELECT COALESCE(SUM(count),0) FROM message_days WHERE guild_id=? AND user_id=? AND day>=?",
                    (guild_id, user_id, day_from))
        return cur.fetchone()[0]
    total = _sum("0000-01-01")
    stats = {
        "total": total,
        "today": _sum(today),
        "week": _sum(week_start),
        "month": _sum(month_start),
        "year": _sum(year_start),
        "week_start": week_start,
    }
    c.close(); return stats

def add_censored_word(guild_id, word):
    c = _conn(); cur = c.cursor()
    cur.execute("INSERT OR IGNORE INTO censored_words VALUES (?, ?)", (guild_id, word.lower().strip()))
    c.commit(); c.close()

def remove_censored_word(guild_id, word):
    c = _conn(); cur = c.cursor()
    cur.execute("DELETE FROM censored_words WHERE guild_id=? AND word=?", (guild_id, word.lower().strip()))
    c.commit(); c.close()

def list_censored_words(guild_id):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT word FROM censored_words WHERE guild_id=? ORDER BY word", (guild_id,)).fetchall()
    c.close()
    return [r["word"] for r in rows]

def guild_stats(guild_id):
    """Live server activity from the bot's own database."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    c = _conn(); cur = c.cursor()
    def one(q, args=()):
        cur.execute(q, args)
        return cur.fetchone()[0]
    stats = {
        "messages_total": one("SELECT COALESCE(SUM(count),0) FROM message_days WHERE guild_id=?", (guild_id,)),
        "messages_today": one("SELECT COALESCE(SUM(count),0) FROM message_days WHERE guild_id=? AND day=?", (guild_id, today)),
        "messages_week": one("SELECT COALESCE(SUM(count),0) FROM message_days WHERE guild_id=? AND day>=?", (guild_id, week_start)),
        "open_tickets": one("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND status='open'", (guild_id,)),
        "tickets_total": one("SELECT COUNT(*) FROM tickets WHERE guild_id=?", (guild_id,)),
        "ratings_total": one("SELECT COUNT(*) FROM ratings WHERE guild_id=?", (guild_id,)),
        "ratings_avg": one("SELECT COALESCE(ROUND(AVG(stars),1),0) FROM ratings WHERE guild_id=?", (guild_id,)),
        "pending_apps": one("SELECT COUNT(*) FROM applications WHERE guild_id=? AND status='pending'", (guild_id,)),
        "loa_active": one("SELECT COUNT(*) FROM loa WHERE guild_id=? AND status='approved'", (guild_id,)),
        "warns_total": one("SELECT COUNT(*) FROM warns WHERE guild_id=?", (guild_id,)),
        "censored_words": one("SELECT COUNT(*) FROM censored_words WHERE guild_id=?", (guild_id,)),
    }
    c.close(); return stats

def top_messages(guild_id, limit=5):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT user_id, SUM(count) AS n FROM message_days WHERE guild_id=? GROUP BY user_id ORDER BY n DESC LIMIT ?", (guild_id, limit)).fetchall()
    c.close()
    return [{"user_id": r["user_id"], "n": r["n"]} for r in rows]

def recent_tickets(guild_id, limit=5):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT channel_id, owner_id, status FROM tickets WHERE guild_id=? ORDER BY channel_id DESC LIMIT ?", (guild_id, limit)).fetchall()
    c.close()
    return [{"channel_id": r["channel_id"], "owner_id": r["owner_id"], "status": r["status"]} for r in rows]

def add_ticket_menu(guild_id, title, placeholder=""):
    c = _conn(); cur = c.cursor()
    pos = cur.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM ticket_menus WHERE guild_id=?", (guild_id,)).fetchone()[0]
    cur.execute("INSERT INTO ticket_menus (guild_id, title, placeholder, position) VALUES (?,?,?,?)",
                (guild_id, title, placeholder, pos))
    c.commit(); mid = cur.lastrowid; c.close(); return mid

def list_ticket_menus(guild_id):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT * FROM ticket_menus WHERE guild_id=? ORDER BY position, id", (guild_id,)).fetchall()
    c.close(); return [dict(r) for r in rows]

def update_ticket_menu(menu_id, guild_id, title, placeholder=""):
    c = _conn(); cur = c.cursor()
    cur.execute("UPDATE ticket_menus SET title=?, placeholder=? WHERE id=? AND guild_id=?",
                (title, placeholder, menu_id, guild_id))
    c.commit(); c.close()

def update_ticket_template(template_id, guild_id, name, description="", menu_id=None, emoji=None, ticket_prefix=None, staff_role_id=None, panel_channel_id=None, category_id=None):
    c = _conn(); cur = c.cursor()
    cur.execute("""UPDATE ticket_templates SET name=?, description=?, menu_id=?, emoji=?,
                   ticket_prefix=?, staff_role_id=?, panel_channel_id=?, category_id=?
                   WHERE id=? AND guild_id=?""",
                (name, description, menu_id, emoji, ticket_prefix, staff_role_id, panel_channel_id, category_id, template_id, guild_id))
    c.commit(); c.close()

def delete_ticket_menu(menu_id, guild_id):
    c = _conn(); cur = c.cursor()
    cur.execute("DELETE FROM ticket_menus WHERE id=? AND guild_id=?", (menu_id, guild_id))
    cur.execute("UPDATE ticket_templates SET menu_id=NULL WHERE menu_id=? AND guild_id=?", (menu_id, guild_id))
    c.commit(); c.close()

def ensure_ticket_menus(guild_id):
    """Every template belongs to a menu. Templates made before menus
    existed get moved into a default first menu automatically."""
    menus = list_ticket_menus(guild_id)
    if not menus:
        mid = add_ticket_menu(guild_id, "What do you need help with?", "What do you need help with? Pick one...")
        menus = list_ticket_menus(guild_id)
    first = menus[0]["id"]
    c = _conn(); cur = c.cursor()
    cur.execute("UPDATE ticket_templates SET menu_id=? WHERE guild_id=? AND menu_id IS NULL", (first, guild_id))
    c.commit(); c.close()
    return list_ticket_menus(guild_id)

def add_ticket_template(guild_id, name, description="", staff_role_id=None, panel_channel_id=None, category_id=None, menu_id=None, emoji=None, ticket_prefix=None):
    c = _conn(); cur = c.cursor()
    cur.execute("INSERT INTO ticket_templates (guild_id, name, description, staff_role_id, panel_channel_id, category_id, menu_id, emoji, ticket_prefix) VALUES (?,?,?,?,?,?,?,?,?)",
                (guild_id, name, description, staff_role_id, panel_channel_id, category_id, menu_id, emoji, ticket_prefix))
    c.commit(); tid = cur.lastrowid; c.close(); return tid

def list_ticket_templates(guild_id):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT * FROM ticket_templates WHERE guild_id=? ORDER BY id", (guild_id,)).fetchall()
    c.close(); return [dict(r) for r in rows]

def get_ticket_template(template_id, guild_id):
    c = _conn(); cur = c.cursor()
    r = cur.execute("SELECT * FROM ticket_templates WHERE id=? AND guild_id=?", (template_id, guild_id)).fetchone()
    c.close(); return dict(r) if r else None

def delete_ticket_template(template_id, guild_id):
    c = _conn(); cur = c.cursor()
    cur.execute("DELETE FROM ticket_templates WHERE id=? AND guild_id=?", (template_id, guild_id))
    c.commit(); c.close()

def count_warns(guild_id, user_id):
    c = _conn(); cur = c.cursor()
    cur.execute("SELECT COUNT(*) FROM warns WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    n = cur.fetchone()[0]; c.close(); return n

def add_application_template(guild_id, name, description="", role_id=None, review_channel_id=None, questions="[]", color=None, cooldown_days=None):
    c = _conn(); cur = c.cursor()
    cur.execute("INSERT INTO application_templates (guild_id, name, description, role_id, review_channel_id, questions, color, cooldown_days) VALUES (?,?,?,?,?,?,?,?)",
                (guild_id, name, description, role_id, review_channel_id, questions, color, cooldown_days))
    c.commit(); tid = cur.lastrowid; c.close(); return tid

def list_application_templates(guild_id):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT * FROM application_templates WHERE guild_id=? ORDER BY id", (guild_id,)).fetchall()
    c.close(); return [dict(r) for r in rows]

def get_application_template(template_id, guild_id):
    c = _conn(); cur = c.cursor()
    r = cur.execute("SELECT * FROM application_templates WHERE id=? AND guild_id=?", (template_id, guild_id)).fetchone()
    c.close(); return dict(r) if r else None

def update_application_template(template_id, guild_id, name, description="", role_id=None, review_channel_id=None, questions="[]", color=None, cooldown_days=None):
    c = _conn(); cur = c.cursor()
    cur.execute("""UPDATE application_templates SET name=?, description=?, role_id=?,
                   review_channel_id=?, questions=?, color=?, cooldown_days=?
                   WHERE id=? AND guild_id=?""",
                (name, description, role_id, review_channel_id, questions, color, cooldown_days, template_id, guild_id))
    c.commit(); c.close()

def delete_application_template(template_id, guild_id):
    c = _conn(); cur = c.cursor()
    cur.execute("DELETE FROM application_templates WHERE id=? AND guild_id=?", (template_id, guild_id))
    c.commit(); c.close()

def add_message_template(guild_id, name, title="", content="", channel_id=None):
    c = _conn(); cur = c.cursor()
    cur.execute("INSERT INTO message_templates (guild_id, name, title, content, channel_id) VALUES (?,?,?,?,?)",
                (guild_id, name, title, content, channel_id))
    c.commit(); tid = cur.lastrowid; c.close(); return tid

def list_message_templates(guild_id):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT * FROM message_templates WHERE guild_id=? ORDER BY id", (guild_id,)).fetchall()
    c.close(); return [dict(r) for r in rows]

def get_message_template(template_id, guild_id):
    c = _conn(); cur = c.cursor()
    r = cur.execute("SELECT * FROM message_templates WHERE id=? AND guild_id=?", (template_id, guild_id)).fetchone()
    c.close(); return dict(r) if r else None

def delete_message_template(template_id, guild_id):
    c = _conn(); cur = c.cursor()
    cur.execute("DELETE FROM message_templates WHERE id=? AND guild_id=?", (template_id, guild_id))
    c.commit(); c.close()

def add_auto_reply(guild_id, trigger, response):
    c = _conn(); cur = c.cursor()
    cur.execute("INSERT INTO auto_replies (guild_id, trigger, response) VALUES (?,?,?)",
                (guild_id, trigger.lower().strip(), response))
    c.commit(); tid = cur.lastrowid; c.close(); return tid

def list_auto_replies(guild_id):
    c = _conn(); cur = c.cursor()
    rows = cur.execute("SELECT * FROM auto_replies WHERE guild_id=? ORDER BY id", (guild_id,)).fetchall()
    c.close(); return [dict(r) for r in rows]

def delete_auto_reply(reply_id, guild_id):
    c = _conn(); cur = c.cursor()
    cur.execute("DELETE FROM auto_replies WHERE id=? AND guild_id=?", (reply_id, guild_id))
    c.commit(); c.close()
