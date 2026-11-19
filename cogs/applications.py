"""Applications - in Discord, not the dashboard.
Setup: /setup-applications (Admin) picks a review channel + a role to give on approval.
Apply: /apply opens a form. Staff review it in Discord with Approve / Deny buttons.
/applications lists pending ones. Stored in bot.db (applications table).
"""
import discord, json
from discord.ext import commands
from discord import app_commands
import database

class ApplyModal(discord.ui.Modal, title="Staff Application"):
    why = discord.ui.TextInput(label="Why do you want this role?", style=discord.TextStyle.paragraph, max_length=500)
    experience = discord.ui.TextInput(label="Any experience? (staff, mod, etc.)", style=discord.TextStyle.paragraph, required=False, max_length=500)
    activity = discord.ui.TextInput(label="How active can you be?", style=discord.TextStyle.short, max_length=200)

    async def on_submit(self, interaction: discord.Interaction):
        answers = json.dumps({"why": str(self.why), "experience": str(self.experience), "activity": str(self.activity)})
        app_id = database.add_application(interaction.guild_id, interaction.user.id, answers)
        settings = database.get_settings(interaction.guild_id)
        channel = interaction.guild.get_channel(settings.get("app_channel_id") or 0)
        e = discord.Embed(title=f"📝 Application #{app_id}", color=discord.Color.blurple())
        e.add_field(name="Applicant", value=interaction.user.mention, inline=False)
        e.add_field(name="Why do you want this role?", value=str(self.why), inline=False)
        e.add_field(name="Experience", value=str(self.experience) or "—", inline=False)
        e.add_field(name="How active can you be?", value=str(self.activity), inline=False)
        if channel:
            await channel.send(embed=e, view=ApplicationReviewView(app_id))
            await interaction.response.send_message(f"✅ Application #{app_id} sent for review!", ephemeral=True)
        else:
            await interaction.response.send_message("✅ Application saved, but no review channel is set — ask an admin to run /setup-applications.", ephemeral=True)

class ApplicationReviewView(discord.ui.View):
    def __init__(self, app_id: int):
        super().__init__(timeout=None)
        self.app_id = app_id

    async def _decide(self, interaction: discord.Interaction, approve: bool):
        app = database.get_application(self.app_id)
        if not app or app["status"] != "pending":
            await interaction.response.send_message("This application was already decided.", ephemeral=True); return
        status = "approved" if approve else "denied"
        database.set_application_status(self.app_id, status)
        settings = database.get_settings(interaction.guild_id)
        member = interaction.guild.get_member(app["user_id"])
        if approve and member and settings.get("app_role_id"):
            role = interaction.guild.get_role(settings["app_role_id"])
            if role:
                try: await member.add_roles(role)
                except Exception: pass
        e = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        e.color = discord.Color.green() if approve else discord.Color.red()
        e.add_field(name="Decision", value=f"{'✅ Approved' if approve else '❌ Denied'} by {interaction.user.mention}", inline=False)
        await interaction.response.edit_message(embed=e, view=None)
        if member:
            try: await member.send(f"Your application #{self.app_id} was **{status}** in {interaction.guild.name}.")
            except Exception: pass

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, True)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._decide(interaction, False)

class Applications(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @app_commands.command(name="setup-applications", description="Set where applications go for review + role given on approval (Admin)")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_applications(self, i: discord.Interaction, review_channel: discord.TextChannel, role: discord.Role = None):
        database.set_setting(i.guild_id, "app_channel_id", review_channel.id)
        if role: database.set_setting(i.guild_id, "app_role_id", role.id)
        await i.response.send_message(f"✅ Applications will go to {review_channel.mention}" + (f" and approved members get {role.mention}." if role else "."))

    @app_commands.command(name="apply", description="Apply for staff - opens the application form")
    async def apply(self, i: discord.Interaction):
        settings = database.get_settings(i.guild_id)
        if not settings.get("app_channel_id"):
            await i.response.send_message("Applications aren't set up yet — ask an admin to run /setup-applications first.", ephemeral=True); return
        await i.response.send_modal(ApplyModal())

    @app_commands.command(name="applications", description="List pending applications (Staff)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def applications(self, i: discord.Interaction):
        rows = database.list_applications(i.guild_id, "pending")
        e = discord.Embed(title="📝 Pending Applications", color=discord.Color.blurple())
        if not rows: e.description = "No pending applications."
        for r in rows:
            a = json.loads(r["answers"]) if r["answers"] else {}
            e.add_field(name=f"#{r['id']} — <@{r['user_id']}>", value=(a.get("why") or "")[:200], inline=False)
        await i.response.send_message(embed=e)

async def setup(bot): await bot.add_cog(Applications(bot))
