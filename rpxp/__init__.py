from .rpxp import RPXP

async def setup(bot):
    cog = RPXP(bot)
    await bot.add_cog(cog)
