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
import copy

DATA_FILE = "data/new_tracker.json"
META_FILE = "data/new_meta.json"
CHANNEL = "TRACKER_CHANNEL_ID"

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

class New_Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_lock = asyncio.Lock()
        self.tracker_message_ids = None
        self.leaderboard_message_id = None
        self.channel = None
        self.guild = None
        self.writing_emoji = None
        self.reading_emoji = None
        self.member_names = None
        
        try:
            with open(META_FILE, "r") as f:
                meta = json.load(f)
                self.tracker_message_ids = meta.get("tracker_message_ids", [])
                self.leaderboard_message_id = meta.get("leaderboard_message_id")

                # Daily writers and readers are no longer local,
                # saving them in meta.json instead means they aren't reset
                # if the bot crashses or is intentionally rebooted.
                self.today_readers = set(meta.get("today's readers", []))
                self.yesterday_readers = set(meta.get("yesterday's readers", []))
                self.two_days_ago_readers = set(meta.get("two days ago's readers", []))
                self.today_writers = set(meta.get("today's writers", []))
                self.yesterday_writers = set(meta.get("yesterday's writers", []))
                self.two_days_ago_writers = set(meta.get("two days ago's writers", []))
        except FileNotFoundError:
            pass

    async def cog_load(self):
        self.writing_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)
        self.member_names = {}
        self.run_daily_update.start()
        self.delete_old_messages.start()
     
            
    @commands.Cog.listener()
    async def on_ready(self):
        if not self.channel:
            channel_id = os.getenv(CHANNEL)
            if channel_id:
                self.channel = self.bot.get_channel(int(channel_id))
                self.guild = self.channel.guild
                print(f"on ready: using {self.channel}")
            
        
    def cog_unload(self):
        self.run_daily_update.cancel()
        self.delete_old_messages.cancel()
        
    async def resolve_member_name(self, user_id: int) -> str:
        if user_id in self.member_names:
            return self.member_names[user_id]

        # Try cached lookup first
        member = self.guild.get_member(user_id)
        if not member:
            try:
                member = await self.guild.fetch_member(user_id)
            except Exception:
                return f"Unknown User ({user_id})"

        self.member_names[user_id] = member.display_name
        return member.display_name

        
    async def format_progress(self, data, today_readers, today_writers):
        readers_text = []
        writers_text = []

        for user_id in today_readers:
            stats = data.get(user_id, {"read": 0})
            name = await self.resolve_member_name(int(user_id))
            readers_text.append(f"{name}: {stats['read']}")

        for user_id in today_writers:
            stats = data.get(user_id, {"write": 0})
            name = await self.resolve_member_name(int(user_id))
            writers_text.append(f"{name}: {stats['write']}")

        return "\n".join(readers_text) or "Nobody yet", "\n".join(writers_text) or "Nobody yet"
    
    def display_current_score(self, data: dict, meta: dict, day: str, past_day_display: bool) -> dict:
        display_data = {}
        
        for user_id, stats in data.items():
            display_data[user_id] = {
                "read": self.calculate_score(stats["read"], user_id, meta, day, "readers", past_day_display),
                "write": self.calculate_score(stats["write"], user_id, meta, day, "writers", past_day_display),
            }
            
        return display_data
    
    def calculate_score(self, score: int, user_id: str, meta: dict, current_day: str, category: str, past_day_display: bool) -> int:
        days = ["two days ago's ", "yesterday's ", "today's "]
        
        if past_day_display:
            cutoff = days.index(current_day) + 1
            active_days = days[:cutoff]
            days = active_days
            
        for day in days:
            if user_id not in meta[day + category] and day != "today's ":
                score //= 2
            elif user_id in meta[day + category]:
                score += 1

        return score
    
    async def make_leaderboard(self, sorted_by_read, sorted_by_write, read_lines, write_lines):
        for user_id, scores in sorted_by_read:
            name = await self.resolve_member_name(int(user_id))
            read_lines.append(f"{name}: {scores['read']}")
        
        for user_id, scores in sorted_by_write:
            name = await self.resolve_member_name(int(user_id))
            write_lines.append(f"{name}: {scores['write']}")
        
        return "\n".join(read_lines + ["", *write_lines])
        

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def run_daily_update(self):
        print("RUN DAILY UPDATE — FROM LOOP")
        await self.daily_update()
        
    @run_daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()

    async def daily_update(self):
        now = datetime.datetime.now(pytz.timezone("US/Pacific"))
        print(f"daily tracker update posted at {now.strftime('%Y-%m%d %H:%M%S %Z')}")
        await self.bot.wait_until_ready()
        self.channel = self.bot.get_channel(int(os.getenv(CHANNEL)))
        self.guild = self.channel.guild
        
        async with self.data_lock:
            data = load_data()
            meta = load_meta()
            
            PST = ZoneInfo("America/Los_Angeles")
            today_str = datetime.datetime.now(PST).date().isoformat()
            
            # Prevents duplicate penalty if already updated today.
            if meta.get("last_updated_date") ==  today_str:
                print("Daily update already performed today.")
                return
            
            for user_id in data:
                member = await self.guild.fetch_member(int(user_id))
                name = member.display_name
                self.member_names[user_id] = name
            
            deep_copy = self.display_current_score(data, meta, day="today's ", past_day_display=False)
            
            # Updates scores and member names.
            # Currently, the penalty is that their score is divided by two.
            for user_id in data:
                if user_id not in set(meta["two days ago's readers"]):
                    data[user_id]["read"] = data[user_id]["read"] // 2
                else:
                    data[user_id]["read"] += 1
                if user_id not in set(meta["two days ago's writers"]):
                    data[user_id]["write"] = data[user_id]["write"] // 2
                else:
                    data[user_id]["write"] += 1

            save_data(data)
            
            sorted_by_read = sorted(deep_copy.items(), key=lambda item: item[1]['read'], reverse=True)
            sorted_by_write = sorted(deep_copy.items(), key=lambda item: item[1]['write'], reverse=True)

            self.writing_emoji = self.bot.get_emoji(1061522051501928498)
            self.reading_emoji = self.bot.get_emoji(1397736959882956842)
            
            read_lines = [f"{self.reading_emoji} **Reading Streaks**"]
            write_lines = [f"{self.writing_emoji } **Writing Streaks**"]

            leaderboard_msg = await self.channel.send(await self.make_leaderboard(
                                                        sorted_by_read, 
                                                        sorted_by_write, 
                                                        read_lines, write_lines
                                                        ))
            self.leaderboard_message_id = leaderboard_msg.id

            # Resets so it still displays the daily message.
            today = datetime.date.today().strftime("%A, %B %d, %Y")
            msg = await self.channel.send(
                f"Today is **{today}**.\n React with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today."
            )
            await msg.add_reaction(str(self.reading_emoji))
            await msg.add_reaction(str(self.writing_emoji))
            
            # Updates for retroactive scoring.
            
            meta["two days ago's readers"] = meta["yesterday's readers"] 
            meta["two days ago's writers"] = meta["yesterday's writers"] 
            meta["yesterday's readers"] = meta["today's readers"]
            meta["yesterday's writers"] = meta["today's writers"]
            self.today_readers = set()
            self.today_writers = set()
            meta["today's readers"] = list(self.today_readers)
            meta["today's writers"] = list(self.today_writers)
            
            self.tracker_message_ids.append(msg.id)
            if len(self.tracker_message_ids) > 3:
                self.tracker_message_ids.pop(0)
            
            meta["tracker_message_ids"] = self.tracker_message_ids
            meta["leaderboard_message_id"] = self.leaderboard_message_id
            meta["last_updated_date"] = today_str
            
            save_meta(meta)
        
    @commands.command(name="force_daily_tracker")
    @commands.is_owner()
    async def test_daily(self, ctx):
        print(f"TEST COMMAND CALLED by {ctx.author} in {ctx.channel}")
        await ctx.send("Running daily update manually...")
        print("RUN DAILY UPDATE — FROM COMMAND (before call)")
        await self.daily_update()
        print("RUN DAILY UPDATE — FROM COMMAND (after call)")
        
    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def delete_old_messages(self):
        MAX_AGE = timedelta(days = 2)
        
        self.channel = self.bot.get_channel(int(os.getenv(CHANNEL)))
        async for message in self.channel.history(limit=100):
            now = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
            message_time = message.created_at.astimezone(ZoneInfo("America/Los_Angeles"))
            message_age = now - message_time
            if message_age > MAX_AGE or ("Reading Streaks" in message.content and message_age >= timedelta(hours = 23)):
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
        await self.on_raw_reaction(payload, added=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        await self.on_raw_reaction(payload, added=False)
        
    @commands.Cog.listener()
    async def on_raw_reaction(self, payload, added: bool):
        # Ignores bot's own reactions.
        if str(payload.user_id) == str(self.bot.user.id):
            return

        # Makes sure it's reacting to today's tracker message.
        if payload.message_id not in getattr(self, "tracker_message_ids", None):
            print("message id not in list")
            return
        
        self.channel = self.bot.get_channel(int(os.getenv(CHANNEL)))
        async with self.data_lock:
            updated = False
            day = ""
            if len(self.tracker_message_ids) > 2:
                if payload.message_id == self.tracker_message_ids[0]:
                    day = "two days ago's "
                elif payload.message_id == self.tracker_message_ids[1]:
                    day = "yesterday's "
                else:
                    day = "today's "
            else:
                    day = "today's "
                
        
            meta = load_meta()
            data = load_data()
            user_id = str(payload.user_id)
            data.setdefault(user_id, {"read": 0, "write": 0})
            emoji = payload.emoji.name
            
            # Adds or removes user from current day.
            if added:
                if emoji == "frogReading" and user_id not in set(meta[day + "readers"]):
                    meta[day + "readers"].append(user_id)
                    updated = True
                    
                elif emoji == "bulbaWriter" and user_id not in set(meta[day + "writers"]):
                    meta[day + "writers"].append(user_id)
                    updated = True
                    
            else:
                if emoji == "frogReading" and user_id in set(meta[day + "readers"]):
                    meta[day + "readers"].remove(user_id)
                    updated = True
                    
                elif emoji == "bulbaWriter" and user_id in set(meta[day + "writers"]):
                    meta[day + "writers"].remove(user_id)
                    updated = True
            
            save_meta(meta)
        if updated:
            # Overly paranoid mutex lock
            async with self.data_lock:
                leaderbard_copy = self.display_current_score(data, meta, day, past_day_display=False)
            
            self.writing_emoji = self.bot.get_emoji(1061522051501928498)
            self.reading_emoji = self.bot.get_emoji(1397736959882956842)
                        
            # sorted_by_read = sorted(leaderbard_copy.items(), key=lambda item: item[1]['read'], reverse=True)
            # sorted_by_write = sorted(leaderbard_copy.items(), key=lambda item: item[1]['write'], reverse=True)

            # read_lines = [f"{self.reading_emoji} **Reading Streaks**"]
            # write_lines = [f"{self.writing_emoji } **Writing Streaks**"]
                
            # updated_leaderboard = await self.make_leaderboard(
            #     sorted_by_read, 
            #     sorted_by_write, 
            #     read_lines, 
            #     write_lines
            # )
            
            # try:
            #     message = await self.channel.fetch_message(self.leaderboard_message_id)
            #     await message.edit(content=updated_leaderboard)
            # except Exception as e:
            #     print(f"Couldn't edit leaderboard: {e}")
            
            today = datetime.date.today().strftime("%A, %B %d, %Y")

            # Edits the current message.
            if day == "today's ":
                readers_text, writers_text = await self.format_progress(
                    leaderbard_copy, set(meta[day + "readers"]), set(meta[day + "writers"]) 
                )
                
                new_content = (
                f"Today is **{today}**.\nReact with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today.\n\n"
                f"**Today's readers:**\n{readers_text}\n\n"
                f"**Today's writers:**\n{writers_text}"
                )
                
                try:
                    message = await self.channel.fetch_message(payload.message_id)
                    await message.edit(content=new_content)
                except Exception as e:
                    print(f"Couldn't edit today's tracker message: {e}")
            else:
                # Retroactively alters current and any existing future days based on new info.
                days = ["two days ago's ", "yesterday's ", "today's "]
                for index in range(len(meta["tracker_message_ids"])):
                    
                    readers_text, writers_text = await self.format_progress(
                        self.display_current_score(data, meta, days[index], past_day_display=True), 
                        set(meta[days[index] + "readers"]), 
                        set(meta[days[index] + "writers"]) 
                    )
                    
                    new_content = (
                        f"Today is **{today}**.\nReact with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today.\n\n"
                        f"**Today's readers:**\n{readers_text}\n\n"
                        f"**Today's writers:**\n{writers_text}"
                    )
                    
                    try:
                        message = await self.channel.fetch_message(meta["tracker_message_ids"][index])
                        await message.edit(content=new_content)
                    except Exception as e:
                        print(f"Couldn't edit past tracker message: {e}")
    
async def setup(bot):
    await bot.add_cog(New_Tracker(bot))