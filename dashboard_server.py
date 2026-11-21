"""REAL dashboard server for Sunny's Best Friend.
This is the difference from the static website dashboard:
- That one was a static/private page, so it could only PRETEND to sign in.
- This one is a real Flask web server. It does real Discord OAuth2:
  Login -> Discord authorize -> Discord sends a code back -> this server
  exchanges the code (with the Client Secret, server-side only) for a
  token -> Discord tells it who you are and which servers you manage.
  Then it only shows you servers where YOU have Manage Server AND the
  bot is actually in that server. Settings here write to the SAME bot.db
  the bot reads, so they apply to the live bot.

Run locally:  python dashboard_server.py   (then open http://localhost:5000)
On Railway / Fly.io: this runs alongside bot.py (see start.sh).

Env vars needed (in .env or host dashboard, NEVER in chat / frontend):
  DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI
  e.g. DISCORD_REDIRECT_URI=https://your-app.up.railway.app/callback
  FLASK_SECRET_KEY=any random long string
In the Discord Developer Portal > OAuth2, add that exact Redirect URI.
"""
import os
from flask import Flask, redirect, request, session, render_template_string
import requests
import database

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-to-a-random-string")
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:5000/callback")
API = "https://discord.com/api/v10"

PAGE = """
<!doctype html><html><head><title>Sunny's Best Friend - Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
*{box-sizing:border-box}
body{font-family:Inter,"gg sans",system-ui,-apple-system,sans-serif;background:#1e1f22;color:#dbdee1;margin:0;line-height:1.5}
.topbar{background:#111214;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:12px 20px;position:sticky;top:0;z-index:10;border-bottom:1px solid #232428}
.topbar .brand{font-weight:800;font-size:17px}.topbar .brand small{color:#b5bac1;font-weight:400;margin-left:8px;font-size:13px}
.topbar a.signin{background:#5865f2;color:#fff;text-decoration:none;padding:8px 18px;border-radius:20px;font-weight:600;font-size:14px}
.topbar a.signin:hover{background:#4752c4}
.wrap{display:flex;min-height:calc(100vh - 57px)}
.sidebar{width:248px;background:#111214;padding:16px;flex-shrink:0}
.sidebar h2{margin:0;color:#fff;font-size:18px}.sidebar small{color:#b5bac1}
.sidebar .group{color:#949ba4;font-size:11px;font-weight:700;letter-spacing:1.2px;margin:26px 0 6px;text-transform:uppercase}
.sidebar a{display:flex;align-items:center;gap:8px;color:#b5bac1;text-decoration:none;padding:9px 12px;border-radius:8px;font-size:15px}
.sidebar a:hover{background:#1e1f22;color:#fff}
.sidebar a.active{background:#404249;color:#fff;font-weight:600}
.main{flex:1;padding:28px;max-width:980px}
.main h2{color:#fff;margin:0 0 4px;font-size:24px}
.main h3{color:#fff;margin:0 0 12px;font-size:17px}
.muted{color:#b5bac1;font-size:14px}
a{color:#949cf7}
.card{background:#2b2d31;border:1px solid #3f4147;padding:20px;border-radius:12px;margin:0 0 16px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:0 0 16px}
.stat{background:#2b2d31;border:1px solid #3f4147;border-radius:12px;padding:16px}
.stat .num{font-size:28px;font-weight:800;color:#fff;line-height:1.1}
.stat .lbl{color:#b5bac1;font-size:13px;margin-top:4px}
.rowline{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid #3f4147}
.rowline:last-child{border-bottom:0}
.rowline b{color:#fff}
.pill{display:inline-block;background:#5865f2;color:#fff;font-size:12px;font-weight:700;padding:2px 10px;border-radius:20px}
.pill.green{background:#248046}.pill.amber{background:#a87300}
button{background:#5865f2;color:#fff;border:0;padding:10px 18px;border-radius:8px;cursor:pointer;font-weight:600;font-size:14px}
button:hover{background:#4752c4}
button.danger{background:#ed4245}button.danger:hover{background:#c03537}
input,select,textarea{padding:10px 12px;border-radius:8px;border:1px solid #3f4147;background:#1e1f22;color:#fff;width:100%;margin:6px 0;font-size:14px;font-family:inherit}
input:focus,select:focus,textarea:focus{outline:2px solid #5865f2;border-color:#5865f2}
label{font-size:14px;font-weight:600;color:#dbdee1}
label small{color:#b5bac1;font-weight:400}
@media(max-width:700px){.wrap{flex-direction:column}.sidebar{width:100%}.main{padding:16px}}</style></head>
<body>
<div class="topbar"><div class="brand">☀️ Sunny's Best Friend <small>All-in-one Discord bot</small></div><a class="signin" href="/login">Sign in with Discord</a></div>
<div class="wrap">
<div class="sidebar">{{sidebar|safe}}</div><div class="main">{{body|safe}}</div></div></body></html>
"""

def _sidebar(guild_id=None, active="servers"):
    if not guild_id:
        return '<h2>Sunny\'s Best Friend</h2><small>Dashboard</small><div class="group">SERVERS</div><a href="/servers">🏠 Your servers</a><a href="/invite">➕ Add bot to a server</a>'
    d = f"/dashboard/{guild_id}"
    def a(path, label, key):
        cls = " class=\"active\"" if key == active else ""
        return f'<a href="{d}{path}"{cls}>{label}</a>'
    return ('<h2>Sunny\'s Best Friend</h2><small>Dashboard</small>'
        '<div class="group">SERVER</div><a href="/servers">← All servers</a>'
        + a("", "🏠 Overview", "settings")
        + '<div class="group">MODERATION</div>'
        + a("/moderation", "🛡️ Moderation", "moderation")
        + a("/ratings", "⭐ Staff ratings", "ratings")
        + '<div class="group">SUPPORT</div>'
        + a("/tickets", "🎫 Tickets", "tickets")
        + a("/loa", "📅 Leave (LOA)", "loa")
        + a("/applications", "📝 Applications", "applications")
        + '<div class="group">COMMUNITY</div>'
        + a("/community", "👋 Welcome & starboard", "community")
        + a("/messages", "💬 Messages", "messages")
        + '<div class="group">FAITH & FUN</div>'
        + a("/faith", "🙏 Daily verse & prayer", "faith")
        + '<div class="group">IN DISCORD</div>'
        '<p style="color:#b5bac1;font-size:13px">Tickets, LOA, strikes and applications are used in Discord with slash commands — /setup-tickets, /loa-request, /apply, /strike, /close.</p>')

def _render(body, guild_id=None, active="servers"):
    return render_template_string(PAGE, body=body, sidebar=_sidebar(guild_id, active))

