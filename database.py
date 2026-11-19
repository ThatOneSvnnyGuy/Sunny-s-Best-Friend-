"""SQLite storage for the all-in-one bot.
Ratings, tickets, levels, economy and warns all live here.
No fake data - everything starts empty.
"""
import sqlite3, time, os

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

def _conn():
    c = sqlite3.connect(DB_PATH)
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
    CREATE TABLE IF NOT EXISTS message_days (
        guild_id INTEGER, user_id INTEGER,
        day TEXT, -- YYYY-MM-DD (UTC)
        count INTEGER DEFAULT 0,
        PRIMARY KEY (guild_id, user_id, day)
    );
    """)
    c.commit()
    # Migrations for older bot.db files (new columns)
    for col in ["faith_channel_id INTEGER", "starboard_channel_id INTEGER", "app_channel_id INTEGER", "app_role_id INTEGER", "prefix TEXT DEFAULT '!'", "autorole_id INTEGER"]:
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
