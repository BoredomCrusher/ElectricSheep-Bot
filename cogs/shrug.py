from discord.ext import commands

class Shrug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if "/shrug" in message.content:
            await message.channel.send("¯\\_(ツ)_/¯")
        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(Shrug(bot))