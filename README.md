# 🤖 Sunny's Best Friend - All-In-One Discord Bot

Python + discord.py. Everything in one bot:
Moderation + AutoMod, Tickets, Levels, Economy, Fun, Music, Giveaways, Polls, Welcome, Utility, Faith (daily prayers + Bible verses), Reminders, AFK, Reaction Roles, Starboard, Suggestions.

## 🙏 Faith - Daily Prayers + Bible Verses

Set it once (admin):
```
/set-faith-channel channel:#daily-verse
```
Then every day at **9:00 AM Central** the bot posts a daily verse + a prayer in that channel automatically.

On-demand commands (anyone):
- `/verse` - random Bible verse
- `/dailyverse` - today's verse (same for everyone that day)
- `/prayer` - a prayer - add a kind: morning, night, strength, peace, gratitude, healing
  - e.g. `/prayer kind:morning`
- `/pray request:please pray for my grandma` - posts a prayer request in the faith channel, others react 🙏

Verses are KJV (public domain), 25 verses in the list - tell Kai if you want more, or a specific translation / topic list.

## ⭐ The rating system you asked for - Ticket-Close Rating

1. User clicks **Create Ticket**
2. Staff clicks **Claim**
3. Staff (or anyone) clicks **Close Ticket** / `/close`
4. Ticket **locks**, and the owner gets a rating prompt **in the ticket AND in DM**:
   ⭐ 1 to ⭐⭐⭐⭐⭐ 5 buttons, then an optional feedback box
5. Rating saves to `bot.db`, posts to your rating-log channel, and shows on:
   - `/ratings @staff` - their average + recent feedback
   - `/leaderboard` - top rated staff
   - `/recent-ratings` - latest ratings (staff/admin only)
6. Channel deletes 10 seconds after they rate (or 5 min if they skip / don't answer)
7. One rating per ticket. No self-rating - only the ticket owner can rate, and only the staff who claimed it gets the credit.

## Step 1 - Make the bot on Discord (5 min, on your PC)

1. Go to https://discord.com/developers/applications - log in
2. **New Application** > name it whatever you want > Create
3. Left menu **Bot** > **Reset Token** > copy that token - **never share it, never post it in Discord**
4. On that same Bot page, turn ON all 3 Privileged Intents:
   - Presence Intent, Server Members Intent, Message Content Intent
   - Save Changes
5. Left menu **OAuth2 > URL Generator**
   - Scopes: tick `bot` and `applications.commands`
   - Bot Permissions: tick `Administrator` (easiest - it needs to make/delete ticket channels)
   - Copy the URL at the bottom, paste it in your browser, pick your server, Authorize

## Step 2 - Run it on your Windows PC

Do NOT use a .ps1 file - your PC blocks those. Use these one-liners in PowerShell / Command Prompt, in the bot folder:

```
python --version
```
You need Python 3.10+. If you don't have it, install from python.org and tick **Add Python to PATH**.

Then, in the folder with `bot.py`:
```
pip install -r requirements.txt
```

Copy the example env file and paste your token:
```
copy .env.example .env
notepad .env
```
Replace `PASTE_YOUR_BOT_TOKEN_HERE` with your token from Step 1. Save + close Notepad.

Optional (makes slash commands show up instantly instead of up to 1 hour):
In Discord, turn on Developer Mode (Settings > Advanced > Developer Mode), right-click your server name > Copy Server ID, paste it in `.env` as `GUILD_ID=123456...`

Then run it:
```
python bot.py
```
You should see:
```
Loaded cogs.tickets
...
✅ Logged in as YourBotName
```

Keep that window open - the bot only runs while your PC is on and that window is open. For 24/7, you'd host it later (Railway / a VPS / Raspberry Pi) - ask me and I'll set that up.

For music (`/play`), you also need FFmpeg: download it from https://www.gyan.dev/ffmpeg/builds/ , unzip, and add its `bin` folder to PATH, or put `ffmpeg.exe` in the same folder as `bot.py`.

## Step 3 - Set up tickets in your server

In Discord, type these slash commands (admin only):

```
/setup-tickets staff_role:@Staff category:#tickets rating_log_channel:#ratings
```
- `staff_role` = the role that can see/claim tickets
- `category` = where ticket channels go (optional)
- `rating_log_channel` = where ⭐ ratings get posted (optional, but recommended)

That posts a **🎫 Need Help?** panel. Anyone clicking **Create Ticket** gets their own private channel.

Other useful setup:
```
/set-welcome channel:#welcome
```

## Commands

| Area | Commands |
|---|---|
| Tickets + Ratings | `/setup-tickets`, `/close`, `/claim`, `/ratings [@staff]`, `/leaderboard`, `/recent-ratings` |
| Moderation | `/kick`, `/ban`, `/timeout`, `/warn`, `/purge`, `/slowmode`, `/lock`, `/unlock` |
| Levels | `/rank`, `/top` - XP for chatting |
| Messages | `/messages [@user]` - total, today, this week, this month, this year |
| Applications | `/setup-applications`, `/apply`, `/applications` - apply + approve/deny in Discord |
| LOA | `/loa-request`, `/loa-approve`, `/loa-deny`, `/loa-list`, `/loa-end`, `/loa-status` - all in Discord |
| Strikes | `/strike`, `/strikes`, `/clear-strikes` - all in Discord |
| Economy | `/balance`, `/daily`, `/work`, `/coinflip`, `/slots` |
| Fun | `/8ball`, `/dice`, `/rps`, `/joke`, `/hug` |
| Music | `/play`, `/stop`, `/skip`, `/queue` |
| Giveaways | `/giveaway 10m Prize Name`, `/poll` |
| Faith | `/verse`, `/dailyverse`, `/prayer`, `/pray`, `/set-faith-channel` - daily post 9am Central |
| Extras | `/remind`, `/afk`, `/suggest`, `/reaction-roles`, `/set-starboard` |
| Utility | `/help`, `/serverinfo`, `/userinfo`, `/avatar`, `/set-welcome` |

## Files

- `bot.py` - starts the bot, loads all cogs
- `database.py` - SQLite (`bot.db`) - ratings, tickets, levels, economy, warns
- `cogs/tickets.py` - ticket panel, claim/close, rating prompt on close
- `cogs/ratings.py` - `/ratings`, `/leaderboard`, `/recent-ratings`
- `cogs/moderation.py`, `cogs/leveling.py`, `cogs/economy.py`, `cogs/fun.py`, `cogs/utility.py`, `cogs/music.py`, `cogs/giveaways.py`
- `requirements.txt`, `.env.example`

## Troubleshooting

- **Slash commands don't show up:** wait up to 1 hour, or set `GUILD_ID` in `.env` and restart. Or kick/re-invite the bot.
- **Bot is offline:** the `python bot.py` window closed, or your PC slept. Re-run it.
- **"Privileged intent" error:** you missed Step 1.4 - turn on Server Members + Message Content intents.
- **Music doesn't play:** FFmpeg isn't installed / not in PATH. See Step 2 note.
- **Ticket button does nothing:** bot needs Administrator (or Manage Channels + View Channel) in that server.
- **Token leaked / someone has it:** Discord Developer Portal > Bot > Reset Token, update `.env`, restart.
