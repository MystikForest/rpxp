import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import time

try:
    from dashboard.third_parties import ThirdPartyIntegration
    DASH = True
except Exception:
    DASH = False


class RPXP(commands.Cog):
    """
    Westmarch-style RP XP tracker.

    ✔ Gives XP every Y messages
    ✔ Has per-user cooldown
    ✔ Only triggers in whitelisted RP channels
    ✔ Announces XP gains in a configured channel and pings the user
    ✔ Fully integrated with AAA3A Dashboard (Third Parties)
    """

    def __init__(self, bot: Red):
        self.bot = bot

        # ---------------------------------------------------
        # CONFIG
        # ---------------------------------------------------
        self.config = Config.get_conf(
            self,
            identifier=235981345234987,
            force_registration=True
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],
            "messages_needed": 5,    # Y messages
            "xp_award": 10,          # X XP
            "cooldown_seconds": 60,  # per-user cooldown
            "announce_channel": None,
        }

        default_member = {
            "xp": 0,
            "msg_count": 0,
            "last_award": 0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        # ---------------------------------------------------
        # DASHBOARD INTEGRATION
        # ---------------------------------------------------
        if DASH:
            self.dashboard = ThirdPartyIntegration(
                cog=self,
                name="RPXP",
                description="Grants XP every # RP messages with cooldown.",
                icon="📜",
                version="1.2.0",
                guild_settings=self._dashboard_schema(),
            )
        else:
            self.dashboard = None

    # =====================================================
    # Dashboard Schema
    # =====================================================
    def _dashboard_schema(self):
        return {
            "enabled": {
                "type": "bool",
                "label": "Enabled",
                "description": "Turn the RPXP system on or off.",
                "default": True,
            },
            "rp_channels": {
                "type": "channels",
                "label": "RP Channels",
                "description": "Only messages in these channels count for RPXP.",
                "default": [],
                "channel_types": ["text", "thread"],
            },
            "messages_needed": {
                "type": "number",
                "label": "Messages Needed",
                "description": "Award XP after this many RP messages.",
                "default": 5,
            },
            "xp_award": {
                "type": "number",
                "label": "XP Award",
                "description": "How much XP to award each time.",
                "default": 1,
            },
            "cooldown_seconds": {
                "type": "number",
                "label": "Cooldown (seconds)",
                "description": "Minimum time between XP awards per user.",
                "default": 60,
            },
            "announce_channel": {
                "type": "channel",
                "label": "Announcement Channel",
                "description": "Where XP awards are posted (user will be pinged).",
                "default": None,
                "channel_types": ["text"],
            },
        }

    # =====================================================
    # Core Logic — XP every Y messages + Cooldown + Announce
    # =====================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        # Must be in RP channel
        if message.channel.id not in guild_conf["rp_channels"]:
            return

        mem_conf = await self.config.member(message.author).all()
        now = time.time()

        # Cooldown check
        if now - mem_conf["last_award"] < guild_conf["cooldown_seconds"]:
            # Still count message even if cooldown prevents award
            await self.config.member(message.author).msg_count.set(mem_conf["msg_count"] + 1)
            return

        # Count this message
        new_count = mem_conf["msg_count"] + 1
        await self.config.member(message.author).msg_count.set(new_count)

        # Not enough messages yet?
        if new_count < guild_conf["messages_needed"]:
            return

        # Award XP
        new_xp = mem_conf["xp"] + guild_conf["xp_award"]
        await self.config.member(message.author).xp.set(new_xp)

        # Reset counters + timestamp
        await self.config.member(message.author).msg_count.set(0)
        await self.config.member(message.author).last_award.set(now)

        # Announce the award
        if guild_conf["announce_channel"]:
            channel = message.guild.get_channel(guild_conf["announce_channel"])
            if channel:
                try:
                    await channel.send(
                        f"🎉 <@{message.author.id}> earned XP for RP activity!
                        Run `!rpxp` to claim it!"
                    )
                except discord.Forbidden:
                    pass

    # =====================================================
    # Commands
    # =====================================================
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RPXP manual commands."""
        pass

    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, user: discord.Member = None):
        """Show XP stats for you or another user."""
        user = user or ctx.author
        conf = await self.config.member(user).all()

        await ctx.send(
            f"**{user.display_name}** has **{conf['xp']} XP**.\n"
            f"Messages toward next award: `{conf['msg_count']}`"
        )

    @rpxp_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_add(self, ctx, user: discord.Member, xp: int):
        """Add XP manually."""
        cur = await self.config.member(user).xp()
        await self.config.member(user).xp.set(cur + xp)
        await ctx.send(f"Added **{xp} XP** to **{user.display_name}**.")

    @rpxp_group.command(name="setannounce")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        """Set announcement channel."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcements will now be sent in {channel.mention}.")
