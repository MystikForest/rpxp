import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time

try:
    from dashboard.rpc import rpc
    DASH_AVAILABLE = True
except Exception:
    DASH_AVAILABLE = False


class RPXP(commands.Cog):
    """
    RP XP system for Westmarch-style servers.
    Now includes:
    - Word-based XP multipliers
    - Anti-spam minimum word filter
    - Cooldown per message (not per award)
    - Award X XP every Y qualifying messages
    - Announcement channel + user ping
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
            "announce_channel": None,      # XP announcements
            "xp_per_award": 5,             # X XP
            "msg_per_award": 10,           # every Y messages
            "min_words": 5,                # minimum word count
            "words_per_count": 25,         # award count = ceil(words/words_per_count)
            "cooldown_seconds": 30,        # per MESSAGE cooldown
        }

        default_member = {
            "last_message_time": 0,        # cooldown timer
            "message_counter": 0,          # counts messages toward award threshold
            "xp": 0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

        if DASH_AVAILABLE:
            rpc.register_cog(self)

    # -------------------------------
    # DASHBOARD RPC SUPPORT
    # -------------------------------
    if DASH_AVAILABLE:
        @rpc.with_action(name="get_config", description="Fetch RPXP config")
        async def dashboard_get_config(self, guild_id: int):
            guild = self.bot.get_guild(guild_id)
            return await self.config.guild(guild).all()

        @rpc.with_action(name="update_config", description="Update RPXP config")
        async def dashboard_update_config(self, guild_id: int, data: dict):
            guild = self.bot.get_guild(guild_id)
            conf = self.config.guild(guild)

            for key, value in data.items():
                if hasattr(conf, key):
                    await getattr(conf, key).set(value)

            return {"status": "ok"}

    # -------------------------------------
    # MESSAGE LISTENER (MAIN LOGIC)
    # -------------------------------------
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):

        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        if message.channel.id not in guild_conf["rp_channels"]:
            return

        # ---------- MINIMUM WORD FILTER ----------
        words = message.content.split()
        if len(words) < guild_conf["min_words"]:
            return

        # ---------- PER-MESSAGE COOLDOWN ----------
        member_conf = await self.config.member(message.author).all()
        now = time.time()

        if now - member_conf["last_message_time"] < guild_conf["cooldown_seconds"]:
            return

        await self.config.member(message.author).last_message_time.set(now)

        # ---------- WORD-BASED MESSAGE MULTIPLIER ----------
        multiplier = math.ceil(len(words) / guild_conf["words_per_count"])

        # ---------- MESSAGE COUNTER FOR THRESHOLD ----------
        new_count = member_conf["message_counter"] + multiplier
        await self.config.member(message.author).message_counter.set(new_count)

        # ---------- ONLY AWARD XP WHEN THRESHOLD HIT ----------
        if new_count < guild_conf["msg_per_award"]:
            return

        # Award time!
        xp_gain = guild_conf["xp_per_award"]
        total_xp = member_conf["xp"] + xp_gain

        await self.config.member(message.author).xp.set(total_xp)
        await self.config.member(message.author).message_counter.set(0)

        # ---------- ANNOUNCEMENT ----------
        channel_id = guild_conf["announce_channel"]
        if channel_id:
            ch = message.guild.get_channel(channel_id)
            if ch:
                await ch.send(
                    f"✨ **RP XP Awarded!** ✨\n"
                    f"{message.author.mention} gained **{xp_gain} XP** for RP."
                )

    # -------------------------------------
    # COMMANDS
    # -------------------------------------

    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RPXP admin commands."""
        pass

    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, member: discord.Member = None):
        """Check your (or someone else’s) RPXP."""
        member = member or ctx.author
        data = await self.config.member(member).all()

        await ctx.send(
            f"**{member.display_name}** has **{data['xp']} XP**.\n"
            f"Message progress: {data['message_counter']} messages toward next award."
        )

    @rpxp_group.command(name="announce")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        """Set the channel where RPXP gets announced."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcement channel set to {channel.mention}")

    @rpxp_group.command(name="setchannels")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setchannels(self, ctx, *channels: discord.TextChannel):
        ids = [ch.id for ch in channels]
        await self.config.guild(ctx.guild).rp_channels.set(ids)
        await ctx.send(
            f"RP channels updated: {', '.join(ch.mention for ch in channels)}"
        )

    @rpxp_group.command(name="add")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_add(self, ctx, member: discord.Member, xp: int):
        cur = await self.config.member(member).xp()
        await self.config.member(member).xp.set(cur + xp)
        await ctx.send(f"Added **{xp} XP** to **{member.display_name}**.")
