# bot.py
import os
import json
import random
import asyncio
import sys
from datetime import datetime, timedelta

import pytz
import discord
from discord.ext import commands, tasks

# ======================
# CONFIG
# ======================
CANDY_FILE = "candy.json"
CANDY_EMOJI = "<:CandyCorn:1419093319895744543>"  # custom emoji
TRICK_OR_TREAT_CHANNEL_ID = 1419091285322629221   # Trick-or-Treat thread
LEADERBOARD_CHANNEL_ID = 1419091463437815831      # Leaderboard channel
CANDY_LOG_CHANNEL_ID = 1419091590445793412        # Candy log channel

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ======================
# DATA STORAGE
# ======================
if os.path.exists(CANDY_FILE):
    with open(CANDY_FILE, "r") as f:
        candy = json.load(f)
else:
    candy = {}

cooldowns = {}          # user_id: datetime for !trickortreat
daily_claimed = {}      # user_id: datetime for daily activity candy

def save_candy():
    with open(CANDY_FILE, "w") as f:
        json.dump(candy, f)

# ======================
# LEADERBOARD TASK
# ======================
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

            leaderboard_text = (
                "🏆 **Trick-or-Treat Leaderboard** 🏆\n"
                "────────────────────────\n\n"
            )
            for i, (user_id, amount) in enumerate(sorted_candy, start=1):
                member = channel.guild.get_member(int(user_id))
                if member:
                    leaderboard_text += f"{i}. {member.display_name} — {amount} {CANDY_EMOJI}\n"

            await channel.send(leaderboard_text)

# ======================
# COMMANDS
# ======================

# Trick or Treat Gamble
@bot.command()
async def trickortreat(ctx):
    if ctx.channel.id != TRICK_OR_TREAT_CHANNEL_ID:
        return

    user_id = str(ctx.author.id)
    now = datetime.now()

    # Cooldown check
    if user_id in cooldowns and now < cooldowns[user_id]:
        remaining = cooldowns[user_id] - now
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes, _ = divmod(remainder, 60)
        await ctx.send(
            f"{ctx.author.mention}, you need to wait {hours}h {minutes}m before trick-or-treating again!"
        )
        return

    # Set cooldown
    cooldowns[user_id] = now + timedelta(hours=24)

    # Candy gain/loss
    if random.random() < 0.25:  # 25% ghost scare
        lost = random.randint(1, 3)
        candy[user_id] = max(0, candy.get(user_id, 0) - lost)
        save_candy()
        await ctx.send(f"👻 Boo! You dropped {lost} {CANDY_EMOJI}, {ctx.author.mention}!")
    else:
        gained = random.randint(1, 5)
        candy[user_id] = candy.get(user_id, 0) + gained
        save_candy()
        await ctx.send(f"🎃 You got {gained} {CANDY_EMOJI}, {ctx.author.mention}!")

# Check candy bag
@bot.command()
async def candybag(ctx):
    if ctx.channel.id != TRICK_OR_TREAT_CHANNEL_ID:
        return
    user_id = str(ctx.author.id)
    amount = candy.get(user_id, 0)
    await ctx.send(f"{ctx.author.mention}, you have {amount} {CANDY_EMOJI}.")

# Mod-only add candy
@bot.command()
@commands.has_permissions(manage_messages=True)
async def addcandy(ctx, member: discord.Member, amount: int):
    candy[str(member.id)] = candy.get(str(member.id), 0) + amount
    save_candy()
    channel = bot.get_channel(CANDY_LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"✅ {amount} {CANDY_EMOJI} added to {member.display_name}.")
    await ctx.message.delete()

# Mod-only remove candy
@bot.command()
@commands.has_permissions(manage_messages=True)
async def removecandy(ctx, member: discord.Member, amount: int):
    candy[str(member.id)] = max(0, candy.get(str(member.id), 0) - amount)
    save_candy()
    channel = bot.get_channel(CANDY_LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"❌ {amount} {CANDY_EMOJI} removed from {member.display_name}.")
    await ctx.message.delete()

# ======================
# EVENTS
# ======================
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = str(message.author.id)
    now = datetime.now()

    # Daily candy (first post of the day)
    if user_id not in daily_claimed or now - daily_claimed[user_id] >= timedelta(days=1):
        candy[user_id] = candy.get(user_id, 0) + 1
        daily_claimed[user_id] = now
        save_candy()

    # Random lucky candy (10% chance)
    if random.random() < 0.1:
        candy[user_id] = candy.get(user_id, 0) + 1
        save_candy()
        # Only announce in Trick-or-Treat thread
        channel = bot.get_channel(TRICK_OR_TREAT_CHANNEL_ID)
        if channel:
            await channel.send(f"🍭 {message.author.mention} found a lucky {CANDY_EMOJI} while being active!")

    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    leaderboard_task.start()

# ======================
# RUN BOT (fixes RuntimeError issue)
# ======================
if sys.platform.startswith("win") and sys.version_info >= (3, 8):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

bot.run(os.getenv("DISCORD_TOKEN"))
