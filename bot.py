import os
import discord
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load Cogs (feature modules)
# initial_extensions = ['cogs.submission_grinder', 'cogs.tracker', 'cogs.exquisite_corpse', 'cogs.bot_commands']

@bot.event
async def on_ready():
    print(f'{bot.user} has awakened, beep beep I\'m a sheep')

# This is supposed to have an await, but not all of the files are done yet,
# so this is going to be added under main once all of the functions are ready.
# for ext in initial_extensions:
#      bot.load_extension(ext)

async def main():
    async with bot:
        await bot.load_extension("cogs.bot_commands")
        await bot.load_extension("cogs.tracker")
        await bot.load_extension("cogs.submission_grinder")
        await bot.start(TOKEN)
        
asyncio.run(main())
