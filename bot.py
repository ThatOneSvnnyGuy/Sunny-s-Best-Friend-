"""Sunny's Best Friend - ALL-IN-ONE Discord Bot - Kai / Connor build
Python + discord.py. Run: python bot.py (after .env is set)
Features: Moderation, AutoMod, Tickets + Ticket-Close Rating,
Levels, Economy, Fun, Music, Giveaways, Polls, Welcome, Utility,
Faith (daily prayers + Bible verses), Reminders, AFK, Reaction Roles, Starboard.
"""
import os, discord
from discord.ext import commands
from dotenv import load_dotenv
import database

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = False

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
    async def setup_hook(self):
        database.init_db()
        for ext in [
            "cogs.tickets", "cogs.ratings", "cogs.moderation",
            "cogs.leveling", "cogs.economy", "cogs.fun",
            "cogs.utility", "cogs.music", "cogs.giveaways",
            "cogs.faith", "cogs.extras", "cogs.loa", "cogs.strikes",
            "cogs.messages", "cogs.applications",
        ]:
            try:
                await self.load_extension(ext)
                print(f"Loaded {ext}")
            except Exception as e:
                print(f"FAILED {ext}: {e}")
        # Sync slash commands globally (takes up to 1h first time, instant on restart usually)
        # For instant testing, set GUILD_ID in .env to sync to one server.
        guild_id = os.getenv("GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced commands to guild {guild_id}")
        else:
            await self.tree.sync()
            print("Synced commands globally")

bot = Bot()

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    print(f"✅ In {len(bot.guilds)} server(s)")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching, name="/verse • /ticket • /help"))

@bot.tree.error
async def on_app_command_error(interaction, error):
    try:
        msg = f"❌ {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

if __name__ == "__main__":
    if not TOKEN:
        print("❌ No DISCORD_TOKEN in .env - copy .env.example to .env and paste your token.")
    else:
        bot.run(TOKEN)
