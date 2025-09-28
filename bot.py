# bot.py
import discord
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime, timedelta
import pytz
import os
import json
import logging

# --- CONFIG ---
TOKEN = os.getenv("TOKEN")  # Set this in Render env variables
BOT_NAME = "Trick-or-Treat"
TRICK_THREAD_ID = 1419091285322629221  # #trick-or-treating
LEADERBOARD_CHANNEL_ID = 1419091463437815831  # #trick-or-treat-leaderboard
CANDY_LOG_CHANNEL_ID = 1419091590445793412  # #candy-log
CANDY_EMOJI = "<:CandyCorn:1419093319895744543>"
LEADERBOARD_EMOJI = "<:TrickorTreat:1419093341026385920>"
DATA_FILE = "candy.json"

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")

# --- DATA STORAGE ---
candy = {}
last_daily = {}
last_trick = {}
last_random_reward = {}

# --- JSON FUNCTIONS ---
def save_data():
    data = {
        "candy": candy,
        "last_daily": {uid: dt.isoformat() for uid, dt in last_daily.items()},
        "last_trick": {uid: dt.isoformat() for uid, dt in last_trick.items()},
        "last_random_reward": {uid: dt.isoformat() for uid, dt in last_random_reward.items()},
    }
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_data():
    global candy, last_daily, last_trick, last_random_reward
    if not os.path.exists(DATA_FILE):
        return
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    candy = {int(uid): amount for uid, amount in data.get("candy", {}).items()}
    last_daily = {int(uid): datetime.fromisoformat(ts) for uid, ts in data.get("last_daily", {}).items()}
    last_trick = {int(uid): datetime.fromisoformat(ts) for uid, ts in data.get("last_trick", {}).items()}
    last_random_reward = {int(uid): datetime.fromisoformat(ts) for uid, ts in data.get("last_random_reward", {}).items()}

# --- FUNCTIONS ---
def add_candy(user_id, amount):
    candy[user_id] = candy.get(user_id, 0) + amount
    if candy[user_id] < 0:
        candy[user_id] = 0
    save_data()

def can_get_daily(user_id):
    now = datetime.utcnow()
    return user_id not in last_daily or now - last_daily[user_id] >= timedelta(hours=24)

def can_trick_or_treat(user_id):
    now = datetime.utcnow()
    return user_id not in last_trick or now - last_trick[user_id] >= timedelta(hours=24)

def can_get_random_reward(user_id):
    now = datetime.utcnow()
    return user_id not in last_random_reward or now - last_random_reward[user_id] >= timedelta(hours=1)

# --- COMMANDS ---
@bot.command(name="candy")
async def candy_command(ctx):
    amount = candy.get(ctx.author.id, 0)
    await ctx.send(f"{ctx.author.display_name}, you have {amount} {CANDY_EMOJI}!")

