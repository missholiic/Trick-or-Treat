import discord
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime, timedelta
import pytz

# --- CONFIG ---
TOKEN = "YOUR_BOT_TOKEN"
BOT_NAME = "Trick-or-Treat"
DAILY_CHANNEL_ID = 1411787882322198600  # #trick-or-treating
LEADERBOARD_CHANNEL_ID = 1411788070134485042  # #trick-or-treat-leaderboard
CANDY_EMOJI = "<:CandyCorn:1408306488170254397>"

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# --- DATA STORAGE ---
candy = {}  # {user_id: count}
last_daily = {}  # {user_id: datetime}
last_trick = {}  # {user_id: datetime}

# --- FUNCTIONS ---
def add_candy(user_id, amount):
    candy[user_id] = candy.get(user_id, 0) + amount
    if candy[user_id] < 0:
        candy[user_id] = 0

def can_get_daily(user_id):
    now = datetime.utcnow()
    return user_id not in last_daily or now - last_daily[user_id] >= timedelta(hours=24)

def can_trick_or_treat(user_id):
    now = datetime.utcnow()
    return user_id not in last_trick or now - last_trick[user_id] >= timedelta(hours=24)

# --- EVENTS ---
@bot.event
async def on_ready():
    print(f"{BOT_NAME} is online!")
    leaderboard_task.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id

    # Daily candy when posting anywhere
    if can_get_daily(user_id):
        add_candy(user_id, 1)
        last_daily[user_id] = datetime.utcnow()
        channel = bot.get_channel(DAILY_CHANNEL_ID)
        if channel:
            await channel.send(
                f"👻 Boo! {message.author.mention} found a stray piece of {CANDY_EMOJI} while hanging out! That’s **+1** to your stash! 🎃"
            )

    await bot.process_commands(message)

# --- COMMANDS ---

# Trick-or-Treat gamble
@bot.command()
async def trickortreat(ctx):
    user_id = ctx.author.id
    if not can_trick_or_treat(user_id):
        await ctx.send(f"⏳ {ctx.author.mention}, you’ve already gone trick-or-treating in the last 24 hours. Try again tomorrow!")
        return

    last_trick[user_id] = datetime.utcnow()
    outcome = random.choice(["win", "lose"])

    if outcome == "win":
        gained = random.randint(1, 5)
        add_candy(user_id, gained)
        await ctx.send(
            f"🍫 {ctx.author.mention} knocked on a door and scored a king-sized bar! You gain **{gained} {CANDY_EMOJI}**!"
        )
    else:
        lost = random.randint(1, 3)
        add_candy(user_id, -lost)
        await ctx.send(
            f"👻 Oh no! {ctx.author.mention} opened the wrong door and a ghost scared away **{lost} {CANDY_EMOJI}**!"
        )

# Leaderboard
@tasks.loop(minutes=1)
async def leaderboard_task():
    now = datetime.now(pytz.timezone("US/Pacific"))
    if now.hour == 17 and now.minute == 0:  # 5pm PST
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if channel:
            sorted_candy = sorted(candy.items(), key=lambda x: x[1], reverse=True)
            if not sorted_candy:
                await channel.send("🎃 The baskets are empty... no candy yet!")
                return

            leaderboard_text = "🏆 **Trick-or-Treat Leaderboard** 🏆\n\n"
            for i, (user_id, amount) in enumerate(sorted_candy, start=1):
                member = channel.guild.get_member(user_id)
                if member:
                    leaderboard_text += f"{i}. {member.display_name} — {amount} {CANDY_EMOJI}\n"

            await channel.send(leaderboard_text)

# Moderator add candy
@bot.command()
@commands.has_permissions(manage_messages=True)
async def addcandy(ctx, member: discord.Member, amount: int):
    add_candy(member.id, amount)
    await ctx.send(f"✅ Added {amount} {CANDY_EMOJI} to {member.display_name}'s basket!")

# Moderator remove candy
@bot.command()
@commands.has_permissions(manage_messages=True)
async def removecandy(ctx, member: discord.Member, amount: int):
    add_candy(member.id, -amount)
    await ctx.send(f"❌ Removed {amount} {CANDY_EMOJI} from {member.display_name}'s basket!")

# Show your candy
@bot.command()
async def mycandy(ctx):
    amount = candy.get(ctx.author.id, 0)
    await ctx.send(f"🍬 {ctx.author.mention}, you have **{amount} {CANDY_EMOJI}**!")

# --- RUN ---
import os
bot.run(os.getenv("TOKEN"))