def _guild_live(guild_id):
    """Member counts straight from Discord, using the bot token (server-side only)."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        return {}
    try:
        r = requests.get(f"{API}/guilds/{guild_id}?with_counts=true",
                         headers={"Authorization": f"Bot {token}"}, timeout=10)
        if r.ok:
            j = r.json()
            return {"members": j.get("approximate_member_count") or j.get("member_count"),
                    "online": j.get("approximate_presence_count"),
                    "name": j.get("name")}
    except Exception:
        pass
    return {}

def _api(token, path):
    r = requests.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    return r.json() if r.ok else None

def _can_access(guild_id):
    """Who can open a server's dashboard: anyone with Manage Server, or
    anyone with the server's staff role (checked through the bot).
    Everything in the dashboard is stored per server, so every staff
    member who opens it sees the same settings."""
    if any(int(g["id"]) == guild_id for g in session.get("guilds", [])):
        return True
    if guild_id in session.get("staff_guilds", []):
        return True
    # Staff-role check (cached in the session so it runs once per login)
    token = os.getenv("DISCORD_TOKEN")
    user = session.get("user") or {}
    staff_role = database.get_settings(guild_id).get("staff_role_id")
    if not token or not user.get("id") or not staff_role:
        return False
    try:
        r = requests.get(f"{API}/guilds/{guild_id}/members/{user['id']}",
                         headers={"Authorization": f"Bot {token}"}, timeout=10)
        if r.ok and int(staff_role) in [int(x) for x in (r.json().get("roles") or [])]:
            session.setdefault("staff_guilds", []).append(guild_id)
            session.modified = True
            return True
    except Exception:
        pass
    return False

def _accessible_guilds():
    """Manageable servers plus staff-role servers, for the server list."""
    out, seen = [], set()
    for g in session.get("guilds", []):
        out.append((g, "manager")); seen.add(int(g["id"]))
    for g in session.get("all_guilds", []):
        gid = int(g["id"])
        if gid in seen:
            continue
        if _can_access(gid):
            out.append((g, "staff")); seen.add(gid)
    return out

@app.route("/")
def home():
    if "user" in session:
        return redirect("/servers")
    return _render("""
    <div class="card"><p>This is the <b>real</b> dashboard. Sign in with Discord for real — no fake preview.</p>
    <a href="/login"><button>Sign in with Discord</button></a>
    <p style="color:#aaa">You will go to discord.com, approve it, and come back here. No password is ever asked for here.</p></div>""")

@app.route("/login")
def login():
    if not CLIENT_ID:
        return "Set DISCORD_CLIENT_ID in env vars first. See dashboard_server.py top.", 500
    url = (f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}"
           f"&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds")
    return redirect(url)

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code: return "No code from Discord.", 400
    r = requests.post(f"{API}/oauth2/token", data={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=10)
    if not r.ok: return f"Token exchange failed: {r.text}", 400
    token = r.json()["access_token"]
    user = _api(token, "/users/@me")
    guilds = _api(token, "/users/@me/guilds") or []
    # Servers where the user can Manage Server (0x20)
    manageable = [g for g in guilds if (int(g.get("permissions", 0)) & 0x20) == 0x20]
    session["user"] = user; session["token"] = token; session["guilds"] = manageable
    session["all_guilds"] = guilds; session["staff_guilds"] = []
    return redirect("/servers")

@app.route("/servers")
def servers():
    if "user" not in session: return redirect("/")
    u = session["user"]; rows = ""
    for g, kind in _accessible_guilds():
        tag = ' <span class="badge">Staff</span>' if kind == "staff" else ""
        rows += f'<div class="card"><b>{g["name"]}</b>{tag}<br><a href="/dashboard/{g["id"]}"><button>Manage this server</button></a> <a href="https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot%20applications.commands&permissions=8&guild_id={g["id"]}">Add bot here</a></div>'
    if not rows: rows = "<p>No servers where you manage the server or are staff. <a href='/invite'>Invite the bot to a server first</a>.</p>"
    return _render(f"""
    <div class="card">Signed in as <b>{u.get('username')}</b> — <a href="/logout">Sign out</a></div>
    <h2>Your servers</h2>{rows}
    <p><a href="/invite">+ Add Sunny's Best Friend to another server</a></p>""")

@app.route("/invite")
def invite():
    if not CLIENT_ID: return "Set DISCORD_CLIENT_ID first.", 500
    url = (f"https://discord.com/oauth2/authorize?client_id={CLIENT_ID}"
           "&scope=bot%20applications.commands&permissions=8")
    return redirect(url)

@app.route("/dashboard/<int:guild_id>", methods=["GET", "POST"])
def dashboard(guild_id):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "lookup":
            try:
                uid = int(request.form.get("user_id"))
            except Exception:
                return redirect(f"/dashboard/{guild_id}?lookup=bad")
            ms = database.get_message_stats(guild_id, uid)
            lvl = database.get_level(guild_id, uid)
            warns = database.count_warns(guild_id, uid)
            strikes = database.list_strikes(guild_id, uid)
            session["lookup"] = {"uid": uid, "messages": ms, "level": lvl, "warns": warns, "strikes": len(strikes)}
            return redirect(f"/dashboard/{guild_id}?lookup=ok")
        if action == "announce":
            token = os.getenv("DISCORD_TOKEN")
            ch = request.form.get("channel_id")
            text = (request.form.get("text") or "").strip()
            if token and ch and text:
                try:
                    requests.post(f"{API}/channels/{ch}/messages",
                        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                        json={"content": text}, timeout=10)
                except Exception:
                    pass
            return redirect(f"/dashboard/{guild_id}?announced=1")
        for key in ["faith_channel_id", "rating_log_channel_id", "welcome_channel_id", "starboard_channel_id", "ticket_category_id", "staff_role_id", "autorole_id", "log_channel_id", "panel_channel_id", "ticket_log_channel_id", "app_channel_id", "app_role_id", "app_panel_channel_id"]:
            v = request.form.get(key)
            if v: database.set_setting(guild_id, key, int(v))
        for key in ["ticket_panel_title", "ticket_panel_description"]:
            v = (request.form.get(key) or "").strip()
            if v: database.set_setting(guild_id, key, v[:200])
        v = (request.form.get("ticket_panel_color") or "").strip()
        if v:
            try: database.set_setting(guild_id, "ticket_panel_color", int(v, 0))
            except Exception: pass
        p = (request.form.get("prefix") or "").strip()
        if p and len(p) <= 3 and not any(c.isspace() for c in p):
            database.set_setting(guild_id, "prefix", p)
        nxt = request.form.get("next") or f"/dashboard/{guild_id}"
        return redirect(f"{nxt}?saved=1")
    s = database.get_settings(guild_id)
    saved = "<p>✅ Saved.</p>" if request.args.get("saved") else ""
    prefix = s.get("prefix") or "!"
    st = database.guild_stats(guild_id)
    live = _guild_live(guild_id)
    name = live.get("name") or f"Server {guild_id}"
    def user_list(rows, key="n", label=""):
        return "".join([f"<div class='rowline'><span>&lt;@{r['user_id']}&gt;</span><b>{r[key]} {label}</b></div>" for r in rows]) or "<p class='muted'>Nothing yet.</p>"
    top_msg = database.top_messages(guild_id)
    top_lvl = database.top_levels(guild_id)
    top_stf = database.top_staff(guild_id, 5)
    recent = database.recent_ratings(guild_id, 5)
    tickets = database.recent_tickets(guild_id)
    apps = database.list_applications(guild_id, "pending")[:5]
    feed = "".join([f"<div class='rowline'><span>⭐ <b>{r['staff_id']}</b> got {r['stars']}★</span><span class='muted'>from &lt;@{r['user_id']}&gt;</span></div>" for r in recent])
    feed += "".join([f"<div class='rowline'><span>🎫 Ticket &lt;#{t['channel_id']}&gt;</span><span class='pill'>{t['status']}</span></div>" for t in tickets])
    feed += "".join([f"<div class='rowline'><span>📝 Application from &lt;@{a['user_id']}&gt;</span><span class='pill amber'>pending</span></div>" for a in apps])
    lookup_html = ""
    lk = session.pop("lookup", None)
    if request.args.get("lookup") == "ok" and lk:
        lookup_html = f"""<div class="card"><h3>🔍 Member &lt;@{lk['uid']}&gt;</h3>
        <div class="rowline"><span>Messages</span><b>{lk['messages']['total']} total • {lk['messages']['today']} today</b></div>
        <div class="rowline"><span>Level</span><b>{lk['level'][1]} • {lk['level'][0]} XP</b></div>
        <div class="rowline"><span>Warns / Strikes</span><b>{lk['warns']} warns • {lk['strikes']} strikes</b></div></div>"""
    elif request.args.get("lookup") == "bad":
        lookup_html = "<div class='card'><p>⚠️ That didn't look like a user ID — copy it from Discord (right-click a member &gt; Copy User ID).</p></div>"
    announced = "<p>✅ Announcement sent.</p>" if request.args.get("announced") else ""
    return _render(f"""
    <div class="card"><a href="/servers">← Back to servers</a>{saved}{announced}
    <h2>{name}</h2>
    <p class="muted">Prefix: <b>{prefix}</b> • Numbers are live from what the bot has seen — messages only count from when the bot was added.</p></div>
    <div class="stats">
      <div class="stat"><div class="num">{live.get("members", "?")}</div><div class="lbl">Members</div></div>
      <div class="stat"><div class="num">{live.get("online", "?")}</div><div class="lbl">Online now</div></div>
      <div class="stat"><div class="num">{st["messages_today"]}</div><div class="lbl">Messages today</div></div>
      <div class="stat"><div class="num">{st["open_tickets"]}</div><div class="lbl">Open tickets</div></div>
      <div class="stat"><div class="num">{st["ratings_avg"]}★</div><div class="lbl">Avg rating ({st["ratings_total"]})</div></div>
      <div class="stat"><div class="num">{st["pending_apps"]}</div><div class="lbl">Applications waiting</div></div>
    </div>
    <div class="card"><h3>🕒 Recent activity</h3>{feed or "<p class='muted'>Nothing yet — activity shows up here as tickets open, ratings come in and applications arrive.</p>"}</div>
    {lookup_html}
    <div class="card"><h3>🔍 Look up a member</h3>
    <form method="post"><input type="hidden" name="action" value="lookup"><label>User ID <input name="user_id" placeholder="Discord user ID number"></label><button>Look up</button></form>
    <p class="muted">See their messages, level, warns and strikes.</p></div>
    <div class="card"><h3>📣 Send an announcement</h3>
    <form method="post"><input type="hidden" name="action" value="announce"><label>Channel ID <input name="channel_id" placeholder="Discord channel ID number"></label><label>Message <textarea name="text" rows="3" placeholder="Type your announcement..."></textarea></label><button>Send to Discord</button></form></div>
    <div class="card"><h3>🏆 Most active members</h3>{user_list(top_msg, "n", "messages")}</div>
    <div class="card"><h3>📈 Top levels</h3>{user_list(top_lvl, "xp", "XP")}</div>
    <div class="card"><h3>⭐ Top rated staff</h3>{user_list(top_stf, "avg", "★ average")}</div>
    <div class="card"><h3>⚙️ Quick settings</h3>
    <form method="post"><input type="hidden" name="next" value="/dashboard/{guild_id}"><label>Command prefix (1-3 characters, e.g. ! or ?)<input name="prefix" value="{prefix}" maxlength="3"></label><button>Save prefix</button></form></div>""", guild_id=guild_id, active="settings")
