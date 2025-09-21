import discord
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime, timedelta
import pytz
import os
import json

# --- CONFIG ---
TOKEN = os.getenv("TOKEN")  # Set this in Render environment variables
BOT_NAME = "Trick-or-Treat"
DAILY_CHANNEL_ID = 1411787882322198600  # #trick-or-treating
LEADERBOARD_CHANNEL_ID = 1411788070134485042  # #trick-or-treat-leaderboard
CANDY_EMOJI = "<:CandyCorn:1408306488170254397>"
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
candy = {}  # {user_id: count}
last_daily = {}  # {user_id: datetime}
last_trick = {}  # {user_id: datetime}
last_random_reward = {}  # {user_id: datetime}


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


# --- EVENTS ---
@bot.event
async def on_ready():
    load_data()
