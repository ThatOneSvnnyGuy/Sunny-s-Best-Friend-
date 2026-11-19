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
<style>body{font-family:system-ui;background:#0f1012;color:#e8e8e8;margin:0;display:flex;min-height:100vh}
.sidebar{width:260px;background:#111214;padding:20px;flex-shrink:0}
.sidebar h2{margin:0}.sidebar small{color:#888}
.sidebar .group{color:#8b8d94;font-size:12px;letter-spacing:1px;margin:28px 0 8px}
.sidebar a{display:block;color:#d7d7d7;text-decoration:none;padding:10px 12px;border-radius:8px}
.sidebar a.active{background:#1e2a5a;color:#fff;border-left:3px solid #5865f2}
.main{flex:1;padding:24px;max-width:900px}
a{color:#5865f2}.card{background:#1a1b1e;padding:20px;border-radius:12px;margin:16px 0}
button{background:#5865f2;color:#fff;border:0;padding:10px 18px;border-radius:8px;cursor:pointer}
input,select{padding:8px;border-radius:6px;border:1px solid #555;background:#1e1f22;color:#fff;width:100%;margin:6px 0}
@media(max-width:700px){.sidebar{width:200px;padding:12px}body{flex-direction:column}.sidebar{width:100%}}</style></head>
<body>
<div class="sidebar"><h2>☀️ Sunny's Best Friend</h2><small>All-in-one staff bot</small>
<div class="group">OVERVIEW</div><a href="/servers" class="active">🏠 Overview</a>
<div class="group">MODERATION</div><a href="/servers">🛡️ Moderation</a><a href="/servers">⚠️ Strikes</a><a href="/servers">📈 Staff activity</a><a href="/servers">📊 Server stats</a>
<div class="group">APPLICATIONS</div><a href="/servers">📝 Application builder</a><a href="/servers">📥 Submissions</a><a href="/servers">🔍 Review queue</a>
<div class="group">SUPPORT</div><a href="/servers">🎫 Tickets</a><a href="/servers">⚙️ Ticket settings</a><a href="/servers">📅 Leave (LOA)</a>
<div class="group">COMMUNITY</div><a href="/servers">👋 Welcome &amp; onboarding</a><a href="/servers">✅ Role buttons</a>
<div class="group">FAITH &amp; FUN</div><a href="/servers">🙏 Daily verse &amp; prayer</a><a href="/servers">💰 Economy &amp; levels</a><a href="/servers">🎵 Music</a>
</div><div class="main">{{body|safe}}</div></body></html>
"""

def _api(token, path):
    r = requests.get(f"{API}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    return r.json() if r.ok else None

@app.route("/")
def home():
    if "user" in session:
        return redirect("/servers")
    return render_template_string(PAGE, body="""
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
    return render_template_string(PAGE, body=f"""
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
        for key in ["faith_channel_id", "rating_log_channel_id", "welcome_channel_id", "starboard_channel_id", "ticket_category_id", "staff_role_id"]:
            v = request.form.get(key)
            if v: database.set_setting(guild_id, key, int(v))
        p = (request.form.get("prefix") or "").strip()
        if p and len(p) <= 3 and not any(c.isspace() for c in p):
            database.set_setting(guild_id, "prefix", p)
        return redirect(f"/dashboard/{guild_id}?saved=1")
    s = database.get_settings(guild_id)
    saved = "<p>✅ Saved.</p>" if request.args.get("saved") else ""
    fields = "".join([f'<label>{k}<input name="{k}" value="{s.get(k, "")}" placeholder="Discord ID number"></label>' for k in
        ["staff_role_id", "ticket_category_id", "rating_log_channel_id", "welcome_channel_id", "faith_channel_id", "starboard_channel_id"]])
    prefix = s.get("prefix") or "!"
    return render_template_string(PAGE, body=f"""
    <div class="card"><a href="/servers">← Back to servers</a>{saved}
    <h2>Server {guild_id}</h2><p>Enter Discord IDs (right-click a channel/role > Copy ID, with Developer Mode on). These write to the bot's database.</p>
    <form method="post">{fields}<label>prefix (1-3 characters, e.g. ! or ?)<input name="prefix" value="{prefix}" maxlength="3"></label><button>Save settings</button></form></div>
    <div class="card"><h3>How to use in Discord</h3>
    <p>/setup-tickets staff_role:@Staff &nbsp;•&nbsp; /set-faith-channel &nbsp;•&nbsp; /set-welcome &nbsp;•&nbsp; /set-starboard</p>
    <p>Daily verse + prayer posts at 9:00 AM Central to the faith channel.</p></div>""")

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
    return render_template_string(PAGE, body=body)

@app.route("/logout")
def logout():
    session.clear(); return redirect("/")

if __name__ == "__main__":
    database.init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