@app.route("/dashboard/<int:guild_id>/ratings")
def ratings_page(guild_id):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    top = database.top_staff(guild_id)
    rows = "".join([f'<div class="card"><b>{r["staff_id"]}</b> — ⭐ {r["avg"]} average, {r["n"]} rating(s)</div>' for r in top]) or "<p>No ratings yet — ratings appear here when a ticket closes and the owner rates support 1-5 stars.</p>"
    body = "<h2>⭐ Staff ratings</h2>" + rows + "<p>Check in Discord: /ratings, /leaderboard, /recent-ratings</p>"
    return _render(body, guild_id=guild_id, active="ratings")


def _section_form(guild_id, active, title, blurb, fields, commands):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    s = database.get_settings(guild_id)
    saved = "<p>✅ Saved.</p>" if request.args.get("saved") else ""
    inputs = "".join([f'<label>{label} <small>({key})</small><input name="{key}" value="{s.get(key, "")}" placeholder="Discord ID number"></label>' for key, label in fields])
    cmds = "<p><b>Used in Discord:</b> " + " • ".join(commands) + "</p>" if commands else ""
    body = f"""<div class="card"><a href="/dashboard/{guild_id}">← Overview</a>{saved}<h2>{title}</h2><p>{blurb}</p>
    <p>Enter Discord IDs (right-click a channel/role &gt; Copy ID, with Developer Mode on).</p>
    <form method="post" action="/dashboard/{guild_id}"><input type="hidden" name="next" value="/dashboard/{guild_id}/{active}">{inputs}<button>Save settings</button></form></div>
    <div class="card">{cmds}</div>"""
    return _render(body, guild_id=guild_id, active=active)

@app.route("/dashboard/<int:guild_id>/moderation")
def section_moderation(guild_id):
    return _section_form(guild_id, "moderation", "🛡️ Moderation",
        "Who can moderate, where mod actions get logged, and what new members get.",
        [("staff_role_id", "Staff role"), ("log_channel_id", "Mod log channel"), ("autorole_id", "Auto-role for new members")],
        ["/kick", "/ban", "/banlist", "/timeout", "/untimeout", "/warn", "/warns", "/strike", "/strikes", "/purge", "/slowmode", "/lock", "/unlock", "/add-word", "/remove-word", "/word-list", "/set-autorole", "/set-log-channel"])

def _guild_roles(guild_id):
    """Roles in the server, from Discord (bot token, server-side only)."""
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        return []
    try:
        r = requests.get(f"{API}/guilds/{guild_id}/roles",
                         headers={"Authorization": f"Bot {token}"}, timeout=10)
        if not r.ok:
            return []
        roles = [x for x in r.json() if int(x["id"]) != int(guild_id)]  # skip @everyone
        roles.sort(key=lambda x: x.get("position", 0), reverse=True)
        return roles
    except Exception:
        return []

def _role_checkboxes(guild_id, selected):
    """Tick the roles that can see/work a ticket type. Falls back to a
    text box of role IDs when Discord can't be reached."""
    roles = _guild_roles(guild_id)
    selected = set(selected or [])
    if not roles:
        return '<label>Role IDs that can see/work these tickets (comma-separated Discord IDs)<input name="role_ids_text" value="' + ",".join(str(x) for x in selected) + '" placeholder="e.g. 123456789, 987654321"></label>'
    boxes = "".join(
        f'<label style="display:block"><input type="checkbox" name="role_ids" value="{r["id"]}"{" checked" if int(r["id"]) in selected else ""}> {r["name"]}</label>'
        for r in roles)
    return '<label>Roles that can see/work these tickets</label>' + boxes + '<p class="muted">Leave all unticked to use the server staff role instead.</p>'

def _parse_role_ids(form):
    ids = []
    for v in form.getlist("role_ids"):
        try: ids.append(int(v))
        except Exception: pass
    if not ids:
        for v in (form.get("role_ids_text") or "").replace(";", ",").split(","):
            try: ids.append(int(v.strip()))
            except Exception: pass
    return ids or None

def _parse_color(form, default=5793266):
    v = (form.get("color") or "").strip()
    if not v:
        return default
    try:
        return int(v, 0)
    except Exception:
        return default

