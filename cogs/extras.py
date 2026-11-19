"""Extras that make it a true all-in-one:
Reminders, AFK, suggestions, reaction roles, starboard.
"""
import discord, asyncio, re
from discord.ext import commands
from discord import app_commands
import database

AFK = {}  # (guild_id, user_id) -> reason

def parse_duration(s: str):
    m = re.match(r"(\d+)([smh])", s.lower())
    if not m: return None
    n, u = int(m.group(1)), m.group(2)
    return n if u == "s" else n*60 if u == "m" else n*3600

class RoleView(discord.ui.View):
    def __init__(self, roles):
        super().__init__(timeout=None)
        self.roles = roles  # list of (role_id, label)
        for rid, label in roles:
            self.add_item(RoleButton(rid, label))
class RoleButton(discord.ui.Button):
    def __init__(self, role_id, label):
        super().__init__(label=label, style=discord.ButtonStyle.primary, custom_id=f"role_{role_id}")
        self.role_id = role_id
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("That role is gone.", ephemeral=True); return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"Removed **{role.name}**", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"Added **{role.name}**", ephemeral=True)

class Extras(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        # AFK: clear on return, notify when mentioned
        key = (message.guild.id, message.author.id)
        if key in AFK:
            del AFK[key]
            await message.channel.send(f"Welcome back {message.author.mention}!", delete_after=5)
        for m in message.mentions:
            k = (message.guild.id, m.id)
            if k in AFK:
                await message.channel.send(f"{m.display_name} is AFK: {AFK[k]}", delete_after=10)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or str(reaction.emoji) != "⭐": return
        if reaction.count < 3: return
        s = database.get_settings(reaction.message.guild.id)
        ch_id = s.get("starboard_channel_id")
        if not ch_id: return
        ch = reaction.message.guild.get_channel(ch_id)
        if ch:
            e = discord.Embed(description=reaction.message.content or "(image / embed)", color=discord.Color.gold())
            e.add_field(name="Original", value=f"[Jump to message]({reaction.message.jump_url}) by {reaction.message.author.mention}")
            await ch.send(embed=e)

    @app_commands.command(name="remind", description="Remind yourself (e.g. 10m, 1h)")
    async def remind(self, i: discord.Interaction, when: str, text: str):
        secs = parse_duration(when)
        if not secs:
            await i.response.send_message("Use like 10m, 1h, 30s", ephemeral=True); return
        await i.response.send_message(f"⏰ I'll remind you in {when}: **{text}**", ephemeral=True)
        await asyncio.sleep(secs)
        try: await i.user.send(f"⏰ Reminder: **{text}**")
        except Exception:
            await i.channel.send(f"{i.user.mention} ⏰ Reminder: **{text}**")

    @app_commands.command(name="afk", description="Set yourself AFK")
    async def afk(self, i: discord.Interaction, reason: str = "AFK"):
        AFK[(i.guild_id, i.user.id)] = reason
        await i.response.send_message(f"💤 {i.user.mention} is now AFK: {reason}")

    @app_commands.command(name="suggest", description="Make a suggestion - people vote 👍👎")
    async def suggest(self, i: discord.Interaction, suggestion: str):
        e = discord.Embed(title="💡 Suggestion", description=suggestion, color=discord.Color.blurple())
        e.add_field(name="From", value=i.user.mention)
        await i.response.send_message(embed=e)
        msg = await i.original_response()
        await msg.add_reaction("👍"); await msg.add_reaction("👎")

    @app_commands.command(name="reaction-roles", description="Post a reaction-role panel (Admin)")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def reaction_roles(self, i: discord.Interaction, role1: discord.Role, role2: discord.Role = None, role3: discord.Role = None):
        roles = [(role1.id, role1.name)]
        if role2: roles.append((role2.id, role2.name))
        if role3: roles.append((role3.id, role3.name))
        e = discord.Embed(title="🎭 Pick Your Roles", description="Click a button to add / remove that role.", color=discord.Color.blurple())
        await i.response.send_message(embed=e, view=RoleView(roles))

    @app_commands.command(name="set-starboard", description="Set starboard channel - messages with 3+ ⭐ go here (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_starboard(self, i: discord.Interaction, channel: discord.TextChannel):
        database.set_setting(i.guild_id, "starboard_channel_id", channel.id)
        await i.response.send_message(f"⭐ Starboard set to {channel.mention} (3+ ⭐ stars)")

async def setup(bot):
    await bot.add_cog(Extras(bot))
