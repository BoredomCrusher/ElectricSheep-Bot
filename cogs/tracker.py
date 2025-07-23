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
        self.today_readers = set() # strings
        self.today_writers = set() # strings
        # self.testing_to_break_stuff.start()
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
        
    # @tasks.loop(seconds = 3)
    # async def testing_to_break_stuff(self):
    #     channel = self.bot.get_channel(CHANNEL_ID)
    #     await channel.send(f"yay this basic functionality works")
        
    # @testing_to_break_stuff.before_loop
    # async def before_testing_to_break_stuff(self):
    #     await self.bot.wait_until_ready()
        
    
    @tasks.loop(hours = 24)
    async def daily_update(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            print("-------------------ERROR: get_channel doesn't work lmao-------------------")
            return
        
        # Resetting so it still displays the daily message
        self.today_readers = set()
        self.today_writers = set()
        
        today = datetime.date.today().strftime("%A, %B %d, %Y")
        msg = await channel.send(
            f"Today is **{today}**.\n React with 📖 if you read today and ✍️ if you wrote today."
        )
        await msg.add_reaction("📖")
        await msg.add_reaction("✍️")

        self.tracker_message_id = msg.id
        self.tracker_channel_id = channel.id
        
    # I'm pretty sure I can delete this, I never used it
    @daily_update.before_loop
    async def before_daily_update(self):
        await self.bot.wait_until_ready()
    
    @commands.command()
    async def read(self, ctx, pages: int):
        data = load_data()
        user_id = str(ctx.author.id)
        data.setdefault(user_id, {"read": 0, "write": 0})
        data[user_id]["read"] += pages
        save_data(data)
        await ctx.send(f"📖 {ctx.author.display_name} logged {pages} pages!")

    @commands.command()
    async def write(self, ctx, words: int):
        data = load_data()
        user_id = str(ctx.author.id)
        data.setdefault(user_id, {"read": 0, "write": 0})
        data[user_id]["write"] += words
        save_data(data)
        await ctx.send(f"✍️ {ctx.author.display_name} logged {words} words!")

    @commands.command()
    async def progress(self, ctx):
        data = load_data()
        user_id = str(ctx.author.id)
        stats = data.get(user_id, {"read": 0, "write": 0})
        await ctx.send(f"📊 {ctx.author.display_name}'s Progress — Read: {stats['read']} pages, Write: {stats['write']} words.")
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        # Ignore bot's own reactions
        if str(payload.user_id) == str(self.bot.user.id):
            return

        # Make sure it's reacting to today's tracker message
        if payload.message_id != getattr(self, "tracker_message_id", None):
            print(f"Ignoring reaction on message {payload.message_id}, expected {self.tracker_message_id}")
            return

        user_id = str(payload.user_id)
        emoji = payload.emoji.name

        data = load_data()
        data.setdefault(user_id, {"read": 0, "write": 0})

        updated = False

        # if emoji == "📖" and user_id not in getattr(self, "today_readers", set()):
        if emoji == "📖" and user_id not in self.today_readers:
            data[user_id]["read"] += 1
            self.today_readers.add(user_id)
            updated = True

        # elif emoji == "✍️" and user_id not in getattr(self, "today_writers", set()):
        elif emoji == "✍️" and user_id not in self.today_writers:
            data[user_id]["write"] += 1
            self.today_writers.add(user_id)
            updated = True

        if updated:
            save_data(data)

            # Regenerate the message content
            readers_text, writers_text = self.format_progress(
                data, self.today_readers, self.today_writers
            )

            today = datetime.date.today().strftime("%A, %B %d, %Y")
            new_content = (
                f"Today is **{today}**. React with 📖 if you read today and ✍️ if you wrote today.\n\n"
                f"**Today's readers:**\n{readers_text}\n\n"
                f"**Today's writers:**\n{writers_text}"
            )

            # Edit the original message
            channel = self.bot.get_channel(self.tracker_channel_id)
            try:
                msg = await channel.fetch_message(self.tracker_message_id)
                print("updating message:", self.tracker_message_id, self.tracker_channel_id)
                await msg.edit(content=new_content)
            except Exception as e:
                print(f"Couldn't edit tracker message: {e}")


async def setup(bot):
    await bot.add_cog(Tracker(bot))
