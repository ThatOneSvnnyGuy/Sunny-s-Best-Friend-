"""Moderation + AutoMod."""
import discord, re
from discord.ext import commands
from discord import app_commands
import database

BAD_WORDS = ["nigger", "faggot"]  # add your own - keep it short, edit this list

class Moderation(commands.Cog):
    def __init__(self, bot): self.bot = bot

    async def _log(self, guild, text):
        s = database.get_settings(guild.id)
        ch_id = s.get("log_channel_id")
        if not ch_id: return
        ch = guild.get_channel(ch_id)
        if ch:
            try: await ch.send(text)
            except Exception: pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        low = message.content.lower()
        # AutoMod: bad words + invite links + spam caps
        if any(w in low for w in BAD_WORDS):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} that word isn't allowed here.", delete_after=5)
            except Exception: pass
        elif "discord.gg/" in low and not message.author.guild_permissions.manage_messages:
            try: await message.delete()
            except Exception: pass

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, i: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.kick(reason=reason); await i.response.send_message(f"👢 Kicked {member.mention} - {reason}")
    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, i: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.ban(reason=reason); await i.response.send_message(f"🔨 Banned {member.mention} - {reason}")
    @app_commands.command(name="timeout", description="Timeout a member (minutes)")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, i: discord.Interaction, member: discord.Member, minutes: int = 10, reason: str = "No reason"):
        import datetime
        await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
        await i.response.send_message(f"⏰ Timed out {member.mention} for {minutes}m - {reason}")
    @app_commands.command(name="warn", description="Warn a member (saved)")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, i: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        database.add_warn(i.guild_id, member.id, i.user.id, reason)
        await i.response.send_message(f"⚠️ Warned {member.mention} - {reason}")
    @app_commands.command(name="purge", description="Delete messages")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, i: discord.Interaction, amount: int = 10):
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=amount)
        await i.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)
    @app_commands.command(name="slowmode", description="Set slowmode (seconds, 0 = off)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, i: discord.Interaction, seconds: int = 5):
        await i.channel.edit(slowmode_delay=seconds)
        await i.response.send_message(f"🐢 Slowmode set to {seconds}s" if seconds else "🐢 Slowmode off")
    @app_commands.command(name="lock", description="Lock this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, i: discord.Interaction):
        await i.channel.set_permissions(i.guild.default_role, send_messages=False)
        await i.response.send_message("🔒 Channel locked")
    @app_commands.command(name="unlock", description="Unlock this channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, i: discord.Interaction):
        await i.channel.set_permissions(i.guild.default_role, send_messages=True)
        await i.response.send_message("🔓 Channel unlocked")

async def setup(bot): await bot.add_cog(Moderation(bot))
