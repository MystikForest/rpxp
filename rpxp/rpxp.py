import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_timedelta

# Dashboard integration
try:
    from dashboard.rpc import rpc
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False


class RPXP(commands.Cog):
    """
    RP XP system for Westmarch-style D&D servers.
    Grants XP only in configured RP channels.
    Integrates with AAA3A Dashboard.
    """

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(
            self,
            identifier=823749234234978234,
            force_registration=True
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],     # channel IDs
            "xp_per_message": 5,
            "cooldown_seconds": 60,  # per-user cooldown in RP channels
        }

        default_member = {
            "last_xp_time": 0,
            "xp": 0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        if DASH_AVAILABLE:
            rpc.register_cog(self)

    # ==========================================================
    # Dashboard Schema
    # ==========================================================
    if DASH_AVAILABLE:
        @rpc.with_action(
            name="get_config",
            description="Fetch RPXP config for Dashboard UI"
        )
        async def dashboard_get_config(self, guild_id: int):
            guild = self.bot.get_guild(guild_id)
            conf = await self.config.guild(guild).all()

            return {
                "enabled": conf["enabled"],
                "rp_channels": conf["rp_channels"],
                "xp_per_message": conf["xp_per_message"],
                "cooldown_seconds": conf["cooldown_seconds"],
            }

        @rpc.with_action(
            name="update_config",
            description="Update RPXP config from Dashboard UI"
        )
        async def dashboard_update_config(self, guild_id: int, data: dict):
            guild = self.bot.get_guild(guild_id)
            conf = self.config.guild(guild)

            await conf.enabled.set(bool(data.get("enabled", True)))
            await conf.rp_channels.set(list(map(int, data.get("rp_channels", []))))
            await conf.xp_per_message.set(int(data.get("xp_per_message", 5)))
            await conf.cooldown_seconds.set(int(data.get("cooldown_seconds", 60)))

            return {"status": "ok"}

    # ==========================================================
    # RPXP Logic
    # ==========================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        if message.channel.id not in guild_conf["rp_channels"]:
            return

        # Cooldown check
        member_conf = await self.config.member(message.author).all()
        now = message.created_at.timestamp()
        cd = guild_conf["cooldown_seconds"]

        if now - member_conf["last_xp_time"] < cd:
            return  # still cooling down

        # Award XP
        xp_gain = guild_conf["xp_per_message"]
        await self.config.member(message.author).xp.set(member_conf["xp"] + xp_gain)
        await self.config.member(message.author).last_xp_time.set(now)

    # ==========================================================
    # Commands
    # ==========================================================

    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RPXP admin and view commands."""
        pass

    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, member: discord.Member = None):
        """Check your (or someone else’s) RPXP."""
        member = member or ctx.author
        data = await self.config.member(member).all()

        await ctx.send(
            f"**{member.display_name}** has **{data['xp']} XP**.\n"
            f"Last gain: {humanize_timedelta(seconds=int(data['last_xp_time'])) if data['last_xp_time'] else 'Never'}"
        )

    @rpxp_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_add(self, ctx, member: discord.Member, xp: int):
        """Manually add XP."""
        cur = await self.config.member(member).xp()
        await self.config.member(member).xp.set(cur + xp)
        await ctx.send(f"Added **{xp} XP** to **{member.display_name}**.")

    @rpxp_group.command(name="setchannels")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setchannels(self, ctx, *channels: discord.TextChannel):
        """Set RP-eligible channels."""
        ids = [ch.id for ch in channels]
        await self.config.guild(ctx.guild).rp_channels.set(ids)
        await ctx.send(
            f"RP channels set to: {', '.join(ch.mention for ch in channels) or 'None'}"
        )

    @rpxp_group.command(name="config")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_config_show(self, ctx):
        """Show current config."""
        conf = await self.config.guild(ctx.guild).all()
        chans = [ctx.guild.get_channel(cid) for cid in conf["rp_channels"]]

        await ctx.send(
            f"**RPXP Config**\n"
            f"Enabled: `{conf['enabled']}`\n"
            f"XP/message: `{conf['xp_per_message']}`\n"
            f"Cooldown: `{conf['cooldown_seconds']} seconds`\n"
            f"Channels: {', '.join(ch.mention for ch in chans if ch) or 'None'}"
        )
