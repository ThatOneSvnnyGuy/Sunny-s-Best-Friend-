"""Faith - Daily prayers + Bible verses for Sunny's Best Friend.
Daily verse + prayer auto-posts at 9:00 AM Central to the faith channel
set with /set-faith-channel. All verses are KJV (public domain).
"""
import discord, random, datetime
from discord.ext import commands, tasks
from discord import app_commands
from zoneinfo import ZoneInfo
import database

CENTRAL = ZoneInfo("America/Chicago")

VERSES = [
    ("John 3:16", "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life."),
    ("Psalm 23:1", "The LORD is my shepherd; I shall not want."),
    ("Philippians 4:13", "I can do all things through Christ which strengtheneth me."),
    ("Jeremiah 29:11", "For I know the thoughts that I think toward you, saith the LORD, thoughts of peace, and not of evil, to give you an expected end."),
    ("Proverbs 3:5-6", "Trust in the LORD with all thine heart; and lean not unto thine own understanding. In all thy ways acknowledge him, and he shall direct thy paths."),
    ("Psalm 46:1", "God is our refuge and strength, a very present help in trouble."),
    ("Isaiah 41:10", "Fear thou not; for I am with thee: be not dismayed; for I am thy God: I will strengthen thee; yea, I will help thee."),
    ("Romans 8:28", "And we know that all things work together for good to them that love God, to them who are the called according to his purpose."),
    ("Psalm 27:1", "The LORD is my light and my salvation; whom shall I fear? the LORD is the strength of my life; of whom shall I be afraid?"),
    ("Matthew 11:28", "Come unto me, all ye that labour and are heavy laden, and I will give you rest."),
    ("Joshua 1:9", "Be strong and of a good courage; be not afraid, neither be thou dismayed: for the LORD thy God is with thee whithersoever thou goest."),
    ("Psalm 118:24", "This is the day which the LORD hath made; we will rejoice and be glad in it."),
    ("1 Corinthians 16:14", "Let all your things be done with charity."),
    ("Galatians 5:22-23", "But the fruit of the Spirit is love, joy, peace, longsuffering, gentleness, goodness, faith, meekness, temperance."),
    ("Psalm 37:4", "Delight thyself also in the LORD; and he shall give thee the desires of thine heart."),
    ("Matthew 6:33", "But seek ye first the kingdom of God, and his righteousness; and all these things shall be added unto you."),
    ("Hebrews 11:1", "Now faith is the substance of things hoped for, the evidence of things not seen."),
    ("Psalm 34:18", "The LORD is nigh unto them that are of a broken heart; and saveth such as be of a contrite spirit."),
    ("2 Timothy 1:7", "For God hath not given us the spirit of fear; but of power, and of love, and of a sound mind."),
    ("Lamentations 3:22-23", "It is of the LORD's mercies that we are not consumed, because his compassions fail not. They are new every morning: great is thy faithfulness."),
    ("Psalm 19:1", "The heavens declare the glory of God; and the firmament sheweth his handywork."),
    ("John 14:27", "Peace I leave with you, my peace I give unto you: not as the world giveth, give I unto you. Let not your heart be troubled, neither let it be afraid."),
    ("Romans 15:13", "Now the God of hope fill you with all joy and peace in believing, that ye may abound in hope, through the power of the Holy Ghost."),
    ("Psalm 119:105", "Thy word is a lamp unto my feet, and a light unto my path."),
    ("1 Peter 5:7", "Casting all your care upon him; for he careth for you."),
]

PRAYERS = {
    "morning": ("Morning Prayer", "Lord, thank You for this new day. Guide my steps, guard my words, and help me love others like You love me. Give me strength for what today brings. Amen."),
    "night": ("Night Prayer", "Lord, thank You for getting me through today. Forgive me where I fell short, calm my mind, and watch over me and the people I love tonight. Amen."),
    "strength": ("Prayer for Strength", "God, I feel weak right now. Please give me strength I don't have on my own, courage to keep going, and peace knowing You're with me. Amen."),
    "peace": ("Prayer for Peace", "Lord, quiet my anxious thoughts. Fill my heart with Your peace, help me let go of what I can't control, and trust You with it all. Amen."),
    "gratitude": ("Prayer of Gratitude", "Thank You, God, for my family, my friends, my home, and every good thing I sometimes take for granted. Help me notice Your blessings today. Amen."),
    "healing": ("Prayer for Healing", "Lord, please bring healing and comfort to those who are hurting, sick, or grieving. Be close to them, give them rest, and give us hope. Amen."),
    "general": ("A Simple Prayer", "Dear God, thank You for loving me. Help me today to be kind, honest, and brave. Bless my family and friends, and lead me in Your way. Amen."),
}

