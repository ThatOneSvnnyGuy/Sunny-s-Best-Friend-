"""XP / Levels - gain XP by chatting, /rank, /top."""
import discord, random
from discord.ext import commands
from discord import app_commands
import database

class Leveling(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        if len(message.content) < 3: return
        _, level = database.add_xp(message.guild.id, message.author.id, random.randint(5, 15))
        # level-up message only on exact level thresholds is handled in DB by level calc - keep quiet to avoid spam
    @app_commands.command(name="rank", description="Check your (or someone's) rank")
    async def rank(self, i: discord.Interaction, member: discord.Member = None):
        member = member or i.user
        xp, level = database.get_level(i.guild_id, member.id)
        e = discord.Embed(title=f"📈 Rank - {member.display_name}", color=discord.Color.blurple())
        e.add_field(name="Level", value=str(level)); e.add_field(name="XP", value=str(xp))
        e.add_field(name="XP to next level", value=str((level+1)**2*100 - xp))
        await i.response.send_message(embed=e)
    @app_commands.command(name="top", description="Top 10 by XP")
    async def top(self, i: discord.Interaction):
        rows = database.top_levels(i.guild_id, 10)
        e = discord.Embed(title="🏆 XP Leaderboard", color=discord.Color.blurple())
        if not rows: e.description = "No XP yet - start chatting!"
        for n, r in enumerate(rows, 1):
            e.add_field(name=f"{n}. <@{r['user_id']}>", value=f"Level {r['level']} - {r['xp']} XP", inline=False)
        await i.response.send_message(embed=e)

async def setup(bot): await bot.add_cog(Leveling(bot))
