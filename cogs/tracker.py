from discord.ext import commands, tasks
import json, os
import datetime

DATA_FILE = "data/tracker.json"
# currently using the bot-spam channel, change this to the tracker channel later
CHANNEL_ID = 1396960304247603210

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker_message_id = None
        self.tracker_channel_id = None
        self.wiriting_emoji = None 
        self.reading_emoji = None
        self.today_readers = set() # strings
        self.today_writers = set() # strings
        self.daily_update.start()
        
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
    
    @tasks.loop(hours = 24)
    async def daily_update(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            print("-------------------ERROR: get_channel doesn't work lmao-------------------")
            return
        
        # Resetting so it still displays the daily message.
        self.today_readers = set()
        self.today_writers = set()
        
        self.wiriting_emoji = self.bot.get_emoji(1061522051501928498)
        self.reading_emoji = self.bot.get_emoji(1397736959882956842)
        today = datetime.date.today().strftime("%A, %B %d, %Y")
        msg = await channel.send(
            f"Today is **{today}**.\n React with {self.reading_emoji} if you read today and {self.wiriting_emoji} if you wrote today."
        )
        await msg.add_reaction(str(self.reading_emoji))
        await msg.add_reaction(str(self.wiriting_emoji))

        self.tracker_message_id = msg.id
        self.tracker_channel_id = channel.id
        
    @daily_update.before_loop
    async def before_daily_update(self):
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
        
        self.wiriting_emoji = self.bot.get_emoji(1061522051501928498)
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
                f"Today is **{today}**.\n React with {self.reading_emoji} if you read today and {self.wiriting_emoji} if you wrote today.\n\n"
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
