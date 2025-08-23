from discord.ext import commands

class Bot_Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        if "/shrug" in message.content.lower():
            await message.channel.send("¯\\_(ツ)_/¯")
        if "good bot" in message.content.lower():
            emoji = self.bot.get_emoji(1058902343539761274)
            if emoji:
                await message.channel.send(f"{emoji}")
        if "bad bot" in message.content.lower():
            emoji = self.bot.get_emoji(1380412150429909012)
            if emoji:
                await message.channel.send(f"I am what I was made to be, blame my creator instead.")
                await message.channel.send(f"{emoji}")
        if "hell yeah" in message.content.lower():
            emoji = self.bot.get_emoji(1058884605752643654)
            if emoji:
                await message.channel.send(f"{emoji}")
        if "just write" in message.content.lower():
            await message.channel.send(f"it's that easy.")
        if "trans rights" in message.content.lower():
            emoji = self.bot.get_emoji(1408954485317042207)
            if emoji:
                await message.channel.send(f"{emoji}")
            
async def setup(bot):
    await bot.add_cog(Bot_Commands(bot))