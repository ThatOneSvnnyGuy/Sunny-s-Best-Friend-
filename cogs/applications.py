"""Applications - in Discord AND the dashboard.
Templates are built in the dashboard (Applications section): a template has
a name (e.g. Staff, Moderator, Event Team), its own questions, the role
given on approval, and the channel applications go to for review.
In Discord: /apply shows a picker when there is more than one template,
then opens a form built from that template's questions (max 5 - Discord's
modal limit). With no templates, /apply uses the built-in staff form.
Staff review in Discord with Approve / Deny buttons, or in the dashboard.
Stored in bot.db (application_templates + applications tables).
"""
import discord, json
from discord.ext import commands
from discord import app_commands
import database

DEFAULT_QUESTIONS = [
    {"label": "Why do you want this role?", "style": "paragraph", "required": True, "max_length": 500},
    {"label": "Any experience? (staff, mod, etc.)", "style": "paragraph", "required": False, "max_length": 500},
    {"label": "How active can you be?", "style": "short", "required": True, "max_length": 200},
]

def _questions_for(template):
    if not template:
        return DEFAULT_QUESTIONS
    try:
        qs = json.loads(template.get("questions") or "[]")
        return qs[:5] if qs else DEFAULT_QUESTIONS
    except Exception:
        return DEFAULT_QUESTIONS

def make_apply_modal(template):
    qs = _questions_for(template)
    title = (template["name"] if template else "Staff Application")[:45]
    class ApplyModal(discord.ui.Modal, title=title):
        def __init__(self):
            super().__init__()
            self.template = template
            self.inputs = []
            for q in qs:
                ti = discord.ui.TextInput(
                    label=q["label"][:45],
                    style=discord.TextStyle.paragraph if q.get("style") == "paragraph" else discord.TextStyle.short,
                    required=bool(q.get("required", True)),
                    max_length=min(int(q.get("max_length") or 200), 4000))
                self.add_item(ti)
                self.inputs.append(ti)
        async def on_submit(self, interaction: discord.Interaction):
            answers = {q["label"]: str(ti) for q, ti in zip(qs, self.inputs)}
            app_id = database.add_application(interaction.guild_id, interaction.user.id, json.dumps(answers))
            if self.template:
                try:
                    c = database._conn(); c.execute("UPDATE applications SET template_id=? WHERE id=?", (self.template["id"], app_id)); c.commit(); c.close()
                except Exception:
                    pass
            settings = database.get_settings(interaction.guild_id)
            review_id = (self.template or {}).get("review_channel_id") or settings.get("app_channel_id")
            channel = interaction.guild.get_channel(review_id or 0)
            color = (self.template or {}).get("color") or 0x5865F2
            e = discord.Embed(title=f"📝 Application #{app_id} — {title}", color=color)
            e.add_field(name="Applicant", value=interaction.user.mention, inline=False)
            for q, ti in zip(qs, self.inputs):
                e.add_field(name=q["label"], value=str(ti) or "—", inline=False)
            if channel:
                view = ApplicationReviewView(app_id)
                msg = await channel.send(embed=e, view=view)
                view.message = msg
                await interaction.response.send_message(f"✅ Application #{app_id} sent for review!", ephemeral=True)
            else:
                await interaction.response.send_message("✅ Application saved, but no review channel is set — ask an admin to set one up in the dashboard.", ephemeral=True)
    return ApplyModal

class ApplyTemplateSelect(discord.ui.Select):
    def __init__(self, templates):
        super().__init__(placeholder="What are you applying for?", custom_id="apply_template_select",
                         options=[discord.SelectOption(label=t["name"][:100], value=str(t["id"]), description=(t.get("description") or "")[:100]) for t in templates])
    async def callback(self, interaction: discord.Interaction):
        tpl = database.get_application_template(int(self.values[0]), interaction.guild_id)
        if tpl:
            left = _cooldown_days_left(interaction, tpl)
            if left > 0:
                await interaction.response.send_message(f"⏳ You already applied for this recently — you can apply again in {left} day(s).", ephemeral=True)
                return
        await interaction.response.send_modal(make_apply_modal(tpl)())

class ApplyTemplateView(discord.ui.View):
    def __init__(self, templates):
        super().__init__(timeout=180)
        self.add_item(ApplyTemplateSelect(templates))

