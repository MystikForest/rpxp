import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time

# Dashboard compatibility
try:
    from dashboard.rpc import rpc
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False


class RPXP(commands.Cog):
    """
    RP XP system for Westmarch-style servers.

    Features:
    ✔ XP only from designated RP channels
    ✔ Word-based multiplier (ceil(words / words_per_count))
    ✔ Anti-spam minimum word filter
    ✔ Per-message cooldown (not per-award)
    ✔ Award X XP every Y messages
    ✔ Announcement channel with pings
    ✔ Fully Dashboard-configurable via AAA3A-cogs Dashboard
    """

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(
            self,
            identifier=9182374912374918273,
            force_registration=True,
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],             # eligible RP channels
            "announce_channel": None,      # XP announcement channel
            "xp_per_award": 5,             # X XP per award
            "msg_per_award": 10,           # Y messages per award
            "min_words": 5,                # minimum words per message
            "words_per_count": 25,         # message multiplier threshold
            "cooldown_seconds": 30,        # per MESSAGE cooldown
        }

        default_member = {
            "last_message_time": 0,
            "message_counter": 0,          # progress toward next award
            "xp": 0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        # Register cog for AAA3A Dashboard if available
        if DASH_AVAILABLE:
            rpc.register_cog(self)

    # ======================================================
    # AAA3A Dashboard RPC Integration
    # ======================================================
    if DASH_AVAILABLE:
        @rpc.with_action(name="get_config", description="Fetch RPXP configuration")
        async def dashboard_get_config(self, guild_id: int):
            guild = self.bot.get_guild(guild_id)
            return await self.config.guild(guild).all()

        @rpc.with_action(name="update_config", description="Update RPXP settings")
        async def dashboard_update_config(self, guild_id: int, data: dict):
            guild = self.bot.get_guild(guild_id)
            conf = self.config.guild(guild)

            for key, value in data.items():
                if hasattr(conf, key):
                    await getattr(conf, key).set(value)

            return {"status": "ok"}

    # ======================================================
    # MESSAGE LISTENER (MAIN XP LOGIC)
    # ======================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):

        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        # -------- Channel check --------
        if message.channel.id not in guild_conf["rp_channels"]:
            return

        # -------- Minimum word filter --------
        words = message.content.split()
        if len(words) < guild_conf["min_words"]:
            return

        # -------- Per-message cooldown --------
        member_conf = await self.config.member(message.author).all()
        now = time.time()

        if now - member_conf["last_message_time"] < guild_conf["cooldown_seconds"]:
            return

        await self.config.member(message.author).last_message_time.set(now)

        # -------- Word multiplier --------
        multiplier = max(1, math.ceil(len(words) / guild_conf["words_per_count"]))

        # Add to message counter
        new_count = member_conf["message_counter"] + multiplier
        await self.config.member(message.author).message_counter.set(new_count)

        # -------- Not enough messages yet --------
        if new_count < guild_conf["msg_per_award"]:
            return

        # =====================================================
        #  Time to award XP!
        # =====================================================
        xp_gain = guild_conf["xp_per_award"]
        total_xp = member_conf["xp"] + xp_gain

        await self.config.member(message.author).xp.set(total_xp)
        await self.config.member(message.author).message_counter.set(0)

        # -------- Announce XP Award --------
        channel_id = guild_conf["announce_channel"]
        if channel_id:
            ann_channel = message.guild.get_channel(channel_id)
            if ann_channel:
                try:
                    await ann_channel.send(
                        f"✨ **RP XP Awarded!** ✨\n"
                        f"{message.author.mention} gained **{xp_gain} XP** for roleplay!"
                    )
                except discord.Forbidden:
                    pass

    # ======================================================
    # COMMANDS
    # ======================================================
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RPXP admin + user commands."""
        pass

    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, member: discord.Member = None):
        """Check RPXP for yourself or another member."""
        member = member or ctx.author
        data = await self.config.member(member).all()

        await ctx.send(
            f"**{member.display_name}** has **{data['xp']} XP**.\n"
            f"Progress: {data['message_counter']} / "
            f"{(await self.config.guild(ctx.guild).msg_per_award())} messages toward next award."
        )

    @rpxp_group.command(name="setannounce")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        """Set the announcement channel for RPXP awards."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcement channel set to {channel.mention}")

    @rpxp_group.command(name="setchannels")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setchannels(self, ctx, *channels: discord.TextChannel):
        """Set which channels grant RPXP."""
        ids = [ch.id for ch in channels]
        await self.config.guild(ctx.guild).rp_channels.set(ids)
        await ctx.send(
            f"RP channels updated: {', '.join(ch.mention for ch in channels)}"
        )

    @rpxp_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_add(self, ctx, member: discord.Member, xp: int):
        """Manually grant XP."""
        current = await self.config.member(member).xp()
        await self.config.member(member).xp.set(current + xp)
        await ctx.send(f"Added **{xp} XP** to **{member.display_name}**.")
