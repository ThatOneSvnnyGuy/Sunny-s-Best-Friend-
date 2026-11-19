"""Economy - coins, daily, work, slots, coinflip."""
import discord, random
from discord.ext import commands
from discord import app_commands
import database

class Economy(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="balance", description="Check your coins")
    async def balance(self, i: discord.Interaction, member: discord.Member = None):
        m = member or i.user
        await i.response.send_message(f"💰 {m.mention} has **{database.get_balance(i.guild_id, m.id)}** coins")
    @app_commands.command(name="daily", description="Claim 100 daily coins")
    async def daily(self, i: discord.Interaction):
        database.add_balance(i.guild_id, i.user.id, 100)
        await i.response.send_message(f"💰 +100 coins! Balance: **{database.get_balance(i.guild_id, i.user.id)}**")
    @app_commands.command(name="work", description="Work for coins")
    async def work(self, i: discord.Interaction):
        amt = random.randint(20, 80)
        database.add_balance(i.guild_id, i.user.id, amt)
        jobs = ["flipped burgers", "mowed a lawn", "delivered wings", "washed cars", "streamed on Twitch"]
        await i.response.send_message(f"💼 You {random.choice(jobs)} and earned **{amt}** coins!")
    @app_commands.command(name="coinflip", description="Bet coins on a coinflip")
    async def coinflip(self, i: discord.Interaction, bet: int, choice: str = "heads"):
        bal = database.get_balance(i.guild_id, i.user.id)
        if bet <= 0 or bet > bal:
            await i.response.send_message(f"You don't have that many coins. Balance: {bal}", ephemeral=True); return
        result = random.choice(["heads", "tails"])
        if result == choice.lower():
            database.add_balance(i.guild_id, i.user.id, bet)
            await i.response.send_message(f"🪙 **{result}** - You won **{bet}** coins!")
        else:
            database.add_balance(i.guild_id, i.user.id, -bet)
            await i.response.send_message(f"🪙 **{result}** - You lost **{bet}** coins.")
    @app_commands.command(name="slots", description="Slot machine - bet coins")
    async def slots(self, i: discord.Interaction, bet: int):
        bal = database.get_balance(i.guild_id, i.user.id)
        if bet <= 0 or bet > bal:
            await i.response.send_message(f"You don't have that many coins. Balance: {bal}", ephemeral=True); return
        emojis = ["🍒","🍋","⭐","🔔","💎"]
        r = [random.choice(emojis) for _ in range(3)]
        if len(set(r)) == 1:
            win = bet * 5; database.add_balance(i.guild_id, i.user.id, win)
            await i.response.send_message(f"{' '.join(r)}\n🎉 JACKPOT! +{win} coins!")
        elif len(set(r)) == 2:
            database.add_balance(i.guild_id, i.user.id, bet)
            await i.response.send_message(f"{' '.join(r)}\nNice - you won {bet} coins back!")
        else:
            database.add_balance(i.guild_id, i.user.id, -bet)
            await i.response.send_message(f"{' '.join(r)}\nYou lost {bet} coins.")

async def setup(bot): await bot.add_cog(Economy(bot))
