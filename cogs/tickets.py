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

# Every live rating view for a ticket (channel message + owner's DM), so one
# rating can instantly shut ALL of them down - no second chance to rate.
_rating_views = {}

def _register_view(channel_id, view):
    _rating_views.setdefault(channel_id, set()).add(view)

async def _close_all_rating_views(channel_id, stars=None):
    """Disable every rating view for this ticket (channel + DM) at once."""
    views = list(_rating_views.pop(channel_id, set()))
    for view in views:
        for child in view.children:
            child.disabled = True
        view.stop()
        msg = getattr(view, "message", None)
        if msg is not None:
            try:
                e = discord.Embed(
                    title="⭐ Rating received - thank you!",
                    description=f"You rated this ticket {stars_text(stars)} ({stars}/5)." if stars else "This ticket was closed with no rating.",
                    color=discord.Color.gold())
                await msg.edit(embed=e, view=view)
            except Exception:
                pass

def stars_text(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)

class FeedbackModal(discord.ui.Modal, title="Rate your support"):
    feedback = discord.ui.TextInput(label="Any feedback? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=500, placeholder="What went well / what could be better?")
    def __init__(self, stars: int, channel_id: int, staff_id):
        super().__init__(); self.stars = stars; self.channel_id = channel_id; self.staff_id = staff_id
    async def on_submit(self, interaction: discord.Interaction):
        ticket = database.get_ticket(self.channel_id)
        if not ticket:
            await interaction.response.send_message("This ticket is already gone.", ephemeral=True); return
        # In a DM, interaction.guild is None - resolve the guild from the ticket row instead
        guild_id = ticket["guild_id"]
        guild = interaction.guild or interaction.client.get_guild(guild_id)
        ok = database.add_rating(guild_id, self.channel_id, interaction.user.id, self.staff_id, self.stars, str(self.feedback) or "")
        if not ok:
            await interaction.response.send_message("You already rated this ticket.", ephemeral=True); return
        # Instantly close ALL rating opportunities for this ticket (channel + DM)
        await _close_all_rating_views(self.channel_id, self.stars)
        await interaction.response.send_message(f"Thanks! You rated this ticket {stars_text(self.stars)} ({self.stars}/5).", ephemeral=True)
        # Log it
        if guild is None:
            return
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
        self.message = None
        _register_view(channel_id, self)
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
        await _close_all_rating_views(self.channel_id, None)
        await interaction.response.send_message("No rating given. Closing ticket...", ephemeral=True)
        await asyncio.sleep(5)
        # In a DM, interaction.guild is None - resolve the guild from the ticket row instead
        ticket = database.get_ticket(self.channel_id)
        guild = interaction.guild or (interaction.client.get_guild(ticket["guild_id"]) if ticket else None)
        if guild is None:
            return
        ch = guild.get_channel(self.channel_id)
        if ch:
            try: await ch.delete(reason="Ticket closed, rating skipped")
            except Exception: pass
    async def on_timeout(self):
        # Rating window expired - shut every rating view for this ticket down
        _rating_views.pop(self.channel_id, None)
        for child in self.children:
            child.disabled = True
        if getattr(self, "message", None) is not None:
            try: await self.message.edit(view=self)
            except Exception: pass

class CloseReasonModal(discord.ui.Modal, title="Close ticket"):
    reason = discord.ui.TextInput(label="Reason for closing (optional)", style=discord.TextStyle.paragraph, required=False, max_length=300, placeholder="e.g. Issue resolved, duplicate ticket...")
    def __init__(self, channel_id: int):
        super().__init__(); self.channel_id = channel_id
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Closing ticket - asking the owner to rate...", ephemeral=True)
        await close_ticket_flow(interaction.guild, interaction.channel, interaction.user, str(self.reason) or None)

class AddUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(placeholder="Choose a user to add to this ticket...", custom_id="ticket_add_user_select", min_values=1, max_values=1)
    async def callback(self, interaction: discord.Interaction):
        await add_user_to_ticket(interaction, self.values[0])

class AddUserSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.add_item(AddUserSelect())

def _can_manage_ticket(guild: discord.Guild, member: discord.Member, ticket):
    """Who can add/remove people in a ticket: STAFF ONLY. The member who
    opened the ticket cannot add people — they have to be staff
    (the staff role, or Manage Channels / Administrator)."""
    if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
        return True
    s = database.get_settings(guild.id)
    role_id = s.get("staff_role_id")
    if role_id and any(r.id == role_id for r in getattr(member, "roles", [])):
        return True
    return False

async def add_user_to_ticket(interaction: discord.Interaction, user: discord.Member):
    t = database.get_ticket(interaction.channel_id)
    if not t:
        await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
    if not _can_manage_ticket(interaction.guild, interaction.user, t):
        await interaction.response.send_message("Only staff can add people to this ticket.", ephemeral=True); return
    if user.id == t["owner_id"]:
        await interaction.response.send_message(f"{user.mention} is the ticket owner — they're already here.", ephemeral=True); return
    await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
    await interaction.response.send_message(f"✅ Added {user.mention} to this ticket.", ephemeral=True)
    try: await interaction.channel.send(f"➕ {user.mention} was added to this ticket by {interaction.user.mention}.")
    except Exception: pass

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
    @discord.ui.button(label="➕ Add User", style=discord.ButtonStyle.secondary, custom_id="ticket_add_user")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Pick a user to add to this ticket:", view=AddUserSelectView(), ephemeral=True)
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CloseReasonModal(interaction.channel_id))

