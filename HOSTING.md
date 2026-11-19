# Hosting Sunny's Best Friend 24/7 (not on your PC)

## First: why the websites were "fake" sign-in

The bot itself IS real. `bot.py` + the cogs are a real discord.py bot — it logs into Discord with your token, joins servers, runs all 47 commands.

The websites I built in Muse (Commands / Privacy / Terms / Dashboard) are just pages. A static page has no server, no Client Secret, and no Redirect URL registered in Discord, so it *cannot* do a real Discord login. That's why those buttons were only a preview — I should have said that clearer, sorry about that.

The real dashboard is now in this folder: `dashboard_server.py`.
It's a real Flask web server that does real Discord OAuth2:
Login -> discord.com -> approve -> Discord sends a code back -> this server exchanges it (with the Client Secret, server-side only) -> Discord tells it who you are and which servers you manage.
It only works when it's running on a real host, next to the bot. That's what this file is for.

## Add the bot to other people's servers

1. In the Developer Portal, open your application > **Bot**.
   Make sure **Public Bot** is ON (it is by default). If it's OFF, only you can add it.
2. Go to **OAuth2 > URL Generator**.
   Scopes: `bot` + `applications.commands`
   Bot Permissions: `Administrator` (easiest)
3. Copy that invite URL and send it to anyone. They pick *their* server, Authorize, and the bot joins.
   They need Manage Server in that server to add it.
4. The bot already works per-server: settings, tickets, ratings, XP and coins are stored by Server ID in `bot.db`, so your server and theirs don't mix.
5. In their server, an admin runs `/setup-tickets`, `/set-faith-channel`, etc. — same as yours.

No code change is needed to add it to other servers. It just needs to be online 24/7 — see below.

## Hosting options (checked Oct 2026 — free tiers change a lot)

There is no truly free, reliable 24/7 host left in 2026. Here's the honest list:

### 1. Render FREE + UptimeRobot ping — $0, doable from your phone (RECOMMENDED FOR CONNOR, IN BED)
- Render free web services sleep after 15 minutes with no traffic, so we keep it awake for free with UptimeRobot (free, 50 monitors).
- This repo is ready: `Dockerfile` + `render.yaml` + `start.sh` (bot + real dashboard together) + `/ping` endpoint in `dashboard_server.py`.
- Phone steps (no PC, no card):
  1. On your phone, push this folder to GitHub (GitHub app > New repo > upload the zip, or tell Kai and he can prep it).
  2. Go to render.com on your phone > Sign up with GitHub > New > Web Service > pick the repo > it finds `render.yaml` / Dockerfile automatically > Create.
  3. In Render > Environment, add: DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI=https://YOUR-APP.onrender.com/callback, FLASK_SECRET_KEY=any random string.
  4. In the Developer Portal > OAuth2, add that exact Redirect URI: `https://YOUR-APP.onrender.com/callback`.
  5. Go to uptimerobot.com on your phone > free account > Add Monitor > HTTP(s) > URL `https://YOUR-APP.onrender.com/ping` > every 5 minutes. This pings it so Render doesn't sleep.
  6. Done — bot stays online 24/7, dashboard is live at that same URL, and anyone can add the bot to their server with the invite link.
- Honest limit: free Render is slower to wake the first time, and if UptimeRobot ever stops pinging it will sleep again. Paid Render Worker (~$7/mo) or Railway (~$5/mo) removes that.

### 1b. Railway — easiest, ~$5/month
- New accounts get a $5 trial credit, then $1/month credit after that — a tiny bot usually stays under $5/month.
- Deploy from GitHub, set your env vars in Railway, done. It doesn't sleep.
- This repo is ready for it: `Dockerfile` + `railway.json` + `start.sh` (bot + dashboard together).
- Steps: push this folder to GitHub > railway.app > New Project > Deploy from GitHub > add variables: DISCORD_TOKEN, DISCORD_CLIENT_ID, DISCORD_CLIENT_SECRET, DISCORD_REDIRECT_URI=https://YOUR-APP.up.railway.app/callback, FLASK_SECRET_KEY=random-string.
- Then in the Developer Portal > OAuth2, add that exact Redirect URI.

### 2. Oracle Cloud Always Free — free forever, hardest setup
- Free ARM VMs (up to 2 OCPUs / 12GB, or 2 small AMD instances). Never sleeps, full VPS.
- Downside: you have to set up the VM yourself (SSH, install Python, run the bot with systemd), and idle instances can be reclaimed if you don't use them.
- Best if you want $0 forever and don't mind a harder setup.

### 3. Render — free to test, NOT for 24/7 free
- Free web services spin down after 15 minutes without traffic, and free Background Workers were retired. A bot needs a paid Worker (~$7/month) to stay online.
- Only use Render free to test, then pay if you stay there.

### 4. Fly.io — no longer free for new accounts
- New organisations get a 7-day trial only, trial machines stop after 5 minutes. Smallest always-on machine is about $2.19/month.
- Good, cheap, but not free anymore.

### 5. Keep it on your PC — $0, but only online when your PC is on
- `python bot.py` in a window. When the PC sleeps / closes, the bot goes offline.
- Fine for testing, not for other people's servers.

## What you need for the REAL dashboard (any host)

In the Developer Portal > OAuth2:
- Copy the **Client ID** (public, safe to share with me if you want help).
- **Client Secret**: click Reset Secret, copy it — NEVER share it in Discord/chat, only paste it into the host's env vars.
- Add a Redirect: `https://YOUR-HOST-URL/callback` (exactly, no trailing slash difference).
- Set those 3 + FLASK_SECRET_KEY as env vars on the host, redeploy.

Then open `https://YOUR-HOST-URL/` > Sign in with Discord — for real this time.