@app.route("/dashboard/<int:guild_id>/tickets", methods=["GET", "POST"])
def section_tickets(guild_id):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    s = database.get_settings(guild_id)
    msg = ""
    def _id(v):
        try: return int(v)
        except Exception: return None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_menu":
            title = (request.form.get("title") or "").strip()
            if title:
                database.ensure_ticket_menus(guild_id)
                database.add_ticket_menu(guild_id, title, (request.form.get("placeholder") or "").strip(),
                    questions=database.parse_question_lines(request.form.get("questions") or ""),
                    ticket_prefix=(request.form.get("ticket_prefix") or "").strip() or None,
                    emoji=(request.form.get("emoji") or "").strip() or None,
                    category_id=_id(request.form.get("category_id")),
                    role_ids=_parse_role_ids(request.form))
                msg = f"<p>✅ Ticket type '<b>{title}</b>' created — it shows up in the panel dropdown.</p>"
            else:
                msg = "<p>⚠️ Give the ticket type a name first.</p>"
        elif action == "edit_menu":
            title = (request.form.get("title") or "").strip()
            if title:
                database.update_ticket_menu(int(request.form.get("menu_id")), guild_id, title,
                    (request.form.get("placeholder") or "").strip(),
                    questions=database.parse_question_lines(request.form.get("questions") or ""),
                    ticket_prefix=(request.form.get("ticket_prefix") or "").strip() or None,
                    emoji=(request.form.get("emoji") or "").strip() or None,
                    category_id=_id(request.form.get("category_id")),
                    role_ids=_parse_role_ids(request.form))
                msg = f"<p>✅ Ticket type '<b>{title}</b>' updated.</p>"
            else:
                msg = "<p>⚠️ A ticket type needs a name.</p>"
        elif action == "delete_menu":
            database.delete_ticket_menu(int(request.form.get("menu_id")), guild_id)
            msg = "<p>✅ Ticket type deleted.</p>"
        elif action == "add_panel":
            title = (request.form.get("title") or "").strip() or "🎫 Need Help?"
            ch = _id(request.form.get("channel_id"))
            if ch:
                mids = [int(x) for x in request.form.getlist("panel_menu_ids") if x.isdigit()]
                database.add_ticket_panel(guild_id, title,
                    (request.form.get("description") or "").strip(),
                    _parse_color(request.form), ch, mids or None)
                msg = f"<p>✅ Panel '<b>{title}</b>' created — hit <b>Post / update</b> to put it in Discord.</p>"
            else:
                msg = "<p>⚠️ Pick the channel the panel goes in first.</p>"
        elif action == "edit_panel":
            title = (request.form.get("title") or "").strip() or "🎫 Need Help?"
            ch = _id(request.form.get("channel_id"))
            if ch:
                mids = [int(x) for x in request.form.getlist("panel_menu_ids") if x.isdigit()]
                database.update_ticket_panel(int(request.form.get("panel_id")), guild_id, title,
                    (request.form.get("description") or "").strip(),
                    _parse_color(request.form), ch, mids or None)
                msg = f"<p>✅ Panel '<b>{title}</b>' updated — hit <b>Post / update</b> to push it to Discord.</p>"
            else:
                msg = "<p>⚠️ Pick the channel the panel goes in first.</p>"
        elif action == "delete_panel":
            database.delete_ticket_panel(int(request.form.get("panel_id")), guild_id)
            msg = "<p>✅ Panel deleted.</p>"
        elif action == "post_panel":
            panel = database.get_ticket_panel(int(request.form.get("panel_id")), guild_id)
            msg = _post_ticket_panel(panel, guild_id) if panel else "<p>⚠️ That panel doesn't exist.</p>"
    menus = database.ensure_ticket_menus(guild_id)
    panels = database.list_ticket_panels(guild_id)
    roles = {int(r["id"]): r["name"] for r in _guild_roles(guild_id)}
    def _role_names(ids):
        if not ids:
            return "server staff role"
        return ", ".join(roles.get(i, str(i)) for i in ids)
    _panel_desc_default = ("Need help? Open a ticket below and our staff team will help you.\n\n"
        "**How it works**\n"
        "• Pick a ticket type from the menu below\n"
        "• Answer its questions, if it has any\n"
        "• A staff member will claim it and help you\n\n"
        "When your ticket closes, you'll be asked to rate your support 1–5 ⭐.")
    edit_menu_id = request.args.get("edit_menu")
    edit_panel_id = request.args.get("edit_panel")

    # --- panels ---
    prows = ""
    for p in panels:
        mids = database.panel_menu_ids(p)
        mnames = ", ".join(m["title"] for m in menus if not mids or m["id"] in mids) or "All ticket types"
        if edit_panel_id and str(p["id"]) == edit_panel_id:
            checks = "".join(
                f'<label style="display:block"><input type="checkbox" name="panel_menu_ids" value="{m["id"]}"{" checked" if (not mids or m["id"] in mids) else ""}> {m["title"]}</label>'
                for m in menus)
            prows += f"""<div class="card"><h3>✏️ Edit panel</h3>
            <form method="post"><input type="hidden" name="action" value="edit_panel"><input type="hidden" name="panel_id" value="{p['id']}">
            <label>Panel title<input name="title" value="{p.get('title') or ''}" maxlength="200"></label>
            <label>Panel description<textarea name="description" rows="3">{p.get('description') or ''}</textarea></label>
            <label>Panel color (hex, e.g. 0x5865F2)<input name="color" value="{hex(p.get('color') or 5793266)}" placeholder="0x5865F2"></label>
            <label>Channel ID<input name="channel_id" value="{p.get('channel_id') or ''}" placeholder="Discord ID number"></label>
            <label>Ticket types in this panel (untick all = every type)</label>{checks}
            <button>Save changes</button> <a href="/dashboard/{guild_id}/tickets"><button type="button">Cancel</button></a></form></div>"""
        else:
            prows += f"""<div class="card"><h3>📌 {p.get('title') or 'Panel'}</h3>
            <p>Channel: {p.get('channel_id') or '—'} • Types: {mnames}</p>
            <form method="post" style="display:inline"><input type="hidden" name="action" value="post_panel"><input type="hidden" name="panel_id" value="{p['id']}"><button>📣 Post / update in Discord</button></form>
            <a href="/dashboard/{guild_id}/tickets?edit_panel={p['id']}"><button type="button">✏️ Edit</button></a>
            <form method="post" style="display:inline"><input type="hidden" name="action" value="delete_panel"><input type="hidden" name="panel_id" value="{p['id']}"><button class="danger">Delete panel</button></form></div>"""
    prows = prows or "<p>No panels yet — make one below, then post it.</p>"
    pchecks = "".join(
        f'<label style="display:block"><input type="checkbox" name="panel_menu_ids" value="{m["id"]}" checked> {m["title"]}</label>'
        for m in menus)

    # --- menus (ticket types) ---
    mrows = ""
    for m in menus:
        qs = database.menu_questions(m)
        rids = database.menu_role_ids(m)
        if edit_menu_id and str(m["id"]) == edit_menu_id:
            mrows += f"""<div class="card"><h3>✏️ Edit ticket type</h3>
            <form method="post"><input type="hidden" name="action" value="edit_menu"><input type="hidden" name="menu_id" value="{m['id']}">
            <label>Name — shows in the panel dropdown<input name="title" value="{m['title']}" maxlength="100"></label>
            <label>Description — the smaller grey text under the name<input name="placeholder" value="{m.get('placeholder') or ''}" maxlength="100"></label>
            <label>Emoji (one emoji, e.g. 🎫)<input name="emoji" value="{m.get('emoji') or ''}" maxlength="10"></label>
            <label>Ticket channel name (e.g. support, so channels are named support-username)<input name="ticket_prefix" value="{m.get('ticket_prefix') or ''}" maxlength="30"></label>
            <label>Category ID (optional — where ticket channels go)<input name="category_id" value="{m.get('category_id') or ''}" placeholder="Discord ID number"></label>
            <label>Questions — one per line: Question | short/long | required/optional (max 5, asked before the ticket opens)<textarea name="questions" rows="4">{database.format_question_lines(qs)}</textarea></label>
            {_role_checkboxes(guild_id, rids)}
            <button>Save changes</button> <a href="/dashboard/{guild_id}/tickets"><button type="button">Cancel</button></a></form></div>"""
        else:
            mrows += f"""<div class="card"><h3>{m.get('emoji') or '🎫'} {m['title']}</h3>
            <p>{m.get('placeholder') or 'No description.'}</p>
            <p>Ticket name: <b>{m.get('ticket_prefix') or 'ticket-' + m['title'].lower().replace(' ', '-')}</b>-username • Questions: {len(qs)} • Roles: {_role_names(rids)} • Category: {m.get('category_id') or 'server default'}</p>
            <a href="/dashboard/{guild_id}/tickets?edit_menu={m['id']}"><button type="button">✏️ Edit</button></a>
            <form method="post" style="display:inline"><input type="hidden" name="action" value="delete_menu"><input type="hidden" name="menu_id" value="{m['id']}"><button class="danger">Delete</button></form></div>"""
    body = f"""<div class="card"><a href="/dashboard/{guild_id}">← Overview</a>{msg}<h2>🎫 Tickets</h2>
    <p>One dropdown per panel, and its options are the <b>ticket types</b> below — like Support, Partnership or Report. Picking one opens a ticket named for that type (support-username, partnership-username...) and asks its questions first, if it has any. Only the roles you pick for that type can see and work its tickets. You can have <b>more than one panel</b> — put different types in different channels. When a ticket closes, the owner rates it 1-5 ⭐.</p></div>
    <div class="card"><h3>Your panels</h3>{prows}</div>
    <div class="card"><h3>＋ New panel</h3>
    <form method="post"><input type="hidden" name="action" value="add_panel">
    <label>Panel title<input name="title" placeholder="e.g. 🎫 Need Help?" maxlength="200"></label>
    <label>Panel description<textarea name="description" rows="3">{_panel_desc_default}</textarea></label>
    <label>Panel color (hex, e.g. 0x5865F2)<input name="color" value="0x5865F2" placeholder="0x5865F2"></label>
    <label>Channel ID<input name="channel_id" placeholder="Discord ID number"></label>
    <label>Ticket types in this panel (untick all = every type)</label>{pchecks}
    <button>Create panel</button></form></div>
    <div class="card"><h3>Your ticket types</h3>{mrows}</div>
    <div class="card"><h3>＋ New ticket type</h3>
    <form method="post"><input type="hidden" name="action" value="add_menu">
    <label>Name — shows in the panel dropdown<input name="title" placeholder="e.g. Partnership" maxlength="100"></label>
    <label>Description — the smaller grey text under the name<input name="placeholder" placeholder="e.g. Partner with our server" maxlength="100"></label>
    <label>Emoji (one emoji, e.g. 🤝)<input name="emoji" placeholder="🤝" maxlength="10"></label>
    <label>Ticket channel name (e.g. partnership, so channels are named partnership-username)<input name="ticket_prefix" placeholder="partnership" maxlength="30"></label>
    <label>Category ID (optional — where ticket channels go)<input name="category_id" placeholder="Discord ID number"></label>
    <label>Questions — one per line: Question | short/long | required/optional (max 5, asked before the ticket opens)<textarea name="questions" rows="4" placeholder="What is your server name? | short | required&#10;Why do you want to partner? | long | required"></textarea></label>
    {_role_checkboxes(guild_id, [])}
    <button>Create ticket type</button></form>
    <p>Enter Discord IDs (right-click a channel/role &gt; Copy ID, with Developer Mode on).</p></div>
    <div class="card"><h3>Server ticket settings</h3>
    <form method="post" action="/dashboard/{guild_id}"><input type="hidden" name="next" value="/dashboard/{guild_id}/tickets">
    <label>Staff role ID <input name="staff_role_id" value="{s.get('staff_role_id') or ''}" placeholder="Discord ID number"></label>
    <label>Ticket category ID <input name="ticket_category_id" value="{s.get('ticket_category_id') or ''}" placeholder="Discord ID number"></label>
    <label>Rating log channel ID <input name="rating_log_channel_id" value="{s.get('rating_log_channel_id') or ''}" placeholder="Discord ID number"></label>
    <label>Ticket log channel ID <input name="ticket_log_channel_id" value="{s.get('ticket_log_channel_id') or ''}" placeholder="Discord ID number"></label>
    <button>Save settings</button></form>
    <p><b>Used in Discord:</b> /setup-tickets • /close • /claim • /add • /remove • /ratings • /leaderboard • /recent-ratings</p></div>"""
    return _render(body, guild_id=guild_id, active="tickets")

