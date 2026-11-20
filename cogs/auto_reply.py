"""Automatic replies.
- @ the bot and it answers: just a mention gets a quick intro (prefix,
  dashboard, /help); ask it about the prefix, tickets, applying or help
  and it answers that. No AI, just fast built-in answers.
- Custom auto-replies: owners set a trigger phrase and a reply in the
  dashboard (Messages section) or with /add-reply - when someone's message
  contains the trigger, the bot replies with it. One reply per message,
  bots are ignored so it can't loop on itself.
"""
import discord, re
from discord.ext import commands
from discord import app_commands
import database

DASHBOARD = "https://sunnys-best-friend-production.up.railway.app"
INVITE = ("https://discord.com/oauth2/authorize?client_id=1344106788794011820"
          "&permissions=1125899906842615&integration_type=0&scope=bot+applications.commands")

def _clean(content: str, bot_id: int) -> str:
    text = re.sub(rf"<@!?{bot_id}>", "", content).strip()
    return re.sub(r"\s+", " ", text)

class AutoReply(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if self.bot.user not in message.mentions:
            # Custom trigger replies (servers only)
            if not message.guild:
                return
            low = message.content.lower()
            for r in database.list_auto_replies(message.guild.id):
                if r["trigger"] and r["trigger"] in low:
                    try:
                        await message.channel.send(r["response"])
                    except Exception:
                        pass
                    return
            return
        # Someone @'d the bot
        prefix = "!"
        if message.guild:
            prefix = database.get_settings(message.guild.id).get("prefix") or "!"
        text = _clean(message.content, self.bot.user.id)
        low = text.lower()
        if not text:
            e = discord.Embed(title="☀️ Hey! I'm Sunny's Best Friend",
                              description=f"Your all-in-one bot — tickets with ratings, moderation, levels, economy, music, giveaways, faith, LOA, strikes, applications and more.\n\n**Prefix:** `{prefix}`\n**Commands:** `{prefix}help` or `/help`\n**Dashboard:** {DASHBOARD}\n**Add me to a server:** {INVITE}",
                              color=discord.Color.blurple())
            await message.channel.send(embed=e)
        elif "prefix" in low:
            await message.channel.send(f"My prefix here is `{prefix}` — try `{prefix}help` or `/help`.")
        elif "help" in low or "command" in low:
            await message.channel.send(f"Here's what I can do — try `/help` for the full list, or `{prefix}help`.\nTickets: open one from the ticket panel • Apply: `/apply` • Check your messages: `/messages` • Daily verse: `/verse` • Dashboard: {DASHBOARD}")
        elif "ticket" in low:
            await message.channel.send("Need help? Pick a topic from the ticket panel in the support channel and a ticket will open for you. When it closes, you'll rate your support 1-5 ⭐.")
        elif "apply" in low:
            await message.channel.send("Want to join the team? Use `/apply` and pick what you're applying for — staff will review it.")
        elif any(w in low for w in ("hi", "hello", "hey", "yo", "sup", "good morning", "good afternoon", "good evening")):
            await message.channel.send(f"Hey {message.author.mention}! 👋 Need something? Try `/help` or just ask — I do tickets, moderation, levels, giveaways and more.")
        elif "thank" in low:
            await message.channel.send("Anytime! ☀️")
        else:
            await message.channel.send(f"Hey {message.author.mention}! I'm Sunny's Best Friend — try `/help` to see what I can do, or check the dashboard: {DASHBOARD}")

    @app_commands.command(name="add-reply", description="Add an automatic reply - when someone says the trigger, the bot replies (Manage Messages)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def add_reply(self, i: discord.Interaction, trigger: str, response: str):
        database.add_auto_reply(i.guild_id, trigger, response)
        await i.response.send_message(f"✅ When someone says `{trigger.lower()}`, I'll reply: {response}", ephemeral=True)

    @app_commands.command(name="remove-reply", description="Remove an automatic reply by its number - see /reply-list (Manage Messages)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def remove_reply(self, i: discord.Interaction, reply_id: int):
        database.delete_auto_reply(reply_id, i.guild_id)
        await i.response.send_message(f"✅ Removed auto-reply #{reply_id} (if it existed).", ephemeral=True)

    @app_commands.command(name="reply-list", description="List the server's automatic replies (Manage Messages)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def reply_list(self, i: discord.Interaction):
        rows = database.list_auto_replies(i.guild_id)
        if not rows:
            await i.response.send_message("No auto-replies set up yet. Use `/add-reply` or make them in the dashboard (Messages section).", ephemeral=True); return
        e = discord.Embed(title="🤖 Automatic replies", color=discord.Color.blurple())
        for r in rows:
            e.add_field(name=f"#{r['id']} — when someone says `{r['trigger']}`", value=r["response"][:200], inline=False)
        await i.response.send_message(embed=e, ephemeral=True)

async def setup(bot): await bot.add_cog(AutoReply(bot))
