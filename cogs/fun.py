"""Fun - 8ball, dice, jokes, memes, rps."""
import discord, random
from discord.ext import commands
from discord import app_commands

# SystemRandom = crypto-grade randomness (no seed, no repeating patterns).
_rng = random.SystemRandom()

# Huge answer pool so it never feels like the same few answers. Split so
# yes / no / maybe / chaotic all show up, and a rare 8-ball "glitch" answer.
_EIGHTBALL_YES = [
    "Yes.", "100% yes.", "Definitely.", "Absolutely.", "Without a doubt.",
    "All signs point to yes.", "It is certain.", "Most likely.", "Yes, and soon.",
    "Heck yes.", "Bet on it.", "The stars say yes.", "Yes — trust the vibe.",
    "For sure.", "No doubt about it.", "Yes, but don't tell anyone I told you.",
    "Obviously yes.", "Yes, yes, a thousand times yes.", "The ball has spoken: yes.",
]
_EIGHTBALL_NO = [
    "No.", "No chance.", "Don't count on it.", "Absolutely not.", "Very doubtful.",
    "My sources say no.", "Nope.", "Not in a million years.", "Hard pass.",
    "The ball says no.", "Not happening.", "No — and it laughed a little.",
    "Outlook not so good.", "Don't even think about it.", "No, no, no.",
    "The universe vetoed it.", "No way, José.", "Yeah... no.",
]
_EIGHTBALL_MAYBE = [
    "Maybe.", "Ask again later.", "Reply hazy, try again.", "Cannot predict now.",
    "Concentrate and ask again.", "Possibly.", "It's 50/50.", "Unclear — flip a coin.",
    "Maybe, if the wind is right.", "Ask me after lunch.", "The ball is buffering...",
    "Somewhere between yes and no.", "Leaning yes, but don't quote me.",
    "Leaning no, but anything can happen.", "Check back in five minutes.",
    "It's complicated.", "Only if you really want it.", "Time will tell.",
]
_EIGHTBALL_CHAOS = [
    "The 8-ball just shrugged.", "That's above my pay grade.",
    "I asked the other 8-balls. They said ask a human.",
    "Plot twist: the answer is a different question.",
    "Yes, but in another timeline.", "No, but in a funnier timeline yes.",
    "The ball rolled off the table. Try again.",
    "Error 8: too much mystery. Try again.",
    "The answer is hidden in your fridge.",
    "Ask your group chat, they'll know.",
]
_EIGHTBALL_ALL = _EIGHTBALL_YES + _EIGHTBALL_NO + _EIGHTBALL_MAYBE + _EIGHTBALL_CHAOS

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_8ball = {}  # user id -> last answer, so it never repeats twice in a row

    @app_commands.command(name="8ball", description="Ask the magic 8-ball")
    async def eightball(self, i: discord.Interaction, question: str):
        # 5% chance of a chaotic answer, otherwise a full random pick —
        # and never the same answer twice in a row for the same person.
        last = self._last_8ball.get(i.user.id)
        for _ in range(10):
            pool = _EIGHTBALL_CHAOS if _rng.random() < 0.05 else _EIGHTBALL_ALL
            answer = _rng.choice(pool)
            if answer != last:
                break
        self._last_8ball[i.user.id] = answer
        await i.response.send_message(f"🎱 **Q:** {question}\n**A:** {answer}")
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