def _post_ticket_panel(panel, guild_id):
    """Post (or update in place) one ticket panel, using the bot token
    (server-side only). One dropdown, whose options are the panel's
    ticket types."""
    if not panel:
        return "<p>⚠️ That panel doesn't exist.</p>"
    token = os.getenv("DISCORD_TOKEN")
    channel_id = panel.get("channel_id")
    if not token:
        return "<p>⚠️ Bot token isn't set on the host, so the panel can't be posted from here — use /setup-tickets in Discord instead.</p>"
    if not channel_id:
        return "<p>⚠️ Set the panel's channel first, then post it.</p>"
    menus = database.ensure_ticket_menus(guild_id)
    wanted = database.panel_menu_ids(panel)
    if wanted:
        menus = [m for m in menus if m["id"] in wanted]
    options = []
    for m in menus:
        o = {"label": m["title"][:100], "value": f"menu_{m['id']}", "description": (m.get("placeholder") or "")[:100]}
        if m.get("emoji") and len(m["emoji"]) <= 4:
            o["emoji"] = {"name": m["emoji"]}
        options.append(o)
    if not options:
        return "<p>⚠️ This panel has no ticket types in it — add one first.</p>"
    title = panel.get("title") or "🎫 Need Help?"
    desc = panel.get("description") or ("Need help? Open a ticket below and our staff team will help you.\n\n"
        "**How it works**\n"
        "• Pick a ticket type from the menu below\n"
        "• Answer its questions, if it has any\n"
        "• A staff member will claim it and help you\n\n"
        "When your ticket closes, you'll be asked to rate your support 1–5 ⭐.")
    color = panel.get("color") or 5793266
    payload = {"embeds": [{"title": title, "description": desc, "color": color,
                           "footer": {"text": "Sunny's Best Friend • Ticket System"}}],
               "components": [{"type": 1, "components": [{"type": 3, "custom_id": "ticket_panel_select",
                               "placeholder": (title or "Pick a ticket type...")[:100], "options": options}]}]}
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    if panel.get("message_id"):
        try:
            r = requests.patch(f"{API}/channels/{channel_id}/messages/{panel['message_id']}",
                               headers=headers, json=payload, timeout=10)
            if r.ok:
                return "<p>✅ Panel updated in Discord.</p>"
        except Exception:
            pass  # message was deleted — fall through and post a fresh one
    try:
        r = requests.post(f"{API}/channels/{channel_id}/messages",
                          headers=headers, json=payload, timeout=10)
    except Exception as e:
        return f"<p>⚠️ Couldn't post the panel: {e}</p>"
    if not r.ok:
        return f"<p>⚠️ Discord said no: {r.text[:200]}</p>"
    msg_id = (r.json() or {}).get("id")
    if msg_id:
        try:
            database.update_ticket_panel(panel["id"], guild_id, panel.get("title"), panel.get("description"),
                                         panel.get("color"), panel.get("channel_id"),
                                         database.panel_menu_ids(panel) or None, message_id=int(msg_id))
        except Exception:
            pass
    return "<p>✅ Ticket panel posted in Discord.</p>"

