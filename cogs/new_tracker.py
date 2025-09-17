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

DATA_FILE = "data/new_tracker.json"
META_FILE = "data/new_meta.json"
CHANNEL = "CHANNEL_ID"

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
        self.tracker_message_ids = None
        self.leaderboard_message_id = None
        self.tracker_channel_id = None
        self.writing_emoji = None 
        self.reading_emoji = None
        self.run_daily_update.start()
        self.delete_old_messages.start()
        self.writing_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)
        
        try:
            with open(META_FILE, "r") as f:
                meta = json.load(f)
                self.tracker_message_ids = meta.get("tracker_message_ids")
                self.tracker_channel_id = meta.get("tracker_channel_id")

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

        
    def cog_unload(self):
        self.run_daily_update.cancel()
        self.delete_old_messages.cancel()
        
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

    # @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    @tasks.loop(seconds = 25)
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
        channel = self.bot.get_channel(int(os.getenv(CHANNEL)))
        if not channel:
            print("-------------------ERROR: tracker get_channel doesn't work lmao-------------------")
            return
        
        guild = channel.guild
        
        data = load_data()
        meta = load_meta()
        
        PST = ZoneInfo("America/Los_Angeles")
        today_str = datetime.datetime.now(PST).date().isoformat()
        
        # Prevents duplicate penalty if already updated today.
        # Currently commented out for testing purposes.
        # if meta.get("last_updated_date") ==  today_str:
        #     print("Daily update already performed today.")
        #     return
        
        # Updates scores
        # Currently, the penalty is that their score is divided by two.
        for user_id in data:
            if user_id not in set(meta["two days ago's readers"]):
                print(f"{user_id}'s main reading score penalized")
                data[user_id]["read"] = max(0, math.floor(data[user_id]["read"] / 2))
            else:
                data[user_id]["read"] += 1
            if user_id not in set(meta["two days ago's writers"]):
                print(f"{user_id}'s main writing score penalized")
                data[user_id]["write"] = max(0, math.floor(data[user_id]["write"] / 2))
            else:
                data[user_id]["write"] += 1
                
        # updating for retroactive points
        meta["two days ago's readers"] = meta["yesterday's readers"] 
        meta["two days ago's writers"] = meta["yesterday's writers"] 
        meta["yesterday's readers"] = meta["today's readers"]
        meta["yesterday's writers"] = meta["today's writers"]
        self.today_readers = set()
        self.today_writers = set()
        meta["today's readers"] = list(self.today_readers)
        meta["today's writers"] = list(self.today_writers)

        save_data(data)
        
        self.writing_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)
        
        shallow_copy = data.copy()
        
        for id, stats in shallow_copy.items():
            stats["read"] = self.calculate_score(stats["read"], meta["today's readers"], meta["yesterday's readers"], meta["two days ago's readers"])
            stats["write"] = self.calculate_score(stats["write"], meta["today's writers"], meta["yesterday's writers"], meta["two days ago's writers"])
        
        # Leaderboard
        # Sort by reading and writing streaks separately
        sorted_by_read = sorted(shallow_copy.items(), key=lambda item: item[1]['read'], reverse=True)
        sorted_by_write = sorted(shallow_copy.items(), key=lambda item: item[1]['write'], reverse=True)

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
        leaderboard_msg = await channel.send("\n".join(read_lines + ["", *write_lines]))
        self.leaderboard_message_id = leaderboard_msg.id

        # Resetting so it still displays the daily message.
        today = datetime.date.today().strftime("%A, %B %d, %Y")
        msg = await channel.send(
            f"Today is **{today}**.\n React with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today."
        )
        await msg.add_reaction(str(self.reading_emoji))
        await msg.add_reaction(str(self.writing_emoji))

        self.tracker_message_ids.append(msg.id)
        if len(self.tracker_message_ids) > 3:
            self.tracker_message_ids.pop(0)
            
        self.tracker_channel_id = channel.id
        
        meta["tracker_message_ids"] = self.tracker_message_ids
        meta["leaderboard_message_id"] = self.leaderboard_message_id
        meta["tracker_channel_id"] = self.tracker_channel_id
        meta["last_updated_date"] = today_str
        
        save_meta(meta)
        
    # @commands.command(name="force_daily_tracker")
    # @commands.is_owner()
    # async def test_daily(self, ctx):
    #     print(f"TEST COMMAND CALLED by {ctx.author} in {ctx.channel}")
    #     await ctx.send("Running daily update manually...")
    #     print("RUN DAILY UPDATE — FROM COMMAND (before call)")
    #     await self.daily_update()
    #     print("RUN DAILY UPDATE — FROM COMMAND (after call)")
        
    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")))
    async def delete_old_messages(self):
        channel = self.bot.get_channel(int(os.getenv(CHANNEL)))
        MAX_AGE = timedelta(days = 2)
        
        async for message in channel.history(limit=100):
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
    

    def calculate_score(self, current_score: int, today: bool, yesterday: bool, two_days_ago: bool):
        days = [today, yesterday, two_days_ago]
        score = current_score
        for wrote in days:
            if wrote:
                score += 1
            else:
                score = math.floor(score / 2)
        return score
        
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
        # Print statement for error handling intentionally removed because
        # it was spamming the terminal.
        if payload.message_id not in getattr(self, "tracker_message_ids", None):
            print("message id not in list")
            return
        
        self.writing_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)

        user_id = str(payload.user_id)
        emoji = payload.emoji.name

        updated = False
        channel = self.bot.get_channel(self.tracker_channel_id)
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
        print("day: " + day)
                
        meta = load_meta()
        data = load_data()
        data.setdefault(user_id, {"read": 0, "write": 0})
        
        if added:
            if emoji == "frogReading" and user_id not in set(meta[day + "readers"]):
                print("add reader")
                meta[day + "readers"].append(user_id)
                save_meta(meta)
                updated = True
                
            elif emoji == "bulbaWriter" and user_id not in set(meta[day + "writers"]):
                print("add writer")
                meta[day + "writers"].append(user_id)
                save_meta(meta)
                updated = True
                
        else:
            if emoji == "frogReading" and user_id in set(meta[day + "readers"]):
                print("remove reader")
                meta[day + "readers"].remove(user_id)
                save_meta(meta)
                updated = True
                
            elif emoji == "bulbaWriter" and user_id in set(meta[day + "writers"]):
                print("remove writer")
                meta[day + "writers"].remove(user_id)
                save_meta(meta)
                updated = True
        
        shallow_copy = data.copy()
        
        for id, stats in shallow_copy.items():
            stats["read"] = self.calculate_score(stats["read"], meta["today's readers"], meta["yesterday's readers"], meta["two days ago's readers"])
            stats["write"] = self.calculate_score(stats["write"], meta["today's writers"], meta["yesterday's writers"], meta["two days ago's writers"])
        
        if updated:
            # update the leaderboard as well with self.tracker_leaderboard_id
            
            
            # Regenerate the message content.
            readers_text, writers_text = self.format_progress(
                shallow_copy, set(meta["today's readers"]), set(meta["today's writers"]) 
            )

            today = datetime.date.today().strftime("%A, %B %d, %Y")
            new_content = (
                f"Today is **{today}**.\nReact with {self.reading_emoji} if you read today and {self.writing_emoji} if you wrote today.\n\n"
                f"**Today's readers:**\n{readers_text}\n\n"
                f"**Today's writers:**\n{writers_text}"
            )

            # Edit the original message.
            try:
                print("updating messages:", payload.message_id, self.tracker_channel_id)
                for id in set(meta["tracker_message_ids"]):
                    message = await channel.fetch_message(id)
                    await message.edit(content=new_content)
            except Exception as e:
                print(f"Couldn't edit tracker message: {e}")
    
async def setup(bot):
    await bot.add_cog(New_Tracker(bot))
