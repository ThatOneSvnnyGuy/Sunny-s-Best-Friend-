"""Tickets + Ticket-Close Rating.
Flow: /setup-tickets -> user clicks Create Ticket -> staff Claim -> Close
-> ticket locks, owner gets a 1-5 star rating prompt IN the ticket + DM
-> rating saves to SQLite, posts to rating-log channel, then channel deletes.
One rating per ticket. Staff is whoever claimed (or closer if unclaimed).
"""
import asyncio, discord, io, time
from discord.ext import commands
from discord import app_commands
import database

# pending star choice while feedback modal is open: (channel_id, user_id) -> stars
_pending = {}

# Tickets already being finished (transcript + delete) — stops the rated,
# skipped and 5-minute-timeout paths from all trying to close one ticket.
_closing = set()

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

async def _build_transcript(channel, header_lines):
    """The ticket's actual transcript: every message in the channel,
    oldest first, as a .txt file. Attachments are listed by URL."""
    lines = list(header_lines) + ["", "— Messages —"]
    count = 0
    try:
        async for m in channel.history(limit=1000, oldest_first=True):
            count += 1
            ts = m.created_at.strftime("%Y-%m-%d %H:%M")
            text = (m.content or "").strip()
            if not text:
                if m.embeds:
                    text = f"[embed: {m.embeds[0].title or 'untitled'}]"
                elif m.stickers:
                    text = f"[sticker: {m.stickers[0].name}]"
                else:
                    text = "[no text]"
            lines.append(f"[{ts}] {m.author} ({m.author.id}): {text}")
            for a in m.attachments:
                lines.append(f"    [attachment: {a.url}]")
    except Exception as e:
        lines.append(f"[couldn't read the rest of the history: {e}]")
    if count >= 1000:
        lines.append("[showing the first 1000 messages]")
    data = "\n".join(lines).encode("utf-8", "replace")
    return discord.File(io.BytesIO(data), filename=f"transcript-{channel.name}.txt")

async def _finish_ticket(guild, channel, *, owner_id, staff_id, label, reason, rating_text):
    """Finish a closed ticket, once: send its transcript to the ticket-log
    channel, then delete the channel. Never fails the close — if the
    transcript can't be sent, the channel still gets deleted."""
    if channel is None or channel.id in _closing:
        return
    _closing.add(channel.id)
    try:
        s = database.get_settings(guild.id) if guild else {}
        log_id = s.get("ticket_log_channel_id")
        header = [
            f"Ticket transcript — #{channel.name}",
            f"Type: {label or 'Ticket'}",
            f"Opened by: <@{owner_id}>",
            f"Staff: <@{staff_id}>" if staff_id else "Staff: no one claimed",
            f"Close reason: {reason}" if reason else "Close reason: —",
            f"Rating: {rating_text}",
            f"Closed: {time.strftime('%Y-%m-%d %H:%M')} UTC",
        ]
        if log_id and guild:
            log_ch = guild.get_channel(log_id)
            if log_ch:
                try:
                    f = await _build_transcript(channel, header)
                    await log_ch.send(
                        f"📄 Transcript for #{channel.name} ({label or 'ticket'}) — opened by <@{owner_id}>, "
                        f"staff <@{staff_id}> — {rating_text}" if staff_id else
                        f"📄 Transcript for #{channel.name} ({label or 'ticket'}) — opened by <@{owner_id}> — {rating_text}",
                        file=f)
                except Exception:
                    pass
    finally:
        try:
            await channel.delete(reason="Ticket closed")
        except Exception:
            pass
        _closing.discard(channel.id)