@app.route("/dashboard/<int:guild_id>/applications", methods=["GET", "POST"])
def section_applications(guild_id):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    s = database.get_settings(guild_id)
    msg = ""
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_template":
            name = (request.form.get("name") or "").strip()
            if name:
                def _id(v):
                    try: return int(v)
                    except Exception: return None
                qs = []
                for line in (request.form.get("questions") or "").splitlines():
                    line = line.strip()
                    if not line: continue
                    parts = [p.strip() for p in line.split("|")]
                    qs.append({"label": parts[0][:45],
                               "style": "paragraph" if len(parts) > 1 and parts[1].lower().startswith("long") else "short",
                               "required": not (len(parts) > 2 and parts[2].lower().startswith("opt")),
                               "max_length": 500 if len(parts) > 1 and parts[1].lower().startswith("long") else 200})
                import json as _json
                def _color(v):
                    try: return int(v, 0)
                    except Exception: return None
                def _days(v):
                    try: return int(v)
                    except Exception: return None
                database.add_application_template(guild_id, name,
                    request.form.get("description") or "",
                    _id(request.form.get("role_id")),
                    _id(request.form.get("review_channel_id")),
                    _json.dumps(qs[:5]),
                    _color(request.form.get("color")),
                    _days(request.form.get("cooldown_days")))
                msg = f"<p>✅ Template '<b>{name}</b>' created with {len(qs[:5])} question(s).</p>"
            else:
                msg = "<p>⚠️ Give the template a name first.</p>"
        elif action == "edit_template":
            name = (request.form.get("name") or "").strip()
            if name:
                def _id(v):
                    try: return int(v)
                    except Exception: return None
                qs = []
                for line in (request.form.get("questions") or "").splitlines():
                    line = line.strip()
                    if not line: continue
                    parts = [p.strip() for p in line.split("|")]
                    qs.append({"label": parts[0][:45],
                               "style": "paragraph" if len(parts) > 1 and parts[1].lower().startswith("long") else "short",
                               "required": not (len(parts) > 2 and parts[2].lower().startswith("opt")),
                               "max_length": 500 if len(parts) > 1 and parts[1].lower().startswith("long") else 200})
                import json as _json
                def _color(v):
                    try: return int(v, 0)
                    except Exception: return None
                def _days(v):
                    try: return int(v)
                    except Exception: return None
                database.update_application_template(int(request.form.get("template_id")), guild_id, name,
                    request.form.get("description") or "",
                    _id(request.form.get("role_id")),
                    _id(request.form.get("review_channel_id")),
                    _json.dumps(qs[:5]),
                    _color(request.form.get("color")),
                    _days(request.form.get("cooldown_days")))
                msg = f"<p>✅ Template '<b>{name}</b>' updated.</p>"
            else:
                msg = "<p>⚠️ Give the template a name first.</p>"
        elif action == "delete_template":
            database.delete_application_template(int(request.form.get("template_id")), guild_id)
            msg = "<p>✅ Template deleted.</p>"
        elif action == "post_panel":
            msg = _post_application_panel(guild_id, s)
        elif action == "decide":
            app_id = int(request.form.get("app_id"))
            approve = request.form.get("decision") == "approve"
            app = database.get_application(app_id)
            if app and app["status"] == "pending":
                database.set_application_status(app_id, "approved" if approve else "denied")
                token = os.getenv("DISCORD_TOKEN")
                tpl = database.get_application_template(app.get("template_id"), guild_id) if app.get("template_id") else None
                role_id = (tpl or {}).get("role_id") or s.get("app_role_id")
                review_id = (tpl or {}).get("review_channel_id") or s.get("app_channel_id")
                if token:
                    if approve and role_id:
                        try: requests.put(f"{API}/guilds/{guild_id}/members/{app['user_id']}/roles/{role_id}", headers={"Authorization": f"Bot {token}"}, timeout=10)
                        except Exception: pass
                    if review_id:
                        try: requests.post(f"{API}/channels/{review_id}/messages", headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                            json={"content": f"Application #{app_id} from <@{app['user_id']}> was **{'✅ Approved' if approve else '❌ Denied'}** from the dashboard."}, timeout=10)
                        except Exception: pass
                msg = f"<p>✅ Application #{app_id} {'approved' if approve else 'denied'}.</p>"
            else:
                msg = "<p>⚠️ That application was already decided.</p>"
    templates = database.list_application_templates(guild_id)
    import json as _json
    edit_app_id = request.args.get("edit_template")
    trows = ""
    for t in templates:
        try: qs = _json.loads(t.get("questions") or "[]")
        except Exception: qs = []
        qlist = "".join([f"<div class='rowline'><span>{q.get('label')}</span><span class='muted'>{'long answer' if q.get('style') == 'paragraph' else 'short answer'}{' • optional' if not q.get('required') else ''}</span></div>" for q in qs]) or "<p class='muted'>Built-in staff questions.</p>"
        if edit_app_id and str(t["id"]) == edit_app_id:
            qlines = "\n".join([f"{q.get('label')} | {'long' if q.get('style') == 'paragraph' else 'short'} | {'required' if q.get('required') else 'optional'}" for q in qs])
            trows += f"""<div class="card"><h3>✏️ Edit template</h3>
            <form method="post"><input type="hidden" name="action" value="edit_template"><input type="hidden" name="template_id" value="{t['id']}">
            <label>Template name<input name="name" value="{t['name']}" maxlength="100"></label>
            <label>Description<input name="description" value="{t.get('description') or ''}" maxlength="200"></label>
            <label>Questions — one per line: <small>Question | short or long | required or optional</small><textarea name="questions" rows="4">{qlines}</textarea></label>
            <label>Role ID given on approval<input name="role_id" value="{t.get('role_id') or ''}" placeholder="Discord ID number"></label>
            <label>Review channel ID<input name="review_channel_id" value="{t.get('review_channel_id') or ''}" placeholder="Discord ID number"></label>
            <label>Embed color (hex, e.g. 0x5865F2)<input name="color" value="{hex(t.get('color')) if t.get('color') else ''}" placeholder="0x5865F2"></label>
            <label>Cooldown in days<input name="cooldown_days" value="{t.get('cooldown_days') or ''}" placeholder="e.g. 7"></label>
            <button>Save changes</button> <a href="/dashboard/{guild_id}/applications"><button type="button">Cancel</button></a></form></div>"""
        else:
            trows += f"""<div class="card"><h3>📝 {t['name']}</h3><p class="muted">{t.get('description') or ''}</p>
            <p>Role on approval: {t.get('role_id') or 'server default'} • Review channel: {t.get('review_channel_id') or 'server default'} • Cooldown: {t.get('cooldown_days') or 'none'} day(s) • Color: {hex(t.get('color')) if t.get('color') else 'default'}</p>{qlist}
            <a href="/dashboard/{guild_id}/applications?edit_template={t['id']}"><button type="button">✏️ Edit</button></a>
            <form method="post" style="display:inline"><input type="hidden" name="action" value="delete_template"><input type="hidden" name="template_id" value="{t['id']}"><button class="danger">Delete template</button></form></div>"""
    pending = database.list_applications(guild_id, "pending")
    prows = ""
    for a in pending:
        try: ans = _json.loads(a.get("answers") or "{}")
        except Exception: ans = {}
        fields = "".join([f"<div class='rowline'><span>{k}</span><b>{str(v)[:120]}</b></div>" for k, v in ans.items()])
        prows += f"""<div class="card"><h3>Application #{a['id']} — &lt;@{a['user_id']}&gt;</h3>{fields}
        <form method="post" style="display:inline"><input type="hidden" name="action" value="decide"><input type="hidden" name="app_id" value="{a['id']}"><input type="hidden" name="decision" value="approve"><button>✅ Approve</button></form>
        <form method="post" style="display:inline"><input type="hidden" name="action" value="decide"><input type="hidden" name="app_id" value="{a['id']}"><input type="hidden" name="decision" value="deny"><button class="danger">❌ Deny</button></form></div>"""
    body = f"""<div class="card"><a href="/dashboard/{guild_id}">← Overview</a>{msg}<h2>📝 Applications</h2>
    <p>Build application forms here — each template is its own application (Staff, Moderator, Event Team...), with its own questions, its own role on approval, its own review channel, its own color, and a cooldown so people can't spam applications. Post an application panel and members pick what to apply for from a dropdown, just like tickets. You can approve or deny pending applications right here too.</p>
    <form method="post"><input type="hidden" name="action" value="post_panel"><button>📣 Post / update the application panel in Discord</button></form>
    <p>Posts a panel with a dropdown of your application types to the panel channel in Server defaults below.</p></div>
    <div class="card"><h3>⏳ Waiting for review ({len(pending)})</h3>{prows or "<p class='muted'>No pending applications.</p>"}</div>
    <h3>Your application templates</h3>{trows or "<p class='muted'>No templates yet — members use the built-in staff form until you make one.</p>"}
    <div class="card"><h3>＋ New template</h3>
    <form method="post"><input type="hidden" name="action" value="add_template">
    <label>Template name (e.g. Staff, Moderator, Event Team)<input name="name" placeholder="Staff" maxlength="100"></label>
    <label>Description<input name="description" placeholder="What is this application for?" maxlength="200"></label>
    <label>Questions — one per line: <small>Question | short or long | required or optional</small><textarea name="questions" rows="4" placeholder="Why do you want this role? | long | required&#10;Any experience? | long | optional&#10;How active can you be? | short | required"></textarea></label>
    <p class="muted">Max 5 questions (Discord's limit). Leave the questions box empty to use the built-in staff questions.</p>
    <label>Role ID given on approval (optional)<input name="role_id" placeholder="Discord ID number"></label>
    <label>Review channel ID (optional — where applications go)<input name="review_channel_id" placeholder="Discord ID number"></label>
    <label>Embed color (hex, e.g. 0x5865F2)<input name="color" placeholder="0x5865F2"></label>
    <label>Cooldown in days (optional — how long before someone can apply for this again)<input name="cooldown_days" placeholder="e.g. 7"></label>
    <button>Create template</button></form></div>
    <div class="card"><h3>Server defaults</h3>
    <form method="post" action="/dashboard/{guild_id}"><input type="hidden" name="next" value="/dashboard/{guild_id}/applications">
    <label>Application channel ID <input name="app_channel_id" value="{s.get('app_channel_id') or ''}" placeholder="Discord ID number"></label>
    <label>Application panel channel ID <input name="app_panel_channel_id" value="{s.get('app_panel_channel_id') or ''}" placeholder="Discord ID number"></label>
    <label>Role given on approval <input name="app_role_id" value="{s.get('app_role_id') or ''}" placeholder="Discord ID number"></label>
    <button>Save defaults</button></form>
    <p><b>Used in Discord:</b> /setup-applications • /apply • /applications</p></div>"""
    return _render(body, guild_id=guild_id, active="applications")

