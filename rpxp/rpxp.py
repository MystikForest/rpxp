import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import time

# Correct third-party decorator import (from Dashboard cog)
try:
    from dashboard.rpc.thirdparties import dashboard_page
    DASH_OK = True
except Exception:
    DASH_OK = False


class RPXP(commands.Cog):
    """
    Westmarch RP XP tracker.

    - Gives X XP every Y messages in whitelisted RP channels
    - Per-user cooldown between awards
    - Announces awards in a configured channel and pings the user
    - Proper Red-Web-Dashboard Third Parties integration
    """

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(
            self,
            identifier=235981345234987,
            force_registration=True
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],
            "messages_needed": 5,      # Y messages
            "xp_award": 10,            # X XP
            "cooldown_seconds": 60,    # cooldown between awards
            "announce_channel": None,  # channel id or None
        }

        default_member = {
            "xp": 0,
            "msg_count": 0,
            "last_award": 0.0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        # Try to register right away if Dashboard is already loaded.
        if DASH_OK:
            self.bot.loop.create_task(self._register_third_party())

    # ---------------------------------------------------------
    # Dashboard Third Parties Registration
    # ---------------------------------------------------------
    async def _register_third_party(self):
        dashboard_cog = self.bot.get_cog("Dashboard")
        if not dashboard_cog or not hasattr(dashboard_cog, "rpc"):
            return

        handler = dashboard_cog.rpc.third_parties_handler

        # Avoid double-register on reload
        existing = getattr(handler, "third_parties", {})
        if self.qualified_name in existing:
            return

        # Register this cog as a third party
        # Docs: must use add_third_party and dashboard_page decorators. :contentReference[oaicite:1]{index=1}
        handler.add_third_party(self)

    @commands.Cog.listener()
    async def on_dashboard_cog_load(self, cog=None):
        """Dashboard fires this when it loads; we re-register."""
        if DASH_OK:
            await self._register_third_party()

    # ---------------------------------------------------------
    # Dashboard Page: /third-party/RPXP/config
    # Visible in Third Parties list.
    # ---------------------------------------------------------
    if DASH_OK:
        @dashboard_page(
            name="config",
            methods=("GET", "PATCH"),
            context_ids=["guild_id"],  # require guild context in dashboard
            hidden=False,
        )
        async def dashboard_config_page(self, guild_id: int, method: str = "GET", data=None, **kwargs):
            """
            Third-party config endpoint.

            GET  -> returns current config JSON
            PATCH -> updates config with provided JSON body
            """
            guild = self.bot.get_guild(int(guild_id))
            if guild is None:
                return {"status": 1, "error_title": "Unknown guild."}

            gconf = self.config.guild(guild)

            if method == "PATCH":
                body = {}
                if data and isinstance(data, dict):
                    body = data.get("json") or data.get("form") or {}

                # Safe, partial updates
                if "enabled" in body:
                    await gconf.enabled.set(bool(body["enabled"]))
                if "messages_needed" in body:
                    await gconf.messages_needed.set(max(1, int(body["messages_needed"])))
                if "xp_award" in body:
                    await gconf.xp_award.set(max(0, int(body["xp_award"])))
                if "cooldown_seconds" in body:
                    await gconf.cooldown_seconds.set(max(0, int(body["cooldown_seconds"])))

                if "rp_channels" in body:
                    # Expect list of channel IDs
                    await gconf.rp_channels.set([int(x) for x in body["rp_channels"]])

                if "announce_channel" in body:
                    val = body["announce_channel"]
                    await gconf.announce_channel.set(int(val) if val else None)

            conf = await gconf.all()
            return {"status": 0, "data": conf}

    # ---------------------------------------------------------
    # Core Logic — XP every Y messages + Cooldown + Announce
    # ---------------------------------------------------------
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

        # count messages regardless of cooldown
        new_count = mem_conf["msg_count"] + 1
        await self.config.member(message.author).msg_count.set(new_count)

        # cooldown blocks award, not counting
        if now - mem_conf["last_award"] < guild_conf["cooldown_seconds"]:
            return

        if new_count < guild_conf["messages_needed"]:
            return

        # award XP
        new_xp = mem_conf["xp"] + guild_conf["xp_award"]
        await self.config.member(message.author).xp.set(new_xp)

        # reset count + timestamp
        await self.config.member(message.author).msg_count.set(0)
        await self.config.member(message.author).last_award.set(now)

        # announce
        ann_id = guild_conf["announce_channel"]
        if ann_id:
            channel = message.guild.get_channel(ann_id)
            if channel:
                try:
                    await channel.send(
                        f"🎉 <@{message.author.id}> earned **{guild_conf['xp_award']} XP** "
                        f"for RP activity in {message.channel.mention}!"
                    )
                except discord.Forbidden:
                    pass

    # ---------------------------------------------------------
    # Commands
    # ---------------------------------------------------------
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RPXP manual commands."""
        pass

    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, user: discord.Member = None):
        """Show XP stats."""
        user = user or ctx.author
        data = await self.config.member(user).all()
        await ctx.send(
            f"**{user.display_name}** has **{data['xp']} XP**.\n"
            f"Messages toward next award: `{data['msg_count']}`"
        )

    @rpxp_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_add(self, ctx, user: discord.Member, xp: int):
        """Manually add XP."""
        cur = await self.config.member(user).xp()
        await self.config.member(user).xp.set(cur + xp)
        await ctx.send(f"Added **{xp} XP** to **{user.display_name}**.")

    @rpxp_group.command(name="setchannels")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setchannels(self, ctx, *channels: discord.TextChannel):
        """Set RP channels."""
        ids = [c.id for c in channels]
        await self.config.guild(ctx.guild).rp_channels.set(ids)
        await ctx.send("RP channels updated.")

    @rpxp_group.command(name="setannounce")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        """Set announcement channel."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcements will now be sent in {channel.mention}.")
