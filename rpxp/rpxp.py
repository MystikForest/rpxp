import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time


class RPXP(commands.Cog):
    """
    Westmarch RP XP tracker (NO dashboard).

    Features:
    - XP every Y message-units
    - units = ceil(words / words_per_unit)
    - anti-spam (min word requirement)
    - per-message cooldown
    - RP-only channels
    - announcement channel
    """

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
            "cooldown_seconds": 15,     # PER MESSAGE cooldown
            "announce_channel": None,
            "words_per_unit": 25,       # words → units
            "min_words": 8,             # anti-spam
        }

        default_member = {
            "xp": 0,
            "msg_count": 0,             # stores units
            "last_message_time": 0.0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

    # =====================================================
    # CORE LOGIC
    # =====================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        # Ignore bots, DMs
        if not message.guild or message.author.bot:
            return

        guild_conf = await self.config.guild(message.guild).all()
        if not guild_conf["enabled"]:
            return

        # Not in RP channel → ignore
        if message.channel.id not in guild_conf["rp_channels"]:
            return

        user_conf = await self.config.member(message.author).all()
        now = time.time()

        # Anti-spam: message too short
        words = len(message.content.split())
        if words < guild_conf["min_words"]:
            return

        # Per-message cooldown
        if now - user_conf["last_message_time"] < guild_conf["cooldown_seconds"]:
            return

        # Accept this message
        await self.config.member(message.author).last_message_time.set(now)

        # Convert to "message-units"
        units = max(1, math.ceil(words / guild_conf["words_per_unit"]))

        new_count = user_conf["msg_count"] + units
        await self.config.member(message.author).msg_count.set(new_count)

        # Threshold not met yet
        if new_count < guild_conf["messages_needed"]:
            return

        # Award XP
        new_xp = user_conf["xp"] + guild_conf["xp_award"]
        await self.config.member(message.author).xp.set(new_xp)

        # Reset units
        await self.config.member(message.author).msg_count.set(0)

        # Announce it
        ann_id = guild_conf["announce_channel"]
        if ann_id:
            chan = message.guild.get_channel(ann_id)
            if chan:
                try:
                    await chan.send(
                        f"🎉 <@{message.author.id}> earned XP for RP activity! Run !rpxp to claim it!"
                    )
                except discord.Forbidden:
                    pass

    # =====================================================
    # COMMANDS
    # =====================================================
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """RP XP commands."""
        pass

    # --- Admin commands ---
    @rpxp_group.command(name="toggle")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_toggle(self, ctx):
        """Toggle RPXP on/off."""
        g = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not g)
        await ctx.send(f"RPXP enabled: **{not g}**")

    @rpxp_group.command(name="addchannel")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_addchannel(self, ctx, channel: discord.TextChannel):
        """Add an RP channel."""
        chans = await self.config.guild(ctx.guild).rp_channels()
        if channel.id not in chans:
            chans.append(channel.id)
            await self.config.guild(ctx.guild).rp_channels.set(chans)
        await ctx.send(f"Added RP channel: {channel.mention}")

    @rpxp_group.command(name="removechannel")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_removechannel(self, ctx, channel: discord.TextChannel):
        """Remove an RP channel."""
        chans = await self.config.guild(ctx.guild).rp_channels()
        if channel.id in chans:
            chans.remove(channel.id)
            await self.config.guild(ctx.guild).rp_channels.set(chans)
        await ctx.send(f"Removed RP channel: {channel.mention}")

    @rpxp_group.command(name="setannounce")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setannounce(self, ctx, channel: discord.TextChannel):
        """Set the announcement channel."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"Announcements will now appear in {channel.mention}.")

    @rpxp_group.command(name="setwords")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setwords(self, ctx, words: int):
        """Set words-per-unit."""
        await self.config.guild(ctx.guild).words_per_unit.set(words)
        await ctx.send(f"Words per unit set to **{words}**.")

    @rpxp_group.command(name="setminwords")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setminwords(self, ctx, words: int):
        """Set minimum words to count."""
        await self.config.guild(ctx.guild).min_words.set(words)
        await ctx.send(f"Minimum words set to **{words}**.")

    @rpxp_group.command(name="setthreshold")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setthreshold(self, ctx, units: int):
        """Set message-units needed for XP."""
        await self.config.guild(ctx.guild).messages_needed.set(units)
        await ctx.send(f"Message-units threshold set to **{units}**.")

    @rpxp_group.command(name="setcooldown")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setcooldown(self, ctx, seconds: int):
        """Set per-message cooldown."""
        await self.config.guild(ctx.guild).cooldown_seconds.set(seconds)
        await ctx.send(f"Cooldown set to **{seconds} seconds**.")

    @rpxp_group.command(name="setxp")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setxp(self, ctx, xp: int):
        """Set XP award amount."""
        await self.config.guild(ctx.guild).xp_award.set(xp)
        await ctx.send(f"XP award set to **{xp}**.")

    # --- Stats commands ---
    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, user: discord.Member = None):
        """See XP stats for you or someone else."""
        user = user or ctx.author
        data = await self.config.member(user).all()
        await ctx.send(
            f"**{user.display_name}** has **{data['xp']} XP**.\n"
            f"Message-units toward next award: `{data['msg_count']}`."
        )

    @commands.admin_or_permissions(manage_guild=True)
    @rpxp_group.command(name="addxp")
    async def rpxp_addxp(self, ctx, user: discord.Member, xp: int):
        """Admin: add XP to a user."""
        cur = await self.config.member(user).xp()
        await self.config.member(user).xp.set(cur + xp)
        await ctx.send(f"Added XP to **{user.display_name}**.")
