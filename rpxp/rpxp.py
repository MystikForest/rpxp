import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
import math
import time


class RPXP(commands.Cog):
    """
    RPXP (Roleplay Experience System)

    Automatically grants XP to users based on message length in RP channels.

    Features:
    • XP every Y message-units
    • message-units = ceil(words / words_per_unit)
    • anti-spam minimum word requirement
    • per-message cooldown
    • RP-only channel whitelist
    • announcement channel ping
    """

    def __init__(self, bot: Red):
        self.bot = bot

        self.config = Config.get_conf(
            self, identifier=823742347892998, force_registration=True
        )

        default_guild = {
            "enabled": True,
            "rp_channels": [],
            "messages_needed": 5,
            "xp_award": 10,
            "cooldown_seconds": 15,     # per-message cooldown
            "announce_channel": None,
            "words_per_unit": 25,
            "min_words": 8,             # anti-spam
        }

        default_member = {
            "xp": 0,
            "msg_count": 0,             # message-units stored
            "last_message_time": 0.0,
        }

        self.config.register_guild(**default_guild)
        self.config.register_member(**default_member)

    # =====================================================
    # CORE RPXP LOGIC
    # =====================================================
    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):

        # Ignore DMs and bots
        if not message.guild or message.author.bot:
            return

        g = await self.config.guild(message.guild).all()
        if not g["enabled"]:
            return

        # Must be an RP channel
        if message.channel.id not in g["rp_channels"]:
            return

        m = await self.config.member(message.author).all()
        now = time.time()

        # Anti-spam minimum word requirement
        words = len(message.content.split())
        if words < g["min_words"]:
            return

        # Per-message cooldown
        if now - m["last_message_time"] < g["cooldown_seconds"]:
            return

        # Accept message
        await self.config.member(message.author).last_message_time.set(now)

        # Convert words → message-units
        units = max(1, math.ceil(words / g["words_per_unit"]))

        new_count = m["msg_count"] + units
        await self.config.member(message.author).msg_count.set(new_count)

        # Not enough message-units yet
        if new_count < g["messages_needed"]:
            return

        # Award XP
        new_xp = m["xp"] + g["xp_award"]
        await self.config.member(message.author).xp.set(new_xp)

        # Reset progress
        await self.config.member(message.author).msg_count.set(0)

        # Announce award
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
    # COMMANDS
    # =====================================================
    @commands.group(name="rpxp")
    @commands.guild_only()
    async def rpxp_group(self, ctx):
        """
        RPXP (Roleplay Experience System)

        Commands for configuring and viewing RPXP.
        Use `?help rpxp` for a full command list.
        """
        pass

    # -----------------------------------------------------
    # Admin Commands
    # -----------------------------------------------------
    @rpxp_group.command(name="toggle")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_toggle(self, ctx):
        """Toggle the RPXP system on or off."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        await ctx.send(f"RPXP enabled: **{not enabled}**")

    @rpxp_group.command(name="addchannel")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_addchannel(self, ctx, channel: discord.TextChannel):
        """Add a channel where RP messages grant XP."""
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
        """Set the channel where XP awards are announced."""
        await self.config.guild(ctx.guild).announce_channel.set(channel.id)
        await ctx.send(f"XP awards will now be announced in {channel.mention}.")

    @rpxp_group.command(name="setwords")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setwords(self, ctx, words: int):
        """Set how many words = 1 message-unit."""
        await self.config.guild(ctx.guild).words_per_unit.set(words)
        await ctx.send(f"Words per unit set to **{words}**.")

    @rpxp_group.command(name="setminwords")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setminwords(self, ctx, words: int):
        """Set the minimum words required for XP to count."""
        await self.config.guild(ctx.guild).min_words.set(words)
        await ctx.send(f"Minimum word requirement set to **{words}**.")

    @rpxp_group.command(name="setthreshold")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setthreshold(self, ctx, units: int):
        """Set how many message-units are required to award XP."""
        await self.config.guild(ctx.guild).messages_needed.set(units)
        await ctx.send(f"Message-unit threshold set to **{units}**.")

    @rpxp_group.command(name="setcooldown")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setcooldown(self, ctx, seconds: int):
        """Set the per-message cooldown."""
        await self.config.guild(ctx.guild).cooldown_seconds.set(seconds)
        await ctx.send(f"Message cooldown set to **{seconds} seconds**.")

    @rpxp_group.command(name="setxp")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_setxp(self, ctx, xp: int):
        """Set the amount of XP awarded when the threshold is reached."""
        await self.config.guild(ctx.guild).xp_award.set(xp)
        await ctx.send(f"XP award amount set to **{xp}**.")

    @rpxp_group.command(name="addxp")
    @commands.admin_or_permissions(manage_guild=True)
    async def rpxp_addxp(self, ctx, user: discord.Member, xp: int):
        """Add XP to a user manually."""
        cur = await self.config.member(user).xp()
        await self.config.member(user).xp.set(cur + xp)
        await ctx.send(f"Added **{xp} XP** to **{user.display_name}**.")

    # -----------------------------------------------------
    # User Commands
    # -----------------------------------------------------
    @rpxp_group.command(name="stats")
    async def rpxp_stats(self, ctx, user: discord.Member = None):
        """
        Show RPXP stats for yourself or another member.
        Example:
            ?rpxp stats @User
        """
        user = user or ctx.author
        data = await self.config.member(user).all()
        await ctx.send(
            f"**{user.display_name}** has **{data['xp']} XP**.\n"
            f"Message-units toward next award: `{data['msg_count']}`."
        )
