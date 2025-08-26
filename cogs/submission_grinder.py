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

NEW_MARKETS_MESSAGE_FILE = "data/new_markets_message.txt"
#CHANNEL = "SUBMISSION_GRINDER_CHANNEL_ID"
CHANNEL = "CHANNEL_ID"

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
    print("HTML parsed.")
    return entries

class Submission_Grinder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # currently bot-spam for testing
        self.channel = None
        self.html =  None
        self.send_daily_grinder_update.start()
        self.daily_fetch_website.start()
        
    # Runs every 24 hours to not scrape the website too often.
    @tasks.loop(time=datetime.time(hour=23, minute=59, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def daily_fetch_website(self):
        fetch_website()
        # The next two lines are probably redundant.
        self.html = read_cached_html()
        new_markets = parse_recently_added(self.html)
        if not new_markets:
            print("Failed to load new markets.")
            return
        else:
            print("New markets loaded.")
        
    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def send_daily_grinder_update(self):
        await self.daily_grinder_update()
    
    @daily_fetch_website.before_loop
    async def before_daily_fetch_website(self):
        await self.bot.wait_until_ready()
    
    async def daily_grinder_update(self):
        now = datetime.datetime.now(pytz.timezone("US/Pacific"))
        print(f"daily grinder update posted at {now.strftime('%Y-%m%d %H:%M%S %Z')}")
        
        new_markets = parse_recently_added(read_cached_html())
        
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
           
        content = ("\n".join(f"-# - {line}" for line in formatted))
        content = content.splitlines()
        
        self.channel = self.bot.get_channel(int(os.getenv(CHANNEL)))
        if not self.channel:
            print("ERROR: scraper get_channel doesn't work.")
            return
        
        print("attempting to open file")
        if os.path.exists(NEW_MARKETS_MESSAGE_FILE):
            with open(NEW_MARKETS_MESSAGE_FILE, "r+") as f:
                data = f.read()
                f.seek(0)
                lines = data.splitlines()
                
                # Writes to file if empty.
                file_was_empty = False
                if not lines:
                    file_was_empty = True
                    print("Message file empty, now writing to file.")
                    for message in content:
                        f.write(message)
                    f.seek(0)
                    lines = f.read().splitlines()
                else:
                    print("Message file not empty.")
                    
                expired_markets = []
                closed_markets = ["\n\n**Temporarily Closed Markets:**\n"]
                open_markets = ["\n\n**Current Markets:**\n"]
                non_paying = [["\nNon-Paying:\n"], ["\nNon_Paying:\n"]]
                paying = [["\nPaying:\n"], ["\nPaying:\n"]]
                # removes expired markets and appends their names to a string
                for line in lines:
                    if line not in content:
                        if "[**" in line:
                            expired_markets.append(line.split("**", 1)[1].split("**")[0])
                    else:
                        if "Temp Closed" in line:
                            if "Non-Paying" in line:
                                non_paying[0].append(line)
                            else:
                                paying[0].append(line)
                        else:
                            if "Non-Paying" in line:
                                non_paying[1].append(line)
                            else:
                                paying[1].append(line)
                print("passed loop")
                expired_markets.sort()
                non_paying[0].sort()
                paying[0].sort()
                non_paying[1].sort()
                paying[1].sort()
                closed_markets = closed_markets + non_paying[0] + paying[0]
                open_markets = open_markets + non_paying[1] + paying[1]

                lines = closed_markets + open_markets

                if not expired_markets:
                    print("No expired markets.")
                else:
                    ''' 
                    This doesn't cover for if there are so many expired markets 
                    that it requires more than one discord message to send, 
                    but that many markets expiring at the same time 
                    with the website this code scrapes from is impossible 
                    unless the code isn't working as intended.
                    '''
                    print("Updating expired markets")

                    await self.channel.send("**Expired markets:**\n" + ", ".join(expired_markets) + ".")
                
                just_added = ["\n**Just Added Today:**"]
                non_paying = ["\nNon-Paying:\n"]
                paying = ["\nPaying:\n"]
                any_new_markets = False
                
                for message in content:
                    if message not in lines:
                        print("just added: " + message)
                        any_new_markets = True
                        if "Non-Paying" in message:
                            non_paying.append(message)
                        else:
                            paying.append(message)
            
                if not any_new_markets: 
                    just_added.append("None.")
                else:
                    non_paying.sort()
                    paying.sort()
                    just_added = just_added + non_paying + paying

                lines = lines + just_added

                if not file_was_empty:
                    f.truncate()
                    print("Writing new content to file.")
                    for line in lines:
                        f.write(line + "\n")
        else:
            print("ERROR: message file not found.")
            return
        print("Attempting to print content.")
        content = lines
        charcount = "".join(content)
                        
        if len(charcount) > 2000:
            print(f"⚠️ Message is too long ({len(content)} characters). Splitting...")
            # Split into chunks
            chunks = []
            chunk = ""
            for line in content:
                if len(chunk) + len(line) + 1 > 2000:
                    chunks.append(chunk)
                    chunk = line
                else:
                    chunk += "\n" + line if chunk else line
            if chunk:
                chunks.append(chunk)

            for c in chunks:
                print(f"printing chunk character size {len(c)}")
                await self.channel.send(c)
        else:
            await self.channel.send(charcount)
            
         
    @send_daily_grinder_update.before_loop
    async def before_daily_grinder_update(self):
        await self.bot.wait_until_ready()
        
    @commands.command(name="force_submission_grinder_update")
    @commands.is_owner()
    async def test_update(self, ctx):
        await ctx.send("Running daily update manually...")
        await self.daily_grinder_update()
        
    @commands.command(name="force_load_new_markets")
    @commands.is_owner()
    async def test_load(self, ctx):
        await ctx.send("Loading new markets...")
        fetch_website()
        
async def setup(bot):
    await bot.add_cog(Submission_Grinder(bot))