def _post_application_panel(guild_id, s):
    """Post the application panel straight from the dashboard, using the bot token (server-side only)."""
    token = os.getenv("DISCORD_TOKEN")
    panel_channel = s.get("app_panel_channel_id") or s.get("app_channel_id")
    if not token:
        return "<p>⚠️ Bot token isn't set on the host, so the panel can't be posted from here.</p>"
    if not panel_channel:
        return "<p>⚠️ Set the application panel channel ID in Server defaults below first, then post the panel.</p>"
    templates = database.list_application_templates(guild_id)
    if not templates:
        return "<p>⚠️ Make an application template first, then post the panel.</p>"
    options = [{"label": t["name"][:100], "value": str(t["id"]), "description": (t.get("description") or "")[:100]} for t in templates]
    try:
        r = requests.post(f"{API}/channels/{panel_channel}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"embeds": [{"title": "📝 Applications", "description": "Want to join the team? Pick what you're applying for from the menu below and fill in the form.", "color": 5793266}],
                  "components": [{"type": 1, "components": [{"type": 3, "custom_id": "apply_template_select", "placeholder": "What are you applying for?", "options": options}]}]},
            timeout=10)
    except Exception as e:
        return f"<p>⚠️ Couldn't post the panel: {e}</p>"
    if r.ok:
        return "<p>✅ Application panel posted in Discord.</p>"
    return f"<p>⚠️ Discord said no: {r.text[:200]}</p>"

