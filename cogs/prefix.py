"""Custom prefix - set it in the dashboard or with /set-prefix.
Prefix commands (using the server's prefix, default "!"):
  !ping  - bot replies Pong
  !help  - lists the main slash commands
  !prefix - shows the current prefix for this server
Slash: /set-prefix (Admin, Manage Server) - 1-3 characters, no spaces.
"""
import discord
from discord.ext import commands
from discord import app_commands
import database

class Prefix(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx):
        await ctx.send(f"Pong! {round(self.bot.latency * 1000)}ms")

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        prefix = ctx.prefix
        e = discord.Embed(title="🤖 Sunny's Best Friend - Commands",
            description=f"Prefix here is `{prefix}` (change it in the dashboard or with /set-prefix).\nSlash commands also work: try `/help`",
            color=discord.Color.blurple())
        e.add_field(name="Tickets + Ratings", value="/setup-tickets, /close, /claim, /ratings, /leaderboard", inline=False)
        e.add_field(name="Messages", value="/messages [@user]", inline=False)
        e.add_field(name="Faith", value="/verse, /dailyverse, /prayer, /pray", inline=False)
        e.add_field(name="Fun / Levels / Economy", value="/8ball, /rank, /top, /balance, /daily, /work", inline=False)
        await ctx.send(embed=e)

    @commands.command(name="prefix")
    async def show_prefix(self, ctx):
        await ctx.send(f"Prefix here is `{ctx.prefix}` — an admin can change it with `/set-prefix` or in the dashboard.")

    @app_commands.command(name="set-prefix", description="Set this server's custom prefix (Admin, 1-3 characters)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def set_prefix(self, interaction: discord.Interaction, prefix: str):
        prefix = prefix.strip()
        if not prefix or len(prefix) > 3 or any(c.isspace() for c in prefix):
            await interaction.response.send_message("Prefix must be 1-3 characters with no spaces, e.g. `!` or `?` or `s!`.", ephemeral=True)
            return
        database.set_setting(interaction.guild_id, "prefix", prefix)
        await interaction.response.send_message(f"✅ Prefix for this server is now `{prefix}` — try `{prefix}ping`")

async def setup(bot):
    await bot.add_cog(Prefix(bot))
