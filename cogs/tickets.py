"""Tickets + Ticket-Close Rating.
Flow: /setup-tickets -> user clicks Create Ticket -> staff Claim -> Close
-> ticket locks, owner gets a 1-5 star rating prompt IN the ticket + DM
-> rating saves to SQLite, posts to rating-log channel, then channel deletes.
One rating per ticket. Staff is whoever claimed (or closer if unclaimed).
"""
import asyncio, discord
from discord.ext import commands
from discord import app_commands
import database

# pending star choice while feedback modal is open: (channel_id, user_id) -> stars
_pending = {}

def stars_text(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)

class FeedbackModal(discord.ui.Modal, title="Rate your support"):
    feedback = discord.ui.TextInput(label="Any feedback? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=500, placeholder="What went well / what could be better?")
    def __init__(self, stars: int, channel_id: int, staff_id):
        super().__init__(); self.stars = stars; self.channel_id = channel_id; self.staff_id = staff_id
    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ticket = database.get_ticket(self.channel_id)
        if not ticket:
            await interaction.response.send_message("This ticket is already gone.", ephemeral=True); return
        ok = database.add_rating(guild.id, self.channel_id, interaction.user.id, self.staff_id, self.stars, str(self.feedback) or "")
        if not ok:
            await interaction.response.send_message("You already rated this ticket.", ephemeral=True); return
        await interaction.response.send_message(f"Thanks! You rated this ticket {stars_text(self.stars)} ({self.stars}/5).", ephemeral=True)
        # Log it
        s = database.get_settings(guild.id)
        log_id = s.get("rating_log_channel_id")
        if log_id:
            ch = guild.get_channel(log_id)
            if ch:
                staff_mention = f"<@{self.staff_id}>" if self.staff_id else "Unclaimed / no staff"
                avg, n = database.staff_average(guild.id, self.staff_id) if self.staff_id else (0, 0)
                e = discord.Embed(title="⭐ New Ticket Rating", color=discord.Color.gold())
                e.add_field(name="Rating", value=f"{stars_text(self.stars)} ({self.stars}/5)", inline=True)
                e.add_field(name="Rated by", value=interaction.user.mention, inline=True)
                e.add_field(name="Staff", value=staff_mention, inline=True)
                if self.staff_id: e.add_field(name="Staff average now", value=f"{avg} ⭐ from {n} rating(s)", inline=True)
                if str(self.feedback): e.add_field(name="Feedback", value=str(self.feedback), inline=False)
                await ch.send(embed=e)
        # Delete the ticket channel shortly after rating
        await asyncio.sleep(10)
        ch = guild.get_channel(self.channel_id)
        if ch:
            try: await ch.delete(reason="Ticket closed + rated")
            except Exception: pass

class RatingView(discord.ui.View):
    def __init__(self, channel_id: int, owner_id: int, staff_id):
        super().__init__(timeout=300)
        self.channel_id = channel_id; self.owner_id = owner_id; self.staff_id = staff_id
    async def _pick(self, interaction: discord.Interaction, stars: int):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the ticket owner can rate this ticket.", ephemeral=True); return
        if database.has_rated(self.channel_id, self.owner_id):
            await interaction.response.send_message("You already rated this ticket.", ephemeral=True); return
        await interaction.response.send_modal(FeedbackModal(stars, self.channel_id, self.staff_id))
    @discord.ui.button(label="⭐ 1", style=discord.ButtonStyle.secondary)
    async def s1(self, i, b): await self._pick(i, 1)
    @discord.ui.button(label="⭐⭐ 2", style=discord.ButtonStyle.secondary)
    async def s2(self, i, b): await self._pick(i, 2)
    @discord.ui.button(label="⭐⭐⭐ 3", style=discord.ButtonStyle.secondary)
    async def s3(self, i, b): await self._pick(i, 3)
    @discord.ui.button(label="⭐⭐⭐⭐ 4", style=discord.ButtonStyle.primary)
    async def s4(self, i, b): await self._pick(i, 4)
    @discord.ui.button(label="⭐⭐⭐⭐⭐ 5", style=discord.ButtonStyle.success)
    async def s5(self, i, b): await self._pick(i, 5)
    @discord.ui.button(label="Skip rating", style=discord.ButtonStyle.danger)
    async def skip(self, interaction, button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the ticket owner can skip.", ephemeral=True); return
        await interaction.response.send_message("No rating given. Closing ticket...", ephemeral=True)
        await asyncio.sleep(5)
        ch = interaction.guild.get_channel(self.channel_id)
        if ch:
            try: await ch.delete(reason="Ticket closed, rating skipped")
            except Exception: pass
    async def on_timeout(self):
        # No rating in 5 min - auto delete
        guild = None
        # find guild via bot cache is hard here, use stored channel lookup in cog task instead
        pass

class TicketControls(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🙋 Claim", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("Not a ticket channel.", ephemeral=True); return
        database.claim_ticket(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket! They'll help you now.", ephemeral=False)
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await close_ticket_flow(interaction.guild, interaction.channel, interaction.user)

async def close_ticket_flow(guild: discord.Guild, channel: discord.TextChannel, closer: discord.Member):
    """Lock the ticket, ask the owner to rate, then delete after rating/timeout."""
    t = database.get_ticket(channel.id)
    if not t:
        return
    owner_id = t["owner_id"]; staff_id = t.get("staff_id") or closer.id
    database.close_ticket(channel.id)
    owner = guild.get_member(owner_id)
    # Lock channel for owner (staff can still read)
    try:
        await channel.set_permissions(owner, send_messages=False, view_channel=True)
    except Exception: pass
    e = discord.Embed(
        title="🔒 Ticket Closed - How was your support?",
        description=f"{owner.mention if owner else 'Ticket owner'}, please rate your experience!\n\nYour rating goes to the staff member who helped you and shows on the staff leaderboard.\n\nYou have **5 minutes** to rate, then this channel deletes.",
        color=discord.Color.gold())
    e.add_field(name="Staff", value=f"<@{staff_id}>" if staff_id else "No staff claimed", inline=True)
    view = RatingView(channel.id, owner_id, staff_id)
    await channel.send(embed=e, view=view)
    # DM the owner too, in case they miss it
    if owner:
        try:
            await owner.send(embed=e, view=RatingView(channel.id, owner_id, staff_id))
        except Exception:
            pass
    # Auto-delete after 5 min if still there and not rated
    await asyncio.sleep(300)
    ch = guild.get_channel(channel.id)
    if ch and not database.has_rated(channel.id, owner_id):
        try: await ch.delete(reason="Ticket closed, rating window expired")
        except Exception: pass

class TicketPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.success, custom_id="create_ticket")
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        s = database.get_settings(guild.id)
        category = guild.get_channel(s.get("ticket_category_id")) if s.get("ticket_category_id") else None
        staff_role = guild.get_role(s.get("staff_role_id")) if s.get("staff_role_id") else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites, reason="Ticket created")
        database.create_ticket(channel.id, guild.id, interaction.user.id)
        e = discord.Embed(title=f"🎫 Ticket - {interaction.user}", description="Thanks for opening a ticket! Describe your issue and staff will be with you soon.\n\n**When this ticket closes, you'll be asked to rate your support 1-5 stars.**", color=discord.Color.blurple())
        await channel.send(f"{interaction.user.mention} {staff_role.mention if staff_role else ''}", embed=e, view=TicketControls())
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class Tickets(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="setup-tickets", description="Post the ticket panel (Admin only)")
    @app_commands.describe(staff_role="Role that can see / claim tickets", category="Category to put tickets in", rating_log_channel="Channel where ratings get posted")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction, staff_role: discord.Role, category: discord.CategoryChannel = None, rating_log_channel: discord.TextChannel = None):
        database.set_setting(interaction.guild_id, "staff_role_id", staff_role.id)
        if category: database.set_setting(interaction.guild_id, "ticket_category_id", category.id)
        if rating_log_channel: database.set_setting(interaction.guild_id, "rating_log_channel_id", rating_log_channel.id)
        e = discord.Embed(title="🎫 Need Help?", description="Click below to open a support ticket.\n\nWhen your ticket closes, you'll rate your support 1-5 ⭐ - that rating counts toward staff leaderboards.", color=discord.Color.blurple())
        await interaction.response.send_message(embed=e, view=TicketPanel())
    @app_commands.command(name="close", description="Close this ticket and ask the owner to rate it")
    async def close_cmd(self, interaction: discord.Interaction):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        await interaction.response.send_message("Closing ticket - asking the owner to rate...", ephemeral=True)
        await close_ticket_flow(interaction.guild, interaction.channel, interaction.user)
    @app_commands.command(name="claim", description="Claim this ticket")
    async def claim_cmd(self, interaction: discord.Interaction):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        database.claim_ticket(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket!")

async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketPanel())
    bot.add_view(TicketControls())