@app.route("/dashboard/<int:guild_id>/messages", methods=["GET", "POST"])
def section_messages(guild_id):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    s = database.get_settings(guild_id)
    msg = ""
    token = os.getenv("DISCORD_TOKEN")
    def _send(channel_id, title, content):
        if not token:
            return "<p>⚠️ Bot token isn't set on the host, so messages can't be sent from here.</p>"
        if not channel_id or not (content or "").strip():
            return "<p>⚠️ Pick a channel and write something first.</p>"
        payload = {"content": content}
        if (title or "").strip():
            payload = {"embeds": [{"title": title, "description": content, "color": 5793266}]}
        try:
            r = requests.post(f"{API}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                json=payload, timeout=10)
        except Exception as e:
            return f"<p>⚠️ Couldn't send: {e}</p>"
        return "<p>✅ Sent to Discord.</p>" if r.ok else f"<p>⚠️ Discord said no: {r.text[:200]}</p>"
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add_template":
            name = (request.form.get("name") or "").strip()
            if name:
                def _id(v):
                    try: return int(v)
                    except Exception: return None
                database.add_message_template(guild_id, name,
                    request.form.get("title") or "",
                    request.form.get("content") or "",
                    _id(request.form.get("channel_id")))
                msg = f"<p>✅ Template '<b>{name}</b>' saved.</p>"
            else:
                msg = "<p>⚠️ Give the template a name first.</p>"
        elif action == "delete_template":
            database.delete_message_template(int(request.form.get("template_id")), guild_id)
            msg = "<p>✅ Template deleted.</p>"
        elif action == "send_template":
            t = database.get_message_template(int(request.form.get("template_id")), guild_id)
            ch = request.form.get("channel_id") or (t.get("channel_id") if t else None)
            msg = _send(ch, t.get("title") if t else "", t.get("content") if t else "")
        elif action == "send_once":
            msg = _send(request.form.get("channel_id"), request.form.get("title"), request.form.get("content"))
        elif action == "add_reply":
            trig = (request.form.get("trigger") or "").strip()
            resp = (request.form.get("response") or "").strip()
            if trig and resp:
                database.add_auto_reply(guild_id, trig, resp)
                msg = f"<p>✅ Auto-reply added: when someone says <b>{trig}</b>, I'll reply.</p>"
            else:
                msg = "<p>⚠️ Fill in both the trigger and the reply.</p>"
        elif action == "delete_reply":
            database.delete_auto_reply(int(request.form.get("reply_id")), guild_id)
            msg = "<p>✅ Auto-reply deleted.</p>"
    templates = database.list_message_templates(guild_id)
    _ars = database.list_auto_replies(guild_id)
    arows = "".join([f"""<div class="rowline"><span>When someone says <b>{r['trigger']}</b> → {r['response'][:100]}</span>
        <form method="post"><input type="hidden" name="action" value="delete_reply"><input type="hidden" name="reply_id" value="{r['id']}"><button class="danger">Delete</button></form></div>""" for r in _ars]) or "<p class='muted'>No auto-replies yet.</p>"
    trows = ""
    for t in templates:
        trows += f"""<div class="card"><h3>💬 {t['name']}</h3>
        <p class="muted">{t.get('title') or 'No title'}</p><p>{t.get('content') or ''}</p>
        <p class="muted">Default channel: {t.get('channel_id') or 'none set'}</p>
        <form method="post"><input type="hidden" name="action" value="send_template"><input type="hidden" name="template_id" value="{t['id']}">
        <label>Send to channel ID (leave blank to use its default)<input name="channel_id" placeholder="Discord channel ID number"></label>
        <button>📣 Send this to Discord</button></form>
        <form method="post"><input type="hidden" name="action" value="delete_template"><input type="hidden" name="template_id" value="{t['id']}"><button class="danger">Delete template</button></form></div>"""
    body = f"""<div class="card"><a href="/dashboard/{guild_id}">← Overview</a>{msg}<h2>💬 Messages</h2>
    <p>Save messages as templates — rules, announcements, event posts, anything — then send any of them to any channel in your server, straight from here. A template with a title sends as a nice embed; without one it sends as a plain message.</p></div>
    <div class="card"><h3>✉️ Send a one-off message</h3>
    <form method="post"><input type="hidden" name="action" value="send_once">
    <label>Channel ID <input name="channel_id" placeholder="Discord channel ID number"></label>
    <label>Title (optional — makes it an embed)<input name="title" placeholder="e.g. Server Rules"></label>
    <label>Message <textarea name="content" rows="4" placeholder="Type your message..."></textarea></label>
    <button>📣 Send to Discord</button></form></div>
    <div class="card"><h3>🤖 Automatic replies</h3>
    <p class="muted">When someone's message contains the trigger, the bot replies with your response. @ the bot and it answers on its own too — prefix, help, tickets, applying.</p>
    {arows}
    <form method="post"><input type="hidden" name="action" value="add_reply">
    <label>Trigger — when someone says...<input name="trigger" placeholder="e.g. what time is the event"></label>
    <label>Reply<input name="response" placeholder="e.g. The event starts Friday at 7pm!"></label>
    <button>Add auto-reply</button></form></div>
    <h3>Your message templates</h3>{trows or "<p class='muted'>No templates yet.</p>"}
    <div class="card"><h3>＋ New template</h3>
    <form method="post"><input type="hidden" name="action" value="add_template">
    <label>Template name<input name="name" placeholder="e.g. Weekly announcement" maxlength="100"></label>
    <label>Title (optional)<input name="title" placeholder="e.g. This week's events" maxlength="200"></label>
    <label>Message <textarea name="content" rows="4" placeholder="Type the message..."></textarea></label>
    <label>Default channel ID (optional)<input name="channel_id" placeholder="Discord channel ID number"></label>
    <button>Save template</button></form></div>"""
    return _render(body, guild_id=guild_id, active="messages")

@app.route("/dashboard/<int:guild_id>/community", methods=["GET", "POST"])
def section_community(guild_id):
    if "user" not in session: return redirect("/")
    if not _can_access(guild_id):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    s = database.get_settings(guild_id)
    msg = ""
    if request.method == "POST":
        if request.form.get("action") == "test_welcome":
            token = os.getenv("DISCORD_TOKEN")
            ch = s.get("welcome_channel_id")
            tpl = s.get("welcome_message") or "👋 Welcome {user} to **{server}**!"
            if token and ch:
                try:
                    r = requests.post(f"{API}/channels/{ch}/messages",
                        headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
                        json={"content": tpl.replace("{user}", "a new member").replace("{server}", "your server")}, timeout=10)
                    msg = "<p>✅ Test welcome sent.</p>" if r.ok else f"<p>⚠️ Discord said no: {r.text[:200]}</p>"
                except Exception as e:
                    msg = f"<p>⚠️ Couldn't send: {e}</p>"
            else:
                msg = "<p>⚠️ Set the welcome channel below first.</p>"
        else:
            wm = (request.form.get("welcome_message") or "").strip()
            if wm:
                database.set_setting(guild_id, "welcome_message", wm)
            v = request.form.get("welcome_channel_id")
            if v: database.set_setting(guild_id, "welcome_channel_id", int(v))
            v = request.form.get("starboard_channel_id")
            if v: database.set_setting(guild_id, "starboard_channel_id", int(v))
            msg = "<p>✅ Saved.</p>"
            s = database.get_settings(guild_id)
    body = f"""<div class="card"><a href="/dashboard/{guild_id}">← Overview</a>{msg}<h2>👋 Welcome & starboard</h2>
    <p>Write your own welcome message — it posts automatically when someone joins. Use <b>{{user}}</b> for the new member and <b>{{server}}</b> for your server name.</p>
    <form method="post"><label>Welcome message<textarea name="welcome_message" rows="3" placeholder="👋 Welcome {{user}} to **{{server}}**! Open a ticket if you need help.">{s.get('welcome_message') or ''}</textarea></label>
    <label>Welcome channel ID <input name="welcome_channel_id" value="{s.get('welcome_channel_id') or ''}" placeholder="Discord ID number"></label>
    <label>Starboard channel ID <input name="starboard_channel_id" value="{s.get('starboard_channel_id') or ''}" placeholder="Discord ID number"></label>
    <button>Save welcome settings</button></form>
    <form method="post"><input type="hidden" name="action" value="test_welcome"><button>🧪 Send a test welcome</button></form></div>
    <div class="card"><p><b>Used in Discord:</b> /set-welcome • /set-starboard • /reaction-roles</p></div>"""
    return _render(body, guild_id=guild_id, active="community")

@app.route("/dashboard/<int:guild_id>/faith")
def section_faith(guild_id):
    return _section_form(guild_id, "faith", "🙏 Daily verse & prayer",
        "Where the daily Bible verse and prayer post at 9:00 AM Central.",
        [("faith_channel_id", "Faith channel")],
        ["/verse", "/dailyverse", "/prayer", "/pray", "/setup-faith", "/disable-faith"])

@app.route("/ping")
def ping():
    return "ok", 200

@app.route("/health")
def health():
    return {"status": "ok", "bot": "Sunny's Best Friend"}, 200

@app.route("/dashboard/<int:guild_id>/loa")
def loa_page(guild_id):
    if "user" not in session: return redirect("/")
    database.init_db()
    rows = database.list_loa(guild_id)
    body = "<h2>📅 Leave (LOA)</h2>" + "".join(
        [f'<div class="card"><b>{r["user_id"]}</b> — {r["status"]} — {r["days"]} day(s)<br>{r["reason"]}</div>' for r in rows]) or "<p>Nobody on LOA.</p>"
    body += "<p>Use in Discord: /loa-request, /loa-approve, /loa-deny, /loa-list, /loa-end</p>"
    return _render(body, guild_id=guild_id, active="loa")

@app.route("/logout")
def logout():
    session.clear(); return redirect("/")

if __name__ == "__main__":
    database.init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
