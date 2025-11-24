import discord
from discord import TextChannel, ForumChannel
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time

# Optional Dashboard support
try:
    from dashboard.rpc import rpc
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False


class RPXP(commands.Cog):
    """
    RP XP system for Westmarch / West Marches style D&D servers.

    Features:
    - XP only from designated RP channels (text OR forum)
    - XP from threads inside RP channels
    - XP from forum posts inside forum RP channels
    - Word-based multiplier (ceil(words / words_per_count))
    - Minimum word requirement (anti-spam)
    - Per-message cooldown
    - Award X XP every Y qualifying messages
    - Announcement channel that pings the user
    - Full config commands
    - Dashboard integration (AAA3A-cogs)
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
            "rp_channels": [],
            "announce_channel": None,

            "xp_per_award": 5,
            "msg_per_award": 10,

            "min_words": 5,
            "words_per_count": 25,

            "cooldown_seconds": 30,
        }

        default_member = {
            "last_message_time": 0,
            "message_counter": 0,
            "xp": 0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        # Register for Dashboard UI
        if DASH_AVAILABLE:
            rpc.register_cog(self)

    # ======================================================
    # Dashboard RPC Actions
    # ======================================================
    if DASH_AVAILABLE:
        @rpc.with_action(name="get_config")
        async def dashboard_get_config(self, guild_id: int):
            guild = self.bot.get_guild(guild_id)
            return await self.config.guild(guild).all()

        @rpc.with_action(name="update_config")
        async def dashboard_update_config(self, guild_id: int, data: dict):
            guild = self.bot.get_guild(guild_id)
            conf = self.config.guild(guild)
            for key, val in data.items():
                if hasattr(conf, key):
                    await getattr(conf, key).set(val)
            return {"status": "ok"}

    # ======================================================
    # MAIN MESSAGE HANDLER
    # ======================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):

        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        rp_channels = guild_conf["rp_channels"]

        # =============================
        # CHANNEL + THREAD DETECTION
        # =============================
        ch = message.channel
        in_rp_channel = False

        # 1) Direct RP channel (text OR forum)
        if ch.id in rp_channels:
            in_rp_channel = True

        # 2) Thread under text channel
        elif isinstance(ch, discord.Thread) and ch.parent_id in rp_channels:
            in_rp_channel = True

        # 3) Forum post (thread whose parent is a ForumChannel)
        elif isinstance(ch, discord.Thread) and isinstance(ch.parent, ForumChannel) and ch.parent.id in rp_channels:
            in_rp_channel = True

        if not in_rp_channel:
            return

        # Minimum word filter
        words = message.content.split()
        if len(words) < guild_conf["min_words"]:
            return

        # Per-message cooldown
        member_conf = await self.config.member(message.author).all()
        now = time.time()
        if now - member_conf["last_message_time"] < guild_conf["cooldown_seconds"]:
            return

        await self.config.member(message.author).last_message_time.set(now)

        # Word multiplier
        multiplier = max(1, math.ceil(len(words) / guild_conf["words_per_count"]))

        # Add message weight
        new_count = member_conf["message_counter"] + multiplier
        await self.config.member(message.author).message_counter.set(new_count)

        # Not enough messages yet
        if new_count < guild_conf["msg_per_award"]:
            return

        # Award XP
        xp_gain = guild_conf["xp_per_award"]
        new_xp = member_conf["xp"] + xp_gain

        await self.config.member(message.author).xp.set(new_xp)
        await self.config.member(message.author).message_counter.set(0)

        # Announce
        ann_id = guild_conf["announce_channel"]
        if ann_id:
            channel = message.guild.get_channel(ann_id)
            if channel:
                try:
                    await channel.send(
                        f"✨ **RP XP Awarded!** ✨\n"
                        f"{message.author.mention} gained XP for RP! Run `!rpxp` to claim it!"
                    )
                except discord.Forbidden:
                    pass

    # ======================================================
    # COMMANDS
    # ======================================================
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RPXP commands"""
        pass

    # ---------- USER COMMAND ----------
    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, member: discord.Member = None):
        """Check your XP."""
        member = member or ctx.author
        data = await self.config.member(member).all()
        guild_conf = await self.config.guild(ctx.guild).all()

        await ctx.send(
            f"**{member.display_name}** has **{data['xp']} XP**.\n"
            f"Progress: {data['message_counter']} / {guild_conf['msg_per_award']} messages."
        )

    # ---------- ADMIN: CONFIG ROOT ----------
    @rpxp_group.group(name="config")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_config(self, ctx):
        """Configure RPXP system."""
        pass

    @rpxp_config.command(name="show")
    async def rpxp_config_show(self, ctx):
        """Show full configuration."""
        conf = await self.config.guild(ctx.guild).all()

        channels = [ctx.guild.get_channel(cid) for cid in conf["rp_channels"]]
        channels_fmt = ", ".join(ch.mention for ch in channels if ch) or "None"

        ann = ctx.guild.get_channel(conf["announce_channel"])
        ann_fmt = ann.mention if ann else "None"

        await ctx.send(
            f"**RPXP Configuration**\n"
            f"Enabled: `{conf['enabled']}`\n"
            f"RP Channels: {channels_fmt}\n"
            f"Announce Channel: {ann_fmt}\n\n"
            f"XP per Award: `{conf['xp_per_award']}`\n"
            f"Messages per Award: `{conf['msg_per_award']}`\n\n"
            f"Minimum Words: `{conf['min_words']}`\n"
            f"Words per Count: `{conf['words_per_count']}`\n\n"
            f"Cooldown Seconds: `{conf['cooldown_seconds']}`"
        )

    # ---------- ADMIN: SET AWARD PARAMETERS ----------
    @rpxp_config.command(name="setaward")
    async def rpxp_config_setaward(self, ctx, xp_per: int, msgs: int):
        """Set X XP per Y messages."""
        await self.config.guild(ctx.guild).xp_per_award.set(xp_per)
        await self.config.guild(ctx.guild).msg_per_award.set(msgs)
        await ctx.send(f"Set award: **{xp_per} XP** every **{msgs} messages**.")

    # ---------- ADMIN: SET WORD PARAMETERS ----------
    @rpxp_config.command(name="setwords")
    async def rpxp_config_setwords(self, ctx, min_words: int, words_per_count: int):
        """Set minimum words and words-per-count threshold."""
        await self.config.guild(ctx.guild).min_words.set(min_words)
        await self.config.guild(ctx.guild).words_per_count.set(words_per_count)
        await ctx.send(
            f"Set minimum words to **{min_words}**, word multiplier chunk to **{words_per_count}**."
        )

    # ---------- ADMIN: SET COOLDOWN ----------
    @rpxp_config.command(name="setcooldown")
    async def rpxp_config_setcooldown(self, ctx, seconds: int):
        """Set per-message cooldown."""
        await self.config.guild(ctx.guild).cooldown_seconds.set(seconds)
        await ctx.send(f"Set cooldown to **{seconds} seconds**.")

    # ---------- ADMIN: MANAGE CHANNELS (TEXT + FORUM) ----------
    @rpxp_config.command(name="addchannel")
    async def rpxp_addchannel(self, ctx, channel: discord.abc.GuildChannel):
        """Add a text or forum channel to RPXP tracking."""
        if not isinstance(channel, (TextChannel, ForumChannel)):
            return await ctx.send("❌ Only text channels or forum channels can be RPXP sources.")

        rp_channels = await self.config.guild(ctx.guild).rp_channels()

        if channel.id not in rp_channels:
            rp_channels.append(channel.id)
            await self.config.guild(ctx.guild).rp_channels.set(rp_channels)

        await ctx.send(f"Added {channel.mention} as an RPXP channel.")

    @rpxp_config.command(name="removechannel")
    async def rpxp_removechannel(self, ctx, channel: discord.abc.GuildChannel):
        """Remove a text or forum channel from RPXP tracking."""
        rp_channels = await self.config.guild(ctx.guild).rp_channels()

        if channel.id in rp_channels:
            rp_channels.remove(channel.id)
            await self.config.guild(ctx.guild).rp_channels.set(rp_channels)

        await ctx.send(f"Removed {channel.mention} from RPXP channels.")

    # ---------- ADMIN: ANNOUNCEMENT CHANNEL ----------
    @rpxp_config.command(name="setannounce")
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcement channel set to {channel.mention}")

    # ---------- ADMIN: TOGGLE ----------
    @rpxp_config.command(name="enable")
    async def rpxp_enable(self, ctx):
        await self.config.guild(ctx.guild).enabled.set(True)
        await ctx.send("RPXP is **enabled**.")

    @rpxp_config.command(name="disable")
    async def rpxp_disable(self, ctx):
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("RPXP is **disabled**.")
