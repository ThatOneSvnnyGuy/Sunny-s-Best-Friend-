"""Fun - 8ball, dice, jokes, memes, rps."""
import discord, random
from discord.ext import commands
from discord import app_commands

class Fun(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="8ball", description="Ask the magic 8-ball")
    async def eightball(self, i: discord.Interaction, question: str):
        answers = ["Yes.", "No.", "Maybe.", "Definitely.", "Ask again later.", "No chance.", "100% yes.", "Don't count on it."]
        await i.response.send_message(f"🎱 **Q:** {question}\n**A:** {random.choice(answers)}")
    @app_commands.command(name="dice", description="Roll a dice")
    async def dice(self, i: discord.Interaction, sides: int = 6):
        await i.response.send_message(f"🎲 You rolled **{random.randint(1, sides)}** (1-{sides})")
    @app_commands.command(name="rps", description="Rock Paper Scissors")
    async def rps(self, i: discord.Interaction, choice: str):
        bot_choice = random.choice(["rock","paper","scissors"])
        c = choice.lower()
        if c not in ["rock","paper","scissors"]:
            await i.response.send_message("Pick rock, paper, or scissors.", ephemeral=True); return
        win = {"rock":"scissors","paper":"rock","scissors":"paper"}
        result = "Tie!" if c==bot_choice else ("You win! 🎉" if win[c]==bot_choice else "I win! 😎")
        await i.response.send_message(f"You: {c} | Me: {bot_choice} - **{result}**")
    @app_commands.command(name="joke", description="Random joke")
    async def joke(self, i: discord.Interaction):
        jokes = ["Why did the scarecrow win an award? He was outstanding in his field.", "I told my computer I needed a break, now it won't stop sending me KitKat ads.", "Why don't skeletons fight? They don't have the guts."]
        await i.response.send_message(f"😂 {random.choice(jokes)}")
    @app_commands.command(name="hug", description="Hug someone")
    async def hug(self, i: discord.Interaction, member: discord.Member):
        await i.response.send_message(f"🤗 {i.user.mention} hugs {member.mention}!")

async def setup(bot): await bot.add_cog(Fun(bot))
