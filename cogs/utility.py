"""Utility - help, serverinfo, userinfo, avatar, poll."""
import discord
from discord.ext import commands
from discord import app_commands

class Utility(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="help", description="All commands")
    async def help_cmd(self, i: discord.Interaction):
        e = discord.Embed(title="🤖 Sunny's Best Friend - Commands", color=discord.Color.blurple())
        e.add_field(name="🙏 Faith", value="/verse, /dailyverse, /prayer, /pray, /set-faith-channel", inline=False)
        e.add_field(name="🎫 Tickets + Ratings", value="/setup-tickets, /close, /claim, /ratings, /leaderboard, /recent-ratings", inline=False)
        e.add_field(name="🛡️ Moderation", value="/kick, /ban, /timeout, /warn, /purge, /slowmode, /lock, /unlock", inline=False)
        e.add_field(name="📈 Levels", value="/rank, /top", inline=False)
        e.add_field(name="💰 Economy", value="/balance, /daily, /work, /coinflip, /slots", inline=False)
        e.add_field(name="🎮 Fun", value="/8ball, /dice, /rps, /joke, /hug", inline=False)
        e.add_field(name="🎵 Music", value="/play, /stop, /skip, /queue", inline=False)
        e.add_field(name="🎉 Giveaways", value="/giveaway, /poll", inline=False)
        e.add_field(name="✨ Extras", value="/remind, /afk, /suggest, /reaction-roles, /set-starboard", inline=False)
        e.add_field(name="ℹ️ Utility", value="/serverinfo, /userinfo, /avatar, /help", inline=False)
        await i.response.send_message(embed=e, ephemeral=True)
    @app_commands.command(name="serverinfo", description="Info about this server")
    async def serverinfo(self, i: discord.Interaction):
        g = i.guild
        e = discord.Embed(title=g.name, color=discord.Color.blurple())
        e.add_field(name="Members", value=str(g.member_count)); e.add_field(name="Created", value=g.created_at.strftime("%Y-%m-%d"))
        e.add_field(name="Owner", value=str(g.owner)); e.add_field(name="Channels", value=str(len(g.channels)))
        if g.icon: e.set_thumbnail(url=g.icon.url)
        await i.response.send_message(embed=e)
    @app_commands.command(name="userinfo", description="Info about a user")
    async def userinfo(self, i: discord.Interaction, member: discord.Member = None):
        m = member or i.user
        e = discord.Embed(title=m.display_name, color=discord.Color.blurple())
        e.add_field(name="Joined", value=m.joined_at.strftime("%Y-%m-%d") if m.joined_at else "?")
        e.add_field(name="Created", value=m.created_at.strftime("%Y-%m-%d"))
        e.add_field(name="Roles", value=", ".join([r.name for r in m.roles[1:]]) or "None")
        e.set_thumbnail(url=m.display_avatar.url)
        await i.response.send_message(embed=e)
    @app_commands.command(name="avatar", description="Show someone's avatar")
    async def avatar(self, i: discord.Interaction, member: discord.Member = None):
        m = member or i.user
        await i.response.send_message(m.display_avatar.url)
    @app_commands.command(name="poll", description="Make a poll")
    async def poll(self, i: discord.Interaction, question: str, option1: str, option2: str):
        e = discord.Embed(title=f"📊 {question}", description=f"👍 {option1}\n👎 {option2}", color=discord.Color.blurple())
        await i.response.send_message(embed=e)
        msg = await i.original_response()
        await msg.add_reaction("👍"); await msg.add_reaction("👎")

async def setup(bot): await bot.add_cog(Utility(bot))
