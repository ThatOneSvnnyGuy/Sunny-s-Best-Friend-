"""The everyday useful stuff other bots have - the gaps that make
people actually keep a bot: unban, untimeout, nick, role toggle,
warns list, member count, announce, autorole, mod-log channel,
snipe, and the bot invite link."""
import discord
from discord import app_commands
import database

INVITE_URL = ("https://discord.com/oauth2/authorize?client_id=1344106788794011820"
              "&permissions=648711860387839&integration_type=0&scope=bot+applications.commands")

class Useful(discord.ext.commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._snipes = {}  # channel_id -> (author, content)

    @discord.ext.commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author and not message.author.bot and message.content:
            self._snipes[message.channel.id] = (str(message.author), message.content)

    @discord.ext.commands.Cog.listener()
    async def on_member_join(self, member):
        s = database.get_settings(member.guild.id)
        role_id = s.get("autorole_id")
        if role_id:
            role = member.guild.get_role(role_id)
            if role:
                try: await member.add_roles(role, reason="Autorole")
                except Exception: pass

    async def _log(self, guild, text):
        s = database.get_settings(guild.id)
        ch_id = s.get("log_channel_id")
        if not ch_id: return
        ch = guild.get_channel(ch_id)
        if ch:
            try: await ch.send(text)
            except Exception: pass

    @app_commands.command(name="unban", description="Unban someone (by name or user ID)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, i: discord.Interaction, user: str):
        async for entry in i.guild.bans():
            u = entry.user
            if str(u.id) == user or str(u) == user or u.name == user:
                await i.guild.unban(u)
                await i.response.send_message(f"✅ Unbanned {u}")
                await self._log(i.guild, f"🔨 Unbanned {u} by {i.user}")
                return
        await i.response.send_message(f"Couldn't find a ban for `{user}` — try their user ID.", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a timeout from a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, i: discord.Interaction, member: discord.Member):
        import datetime
        await member.timeout(None)
        await i.response.send_message(f"✅ Removed timeout from {member.mention}")

    @app_commands.command(name="nick", description="Change a member's nickname (blank = reset)")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def nick(self, i: discord.Interaction, member: discord.Member, nickname: str = ""):
        await member.edit(nick=nickname or None)
        await i.response.send_message(f"✅ {member.mention} is now `{nickname or member.name}`")

    @app_commands.command(name="role", description="Give or take a role from a member (toggles it)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role(self, i: discord.Interaction, member: discord.Member, role: discord.Role):
        if role in member.roles:
            await member.remove_roles(role)
            await i.response.send_message(f"➖ Removed {role.mention} from {member.mention}")
        else:
            await member.add_roles(role)
            await i.response.send_message(f"➕ Gave {role.mention} to {member.mention}")

    @app_commands.command(name="warns", description="Show a member's saved warnings")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warns(self, i: discord.Interaction, member: discord.Member):
        c = database._conn(); cur = c.cursor()
        cur.execute("SELECT reason, created_at FROM warns WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT 10", (i.guild_id, member.id))
        rows = cur.fetchall(); c.close()
        if not rows:
            await i.response.send_message(f"{member.mention} has no warnings.")
            return
        text = "\n".join(f"• {r['reason']}" for r in rows)
        await i.response.send_message(f"⚠️ Warnings for {member.mention} ({len(rows)}):\n{text}")

    @app_commands.command(name="membercount", description="How many members are in this server")
    async def membercount(self, i: discord.Interaction):
        g = i.guild
        bots = sum(1 for m in g.members if m.bot)
        await i.response.send_message(f"👥 **{g.name}** — {g.member_count} members ({g.member_count - bots} people, {bots} bots)")

    @app_commands.command(name="invite", description="Get the link to add Sunny's Best Friend to a server")
    async def invite(self, i: discord.Interaction):
        await i.response.send_message(f"☀️ Add me to a server: {INVITE_URL}")

    @app_commands.command(name="announce", description="Post an announcement in a channel (Admin)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def announce(self, i: discord.Interaction, channel: discord.TextChannel, message: str):
        e = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.blurple())
        await channel.send(embed=e)
        await i.response.send_message(f"✅ Posted in {channel.mention}", ephemeral=True)

    @app_commands.command(name="snipe", description="Show the last deleted message in this channel")
    async def snipe(self, i: discord.Interaction):
        s = self._snipes.get(i.channel.id)
        if not s:
            await i.response.send_message("Nothing deleted here recently.", ephemeral=True)
            return
        await i.response.send_message(f"🗑️ **{s[0]}** said: {s[1]}")

    @app_commands.command(name="set-autorole", description="Role given automatically to everyone who joins (Admin)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def set_autorole(self, i: discord.Interaction, role: discord.Role):
        database.set_setting(i.guild_id, "autorole_id", role.id)
        await i.response.send_message(f"✅ New members will automatically get {role.mention}")

    @app_commands.command(name="set-log-channel", description="Where kick/ban/warn logs go (Admin)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_log_channel(self, i: discord.Interaction, channel: discord.TextChannel):
        database.set_setting(i.guild_id, "log_channel_id", channel.id)
        await i.response.send_message(f"✅ Mod logs will go to {channel.mention}")

async def setup(bot):
    await bot.add_cog(Useful(bot))
