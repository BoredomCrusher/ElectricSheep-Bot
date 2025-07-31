'''
1.) scrape from website once per day at midnight PST
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
    print("Scraping website.")
    response = requests.get(os.getenv("URL"))
    if not os.path.exists("data/cached_website.html"):
        return {}
    with open("data/cached_website.html", "w", encoding="utf-8") as f:
        f.write(response.text)
        
# Reads html, currently used on html manually copied from source on 07-31-2025.
def read_cached_html():
    if not os.path.exists("data/cached_website.html"):
        return {}
    with open("data/cached_website.html", "r", encoding="utf-8") as f:
        return f.read()
    
def parse_recently_added(html):
    soup = BeautifulSoup(html, "html.parser")

    section = soup.find("div", id="divRecentlyAddedMarketsTabArea")
    if not section:
        print("Could not find Recently Added Markets section")
        return []

    entries = []
    rows = section.find_all("div", class_=lambda x: x and x.startswith("MarketSearchListingRow"))

    for row in rows:
        name_tag = row.find("div", class_=lambda x: x and "Name" in x)
        name = name_tag.get_text(strip=True) if name_tag else "Unnamed"
        link_tag = name_tag.find("a") if name_tag else None
        link = os.getenv("URL") + link_tag["href"] if link_tag else ""

        genres = row.find("div", class_=lambda x: x and "Genre" in x)
        genre_list = []
        if genres:
            icons = genres.find_all("img")
            genre_list = [icon.get("alt") for icon in icons if icon.get("alt")]

        lengths = row.find("div", class_=lambda x: x and "Length" in x)
        length_list = []
        if lengths:
            icons = lengths.find_all("img")
            length_list = [icon.get("alt") for icon in icons if icon.get("alt")]

        pay_tag = row.find("span")
        pay = pay_tag.get_text(strip=True) if pay_tag else "Unspecified"

        entries.append({
            "name": name,
            "link": link,
            "genres": genre_list,
            "lengths": length_list,
            "pay": pay
        })

    return entries

class Submission_Grinder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # currently bot-spam for testing
        self.channel = None
        self.html =  None
        self.daily_grinder_update.start()
        
    # @tasks.loop(time=datetime.time(hour=15, minute=30, tzinfo=ZoneInfo("America/Los_Angeles")))
    @tasks.loop(hours=10000)
    async def daily_grinder_update(self):
        now = datetime.datetime.now(pytz.timezone("US/Pacific"))
        print(f"daily grinder update posted at {now.strftime('%Y-%m%d %H:%M%S %Z')}")
        
        # fetch_website()
        self.html = read_cached_html()
        new_markets = parse_recently_added(self.html)
        if not new_markets:
            print("Failed to load new markets")
            return
        
         # Format markets for Discord
        formatted = []
        for market in new_markets:
            name = market["name"]
            link = market["link"]
            genres = ", ".join(market["genres"]) if market["genres"] else "Unspecified"
            lengths = ", ".join(market["lengths"]) if market["lengths"] else "Unspecified"
            pay = market["pay"]

            line = f"[**{name}**]({link}) — Genres: *{genres}*, Lengths: *{lengths}*, Pay: *{pay}*"
            formatted.append(line)

        content = "**Recently Added Markets:**\n" + "\n".join(f"- {line}" for line in formatted)
        
        self.channel = self.bot.get_channel(int(os.getenv("CHANNEL_ID")))
        if not self.channel:
            print("-------------------ERROR: scraper get_channel doesn't work lmao-------------------")
            return
        if len(content) > 2000:
            print(f"⚠️ Message is too long ({len(content)} characters). Splitting...")
            # Split into chunks
            chunks = []
            chunk = ""
            for line in content.split("\n"):
                if len(chunk) + len(line) + 1 > 2000:
                    chunks.append(chunk)
                    chunk = line
                else:
                    chunk += "\n" + line if chunk else line
            if chunk:
                chunks.append(chunk)

            for c in chunks:
                await self.channel.send(c)
        else:
            await self.channel.send(content)
        # Try to update existing message if it exists
        if os.path.exists(NEW_MARKETS_MESSAGE_FILE):
            with open(NEW_MARKETS_MESSAGE_FILE, "r") as f:
                data = json.load(f)
                msg_id = data.get("message_id")
                try:
                    msg = await self.channel.fetch_message(msg_id)
                    await msg.edit(content=msg.content + "\n\n**New Markets:**\n" + "\n".join(f"- {line}" for line in formatted))
                    return  # Exit after updating existing message
                except discord.NotFound:
                    print("New markets message not found.")
        else:
            print(f"{NEW_MARKETS_MESSAGE_FILE} not found.")

        # Otherwise, post a new message
        # msg = await self.channel.send(content)
        #with open(NEW_MARKETS_MESSAGE_FILE, "w") as f:
         #   json.dump({"message_id": msg.id}, f)
            
    @daily_grinder_update.before_loop
    async def before_daily_grinder_update(self):
        await self.bot.wait_until_ready()
        
async def setup(bot):
    await bot.add_cog(Submission_Grinder(bot))