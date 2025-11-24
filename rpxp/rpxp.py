import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time

# Dashboard imports
try:
    from dashboard.rpc.thirdparties import dashboard_page
    from dashboard.web import Form, fields
    DASH_OK = True
except Exception:
    DASH_OK = False


class RPXP(commands.Cog):
    """
    Westmarch RP XP tracker with Dashboard Form UI.
    - XP every Y message-units
    - Units = ceil(words / words_per_unit)
    - Anti-spam: ignore messages below minimum words
    - Per-message cooldown
    - Announcement channel
    """

    __thirdparty__ = True  # REQUIRED for AAA3A Dashboard

    def get_thirdparty_name(self):
        return "RPXP"        # REQUIRED

    def get_thirdparty_pages(self):
        return ["config"]    # REQUIRED: list of dashboard_page names

    def __init__(self, bot: Red):
        self.bot = bot

        # ---- CONFIG ----
        self.config = Config.get_conf(
            self, identifier=82374234789234, force_registration=True
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],
            "messages_needed": 5,
            "xp_award": 10,
            "cooldown_seconds": 15,   # PER MESSAGE
            "announce_channel": None,
            "words_per_unit": 25,
            "min_words": 8,           # Anti-spam filter
        }

        default_member = {
            "xp": 0,
            "msg_count": 0,
            "last_message_time": 0.0,  # per-message cooldown
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        # Register with Dashboard
        if DASH_OK:
            self.bot.loop.create_task(self._register_third_party())


    # =====================================================
    # THIRD-PARTY REGISTRATION
    # =====================================================
    async def _register_third_party(self):
        dashboard_cog = self.bot.get_cog("Dashboard")
        if not dashboard_cog or not hasattr(dashboard_cog, "rpc"):
            return

        handler = dashboard_cog.rpc.third_parties_handler

        existing = getattr(handler, "third_parties", {})
        if self.qualified_name not in existing:
            handler.add_third_party(self)


    @commands.Cog.listener()
    async def on_dashboard_cog_load(self, cog=None):
        if DASH_OK:
            await self._register_third_party()


    # =====================================================
    # DASHBOARD FORM UI PAGE
    # =====================================================
    if DASH_OK:
        @dashboard_page(
            name="config",
            methods=("GET", "POST"),
            context_ids=["guild_id"],
            hidden=False,
            require_admin=True,
        )
        async def rpxp_config_form(self, guild_id, method="GET", data=None, **kwargs):

            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                return {"status": 1, "error_title": "Guild not found"}

            gconf = await self.config.guild(guild).all()

            # ---- Build Form ----
            form = Form(
                title="RPXP Configuration",
                description="Configure RPXP behavior.",
                submit_text="Save Settings"
            )

            form.add_field(
                "enabled", fields.BoolField,
                label="Enable RPXP",
                default=gconf["enabled"]
            )

            form.add_field(
                "messages_needed", fields.NumberField,
                label="Message Units Needed (Y)",
                description="How many message-units trigger XP award.",
                default=gconf["messages_needed"], min=1
            )

            form.add_field(
                "words_per_unit", fields.NumberField,
                label="Words per Unit",
                description="How many words = 1 message-unit.",
                default=gconf["words_per_unit"], min=1
            )

            form.add_field(
                "min_words", fields.NumberField,
                label="Minimum Words",
                description="Messages below this many words count as spam and are ignored.",
                default=gconf["min_words"], min=1
            )

            form.add_field(
                "xp_award", fields.NumberField,
                label="XP Award",
                default=gconf["xp_award"], min=0
            )

            form.add_field(
                "cooldown_seconds", fields.NumberField,
                label="Per-message Cooldown (seconds)",
                description="User cannot gain units from messages faster than this.",
                default=gconf["cooldown_seconds"], min=0
            )

            form.add_field(
                "rp_channels", fields.ChannelsField,
                label="RP Channels",
                description="Only these channels count for RPXP.",
                default=gconf["rp_channels"],
                channel_types=["text", "thread"],
                multiselect=True
            )

            form.add_field(
                "announce_channel", fields.ChannelField,
                label="Announcement Channel",
                description="Where XP awards will be posted.",
                default=gconf["announce_channel"],
                channel_types=["text"]
            )

            # ---- POST → Save ----
            if method == "POST":
                cleaned = await form.validate(data)
                if cleaned is None:
                    return form

                await self.config.guild(guild).enabled.set(cleaned["enabled"])
                await self.config.guild(guild).messages_needed.set(cleaned["messages_needed"])
                await self.config.guild(guild).words_per_unit.set(cleaned["words_per_unit"])
                await self.config.guild(guild).min_words.set(cleaned["min_words"])
                await self.config.guild(guild).xp_award.set(cleaned["xp_award"])
                await self.config.guild(guild).cooldown_seconds.set(cleaned["cooldown_seconds"])
                await self.config.guild(guild).rp_channels.set(cleaned["rp_channels"])
                await self.config.guild(guild).announce_channel.set(cleaned["announce_channel"])

                form.success("RPXP settings saved!")
                return form

            return form


    # =====================================================
    # CORE XP SYSTEM
    # =====================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):

        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        if message.channel.id not in guild_conf["rp_channels"]:
            return

        mem_conf = await self.config.member(message.author).all()
        now = time.time()

        # ---- Anti-Spam Minimum Word Requirement ----
        words = len(message.content.split())
        if words < guild_conf["min_words"]:
            return

        # ---- PER-MESSAGE Cooldown ----
        if now - mem_conf["last_message_time"] < guild_conf["cooldown_seconds"]:
            return

        # Accept message
        await self.config.member(message.author).last_message_time.set(now)

        # ---- Convert to message-units ----
        units = max(1, math.ceil(words / guild_conf["words_per_unit"]))
        new_count = mem_conf["msg_count"] + units
        await self.config.member(message.author).msg_count.set(new_count)

        # ---- Not enough units yet ----
        if new_count < guild_conf["messages_needed"]:
            return

        # ---- Award XP ----
        new_xp = mem_conf["xp"] + guild_conf["xp_award"]
        await self.config.member(message.author).xp.set(new_xp)

        await self.config.member(message.author).msg_count.set(0)

        # ---- Announce Award ----
        if guild_conf["announce_channel"]:
            chan = message.guild.get_channel(guild_conf["announce_channel"])
            if chan:
                try:
                    await chan.send(
                        f"🎉 <@{message.author.id}> earned **{guild_conf['xp_award']} XP** "
                        f"for RP activity in {message.channel.mention}!"
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
    async def rpxp_stats(self, ctx, user: discord.Member=None):
        """Show XP stats for a user."""
        user = user or ctx.author
        data = await self.config.member(user).all()
        await ctx.send(
            f"**{user.display_name}** has **{data['xp']} XP**.\n"
            f"Message-units toward next award: `{data['msg_count']}`."
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