class FeedbackModal(discord.ui.Modal, title="Rate your support"):
    feedback = discord.ui.TextInput(label="Any feedback? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=500, placeholder="What went well / what could be better?")
    def __init__(self, stars: int, channel_id: int, staff_id, guild=None, channel=None, label=None, reason=None):
        super().__init__(); self.stars = stars; self.channel_id = channel_id; self.staff_id = staff_id
        self.guild = guild; self.channel = channel; self.label = label; self.reason = reason
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
        # Transcript + delete. The rating is just the staff member's overall
        # rating — their average and count — nothing else counts as a
        # "completion" for them.
        rating_text = f"{self.stars}/5 {stars_text(self.stars)}"
        if str(self.feedback):
            rating_text += f" — “{str(self.feedback)}”"
        channel = self.channel or guild.get_channel(self.channel_id)
        await _finish_ticket(guild, channel, owner_id=interaction.user.id, staff_id=self.staff_id,
                             label=self.label, reason=self.reason, rating_text=rating_text)

class RatingView(discord.ui.View):
    def __init__(self, channel_id: int, owner_id: int, staff_id, guild=None, channel=None, label=None, reason=None):
        super().__init__(timeout=300)
        self.channel_id = channel_id; self.owner_id = owner_id; self.staff_id = staff_id
        self.message = None
        # The guild/channel are kept on the view so Skip can always finish
        # the ticket, even from the DM where interaction.guild is None.
        self.guild = guild; self.channel = channel; self.label = label; self.reason = reason
        _register_view(channel_id, self)
    async def _pick(self, interaction: discord.Interaction, stars: int):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the ticket owner can rate this ticket.", ephemeral=True); return
        if database.has_rated(self.channel_id, self.owner_id):
            await interaction.response.send_message("You already rated this ticket.", ephemeral=True); return
        await interaction.response.send_modal(FeedbackModal(stars, self.channel_id, self.staff_id,
                                                            guild=self.guild, channel=self.channel,
                                                            label=self.label, reason=self.reason))
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
        # Answer first — nothing after this may stop the ticket closing.
        try:
            await interaction.response.send_message("No rating given. Closing ticket...", ephemeral=True)
        except Exception:
            pass
        await _close_all_rating_views(self.channel_id, None)
        # Skipping records NOTHING for the staff member — no rating, no
        # count, no "completion". The rating is only their overall average
        # when someone actually rates.
        guild = self.guild or interaction.guild
        channel = self.channel or (guild.get_channel(self.channel_id) if guild else None)
        if guild is None:
            ticket = database.get_ticket(self.channel_id)
            guild = interaction.client.get_guild(ticket["guild_id"]) if ticket else None
            channel = guild.get_channel(self.channel_id) if guild else None
        await _finish_ticket(guild, channel, owner_id=self.owner_id, staff_id=self.staff_id,
                             label=self.label, reason=self.reason,
                             rating_text="Skipped — no rating given")
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

def _ticket_menu_roles(guild: discord.Guild, ticket):
    """Roles that can work this ticket: the ticket menu's own roles, else
    the guild staff role. The opener's roles never count on their own."""
    menu = None
    if ticket and ticket.get("menu_id"):
        menu = database.get_ticket_menu(ticket["menu_id"], guild.id)
    if menu:
        roles = [guild.get_role(rid) for rid in database.menu_role_ids(menu)]
        roles = [r for r in roles if r is not None]
        if roles:
            return roles
    s = database.get_settings(guild.id)
    staff_role = guild.get_role(s.get("staff_role_id")) if s.get("staff_role_id") else None
    return [staff_role] if staff_role else []

def _can_manage_ticket(guild: discord.Guild, member: discord.Member, ticket):
    """Who can add/remove people, claim, or work a ticket: STAFF ONLY.
    The member who opened the ticket cannot — they have to be staff
    (the ticket menu's roles, the guild staff role, or Manage Channels /
    Administrator)."""
    if member.guild_permissions.manage_channels or member.guild_permissions.administrator:
        return True
    member_role_ids = {r.id for r in getattr(member, "roles", [])}
    s = database.get_settings(guild.id)
    role_id = s.get("staff_role_id")
    if role_id and role_id in member_role_ids:
        return True
    if any(r.id in member_role_ids for r in _ticket_menu_roles(guild, ticket)):
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
    @discord.ui.button(emoji="🙋", style=discord.ButtonStyle.primary, custom_id="ticket_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("Not a ticket channel.", ephemeral=True); return
        if interaction.user.id == t["owner_id"]:
            await interaction.response.send_message("You opened this ticket — let a staff member claim it.", ephemeral=True); return
        if not _can_manage_ticket(interaction.guild, interaction.user, t):
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True); return
        database.claim_ticket(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(f"{interaction.user.mention} claimed this ticket! They'll help you now.", ephemeral=False)
    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.secondary, custom_id="ticket_add_user")
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Pick a user to add to this ticket:", view=AddUserSelectView(), ephemeral=True)
    @discord.ui.button(emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket_close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        t = database.get_ticket(interaction.channel_id)
        if t and interaction.user.id != t["owner_id"] and not _can_manage_ticket(interaction.guild, interaction.user, t):
            await interaction.response.send_message("Only the ticket owner or staff can close this ticket.", ephemeral=True); return
        await interaction.response.send_modal(CloseReasonModal(interaction.channel_id))

async def close_ticket_flow(guild: discord.Guild, channel: discord.TextChannel, closer: discord.Member, reason: str = None):
    """Lock the ticket, ask the owner to rate, then delete after rating/timeout."""
    t = database.get_ticket(channel.id)
    if not t:
        return
    owner_id = t["owner_id"]; staff_id = t.get("staff_id") or closer.id
    database.close_ticket(channel.id)
    label = None
    if t.get("menu_id"):
        menu = database.get_ticket_menu(t["menu_id"], guild.id)
        label = menu["title"] if menu else None
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
    view = RatingView(channel.id, owner_id, staff_id, guild=guild, channel=channel, label=label, reason=reason)
    msg = await channel.send(embed=e, view=view)
    view.message = msg
    # DM the owner too, in case they miss it
    if owner:
        try:
            dm_view = RatingView(channel.id, owner_id, staff_id, guild=guild, channel=channel, label=label, reason=reason)
            dm_msg = await owner.send(embed=e, view=dm_view)
            dm_view.message = dm_msg
        except Exception:
            pass
    # Auto-delete after 5 min if still there and not rated
    await asyncio.sleep(300)
    ch = guild.get_channel(channel.id)
    if ch and not database.has_rated(channel.id, owner_id):
        await _finish_ticket(guild, ch, owner_id=owner_id, staff_id=staff_id,
                             label=label, reason=reason,
                             rating_text="No rating — window expired")

TOPICS = [(v, (f"{e} {l}" if e else l), d, e) for v, l, d, e, _p in database.BUILTIN_TICKET_TOPICS]

def _slug(text: str) -> str:
    """Make a string safe for a Discord channel name."""
    out = "".join(ch if ch.isalnum() else "-" for ch in (text or "").lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "ticket"

def _unique_channel_name(guild, base):
    """A new ticket of the same type always gets its own channel, even if
    the last one is still around (e.g. in its rating window):
    partnership-username, partnership-username-2, ..."""
    base = base[:90]
    names = {c.name for c in (getattr(guild, "channels", None) or [])}
    if base not in names:
        return base
    n = 2
    while f"{base}-{n}" in names:
        n += 1
    return f"{base}-{n}"

# ---------------------------------------------------------------------------
# NEW PANEL MODEL (2026-11-20): one dropdown per panel, and its options ARE
# the menus (ticket types) made in the dashboard. Picking a menu opens a
# ticket named for that menu (support-username, partnership-username, ...)
# and asks that menu's questions first, if it has any. A guild can have
# more than one panel.
# ---------------------------------------------------------------------------

def panel_options(guild_id, menu_ids=None):
    """The panel dropdown's options: (value, label, description, emoji).
    menu_ids=None means every menu in the guild."""
    menus = database.ensure_ticket_menus(guild_id) if guild_id else []
    if menu_ids:
        menus = [m for m in menus if m["id"] in menu_ids]
    opts = []
    for m in menus:
        emoji = m.get("emoji") or None
        if emoji and len(emoji) > 4:
            emoji = None  # custom <:name:id> emoji aren't usable in select options
        opts.append((f"menu_{m['id']}", m["title"][:100], (m.get("placeholder") or "")[:100], emoji))
    return opts

class TicketQuestionsModal(discord.ui.Modal):
    """The questions for the menu the member picked, asked before the
    ticket opens. Discord modals cap at 5 questions."""
    def __init__(self, menu):
        self.menu = menu
        self.questions = database.menu_questions(menu)[:5]
        super().__init__(title=(menu["title"] or "Ticket")[:45])
        for q in self.questions:
            self.add_item(discord.ui.TextInput(
                label=q["question"][:45],
                style=discord.TextStyle.paragraph if q.get("kind") == "long" else discord.TextStyle.short,
                required=bool(q.get("required", True)), max_length=1000))
    async def on_submit(self, interaction: discord.Interaction):
        answers = {}
        for q, child in zip(self.questions, self.children):
            val = (child.value or "").strip()
            if val:
                answers[q["question"]] = val
        await interaction.response.defer(ephemeral=True)
        await create_ticket_for_menu(interaction, self.menu, answers)

def _ticket_open_embed(label, opener_mention):
    """The message in the ticket when it opens — kept short on purpose."""
    e = discord.Embed(title=f"🎫 {label}",
        description=f"{opener_mention} — staff will be with you shortly.",
        color=discord.Color.blurple(), timestamp=discord.utils.utcnow())
    e.set_footer(text="Sunny's Best Friend • Ticket System")
    return e

def _format_answers(answers):
    """Answers as their own message, sent right after the open message.
    A name plus a member count reads like a sentence ("Vezzy Studios
    has 815 members"); anything else is a plain list."""
    items = [(q, a) for q, a in (answers or {}).items() if (a or "").strip()]
    if len(items) == 2:
        (q1, a1), (q2, a2) = items
        if "member" in q2.lower() and a2.strip().isdigit():
            return f"📋 {a1.strip()} has {a2.strip()} members"
    return "📋 **Ticket answers**\n" + "\n".join(f"• **{q}**: {a}" for q, a in items)

async def create_ticket_for_menu(interaction: discord.Interaction, menu, answers=None):
    """Open the ticket for a menu: named for what it is, visible only to
    the opener, the bot, and that menu's roles (or the guild staff role)."""
    guild = interaction.guild
    s = database.get_settings(guild.id)
    roles = _ticket_menu_roles(guild, {"menu_id": menu["id"]})
    category = guild.get_channel(menu.get("category_id") or s.get("ticket_category_id")) if (menu.get("category_id") or s.get("ticket_category_id")) else None
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    for r in roles:
        overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    prefix = _slug(menu.get("ticket_prefix") or "")
    label = menu["title"]
    base = f"{prefix}-{_slug(interaction.user.name)}" if prefix else f"ticket-{_slug(label)}-{_slug(interaction.user.name)}"
    channel = await guild.create_text_channel(_unique_channel_name(guild, base), category=category, overwrites=overwrites,
        topic=f"Ticket opened by {interaction.user} • {label}"[:1024], reason=f"Ticket created: {label}")
    database.create_ticket(channel.id, guild.id, interaction.user.id, menu_id=menu["id"])
    mentions = " ".join(r.mention for r in roles)
    log_id = s.get("ticket_log_channel_id")
    if log_id:
        log_ch = guild.get_channel(log_id)
        if log_ch:
            try: await log_ch.send(f"🎫 New ticket {channel.mention} opened by {interaction.user.mention} — **{label}** {mentions}")
            except Exception: pass
    await channel.send(f"{interaction.user.mention} {mentions}", embed=_ticket_open_embed(label, interaction.user.mention), view=TicketControls())
    if answers:
        await channel.send(_format_answers(answers))
    msg = f"Ticket created: {channel.mention}"
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)

class TicketPanelSelect(discord.ui.Select):
    def __init__(self, guild_id=None, menu_ids=None, placeholder="Pick a ticket type..."):
        opts = panel_options(guild_id, menu_ids) if guild_id else []
        if not opts:
            # No ticket types set up yet — the dropdown still has to have
            # one option to exist, and picking it explains what to do.
            opts = [("menu_0", "—", "Pick a ticket type", None)]
        super().__init__(
            placeholder=placeholder[:150],
            custom_id="ticket_panel_select",
            options=[discord.SelectOption(label=label, value=value, description=desc, emoji=emoji) for value, label, desc, emoji in opts],
        )
    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        if not value.startswith("menu_") or value == "menu_0":
            await interaction.response.send_message("No ticket types set up yet — ask an admin to add some in the dashboard.", ephemeral=True); return
        menu = database.get_ticket_menu(int(value[5:]), interaction.guild_id)
        if not menu:
            await interaction.response.send_message("That ticket type doesn't exist anymore.", ephemeral=True); return
        questions = database.menu_questions(menu)
        if questions:
            await interaction.response.send_modal(TicketQuestionsModal(menu))
        else:
            await create_ticket_for_menu(interaction, menu)

class TicketPanelView(discord.ui.View):
    def __init__(self, guild_id=None, panel=None):
        super().__init__(timeout=None)
        menu_ids = database.panel_menu_ids(panel) if panel else None
        placeholder = (panel.get("title") if panel else None) or "Pick a ticket type..."
        self.add_item(TicketPanelSelect(guild_id, menu_ids, placeholder))

def panel_embed(panel, guild_id):
    title = panel.get("title") or "🎫 Need Help?"
    desc = panel.get("description") or ("Need help? Open a ticket below and our staff team will help you.\n\n"
        "**How it works**\n"
        "• Pick a ticket type from the menu below\n"
        "• Answer its questions, if it has any\n"
        "• A staff member will claim it and help you\n\n"
        "When your ticket closes, you'll be asked to rate your support 1–5 ⭐.")
    color = panel.get("color") or 5793266
    e = discord.Embed(title=title, description=desc, color=color)
    e.set_footer(text="Sunny's Best Friend • Ticket System")
    return e

async def post_panel(bot, guild, panel):
    """Post a panel, or update it in place if it was posted before."""
    channel = guild.get_channel(panel.get("channel_id"))
    if not channel:
        return None
    view = TicketPanelView(guild.id, panel)
    e = panel_embed(panel, guild.id)
    msg_id = panel.get("message_id")
    if msg_id:
        try:
            msg = await channel.fetch_message(msg_id)
            await msg.edit(embed=e, view=view)
            return msg
        except Exception:
            pass
    msg = await channel.send(embed=e, view=view)
    database.update_ticket_panel(panel["id"], guild.id, panel.get("title"), panel.get("description"),
                                 panel.get("color"), panel.get("channel_id"),
                                 database.panel_menu_ids(panel) or None, message_id=msg.id)
    return msg

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

# (guild_id, panel_id) pairs whose persistent views are already registered,
# so reconnects don't register the same views twice.
_registered_panel_views = set()

def register_panel_views(bot, guild_id):
    """Register this guild's panels as persistent views, so the dropdowns
    keep working after a bot restart. Old slot-based panels too."""
    for panel in database.list_ticket_panels(guild_id):
        key = (guild_id, panel["id"])
        if key in _registered_panel_views:
            continue
        bot.add_view(TicketPanelView(guild_id, panel))
        _registered_panel_views.add(key)
    for page in range(panel_pages(guild_id)):
        key = (guild_id, "old", page)
        if key in _registered_panel_views:
            continue
        bot.add_view(TicketPanel(guild_id, page))
        _registered_panel_views.add(key)

# ---------------------------------------------------------------------------
# OLD PANEL MODEL — kept so panels already posted keep working. A panel had
# one dropdown per menu (up to 5 per message); its options were ticket
# templates. New panels use TicketPanelView above instead.
# ---------------------------------------------------------------------------

def panel_menus(guild_id):
    """The OLD ticket panel's dropdown menus, in order. Each menu is
    (slot, title, placeholder, [(value, label, description, emoji)]).
    Slot 1 keeps the historic custom_id so panels already posted keep
    working."""
    if not guild_id:
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
        if not opts:
            continue  # a menu with no options doesn't get a dropdown
        out.append((i, m["title"], m.get("placeholder") or m["title"], opts))
    return out

def panel_pages(guild_id):
    """How many panel messages the guild's OLD menus need (5 dropdowns max per message)."""
    import math
    return max(1, math.ceil(len(panel_menus(guild_id)) / 5))

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
    base = f"{prefix}-{_slug(interaction.user.name)}" if prefix else f"ticket-{_slug(slug)}-{_slug(interaction.user.name)}"
    channel = await guild.create_text_channel(_unique_channel_name(guild, base), category=category, overwrites=overwrites,
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
    e.add_field(name="Buttons", value="🙋 Claim this ticket  •  ➕ Add someone  •  🔒 Close this ticket", inline=False)
    e.set_footer(text="Sunny's Best Friend • Ticket System")
    await channel.send(f"{interaction.user.mention} {staff_role.mention if staff_role else ''}", embed=e, view=TicketControls())
    await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketPanel(discord.ui.View):
    def __init__(self, guild_id=None, page=0):
        super().__init__(timeout=None)
        for slot, title, placeholder, opts in panel_menus(guild_id)[page * 5:(page + 1) * 5]:
            # The dropdown button shows the menu NAME (title); the question
            # text lives in the panel embed above it, not on the button.
            self.add_item(TicketMenuSelect(slot, guild_id, opts, title))

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
        database.ensure_ticket_menus(interaction.guild_id)
        title, desc, color = panel_embed_settings(interaction.guild_id)
        panels = database.list_ticket_panels(interaction.guild_id)
        panel = next((p for p in panels if p.get("channel_id") == panel_channel.id), None)
        if panel is None:
            pid = database.add_ticket_panel(interaction.guild_id, title, desc, color, panel_channel.id, None)
            panel = database.get_ticket_panel(pid, interaction.guild_id)
        msg = await post_panel(self.bot, interaction.guild, panel)
        register_panel_views(self.bot, interaction.guild_id)
        if msg is None:
            await interaction.response.send_message("Couldn't post the panel — check the channel.", ephemeral=True); return
        await interaction.response.send_message(
            f"✅ Tickets set up:\n"
            f"• Panel posted in {panel_channel.mention}\n"
            f"• Staff role: {staff_role.mention}\n"
            f"• Ratings go to {rating_log_channel.mention}\n"
            f"• New-ticket alerts go to {ticket_log_channel.mention}\n"
            f"• Ticket channels go in {category.mention if category else 'no category'}\n"
            f"• Ticket types are the menus in the dashboard — add questions, a ticket name and roles per type there", ephemeral=True)
    @app_commands.command(name="close", description="Close this ticket and ask the owner to rate it")
    async def close_cmd(self, interaction: discord.Interaction):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        if interaction.user.id != t["owner_id"] and not _can_manage_ticket(interaction.guild, interaction.user, t):
            await interaction.response.send_message("Only the ticket owner or staff can close this ticket.", ephemeral=True); return
        await interaction.response.send_modal(CloseReasonModal(interaction.channel_id))
    @app_commands.command(name="claim", description="Claim this ticket")
    async def claim_cmd(self, interaction: discord.Interaction):
        t = database.get_ticket(interaction.channel_id)
        if not t:
            await interaction.response.send_message("This isn't a ticket channel.", ephemeral=True); return
        if interaction.user.id == t["owner_id"]:
            await interaction.response.send_message("You opened this ticket — let a staff member claim it.", ephemeral=True); return
        if not _can_manage_ticket(interaction.guild, interaction.user, t):
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True); return
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
    bot.add_view(TicketPanelView())
    bot.add_view(TicketControls())
