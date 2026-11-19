"""Message counts - /messages [@user]
Shows how many messages someone sent: total, today, this week,
this month, this year. Counts start when the bot is running and
sees a message - it can't count messages from before it was added.
"""
import discord
from discord.ext import commands
from discord import app_commands
import database

class Messages(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        database.record_message(message.guild.id, message.author.id)

    @app_commands.command(name="messages", description="How many messages has someone sent? Total, today, week, month, year")
    @app_commands.describe(member="Who to check - leave blank for yourself")
    async def messages(self, i: discord.Interaction, member: discord.Member = None):
        member = member or i.user
        s = database.get_message_stats(i.guild_id, member.id)
        e = discord.Embed(
            title=f"💬 Messages - {member.display_name}",
            color=discord.Color.blurple(),
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Total", value=f"**{s['total']:,}**", inline=True)
        e.add_field(name="Today", value=f"**{s['today']:,}**", inline=True)
        e.add_field(name="This week", value=f"**{s['week']:,}**", inline=True)
        e.add_field(name="This month", value=f"**{s['month']:,}**", inline=True)
        e.add_field(name="This year", value=f"**{s['year']:,}**", inline=True)
        e.set_footer(text="Week = Mon-Sun (UTC) • Counts start when the bot started tracking - messages sent before that aren't counted.")
        await i.response.send_message(embed=e)

async def setup(bot): await bot.add_cog(Messages(bot))