async def close_ticket_flow(guild: discord.Guild, channel: discord.TextChannel, closer: discord.Member, reason: str = None):
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
    e.add_field(name="Opened by", value=f"<@{owner_id}>", inline=True)
    if reason:
        e.add_field(name="Close reason", value=reason, inline=False)
    view = RatingView(channel.id, owner_id, staff_id)
    msg = await channel.send(embed=e, view=view)
    view.message = msg
    # DM the owner too, in case they miss it
    if owner:
        try:
            dm_view = RatingView(channel.id, owner_id, staff_id)
            dm_msg = await owner.send(embed=e, view=dm_view)
            dm_view.message = dm_msg
        except Exception:
            pass
    # Auto-delete after 5 min if still there and not rated
    await asyncio.sleep(300)
    ch = guild.get_channel(channel.id)
    if ch and not database.has_rated(channel.id, owner_id):
        try: await ch.delete(reason="Ticket closed, rating window expired")
        except Exception: pass

TOPICS = [
    ("general", "💬 General Help", "I need help with something", None),
    ("report", "🚨 Report a Player", "Report someone breaking the rules", None),
    ("bug", "🐛 Bug Report", "Something in the server / bot is broken", None),
    ("billing", "💳 Billing / Purchase", "Help with a purchase, order or payment", None),
    ("appeal", "⚖️ Appeal a Punishment", "Appeal a ban, timeout or warning", None),
    ("other", "✨ Something Else", "Anything that doesn't fit above", None),
]

