from .rpxp import RPXP

async def setup(bot):
    await bot.add_cog(RPXP(bot))