@bot.command(name="trickortreat")
async def trickortreat_command(ctx):
    if ctx.channel.id != TRICK_THREAD_ID:
        return  # restrict command use to trick-or-treat thread
    if not can_trick_or_treat(ctx.author.id):
        wait_time = timedelta(hours=24) - (datetime.utcnow() - last_trick[ctx.author.id])
        hours, remainder = divmod(int(wait_time.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        await ctx.send(f"⏳ You must wait {hours}h {minutes}m before trick-or-treating again.")
        return
    last_trick[ctx.author.id] = datetime.utcnow()
    if random.random() < 0.7:
        gain = random.randint(1, 5)
        add_candy(ctx.author.id, gain)
        await ctx.send(f"🍬 {ctx.author.display_name} found {gain} {CANDY_EMOJI}!")
    else:
        loss = random.randint(1, 3)
        add_candy(ctx.author.id, -loss)
        await ctx.send(f"👻 A ghost scared {ctx.author.display_name}! They dropped {loss} {CANDY_EMOJI}...")

@bot.command(name="addcandy")
@commands.has_permissions(manage_messages=True)
async def addcandy_command(ctx, member: discord.Member, amount: int):
    if ctx.channel.id != CANDY_LOG_CHANNEL_ID:
        return
    add_candy(member.id, amount)
    await ctx.send(f"✅ Added {amount} {CANDY_EMOJI} to {member.display_name}.")

@bot.command(name="removecandy")
@commands.has_permissions(manage_messages=True)
async def removecandy_command(ctx, member: discord.Member, amount: int):
    if ctx.channel.id != CANDY_LOG_CHANNEL_ID:
        return
    add_candy(member.id, -amount)
    await ctx.send(f"✅ Removed {amount} {CANDY_EMOJI} from {member.display_name}.")

# --- EVENTS ---
@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.channel.id != TRICK_THREAD_ID:
        # Daily reward: 1 candy for first post per day
        if can_get_daily(message.author.id):
            last_daily[message.author.id] = datetime.utcnow()
            add_candy(message.author.id, 1)
            trick_channel = bot.get_channel(TRICK_THREAD_ID)
            if trick_channel:
                await trick_channel.send(f"🎃 {message.author.display_name} earned 1 {CANDY_EMOJI} for being active today!")
        # Random reward: 10% chance, max 1 per hour
        if can_get_random_reward(message.author.id) and random.random() < 0.1:
            last_random_reward[message.author.id] = datetime.utcnow()
            add_candy(message.author.id, 1)
            trick_channel = bot.get_channel(TRICK_THREAD_ID)
            if trick_channel:
                await trick_channel.send(f"✨ {message.author.display_name} stumbled upon a hidden {CANDY_EMOJI}!")
    await bot.process_commands(message)

# --- LEADERBOARD ---
@tasks.loop(minutes=1)
async def leaderboard_task():
    now = datetime.now(pytz.timezone("US/Pacific"))
    if now.hour == 17 and now.minute == 0:  # between 5:00–5:05 PM PST
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if channel:
            sorted_candy = sorted(candy.items(), key=lambda x: x[1], reverse=True)
            if not sorted_candy:
                await channel.send("🎃 The baskets are empty... no candy yet!")
                return
            leaderboard_text = f"{LEADERBOARD_EMOJI} **Trick-or-Treat Leaderboard** {LEADERBOARD_EMOJI}\n\n"
            for i, (user_id, amount) in enumerate(sorted_candy, start=1):
                member = channel.guild.get_member(user_id)
                if member:
                    leaderboard_text += f"{i}. {member.display_name} — {amount} {CANDY_EMOJI}\n"
            leaderboard_text += "\n━━━━━━━━━━━━━━━━━━━━━━━"
            await channel.send(leaderboard_text)

# Force leaderboard (mod-only)
@bot.command(name="forceleaderboard")
@commands.has_permissions(manage_messages=True)
async def forceleaderboard(ctx):
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if channel:
        sorted_candy = sorted(candy.items(), key=lambda x: x[1], reverse=True)
        if not sorted_candy:
            await channel.send("🎃 The baskets are empty... no candy yet!")
            return
        leaderboard_text = f"{LEADERBOARD_EMOJI} **Trick-or-Treat Leaderboard** {LEADERBOARD_EMOJI}\n\n"
        for i, (user_id, amount) in enumerate(sorted_candy, start=1):
            member = channel.guild.get_member(user_id)
            if member:
                leaderboard_text += f"{i}. {member.display_name} — {amount} {CANDY_EMOJI}\n"
        leaderboard_text += "\n━━━━━━━━━━━━━━━━━━━━━━━"
        await channel.send(leaderboard_text)

@bot.event
async def on_ready():
    load_data()
    leaderboard_task.start()
    print(f"{BOT_NAME} is online as {bot.user}")

# --- STARTUP WRAPPER ---
logging.basicConfig(level=logging.INFO)

async def main():
    try:
        await bot.start(TOKEN)
    except Exception as e:
        logging.error("Bot crashed with error:", exc_info=e)
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error("Fatal error starting bot:", exc_info=e)