def verse_for_today():
    # Same verse for everyone on the same day
    day = datetime.date.today().toordinal()
    return VERSES[day % len(VERSES)]

class Faith(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Start the daily loop only once the bot is actually logged in / ready.
        # Starting it in __init__ fails when the client isn't initialised yet.
        if not self.daily_post.is_running():
            self.daily_post.start()

    def cog_unload(self):
        self.daily_post.cancel()

    def _daily_embeds(self):
        ref, text = verse_for_today()
        title, prayer = list(PRAYERS.values())[datetime.date.today().toordinal() % len(PRAYERS)]
        verse_e = discord.Embed(title=f"📖 Daily Verse — {ref}", description=text, color=discord.Color.gold())
        verse_e.set_footer(text="Sunny's Best Friend • Daily verse")
        prayer_e = discord.Embed(title=f"🙏 Daily Prayer — {title}", description=prayer, color=discord.Color.gold())
        prayer_e.set_footer(text="Sunny's Best Friend • Daily prayer")
        return verse_e, prayer_e

    async def _post_daily(self, guild):
        """Post today's verse + prayer to this server's configured channels.
        Verse and prayer can go to different channels; both fall back to
        the main faith channel. Returns True if anything was posted."""
        s = database.get_settings(guild.id)
        main_id = s.get("faith_channel_id")
        verse_id = s.get("faith_verse_channel_id") or main_id
        prayer_id = s.get("faith_prayer_channel_id") or main_id
        if not verse_id and not prayer_id:
            return False
        verse_e, prayer_e = self._daily_embeds()
        posted = False
        if verse_id:
            ch = guild.get_channel(verse_id)
            if ch:
                try:
                    await ch.send(embed=verse_e); posted = True
                except Exception:
                    pass
        if prayer_id:
            ch = guild.get_channel(prayer_id)
            if ch and ch.id != verse_id:
                try:
                    await ch.send(embed=prayer_e); posted = True
                except Exception:
                    pass
            elif ch and ch.id == verse_id:
                # Same channel for both: post the prayer as a second message.
                try:
                    await ch.send(embed=prayer_e); posted = True
                except Exception:
                    pass
        return posted

    @tasks.loop(minutes=30)
    async def daily_post(self):
        # Runs every 30 min and posts once per day, in the hour each server
        # chose (default 9 AM Central). The date guard stops double-posts
        # even if the bot restarts mid-hour.
        now = datetime.datetime.now(CENTRAL)
        today = now.strftime("%Y-%m-%d")
        for guild in self.bot.guilds:
            s = database.get_settings(guild.id)
            if not (s.get("faith_channel_id") or s.get("faith_verse_channel_id") or s.get("faith_prayer_channel_id")):
                continue
            hour = s.get("faith_hour")
            hour = hour if isinstance(hour, int) else 9
            if now.hour != hour:
                continue
            if s.get("faith_last_posted") == today:
                continue
            if await self._post_daily(guild):
                database.set_setting(guild.id, "faith_last_posted", today)

    @daily_post.before_loop
    async def _wait(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="setup-faith", description="Set up daily verse + prayer — pick the channels and the time, like tickets (Admin)")
    @app_commands.describe(
        channel="Main channel for the daily verse + prayer",
        verse_channel="Optional: separate channel just for the verse",
        prayer_channel="Optional: separate channel just for the prayer",
        hour="What hour (Central, 0-23) it posts — default 9 AM")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_faith(self, i: discord.Interaction, channel: discord.TextChannel,
                          verse_channel: discord.TextChannel = None,
                          prayer_channel: discord.TextChannel = None,
                          hour: int = 9):
        if hour < 0 or hour > 23:
            await i.response.send_message("Hour has to be 0-23 (Central time).", ephemeral=True); return
        database.set_setting(i.guild_id, "faith_channel_id", channel.id)
        database.set_setting(i.guild_id, "faith_hour", hour)
        if verse_channel:
            database.set_setting(i.guild_id, "faith_verse_channel_id", verse_channel.id)
        if prayer_channel:
            database.set_setting(i.guild_id, "faith_prayer_channel_id", prayer_channel.id)
        verse_dest = verse_channel.mention if verse_channel else channel.mention
        prayer_dest = prayer_channel.mention if prayer_channel else channel.mention
        when = f"{hour}:00 {'AM' if hour < 12 else 'PM'} Central"
        if hour == 0: when = "12:00 AM Central"
        elif hour == 12: when = "12:00 PM Central"
        elif hour > 12: when = f"{hour - 12}:00 PM Central"
        elif hour < 12: when = f"{hour}:00 AM Central"
        # Post a sample right now so you can see it works, like the ticket panel.
        verse_e, prayer_e = self._daily_embeds()
        try:
            dest = i.guild.get_channel((verse_channel.id if verse_channel else channel.id))
            if dest: await dest.send(embed=verse_e)
            dest2 = i.guild.get_channel((prayer_channel.id if prayer_channel else channel.id))
            if dest2: await dest2.send(embed=prayer_e)
        except Exception:
            pass
        await i.response.send_message(
            f"🙏 Daily verse + prayer set up:\n"
            f"• Verse goes to {verse_dest}\n"
            f"• Prayer goes to {prayer_dest}\n"
            f"• Every day at {when}\n"
            f"(I just posted a sample in each channel so you can see it.)", ephemeral=True)

    @app_commands.command(name="disable-faith", description="Turn off the daily verse + prayer posts (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def disable_faith(self, i: discord.Interaction):
        for key in ("faith_channel_id", "faith_verse_channel_id", "faith_prayer_channel_id"):
            database.set_setting(i.guild_id, key, None)
        await i.response.send_message("🙏 Daily verse + prayer turned off. Run `/setup-faith` to turn it back on.", ephemeral=True)

    @app_commands.command(name="verse", description="Get a random Bible verse")
    async def verse(self, i: discord.Interaction):
        ref, text = random.choice(VERSES)
        e = discord.Embed(title=f"📖 {ref}", description=text, color=discord.Color.gold())
        await i.response.send_message(embed=e)

    @app_commands.command(name="dailyverse", description="Today's Bible verse")
    async def dailyverse(self, i: discord.Interaction):
        ref, text = verse_for_today()
        e = discord.Embed(title=f"📖 Today's Verse - {ref}", description=text, color=discord.Color.gold())
        await i.response.send_message(embed=e)

    @app_commands.command(name="prayer", description="Get a prayer (morning, night, strength, peace, gratitude, healing)")
    @app_commands.describe(kind="morning / night / strength / peace / gratitude / healing")
    async def prayer(self, i: discord.Interaction, kind: str = "general"):
        title, text = PRAYERS.get(kind.lower(), PRAYERS["general"])
        e = discord.Embed(title=f"🙏 {title}", description=text, color=discord.Color.gold())
        await i.response.send_message(embed=e)

    @app_commands.command(name="pray", description="Ask for prayer - posts your request for others to pray for")
    async def pray(self, i: discord.Interaction, request: str):
        s = database.get_settings(i.guild_id)
        ch_id = s.get("faith_channel_id")
        e = discord.Embed(title="🙏 Prayer Request", description=request, color=discord.Color.gold())
        e.add_field(name="From", value=i.user.mention)
        e.set_footer(text="React 🙏 to let them know you're praying for them.")
        if ch_id:
            ch = i.guild.get_channel(ch_id)
            if ch:
                msg = await ch.send(embed=e); await msg.add_reaction("🙏")
                await i.response.send_message(f"Posted your prayer request in {ch.mention} 🙏", ephemeral=True); return
        await i.response.send_message(embed=e)

    @app_commands.command(name="set-faith-channel", description="Set where daily verse + prayer posts (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_faith(self, i: discord.Interaction, channel: discord.TextChannel):
        database.set_setting(i.guild_id, "faith_channel_id", channel.id)
        await i.response.send_message(f"🙏 Daily verse + prayer will post in {channel.mention} every day at 9:00 AM Central.")

async def setup(bot):
    await bot.add_cog(Faith(bot))
