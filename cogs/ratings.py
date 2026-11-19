"""Rating leaderboards + staff stats.
Ratings only come from closed tickets - no fake / self ratings.
"""
import discord
from discord.ext import commands
from discord import app_commands
import database
from cogs.tickets import stars_text

class Ratings(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="ratings", description="See a staff member's ticket ratings")
    @app_commands.describe(member="Staff member to check (leave blank for yourself)")
    async def ratings(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        avg, n = database.staff_average(interaction.guild_id, member.id)
        rows = database.staff_ratings(interaction.guild_id, member.id)[:5]
        e = discord.Embed(title=f"⭐ Ratings - {member.display_name}", color=discord.Color.gold())
        if n == 0:
            e.description = "No ratings yet. Ratings come from closed tickets."
        else:
            e.description = f"**{avg} / 5** {stars_text(round(avg))}\nFrom **{n}** ticket rating(s)"
            for r in rows:
                e.add_field(name=f"{stars_text(r['stars'])} - <@{r['user_id']}>", value=r['feedback'] or "No feedback", inline=False)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="leaderboard", description="Top rated staff from ticket ratings")
    async def leaderboard(self, interaction: discord.Interaction):
        top = database.top_staff(interaction.guild_id, 10)
        e = discord.Embed(title="🏆 Staff Rating Leaderboard", description="From closed-ticket ratings only.", color=discord.Color.gold())
        if not top:
            e.description = "No ratings yet - close a ticket and get rated!"
        for i, r in enumerate(top, 1):
            e.add_field(name=f"{i}. <@{r['staff_id']}>", value=f"{round(r['avg'],2)} ⭐ ({r['n']} ratings)", inline=False)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="recent-ratings", description="Most recent ticket ratings (Staff/Admin)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def recent(self, interaction: discord.Interaction):
        rows = database.recent_ratings(interaction.guild_id, 10)
        e = discord.Embed(title="⭐ Recent Ticket Ratings", color=discord.Color.gold())
        if not rows:
            e.description = "No ratings yet."
        for r in rows:
            staff = f"<@{r['staff_id']}>" if r['staff_id'] else "Unclaimed"
            e.add_field(name=f"{stars_text(r['stars'])} - Staff: {staff}", value=f"By <@{r['user_id']}> - {r['feedback'] or 'No feedback'}", inline=False)
        await interaction.response.send_message(embed=e, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Ratings(bot))
