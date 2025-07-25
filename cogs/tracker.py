from discord.ext import commands, tasks
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
load_dotenv()
from datetime import timedelta, timezone
import datetime
import discord
import asyncio
import json, os
import pytz
import math

DATA_FILE = "data/tracker.json"
META_FILE = "data/meta.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)
    
def load_meta():
    if not os.path.exists(META_FILE):
        return {}
    with open(META_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)
        
def save_meta(meta):
    with open(META_FILE, "w") as f:
        json.dump(meta, f, indent=2)

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker_message_id = None
        self.tracker_channel_id = None
        self.writing_emoji = None 
        self.reading_emoji = None
        self.today_readers = set() # strings
        self.today_writers = set() # strings
        self.daily_update.start()
        self.delete_old_messages.start()
        
        try:
            with open("data/meta.json", "r") as f:
                meta = json.load(f)
                self.tracker_message_id = meta.get("tracker_message_id")
                self.tracker_channel_id = meta.get("tracker_channel_id")
        except FileNotFoundError:
            pass

        
    def cog_unload(self):
        self.daily_update.cancel()
        
    def format_progress(self, data, today_readers, today_writers):
        readers_text = []
        writers_text = []

        for user_id in today_readers:
            stats = data.get(user_id, {"read": 0})
            member = self.bot.get_user(int(user_id))  # Convert string back to int
            name = member.display_name if member else f"<@{user_id}>"
            readers_text.append(f"{name}: {stats['read']}")

        for user_id in today_writers:
            stats = data.get(user_id, {"write": 0})
            member = self.bot.get_user(int(user_id))
            name = member.display_name if member else f"<@{user_id}>"
            writers_text.append(f"{name}: {stats['write']}")

        return "\n".join(readers_text) or "Nobody yet", "\n".join(writers_text) or "Nobody yet"

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def daily_update(self):
        now = datetime.datetime.now(pytz.timezone("US/Pacific"))
        print(f"daily update posted at {now.strftime('%Y-%m%d %H:%M%S %Z')}")
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(int(os.getenv("TRACKER_CHANNEL_ID")))
        if not channel:
            print("-------------------ERROR: get_channel doesn't work lmao-------------------")
            return
        
        guild = channel.guild
        
        data = load_data()
        meta = load_meta()
        
        PST = ZoneInfo("America/Los_Angeles")
        today_str = datetime.now(PST).date().isoformat()
        
        # Prevents duplicate penalty if already updated today.
        # Ironically, this might be redundant since it currently only posts at midnight.
        if meta.get("last_updated_date") ==  today_str:
            print("Daily update already performed today.")
            return
        
        # Penalizes users who didn’t react yesterday,
        # max() is so scores don't go negative.
        # Currently, the penalty is that their score is divided by two.
        rip = self.bot.get_emoji(1398098610733842452)
        for user_id in data:
            if user_id not in self.today_readers:
                try:
                    member = await guild.fetch_member(int(user_id))
                    name = member.display_name
                except Exception:
                    name = f"<@{user_id}>"
                await channel.send(f"{name}'s reading streak has been broken {rip}")
                data[user_id]["read"] = max(0, math.floor(data[user_id]["read"] / 2))
            if user_id not in self.today_writers:
                try:
                    member = await guild.fetch_member(int(user_id))
                    name = member.display_name
                except Exception:
                    name = f"<@{user_id}>"
                await channel.send(f"{name}'s writing streak has been broken {rip}")
                data[user_id]["write"] = max(0, math.floor(data[user_id]["write"] / 2))

        save_data(data)
        
        self.writing_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)
        
        
        # Leaderboard
        # Sort by reading and writing streaks separately
        sorted_by_read = sorted(data.items(), key=lambda item: item[1]['read'], reverse=True)
        sorted_by_write = sorted(data.items(), key=lambda item: item[1]['write'], reverse=True)

        read_lines = [f"{self.reading_emoji} **Reading Streaks**"]
        write_lines = [f"{self.writing_emoji } **Writing Streaks**"]

        for user_id, stats in sorted_by_read:
            try:
                member = await guild.fetch_member(int(user_id))
                name = member.display_name
            except Exception:
                print(f"Member name not found for ID {user_id}")
                name = f"<@{user_id}>"
            read_lines.append(f"{name}: {stats['read']}")

        for user_id, stats in sorted_by_write:
            try:
                member = await guild.fetch_member(int(user_id))
                name = member.display_name
            except Exception:
                print(f"Member name not found for ID {user_id}")
                name = f"<@{user_id}>"
            write_lines.append(f"{name}: {stats['write']}")

        # Send leaderboard as one message
        await channel.send("\n".join(read_lines + ["", *write_lines]))

        # Resetting so it still displays the daily message.
        self.today_readers = set()
        self.today_writers = set()
        
        
        today = datetime.date.today().strftime("%A, %B %d, %Y")
        msg = await channel.send(
            f"Today is **{today}**.\n React with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today."
        )
        await msg.add_reaction(str(self.reading_emoji))
        await msg.add_reaction(str(self.writing_emoji))

        self.tracker_message_id = msg.id
        self.tracker_channel_id = channel.id
        
        meta["tracker_message_id"] = self.tracker_message_id
        meta["tracker_channel_id"] = self.tracker_channel_id
        meta["last_updated_date"] = today_str
        
        save_meta(meta)
        
    @daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()
        
    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def delete_old_messages(self):
        channel = self.bot.get_channel(int(os.getenv("TRACKER_CHANNEL_ID")))
        MAX_AGE = timedelta(days = 3)
        
        async for message in channel.history(limit=100):
            now = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
            message_time = message.created_at.astimezone(ZoneInfo("America/Los_Angeles"))
            message_age = now - message_time
            if message_age > MAX_AGE:
                try:
                    await message.delete()
                    print("old message deleted")
                    await asyncio.sleep(1)
                except discord.Forbidden:
                    print(f"Cannot delete message {message.id}")
                except discord.HTTPException as e:
                    print(f"Failed to delete message {message.id} : {e}")
    
    @delete_old_messages.before_loop
    async def before_delete_old_messages(self):
        await self.bot.wait_until_ready()
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # Ignores bot's own reactions.
        if str(payload.user_id) == str(self.bot.user.id):
            return

        # Makes sure it's reacting to today's tracker message.
        if payload.message_id != getattr(self, "tracker_message_id", None):
            print(f"Ignoring reaction on message {payload.message_id}, expected {self.tracker_message_id}")
            return
        
        self.writing_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)

        user_id = str(payload.user_id)
        emoji = payload.emoji.name

        data = load_data()
        data.setdefault(user_id, {"read": 0, "write": 0})

        updated = False

        # emoji needs to be compared to the name of the cuustom emoji instead of self.bot.get_emoji()
        if emoji == "frogReading" and user_id not in self.today_readers:
            data[user_id]["read"] += 1
            self.today_readers.add(user_id)
            updated = True

        # emoji needs to be compared to the name of the cuustom emoji instead of self.bot.get_emoji()
        elif emoji == "bulbaWriter" and user_id not in self.today_writers:
            data[user_id]["write"] += 1
            self.today_writers.add(user_id)
            updated = True

        if updated:
            save_data(data)

            # Regenerate the message content.
            readers_text, writers_text = self.format_progress(
                data, self.today_readers, self.today_writers
            )

            today = datetime.date.today().strftime("%A, %B %d, %Y")
            new_content = (
                f"Today is **{today}**.\n React with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today.\n\n"
                f"**Today's readers:**\n{readers_text}\n\n"
                f"**Today's writers:**\n{writers_text}"
            )

            # Edit the original message.
            channel = self.bot.get_channel(self.tracker_channel_id)
            try:
                msg = await channel.fetch_message(self.tracker_message_id)
                print("updating message:", self.tracker_message_id, self.tracker_channel_id)
                await msg.edit(content=new_content)
            except Exception as e:
                print(f"Couldn't edit tracker message: {e}")
    
async def setup(bot):
    await bot.add_cog(Tracker(bot))
