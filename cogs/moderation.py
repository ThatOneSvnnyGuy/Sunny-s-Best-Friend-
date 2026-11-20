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

    async def _check_message(self, message):
        """Delete a message if it has a censored word. Returns True if deleted.
        Applies to EVERYONE (mods and owner included) - the old version skipped
        anyone with Manage Messages, which is every admin/owner, so it looked
        broken when tested by the person who set it up."""
        if message.author.bot or not message.guild: return False
        words = [w.lower() for w in BAD_WORDS] + database.list_censored_words(message.guild.id)
        low = message.content.lower()
        hit = None
        for w in words:
            if re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", low):
                hit = w; break
        if hit:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} that word isn't allowed here.", delete_after=5)
                await self._log(message.guild, f"🤬 Censored word `{hit}` from {message.author} (`{message.author.id}`) in {message.channel.mention}")
            except Exception: pass
            return True
        return False

    @commands.Cog.listener()
    async def on_message(self, message):
        if await self._check_message(message): return
        if not message.guild or message.author.bot: return
        low = message.content.lower()
        # AutoMod: invite links
        if "discord.gg/" in low and not message.author.guild_permissions.manage_messages:
            try: await message.delete()
            except Exception: pass

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        # Censor edited messages too - editing can't dodge the filter
        await self._check_message(after)

    @app_commands.command(name="add-word", description="Censor a word - messages with it get deleted (Manage Messages only)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def add_word(self, i: discord.Interaction, word: str):
        database.add_censored_word(i.guild_id, word)
        await i.response.send_message(f"🤬 Added `{word.lower()}` to the censored words. Messages with it will be deleted instantly.", ephemeral=True)
    @app_commands.command(name="remove-word", description="Stop censoring a word (Manage Messages only)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def remove_word(self, i: discord.Interaction, word: str):
        database.remove_censored_word(i.guild_id, word)
        await i.response.send_message(f"✅ Removed `{word.lower()}` from the censored words.", ephemeral=True)
    @app_commands.command(name="word-list", description="Show all censored words in this server")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def word_list(self, i: discord.Interaction):
        words = database.list_censored_words(i.guild_id)
        base = ", ".join(f"`{w}`" for w in BAD_WORDS)
        extra = ", ".join(f"`{w}`" for w in words) if words else "none added yet"
        await i.response.send_message(f"🤬 Censored words:\n• Built-in: {base}\n• Added in this server: {extra}\n\nAdd one with /add-word, remove one with /remove-word.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, i: discord.Interaction, member: discord.Member, reason: str = "No reason"):
        await member.kick(reason=reason); await i.response.send_message(f"👢 Kicked {member.mention} - {reason}")
    @app_commands.command(name="ban", description="Ban someone by @mention or user ID - works even if they are not in this server")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, i: discord.Interaction, user: str, reason: str = "No reason"):
        # Accept @mention (<@123...>), a plain user ID, or a username.
        uid = None
        raw = user.strip().strip("<>@! ")
        if raw.isdigit():
            uid = int(raw)
        else:
            # Try a member in the server by name / mention first
            member = None
            if i.guild:
                member = i.guild.get_member_named(user.strip())
                if not member:
                    for m in i.guild.members:
                        if m.name.lower() == user.strip().lower() or str(m) == user.strip():
                            member = m; break
            if member:
                await member.ban(reason=reason)
                await i.response.send_message(f"🔨 Banned {member.mention} (`{member.id}`) - {reason}")
                await self._log(i.guild, f"🔨 Banned {member} (`{member.id}`) by {i.user} - {reason}")
                return
            await i.response.send_message("Couldn't find that user. Use their @mention or their user ID (right-click them in Discord > Copy User ID, with Developer Mode on) — it works even if they left / are not in this server.", ephemeral=True)
            return
        # Ban by ID, even if they are not in the server (hackban)
        target = discord.Object(id=uid)
        try:
            await i.guild.ban(target, reason=reason)
        except discord.NotFound:
            await i.response.send_message(f"No Discord user exists with ID `{uid}`.", ephemeral=True)
            return
        except discord.Forbidden:
            await i.response.send_message("I don't have permission to ban that user.", ephemeral=True)
            return
        # Show their name if Discord knows them
        try:
            u = await self.bot.fetch_user(uid)
            name = f"{u} (`{uid}`)"
        except Exception:
            name = f"user ID `{uid}`"
        await i.response.send_message(f"🔨 Banned {name} - {reason}")
        await self._log(i.guild, f"🔨 Banned {name} by {i.user} - {reason}")

    @app_commands.command(name="banlist", description="Show everyone currently banned from this server")
    @app_commands.checks.has_permissions(ban_members=True)
    async def banlist(self, i: discord.Interaction):
        bans = [entry async for entry in i.guild.bans()]
        if not bans:
            await i.response.send_message("Nobody is banned from this server.")
            return
        text = "\n".join(f"• {entry.user} (`{entry.user.id}`) - {entry.reason or 'No reason'}" for entry in bans[:20])
        await i.response.send_message(f"🔨 Banned ({len(bans)}):\n{text}")
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
