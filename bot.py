import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Load Cogs (feature modules)
initial_extensions = ['cogs.submission_grinder', 'cogs.tracker', 'cogs.exquisite_corpse', 'cogs.shrug']

@bot.event
async def on_ready():
    print(f'{bot.user} has awakened, beep beep I\'m a sheep')

for ext in initial_extensions:
    bot.load_extension(ext)

bot.run(TOKEN)