def _slug(text: str) -> str:
    """Make a string safe for a Discord channel name."""
    out = "".join(ch if ch.isalnum() else "-" for ch in (text or "").lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "ticket"

def panel_menus(guild_id):
    """The ticket panel's dropdown menus, in order. Each menu is
    (slot, title, placeholder, [(value, label, description, emoji)]).
    There is NO cap on the number of menus — Discord only allows 5
    dropdowns per message, so the panel is split into pages of 5
    (see TicketPanel / panel_pages). Slot 1 keeps the historic custom_id
    so panels already posted keep working. With no templates, slot 1
    is the built-in topics."""
    if not guild_id:
        # Generic view for restart persistence: slot 1 has the built-in
        # topics, slots 2-5 exist only so their interactions still dispatch
        # (real values come from the interaction, not the registered options).
        menus = [(1, "What do you need help with?", "What do you need help with? Pick one...", TOPICS)]
        for slot in (2, 3, 4, 5):
            menus.append((slot, f"Menu {slot}", "Pick one...", [("none", "—", "No options in this menu yet", None)]))
        return menus
    menus = database.ensure_ticket_menus(guild_id)
    templates = database.list_ticket_templates(guild_id)
    by_menu = {}
    for t in templates:
        by_menu.setdefault(t.get("menu_id") or menus[0]["id"], []).append(t)
    out = []
    for i, m in enumerate(menus, start=1):
        opts = []
        for t in by_menu.get(m["id"], []):
            emoji = t.get("emoji") or None
            if emoji and len(emoji) > 4:
                emoji = None  # custom <:name:id> emoji aren't usable in select options
            opts.append((f"tpl_{t['id']}", t["name"][:100], (t.get("description") or "")[:100], emoji))
        if i == 1 and not opts:
            opts = list(TOPICS)
        if not opts:
            opts = [("none", "—", "No options in this menu yet", None)]
        out.append((i, m["title"], m.get("placeholder") or m["title"], opts))
    return out

def panel_pages(guild_id):
    """How many panel messages the guild's menus need (5 dropdowns max per message)."""
    import math
    return max(1, math.ceil(len(panel_menus(guild_id)) / 5))

# (guild_id, page) pairs whose persistent views are already registered,
# so reconnects don't register the same views twice.
_registered_panel_views = set()

def register_panel_views(bot, guild_id):
    """Register this guild's panel pages as persistent views, so the
    dropdowns keep working after a bot restart."""
    for page in range(panel_pages(guild_id)):
        key = (guild_id, page)
        if key in _registered_panel_views:
            continue
        bot.add_view(TicketPanel(guild_id, page))
        _registered_panel_views.add(key)

def panel_embed_settings(guild_id):
    """Panel embed title / description / color, with defaults."""
    s = database.get_settings(guild_id) if guild_id else {}
    title = s.get("ticket_panel_title") or "🎫 Need Help?"
    desc = s.get("ticket_panel_description") or ("Need help? Open a ticket below and our staff team will help you.\n\n"
        "**How it works**\n"
        "• Pick a topic from the menu below\n"
        "• Describe your issue in the ticket\n"
        "• A staff member will claim it and help you\n\n"
        "When your ticket closes, you'll be asked to rate your support 1–5 ⭐.")
    color = s.get("ticket_panel_color") or 5793266
    return title, desc, color

class TicketMenuSelect(discord.ui.Select):
    def __init__(self, slot, guild_id=None, options=None, placeholder="Pick one..."):
        opts = options if options is not None else TOPICS
        # Slot 1 keeps the original custom_id so old posted panels still work.
        custom_id = "ticket_topic_select" if slot == 1 else f"ticket_menu_{slot}"
        super().__init__(
            placeholder=placeholder[:150],
            custom_id=custom_id,
            options=[discord.SelectOption(label=label, value=value, description=desc, emoji=emoji) for value, label, desc, emoji in opts],
        )
    async def callback(self, interaction: discord.Interaction):
        topic = self.values[0]
        if topic == "none":
            await interaction.response.send_message("That menu has no options yet — ask an admin to add some in the dashboard.", ephemeral=True); return
        label = topic
        if interaction.guild_id:
            for _, _, _, opts in panel_menus(interaction.guild_id):
                for v, l, _, _ in opts:
                    if v == topic:
                        label = l
        await create_ticket_for(interaction, topic, label)

async def create_ticket_for(interaction: discord.Interaction, topic: str, label: str):
    guild = interaction.guild
    s = database.get_settings(guild.id)
    # A dashboard template can override the staff role / category / ticket name for its own tickets
    tpl = None
    if topic.startswith("tpl_"):
        try: tpl = database.get_ticket_template(int(topic[4:]), guild.id)
        except Exception: tpl = None
    category = guild.get_channel((tpl or {}).get("category_id") or s.get("ticket_category_id")) if ((tpl or {}).get("category_id") or s.get("ticket_category_id")) else None
    staff_role = guild.get_role((tpl or {}).get("staff_role_id") or s.get("staff_role_id")) if ((tpl or {}).get("staff_role_id") or s.get("staff_role_id")) else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    prefix = _slug((tpl or {}).get("ticket_prefix") or "")
    slug = topic.replace("_", "-")
    name = f"{prefix}-{_slug(interaction.user.name)}" if prefix else f"ticket-{_slug(slug)}-{_slug(interaction.user.name)}"
    channel = await guild.create_text_channel(name[:100], category=category, overwrites=overwrites,
        topic=f"Ticket opened by {interaction.user} • {label}"[:1024], reason=f"Ticket created: {label}")
    database.create_ticket(channel.id, guild.id, interaction.user.id)
    log_id = s.get("ticket_log_channel_id")
    if log_id:
        log_ch = guild.get_channel(log_id)
        if log_ch:
            try: await log_ch.send(f"🎫 New ticket {channel.mention} opened by {interaction.user.mention} — **{label}** {staff_role.mention if staff_role else ''}")
            except Exception: pass
    e = discord.Embed(title=f"Ticket — {label}",
        description=f"{interaction.user.mention}, thanks for opening a ticket. A member of staff will be with you shortly.",
        color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
    e.add_field(name="Opened by", value=interaction.user.mention, inline=True)
    e.add_field(name="Topic", value=label, inline=True)
    e.add_field(name="What happens next",
        value="• Describe your issue in as much detail as you can\n"
              "• Staff will claim this ticket when they're available\n"
              "• When it closes, you'll rate your support 1–5 ⭐",
        inline=False)
    e.set_footer(text="Sunny's Best Friend • Ticket System")
    await channel.send(f"{interaction.user.mention} {staff_role.mention if staff_role else ''}", embed=e, view=TicketControls())
    await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketPanel(discord.ui.View):
    def __init__(self, guild_id=None, page=0):
        super().__init__(timeout=None)
        for slot, _title, placeholder, opts in panel_menus(guild_id)[page * 5:(page + 1) * 5]:
            self.add_item(TicketMenuSelect(slot, guild_id, opts, placeholder))

class Tickets(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @app_commands.command(name="setup-tickets", description="Set up tickets - pick exactly where everything goes (Admin only)")
    @app_commands.describe(
        staff_role="Role that can see / claim tickets",
        panel_channel="Channel the ticket panel is posted in",
        rating_log_channel="Channel ratings get posted to when a ticket closes",
        ticket_log_channel="Channel new-ticket alerts go to (staff get pinged there)",
        category="Category to put new ticket channels in")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_tickets(self, interaction: discord.Interaction, staff_role: discord.Role, panel_channel: discord.TextChannel, rating_log_channel: discord.TextChannel, ticket_log_channel: discord.TextChannel, category: discord.CategoryChannel = None):
        database.set_setting(interaction.guild_id, "staff_role_id", staff_role.id)
        database.set_setting(interaction.guild_id, "panel_channel_id", panel_channel.id)
        database.set_setting(interaction.guild_id, "rating_log_channel_id", rating_log_channel.id)
        database.set_setting(interaction.guild_id, "ticket_log_channel_id", ticket_log_channel.id)
        if category: database.set_setting(interaction.guild_id, "ticket_category_id", category.id)
        title, desc, color = panel_embed_settings(interaction.guild_id)
        e = discord.Embed(title=title, description=desc, color=color)
        e.set_footer(text="Sunny's Best Friend • Ticket System")
        pages = panel_pages(interaction.guild_id)
        for page in range(pages):
            await panel_channel.send(embed=e, view=TicketPanel(interaction.guild_id, page))
        register_panel_views(self.bot, interaction.guild_id)
        await interaction.response.send_message(
            f"✅ Tickets set up:\n"
            f"• Panel posted in {panel_channel.mention}\n"
            f"• Staff role: {staff_role.mention}\n"
            f"• Ratings go to {rating_log_channel.mention}\n"
            f"• New-ticket alerts go to {ticket_log_channel.mention}\n"
            f"• Ticket channels go in {category.mention if category else 'no category'}", ephemeral=True)
    @app_commands.command(name="close", description="Close this ticket and ask the owner to rate it")
    async def close_cmd(self, interaction: discord.Interaction):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        await interaction.response.send_modal(CloseReasonModal(interaction.channel_id))
    @app_commands.command(name="claim", description="Claim this ticket")
    async def claim_cmd(self, interaction: discord.Interaction):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        database.claim_ticket(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket!")
    @app_commands.command(name="add", description="Add someone to this ticket")
    @app_commands.describe(user="The person to add to this ticket")
    async def add_cmd(self, interaction: discord.Interaction, user: discord.Member):
        await add_user_to_ticket(interaction, user)
    @app_commands.command(name="remove", description="Remove someone from this ticket")
    @app_commands.describe(user="The person to remove from this ticket")
    async def remove_cmd(self, interaction: discord.Interaction, user: discord.Member):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        if not _can_manage_ticket(interaction.guild, interaction.user, t):
            await interaction.response.send_message("Only staff can remove people from this ticket.", ephemeral=True); return
        if user.id == t["owner_id"]:
            await interaction.response.send_message("You can't remove the ticket owner.", ephemeral=True); return
        if user.id == interaction.guild.me.id:
            await interaction.response.send_message("You can't remove me from the ticket.", ephemeral=True); return
        await interaction.channel.set_permissions(user, overwrite=None)
        await interaction.response.send_message(f"Removed {user.mention} from this ticket.")

async def setup(bot):
    await bot.add_cog(Tickets(bot))
    bot.add_view(TicketPanel())
    bot.add_view(TicketControls())