class ApplicationPanelView(discord.ui.View):
    """Persistent panel posted from the dashboard: a dropdown of every
    application template. Registered at startup so it keeps working
    after restarts (real options come from the interaction)."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ApplyTemplateSelect([{"id": 0, "name": "—", "description": "No application types yet"}]))

def _cooldown_days_left(interaction, tpl):
    """Days left on a per-template cooldown (0 = free to apply)."""
    import time as _time
    days = (tpl or {}).get("cooldown_days")
    if not days:
        return 0
    last = database.last_application_time(interaction.guild_id, interaction.user.id, tpl["id"])
    if not last:
        return 0
    left = (days * 86400 - (_time.time() - last)) / 86400
    return max(0, int(left) + (1 if left % 1 else 0))

class DenyReasonModal(discord.ui.Modal, title="Deny application"):
    reason = discord.ui.TextInput(label="Why is it denied? (optional)", style=discord.TextStyle.paragraph, required=False, max_length=300, placeholder="The applicant gets this reason in a DM.")
    def __init__(self, view):
        super().__init__(); self.view = view
    async def on_submit(self, interaction: discord.Interaction):
        await self.view._decide(interaction, False, str(self.reason) or None)

class ApplicationReviewView(discord.ui.View):
    def __init__(self, app_id: int):
        super().__init__(timeout=None)
        self.app_id = app_id

    async def _decide(self, interaction: discord.Interaction, approve: bool, reason: str = None):
        app = database.get_application(self.app_id)
        if not app or app["status"] != "pending":
            if not interaction.response.is_done():
                await interaction.response.send_message("This application was already decided.", ephemeral=True)
            return
        status = "approved" if approve else "denied"
        database.set_application_status(self.app_id, status)
        settings = database.get_settings(interaction.guild_id)
        role_id = settings.get("app_role_id")
        tpl = database.get_application_template(app.get("template_id"), interaction.guild_id) if app.get("template_id") else None
        if tpl and tpl.get("role_id"):
            role_id = tpl["role_id"]
        member = interaction.guild.get_member(app["user_id"])
        if approve and member and role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try: await member.add_roles(role)
                except Exception: pass
        # The review message: stored on the view when posted, or the message
        # the button sits on. (A modal submit has no message of its own.)
        msg = getattr(self, "message", None) or getattr(interaction, "message", None)
        e = msg.embeds[0] if msg and msg.embeds else discord.Embed()
        e.color = discord.Color.green() if approve else discord.Color.red()
        e.add_field(name="Decision", value=f"{'✅ Approved' if approve else '❌ Denied'} by {interaction.user.mention}", inline=False)
        if reason:
            e.add_field(name="Reason", value=reason, inline=False)
        if msg:
            try: await msg.edit(embed=e, view=None)
            except Exception: pass
        if not interaction.response.is_done():
            if getattr(interaction, "message", None) is not None:
                await interaction.response.edit_message(embed=e, view=None)
            else:
                await interaction.response.send_message(f"Application #{self.app_id} {status}.", ephemeral=True)
        if member:
            try:
                dm = f"Your application #{self.app_id} was **{status}** in {interaction.guild.name}."
                if reason:
                    dm += f"\nReason: {reason}"
                await member.send(dm)
            except Exception: pass

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DenyReasonModal(self))

class Applications(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="setup-applications", description="Set where applications go for review + role given on approval (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_applications(self, i: discord.Interaction, review_channel: discord.TextChannel, role: discord.Role = None):
        database.set_setting(i.guild_id, "app_channel_id", review_channel.id)
        if role: database.set_setting(i.guild_id, "app_role_id", role.id)
        await i.response.send_message(f"✅ Applications will go to {review_channel.mention}" + (f" and approved members get {role.mention}." if role else "."))

    @app_commands.command(name="apply", description="Apply - pick what you're applying for, then fill in the form")
    async def apply(self, i: discord.Interaction):
        templates = database.list_application_templates(i.guild_id)
        settings = database.get_settings(i.guild_id)
        if not templates and not settings.get("app_channel_id"):
            await i.response.send_message("Applications aren't set up yet — ask an admin to make a template in the dashboard first.", ephemeral=True); return
        if len(templates) == 1:
            left = _cooldown_days_left(i, templates[0])
            if left > 0:
                await i.response.send_message(f"⏳ You already applied for this recently — you can apply again in {left} day(s).", ephemeral=True); return
            await i.response.send_modal(make_apply_modal(templates[0])())
        elif len(templates) > 1:
            await i.response.send_message("What are you applying for?", view=ApplyTemplateView(templates), ephemeral=True)
        else:
            await i.response.send_modal(make_apply_modal(None)())

    @app_commands.command(name="applications", description="List pending applications (Staff)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def applications(self, i: discord.Interaction):
        rows = database.list_applications(i.guild_id, "pending")
        e = discord.Embed(title="📝 Pending Applications", color=discord.Color.blurple())
        if not rows: e.description = "No pending applications."
        for r in rows:
            a = json.loads(r["answers"]) if r["answers"] else {}
            first = next(iter(a.values()), "") if a else ""
            e.add_field(name=f"#{r['id']} — <@{r['user_id']}>", value=str(first)[:200], inline=False)
        await i.response.send_message(embed=e)

async def setup(bot):
    await bot.add_cog(Applications(bot))
    bot.add_view(ApplicationPanelView())
