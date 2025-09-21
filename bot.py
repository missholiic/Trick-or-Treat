import discord
from discord.ext import commands
import json
import os
import time

bot = commands.Bot(command_prefix="!")

# Load data from JSON file
def load_data():
    if not os.path.exists("candy.json"):
        with open("candy.json", "w") as f:
            json.dump({"users": {}}, f, indent=4)
    with open("candy.json", "r") as f:
        return json.load(f)

# Save data to JSON file
def save_data(data):
    with open("candy.json", "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# Ensure a user exists in the JSON
def ensure_user(user_id):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "candy": 0,
            "cooldowns": {}
        }
        save_data(data)

# Check cooldown
def is_on_cooldown(user_id, command, cooldown_seconds):
    user_id = str(user_id)
    ensure_user(user_id)
    last_used = data["users"][user_id]["cooldowns"].get(command, 0)
    current_time = time.time()
    if current_time - last_used < cooldown_seconds:
        return cooldown_seconds - (current_time - last_used)
    return 0

# Set cooldown
def set_cooldown(user_id, command):
    user_id = str(user_id)
    ensure_user(user_id)
    data["users"][user_id]["cooldowns"][command] = time.time()
    save_data(data)

# Add candy
def add_candy(user_id, amount):
    user_id = str(user_id)
    ensure_user(user_id)
    data["users"][user_id]["candy"] += amount
    save_data(data)

# Example command: trick-or-treat
@bot.command()
async def trick(ctx):
    user_id = ctx.author.id
    cooldown_time = 60  # seconds
    remaining = is_on_cooldown(user_id, "trick", cooldown_time)

    if remaining > 0:
        await ctx.send(f"⏳ You need to wait {int(remaining)}s before trick-or-treating again!")
    else:
        add_candy(user_id, 5)
        set_cooldown(user_id, "trick")
        await ctx.send(f"🍬 {ctx.author.mention}, you got 5 candy! Total: {data['users'][str(user_id)]['candy']}")

# Example command: check candy
@bot.command()
async def candy(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    amount = data["users"][user_id]["candy"]
    await ctx.send(f"🍭 {ctx.author.mention}, you have {amount} candy.")

bot.run("YOUR_BOT_TOKEN")
