'''
1.) scrape from https://thegrinder.diabolicalplots.com/ once per day at midnight PST
    - copy the current code of the main page while writing and testing 
      so I don't scrape it a lot of times in one day 
2.) parse it and only grab from the "recently added" section
3.) format it and post it to its own channel (test with bot-spam)
4.) for everything after the first post, update the post to include 
    new markets under its own section
'''
from discord.ext import commands, tasks
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()
from bs4 import BeautifulSoup
import discord
import requests
import json, os
import asyncio
import datetime
import pytz

NEW_MARKETS_MESSAGE_FILE = "data/new_markets_message.json"

# Scrapes website.
# DO NOT SPAM THIS.
def fetch_website():
    response = requests.get(os.getenv("URL"))
    with open("data/cached_website.html", "w", encoding="utf-8") as f:
        f.write(response.text)
        
# Reads html, currently used on html manually copied from source on 07-31-2025.
def read_cached_html():
    with open("data/cached_website.html", "r", encoding="utf-8") as f:
        return f.read()
    
def parse_recently_added(html):
    soup = BeautifulSoup(html, "html.parser")
    recently_added = soup.find("div", class_="market_section", string=lambda s: "Recently Added" in s)
    
    if recently_added:
        market_list = recently_added.find_next_sibling("ul")
        items = market_list.find_all("li")
        return [item.get_text(strip=True) for item in items]
    return []

class Submission_Grinder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # currently bot-spam for testing
        self.channel = channel = self.bot.get_channel(int(os.getenv("CHANNEL_ID")))
        self.html =  read_cached_html()
        self.daily_grinder_update.start()
        
    @tasks.loop(time=datetime.time(hour=13, minute=50, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def daily_grinder_update(self):
        now = datetime.datetime.now(pytz.timezone("US/Pacific"))
        print(f"daily grinder update posted at {now.strftime('%Y-%m%d %H:%M%S %Z')}")
        new_markets = parse_recently_added(self.html)
        
        if not new_markets:
            print("Failed to load new markets")
            return
        
        content = "**Recently Added Markets:**\n" + "\n".join(f"- {m}" for m in new_markets)

        if os.path.exists(NEW_MARKETS_MESSAGE_FILE):
            with open(NEW_MARKETS_MESSAGE_FILE, "r") as f:
                data = json.load(f)
                msg_id = data.get("message_id")
                try:
                    msg = await self.channel.fetch_message(msg_id)
                    await msg.edit(content=msg.content + "\n\n**New Markets:**\n" + "\n".join(f"- {m}" for m in new_markets))
                except discord.NotFound:
                    print("New markets message not found.")
                    pass
        
        msg = await self.channel.send(content)
        with open(NEW_MARKETS_MESSAGE_FILE, "w") as f:
            json.dump({"message_id" : msg.id}, f)
            
    @daily_grinder_update.before_loop
    async def before_daily_grinder_update(self):
        await self.bot.wait_until_ready()
        
async def setup(bot):
    await bot.add_cog(Submission_Grinder(bot))