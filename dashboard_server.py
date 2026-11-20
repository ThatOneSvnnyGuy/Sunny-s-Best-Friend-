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
<style>body{font-family:"gg sans",system-ui,sans-serif;background:#313338;color:#dbdee1;margin:0}
.topbar{background:#1e1f22;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:12px 20px}
.topbar .brand{font-weight:700}.topbar .brand small{color:#b5bac1;font-weight:400;margin-left:8px}
.topbar a.signin{background:#5865f2;color:#fff;text-decoration:none;padding:8px 16px;border-radius:4px;font-weight:600}
.wrap{display:flex;min-height:calc(100vh - 48px)}
.sidebar{width:264px;background:#2b2d31;padding:16px;flex-shrink:0}
.sidebar h2{margin:0;color:#fff}.sidebar small{color:#b5bac1}
.sidebar .group{color:#949ba4;font-size:12px;letter-spacing:1px;margin:24px 0 8px}
.sidebar a{display:block;color:#dbdee1;text-decoration:none;padding:8px 12px;border-radius:4px}
.sidebar a.active{background:#404249;color:#fff}
.main{flex:1;padding:24px;max-width:880px;background:#f2f3f5;color:#313338}
a{color:#5865f2}.card{background:#fff;border:1px solid #e3e5e8;padding:20px;border-radius:8px;margin:16px 0}
button{background:#5865f2;color:#fff;border:0;padding:10px 18px;border-radius:4px;cursor:pointer}
input,select{padding:8px;border-radius:4px;border:1px solid #e3e5e8;background:#fff;color:#313338;width:100%;margin:6px 0}
@media(max-width:700px){.wrap{flex-direction:column}.sidebar{width:100%}}</style></head>
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
    # Only servers where the user can Manage Server (0x20)
    manageable = [g for g in guilds if (int(g.get("permissions", 0)) & 0x20) == 0x20]
    session["user"] = user; session["token"] = token; session["guilds"] = manageable
    return redirect("/servers")

@app.route("/servers")
def servers():
    if "user" not in session: return redirect("/")
    u = session["user"]; rows = ""
    for g in session.get("guilds", []):
        rows += f'<div class="card"><b>{g["name"]}</b><br><a href="/dashboard/{g["id"]}"><button>Manage this server</button></a> <a href="https://discord.com/oauth2/authorize?client_id={CLIENT_ID}&scope=bot%20applications.commands&permissions=8&guild_id={g["id"]}">Add bot here</a></div>'
    if not rows: rows = "<p>No servers where you have Manage Server. <a href='/invite'>Invite the bot to a server first</a>.</p>"
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
    if not any(int(g["id"]) == guild_id for g in session.get("guilds", [])):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    if request.method == "POST":
        for key in ["faith_channel_id", "rating_log_channel_id", "welcome_channel_id", "starboard_channel_id", "ticket_category_id", "staff_role_id", "autorole_id", "log_channel_id", "panel_channel_id", "ticket_log_channel_id", "app_channel_id", "app_role_id"]:
            v = request.form.get(key)
            if v: database.set_setting(guild_id, key, int(v))
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
    def row(label, key):
        v = s.get(key) or "not set"
        return f"<p><b>{label}:</b> {v}</p>"
    def user_list(rows, key="n", label=""):
        return "".join([f"<p>&lt;@{r['user_id']}&gt; — {r[key]} {label}</p>" for r in rows]) or "<p>Nothing yet.</p>"
    top_msg = database.top_messages(guild_id)
    top_lvl = database.top_levels(guild_id)
    top_stf = database.top_staff(guild_id, 5)
    recent = database.recent_ratings(guild_id, 5)
    tickets = database.recent_tickets(guild_id)
    return _render(f"""
    <div class="card"><a href="/servers">← Back to servers</a>{saved}
    <h2>{name}</h2>
    <p><b>{live.get("members", "?")} members</b> • <b>{live.get("online", "?")} online now</b> • Prefix: <b>{prefix}</b></p>
    <p>Numbers below are live from what the bot has seen in your server — messages only count from when the bot was added.</p></div>
    <div class="card"><h3>📊 What's happening</h3>
    <p>💬 Messages: <b>{st["messages_total"]}</b> total • <b>{st["messages_today"]}</b> today • <b>{st["messages_week"]}</b> this week</p>
    <p>🎫 Tickets: <b>{st["open_tickets"]}</b> open • {st["tickets_total"]} total</p>
    <p>⭐ Ratings: <b>{st["ratings_avg"]}★</b> average from {st["ratings_total"]} rating(s)</p>
    <p>📝 Applications waiting: <b>{st["pending_apps"]}</b> • 📅 On leave: <b>{st["loa_active"]}</b> • ⚠️ Warns: <b>{st["warns_total"]}</b></p></div>
    <div class="card"><h3>🏆 Most active members</h3>{user_list(top_msg, "n", "messages")}</div>
    <div class="card"><h3>📈 Top levels</h3>{user_list(top_lvl, "xp", "XP")}</div>
    <div class="card"><h3>⭐ Top rated staff</h3>{user_list(top_stf, "avg", "★ average")}</div>
    <div class="card"><h3>🕒 Recent ratings</h3>{''.join([f"<p><b>{r['staff_id']}</b> got {r['stars']}★ from &lt;@{r['user_id']}&gt;</p>" for r in recent]) or "<p>No ratings yet.</p>"}</div>
    <div class="card"><h3>🎫 Recent tickets</h3>{''.join([f"<p>Ticket &lt;#{t['channel_id']}&gt; — &lt;@{t['owner_id']}&gt; — {t['status']}</p>" for t in tickets]) or "<p>No tickets yet.</p>"}</div>
    <div class="card"><h3>⚙️ Settings</h3>
    <form method="post"><input type="hidden" name="next" value="/dashboard/{guild_id}"><label>Command prefix (1-3 characters, e.g. ! or ?)<input name="prefix" value="{prefix}" maxlength="3"></label><button>Save prefix</button></form>
    <p>Change each section on the left: {row("Staff role", "staff_role_id")}{row("Panel channel", "panel_channel_id")}{row("Faith channel", "faith_channel_id")}</p></div>""", guild_id=guild_id, active="settings")
@app.route("/dashboard/<int:guild_id>/ratings")
def ratings_page(guild_id):
    if "user" not in session: return redirect("/")
    if not any(int(g["id"]) == guild_id for g in session.get("guilds", [])):
        return "You don't manage that server, or the bot isn't in it.", 403
    database.init_db()
    top = database.top_staff(guild_id)
    rows = "".join([f'<div class="card"><b>{r["staff_id"]}</b> — ⭐ {r["avg"]} average, {r["n"]} rating(s)</div>' for r in top]) or "<p>No ratings yet — ratings appear here when a ticket closes and the owner rates support 1-5 stars.</p>"
    body = "<h2>⭐ Staff ratings</h2>" + rows + "<p>Check in Discord: /ratings, /leaderboard, /recent-ratings</p>"
    return _render(body, guild_id=guild_id, active="ratings")


def _section_form(guild_id, active, title, blurb, fields, commands):
    if "user" not in session: return redirect("/")
    if not any(int(g["id"]) == guild_id for g in session.get("guilds", [])):
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

@app.route("/dashboard/<int:guild_id>/tickets", methods=["GET", "POST"])
def section_tickets(guild_id):
    if "user" not in session: return redirect("/")
    if not any(int(g["id"]) == guild_id for g in session.get("guilds", [])):
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
                database.add_ticket_template(guild_id, name,
                    request.form.get("description") or "",
                    _id(request.form.get("staff_role_id")),
                    _id(request.form.get("panel_channel_id")),
                    _id(request.form.get("category_id")))
                msg = f"<p>✅ Template '<b>{name}</b>' created.</p>"
            else:
                msg = "<p>⚠️ Give the template a name first.</p>"
        elif action == "delete_template":
            database.delete_ticket_template(int(request.form.get("template_id")), guild_id)
            msg = "<p>✅ Template deleted.</p>"
        elif action == "post_panel":
            msg = _post_ticket_panel(guild_id, s)
    templates = database.list_ticket_templates(guild_id)
    rows = "".join([f"""<div class="card"><h3>🎫 {t['name']}</h3>
        <p>{t.get('description') or 'No description.'}</p>
        <p>Staff role: {t.get('staff_role_id') or 'server default'} • Panel channel: {t.get('panel_channel_id') or 'server default'} • Category: {t.get('category_id') or 'server default'}</p>
        <form method="post"><input type="hidden" name="action" value="delete_template"><input type="hidden" name="template_id" value="{t['id']}"><button>Delete template</button></form></div>""" for t in templates]) or "<p>No templates yet — members see the built-in topics (General Help, Report a Player, Bug Report, Billing, Appeal, Something Else) until you add one.</p>"
    body = f"""<div class="card"><a href="/dashboard/{guild_id}">← Overview</a>{msg}<h2>🎫 Tickets</h2>
    <p>Make ticket templates here and they show up as the dropdown on your ticket panel — no Discord command needed. Each template can have its own staff role, panel channel and category. When a ticket closes, the owner rates it 1-5 ⭐.</p>
    <form method="post"><input type="hidden" name="action" value="post_panel"><button>📣 Post / update the ticket panel in Discord</button></form>
    <p>Posts the panel to the panel channel in your server settings (set it below). Run this after adding or deleting templates.</p></div>
    <div class="card"><h3>Your ticket templates</h3>{rows}</div>
    <div class="card"><h3>＋ New template</h3>
    <form method="post"><input type="hidden" name="action" value="add_template">
    <label>Template name (shows in the dropdown)<input name="name" placeholder="e.g. Report a Player" maxlength="100"></label>
    <label>Description<input name="description" placeholder="e.g. Report someone breaking the rules" maxlength="100"></label>
    <label>Staff role ID (optional — leave blank to use the server default)<input name="staff_role_id" placeholder="Discord ID number"></label>
    <label>Panel channel ID (optional)<input name="panel_channel_id" placeholder="Discord ID number"></label>
    <label>Category ID (optional — where ticket channels go)<input name="category_id" placeholder="Discord ID number"></label>
    <button>Create template</button></form>
    <p>Enter Discord IDs (right-click a channel/role &gt; Copy ID, with Developer Mode on).</p></div>
    <div class="card"><h3>Server ticket settings</h3>
    <form method="post" action="/dashboard/{guild_id}"><input type="hidden" name="next" value="/dashboard/{guild_id}/tickets">
    <label>Staff role ID <input name="staff_role_id" value="{s.get('staff_role_id') or ''}" placeholder="Discord ID number"></label>
    <label>Panel channel ID <input name="panel_channel_id" value="{s.get('panel_channel_id') or ''}" placeholder="Discord ID number"></label>
    <label>Ticket category ID <input name="ticket_category_id" value="{s.get('ticket_category_id') or ''}" placeholder="Discord ID number"></label>
    <label>Rating log channel ID <input name="rating_log_channel_id" value="{s.get('rating_log_channel_id') or ''}" placeholder="Discord ID number"></label>
    <label>Ticket log channel ID <input name="ticket_log_channel_id" value="{s.get('ticket_log_channel_id') or ''}" placeholder="Discord ID number"></label>
    <button>Save settings</button></form>
    <p><b>Used in Discord:</b> /setup-tickets • /close • /claim • /ratings • /leaderboard • /recent-ratings</p></div>"""
    return _render(body, guild_id=guild_id, active="tickets")

def _post_ticket_panel(guild_id, s):
    """Post the ticket panel straight from the dashboard, using the bot token (server-side only)."""
    token = os.getenv("DISCORD_TOKEN")
    panel_channel = s.get("panel_channel_id")
    if not token:
        return "<p>⚠️ Bot token isn't set on the host, so the panel can't be posted from here — use /setup-tickets in Discord instead.</p>"
    if not panel_channel:
        return "<p>⚠️ Set the panel channel ID below first, then post the panel.</p>"
    templates = database.list_ticket_templates(guild_id)
    if templates:
        options = [{"label": t["name"][:100], "value": f"tpl_{t['id']}", "description": (t.get("description") or "")[:100]} for t in templates]
    else:
        options = [{"label": "💬 General Help", "value": "general", "description": "I need help with something"},
                   {"label": "🚨 Report a Player", "value": "report", "description": "Report someone breaking the rules"},
                   {"label": "🐛 Bug Report", "value": "bug", "description": "Something in the server / bot is broken"},
                   {"label": "💳 Billing / Purchase", "value": "billing", "description": "Help with a purchase, order or payment"},
                   {"label": "⚖️ Appeal a Punishment", "value": "appeal", "description": "Appeal a ban, timeout or warning"},
                   {"label": "✨ Something Else", "value": "other", "description": "Anything that doesn't fit above"}]
    try:
        r = requests.post(f"{API}/channels/{panel_channel}/messages",
            headers={"Authorization": f"Bot {token}", "Content-Type": "application/json"},
            json={"embeds": [{"title": "🎫 Need Help?", "description": "Pick what you need help with from the menu below to open a support ticket.\n\nWhen your ticket closes, you'll rate your support 1-5 ⭐ - that rating counts toward staff leaderboards.", "color": 5793266}],
                  "components": [{"type": 1, "components": [{"type": 3, "custom_id": "ticket_topic_select", "placeholder": "What do you need help with? Pick one...", "options": options}]}]},
            timeout=10)
    except Exception as e:
        return f"<p>⚠️ Couldn't post the panel: {e}</p>"
    if r.ok:
        return "<p>✅ Ticket panel posted in Discord.</p>"
    return f"<p>⚠️ Discord said no: {r.text[:200]}</p>"

@app.route("/dashboard/<int:guild_id>/applications")
def section_applications(guild_id):
    return _section_form(guild_id, "applications", "📝 Applications",
        "Where applications are sent and which role approved applicants get.",
        [("app_channel_id", "Application channel"), ("app_role_id", "Role given on approval")],
        ["/setup-applications", "/apply", "/applications"])

@app.route("/dashboard/<int:guild_id>/community")
def section_community(guild_id):
    return _section_form(guild_id, "community", "👋 Welcome & starboard",
        "Where welcome messages and starred messages go.",
        [("welcome_channel_id", "Welcome channel"), ("starboard_channel_id", "Starboard channel")],
        ["/set-welcome", "/set-starboard", "/reaction-roles"])

@app.route("/dashboard/<int:guild_id>/faith")
def section_faith(guild_id):
    return _section_form(guild_id, "faith", "🙏 Daily verse & prayer",
        "Where the daily Bible verse and prayer post at 9:00 AM Central.",
        [("faith_channel_id", "Faith channel")],
        ["/verse", "/dailyverse", "/prayer", "/pray", "/set-faith-channel"])

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
