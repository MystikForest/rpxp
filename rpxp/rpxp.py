import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time
import typing

# ============================================================
# Dashboard integration pattern from AAA3A-cogs (EmbedUtils)
# ============================================================
def dashboard_page(*args, **kwargs):
    """
    Decorator to mark methods as Dashboard pages.
    Sets attribute __dashboard_decorator_params__ on the function.
    """
    def decorator(func: typing.Callable):
        func.__dashboard_decorator_params__ = (args, kwargs)
        return func
    return decorator

class DashboardIntegration:
    """Mixin class to auto-register cog with Dashboard Third-Parties."""
    @commands.Cog.listener()
    async def on_dashboard_cog_add(self, dashboard_cog: commands.Cog) -> None:
        dashboard_cog.rpc.third_parties_handler.add_third_party(self)

class RPXP(DashboardIntegration, commands.Cog):
    """
    Westmarch RP XP tracker with Dashboard Form UI.
    - Award XP after Y message-units in RP channels
    - message-units = ceil(word_count / words_per_unit)
    - Anti-spam: minimum word count required
    - Per-message cooldown (prevents message from counting if too soon)
    - Announcement channel posts alert and pings user
    """

    __thirdparty__ = True

    def get_thirdparty_name(self):
        return "RPXP"

    def get_thirdparty_pages(self):
        return ["config"]

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=823742347892334, force_registration=True
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],
            "messages_needed": 5,
            "xp_award": 10,
            "cooldown_seconds": 15,
            "announce_channel": None,
            "words_per_unit": 25,
            "min_words": 8,
        }

        default_member = {
            "xp": 0,
            "msg_count": 0,
            "last_message_time": 0.0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

    # =====================================================
    # Dashboard page: Config form
    # =====================================================
    @dashboard_page(
        name="config",
        description="Configure RPXP settings",
        methods=("GET", "POST")
    )
    async def dashboard_config(self, user: discord.User, guild: discord.Guild, **kwargs):
        """
        Dashboard → Third Parties → RPXP → Config
        Presents a form to edit the guild configuration.
        """
        # Permission check: owner or mod
        is_owner = user.id in self.bot.owner_ids
        member = guild.get_member(user.id)
        if not is_owner and (member is None or not await self.bot.is_mod(member)):
            return {
                "status": 0,
                "error_code": 403,
                "message": "You don’t have permissions to access this page."
            }

        gconf = await self.config.guild(guild).all()

        import wtforms
        from wtforms import validators

        class RPXPForm(kwargs["Form"]):
            def __init__(self):
                super().__init__(prefix="rpxp_")

            enabled = wtforms.BooleanField(
                "Enable RPXP",
                default=gconf["enabled"],
            )

            messages_needed = wtforms.IntegerField(
                "Message-Units Needed (Y)",
                default=gconf["messages_needed"],
                validators=[validators.NumberRange(min=1)],
            )

            xp_award = wtforms.IntegerField(
                "XP Award (X)",
                default=gconf["xp_award"],
                validators=[validators.NumberRange(min=0)],
            )

            cooldown_seconds = wtforms.IntegerField(
                "Per-Message Cooldown (seconds)",
                default=gconf["cooldown_seconds"],
                validators=[validators.NumberRange(min=0)],
            )

            words_per_unit = wtforms.IntegerField(
                "Words per Unit",
                default=gconf["words_per_unit"],
                validators=[validators.NumberRange(min=1)],
            )

            min_words = wtforms.IntegerField(
                "Minimum Words (Anti-Spam)",
                default=gconf["min_words"],
                validators=[validators.NumberRange(min=1)],
            )

            rp_channels = wtforms.SelectMultipleField(
                "RP Channels",
                choices=[],
                default=[str(x) for x in gconf["rp_channels"]],
                validators=[],
            )

            announce_channel = wtforms.SelectField(
                "Announcement Channel",
                choices=[],
                default=str(gconf["announce_channel"]) if gconf["announce_channel"] else "",
                validators=[],
            )

            submit = wtforms.SubmitField("Save RPXP Settings")

        form = RPXPForm()

        # Build channel choices
        sorted_channels = kwargs["get_sorted_channels"](guild)
        chan_choices = [(str(cid), label) for (label, cid) in sorted_channels]
        form.rp_channels.choices = chan_choices
        form.announce_channel.choices = [("", "None")] + chan_choices

        if form.validate_on_submit():
            # parse RP channel IDs
            rp_ids = []
            for cid_str in (form.rp_channels.data or []):
                try:
                    rp_ids.append(int(cid_str))
                except:
                    continue

            ann_val = form.announce_channel.data or ""
            ann_id = int(ann_val) if ann_val.isdigit() else None

            await self.config.guild(guild).enabled.set(bool(form.enabled.data))
            await self.config.guild(guild).messages_needed.set(int(form.messages_needed.data))
            await self.config.guild(guild).xp_award.set(int(form.xp_award.data))
            await self.config.guild(guild).cooldown_seconds.set(int(form.cooldown_seconds.data))
            await self.config.guild(guild).words_per_unit.set(int(form.words_per_unit.data))
            await self.config.guild(guild).min_words.set(int(form.min_words.data))
            await self.config.guild(guild).rp_channels.set(rp_ids)
            await self.config.guild(guild).announce_channel.set(ann_id)

            return {
                "status": 0,
                "notifications": [
                    {"message": "RPXP settings saved!", "category": "success"}
                ],
                "redirect_url": kwargs["request_url"]
            }

        # Render form as HTML
        html = f"""
        <div class="card">
          <div class="card-header"><h3>RPXP Configuration</h3></div>
          <div class="card-body">
            <form method="POST">
              {form.hidden_tag()}
              <div class="form-group">
                {form.enabled.label} {form.enabled()}
              </div>
              <div class="form-group">
                {form.messages_needed.label}
                {form.messages_needed(class_="form-control")}
                <small class="form-text text-muted">Units needed to award XP.</small>
              </div>
              <div class="form-group">
                {form.xp_award.label}
                {form.xp_award(class_="form-control")}
              </div>
              <div class="form-group">
                {form.cooldown_seconds.label}
                {form.cooldown_seconds(class_="form-control")}
                <small class="form-text text-muted">Message-unit count is blocked if message is too soon.</small>
              </div>
              <div class="form-group">
                {form.words_per_unit.label}
                {form.words_per_unit(class_="form-control")}
                <small class="form-text text-muted">Words → message-units conversion.</small>
              </div>
              <div class="form-group">
                {form.min_words.label}
                {form.min_words(class_="form-control")}
                <small class="form-text text-muted">Messages below this word count are ignored.</small>
              </div>
              <div class="form-group">
                {form.rp_channels.label}
                {form.rp_channels(class_="form-control")}
              </div>
              <div class="form-group">
                {form.announce_channel.label}
                {form.announce_channel(class_="form-control")}
              </div>
              {form.submit(class_="btn btn-primary")}
            </form>
          </div>
        </div>
        """
        return {
            "status": 0,
            "web_content": {
                "source": html,
                "standalone": True
            }
        }

    # =====================================================
    # Core XP logic
    # =====================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        g = await self.config.guild(message.guild).all()
        if not g["enabled"]:
            return

        if message.channel.id not in g["rp_channels"]:
            return

        m = await self.config.member(message.author).all()
        now = time.time()

        words = len(message.content.split())
        if words < g["min_words"]:
            return

        if now - m["last_message_time"] < g["cooldown_seconds"]:
            return

        await self.config.member(message.author).last_message_time.set(now)

        units = max(1, math.ceil(words / g["words_per_unit"]))
        new_count = m["msg_count"] + units
        await self.config.member(message.author).msg_count.set(new_count)

        if new_count < g["messages_needed"]:
            return

        new_xp = m["xp"] + g["xp_award"]
        await self.config.member(message.author).xp.set(new_xp)
        await self.config.member(message.author).msg_count.set(0)

        ann_id = g["announce_channel"]
        if ann_id:
            chan = message.guild.get_channel(ann_id)
            if chan:
                try:
                    await chan.send(
                        f"🎉 <@{message.author.id}> earned XP for RP activity!"
                    )
                except discord.Forbidden:
                    pass

    # =====================================================
    # Commands
    # =====================================================
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RP XP commands."""
        pass

    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, user: discord.Member = None):
        """Show XP stats for a user."""
        user = user or ctx.author
        d = await self.config.member(user).all()
        await ctx.send(
            f"**{user.display_name}** has **{d['xp']} XP**.\n"
            f"Message-units toward next award: `{d['msg_count']}`."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @rpxp_group.command(name="add")
    async def rpxp_add(self, ctx, user: discord.Member, xp: int):
        """Manually add XP."""
        cur = await self.config.member(user).xp()
        await self.config.member(user).xp.set(cur + xp)
        await ctx.send(f"Added **{xp} XP** to **{user.display_name}**.")

    @commands.admin_or_permissions(manage_guild=True)
    @rpxp_group.command(name="setannounce")
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        """Set announcement channel."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcements will now appear in {channel.mention}.")
