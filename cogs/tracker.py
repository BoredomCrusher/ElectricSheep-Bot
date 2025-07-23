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
        
def format_progress(self, data, readers, writers):
    reader_lines = []
    writer_lines = []

    for uid in readers:
        user_data = data.get(str(uid), {"read": 0})
        reader_lines.append(f"<@{uid}>: {user_data['read']} pages")

    for uid in writers:
        user_data = data.get(str(uid), {"write": 0})
        writer_lines.append(f"<@{uid}>: {user_data['write']} words")

    return "\n".join(reader_lines) or "No readers yet.", "\n".join(writer_lines) or "No writers yet."


class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tracker_message_id = None 
        self.today_readers = set()
        self.today_writers = set()
        self.daily_update.start()

        
    def cog_unload(self):
        self.daily_update.cancel()
        
    
    # @tasks.loop(hours = 24)
    @tasks.loop(minutes = 1)
    async def daily_update(self):
        await self.bot.wait_until_ready()
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            print("-------------------ERROR: get_channel doesn't work lmao-------------------")
            return
        
        today = datetime.date.today().strftime("%A, %B %d, %Y")
        msg = await channel.send(
            f"Today is **{today}**. React with 📖 if you read today and ✍️ if you wrote today."
        )
        self.tracker_message_id = msg.id
        self.tracker_channel_id = channel.id
        
            
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
        if payload.user_id == self.bot.user.id:
            return

        # Make sure it's reacting to today's tracker message
        if payload.message_id != getattr(self, "tracker_message_id", None):
            return

        user_id = str(payload.user_id)
        emoji = payload.emoji.name

        data = load_data()
        data.setdefault(user_id, {"read": 0, "write": 0})

        updated = False

        if emoji == "📖" and user_id not in getattr(self, "today_readers", set()):
            data[user_id]["read"] += 1
            self.today_readers.add(user_id)
            updated = True

        elif emoji == "✍️" and user_id not in getattr(self, "today_writers", set()):
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
                await msg.edit(content=new_content)
            except Exception as e:
                print(f"Couldn't edit tracker message: {e}")


async def setup(bot):
    await bot.add_cog(Tracker(bot))
