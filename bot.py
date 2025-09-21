# bot.py
import os
import json
import random
import asyncio
from datetime import datetime, timedelta

import sys
print("Python version running on Render:", sys.version)

import pytz
import discord
from discord.ext import commands, tasks

# ---------------- CONFIG ----------------
# Channels (ids you provided)
TRICK_CHANNEL_ID = 1419091285322629221       # trick-or-treating thread (where bot posts daily & trick results)
LEADERBOARD_CHANNEL_ID = 1419091463437815831 # trick-or-treat-leaderboard thread (where daily leaderboard posts)
CANDY_LOG_CHANNEL_ID = 1419091590445793412   # candy-log (mods-only commands must run here)

# Emojis (baked-in)
CANDY_EMOJI = "<:CandyCorn:1419093319895744543>"
TRICK_ICON = "<:TrickorTreat:1419093341026385920>"
GHOST = "👻"

# Files + timing
DATA_FILE = "candy_data.json"
TIMEZONE = "US/Pacific"
LEADERBOARD_HOUR = 17  # 5 PM PST
DAILY_COOLDOWN_HOURS = 24
TRICK_COOLDOWN_HOURS = 24
BONUS_POST_CHANCE = 0.05  # 5% chance to find a bonus candy when posting (tweakable)

# ---------------- INTENTS & BOT ----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- Persistence helpers ----------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # default structure
    return {"users": {}, "cooldowns": {}}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=4)

DATA = load_data()  # global data structure

def ensure_user_record(uid: str):
    if uid not in DATA["users"]:
        DATA["users"][uid] = {"candy": 0}
    if uid not in DATA["cooldowns"]:
        DATA["cooldowns"][uid] = {"daily": None, "trick": None}
    return DATA["users"][uid], DATA["cooldowns"][uid]

def parse_iso(s):
    if not s:
        return None
    return datetime.fromisoformat(s)

def now_utc():
    return datetime.utcnow()

def remaining_from_iso(iso_str, hours):
    if not iso_str:
        return None
    last = parse_iso(iso_str)
    reset_time = last + timedelta(hours=hours)
    remaining = reset_time - now_utc()
    return remaining if remaining.total_seconds() > 0 else None

# ---------------- Utilities ----------------
def format_timedelta(td: timedelta):
    if not td:
        return "0m"
    total = int(td.total_seconds())
    hours, rem = divmod(total, 3600)
    minutes, _ = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"

async def post_to_trick_channel(content=None, embed=None):
    channel = bot.get_channel(TRICK_CHANNEL_ID)
    if channel:
        try:
            if embed:
                await channel.send(embed=embed)
            else:
                await channel.send(content)
        except discord.Forbidden:
            print("Permission error: cannot post in trick channel.")

# ---------------- Event: on_ready ----------------
@bot.event
async def on_ready():
    print(f"🎃 Trick-or-Treat Bot online as {bot.user}")
    if not daily_leaderboard_task.is_running():
        daily_leaderboard_task.start()

# ---------------- Event: grant daily candy when user posts anywhere ----------------
@bot.event
async def on_message(message: discord.Message):
    # allow other commands to be processed after
    if message.author.bot:
        return

    uid = str(message.author.id)
    user_rec, cd_rec = ensure_user_record(uid)

    # DAILY: if 24h passed since last daily -> grant +1 and announce in trick channel
    last_daily_iso = cd_rec.get("daily")
    can_claim_daily = True
    if last_daily_iso:
        rem = remaining_from_iso(last_daily_iso, DAILY_COOLDOWN_HOURS)
        if rem:
            can_claim_daily = False

    if can_claim_daily:
        user_rec["candy"] = user_rec.get("candy", 0) + 1
        # update last_daily to now (store ISO)
        cd_rec["daily"] = now_utc().isoformat()
        save_data()
        # announce in trick channel only
        await post_to_trick_channel(
            f"👻 {message.author.mention} found a stray {CANDY_EMOJI} while hanging out — **+1**! "
            f"(Total: **{user_rec['candy']}** {CANDY_EMOJI})"
        )

    # BONUS: small chance (independent) to find a hidden candy (posted into trick channel)
    if random.random() < BONUS_POST_CHANCE:
        user_rec["candy"] = user_rec.get("candy", 0) + 1
        save_data()
        await post_to_trick_channel(
            f"✨ {message.author.mention} stumbled upon a hidden {CANDY_EMOJI}! (+1, Total: **{user_rec['candy']}** {CANDY_EMOJI})"
        )

    # process other commands after handling message
    await bot.process_commands(message)

# ---------------- Command: trickortreat (24h cooldown per user) ----------------
@bot.command(name="trickortreat")
async def trick_or_treat_command(ctx: commands.Context):
    # must be used in trick thread
    if ctx.channel.id != TRICK_CHANNEL_ID:
        await ctx.send(f"🍬 Please use this command in <#{TRICK_CHANNEL_ID}> to keep things tidy.")
        return

    uid = str(ctx.author.id)
    user_rec, cd_rec = ensure_user_record(uid)

    # check cooldown
    rem = remaining_from_iso(cd_rec.get("trick"), TRICK_COOLDOWN_HOURS)
    if rem:
        await ctx.send(
            f"⏳ {ctx.author.mention}, you already went trick-or-treating! Come back in **{format_timedelta(rem)}** to try again."
        )
        return

    # set cooldown now
    cd_rec["trick"] = now_utc().isoformat()

    # roll outcome: 50/50 treat or trick
    if random.choice([True, False]):
        gain = random.randint(1, 5)  # win 1-5 candies
        user_rec["candy"] = user_rec.get("candy", 0) + gain
        save_data()
        # announce in trick channel
        await post_to_trick_channel(
            f"🍫 {ctx.author.mention} knocked on a door and scored a **king-sized bar** {TRICK_ICON}! "
            f"You gained **{gain} {CANDY_EMOJI}**. (Total: **{user_rec['candy']}** {CANDY_EMOJI})"
        )
    else:
        loss = random.randint(1, 3)  # lose 1-3 candies
        before = user_rec.get("candy", 0)
        lost_actual = min(before, loss)
        user_rec["candy"] = max(0, before - loss)
        save_data()
        await post_to_trick_channel(
            f"👻 Boo! {ctx.author.mention} got tricked and dropped **{lost_actual} {CANDY_EMOJI}**! "
            f"(Total: **{user_rec['candy']}** {CANDY_EMOJI})"
        )

# ---------------- Command: candybag (embed) - only in trick thread ----------------
@bot.command(name="candybag")
async def candybag_command(ctx: commands.Context):
    if ctx.channel.id != TRICK_CHANNEL_ID:
        await ctx.send(f"📮 You can check your candy bag in <#{TRICK_CHANNEL_ID}>. Please go there and try again.")
        return

    uid = str(ctx.author.id)
    user_rec, _ = ensure_user_record(uid)
    candies = user_rec.get("candy", 0)

    embed = discord.Embed(
        title=f"{ctx.author.display_name}'s Candy Bag {CANDY_EMOJI}",
        description=f"You currently have **{candies} {CANDY_EMOJI}**.",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Keep posting and trick-or-treating to collect more candy!")
    # optional thumbnail: use your server emoji URL or a hosted image
    # embed.set_thumbnail(url="https://example.com/candybag.png")
    await ctx.send(embed=embed)

# ---------------- Command: cooldown (plain text) ----------------
@bot.command(name="cooldown")
async def cooldown_command(ctx: commands.Context):
    uid = str(ctx.author.id)
    _, cd_rec = ensure_user_record(uid)

    rem_daily = remaining_from_iso(cd_rec.get("daily"), DAILY_COOLDOWN_HOURS)
    rem_trick = remaining_from_iso(cd_rec.get("trick"), TRICK_COOLDOWN_HOURS)

    lines = []
    if rem_daily:
        lines.append(f"🍬 Daily candy available in **{format_timedelta(rem_daily)}**")
    else:
        lines.append("🍬 Daily candy: **Ready to claim** — just post anywhere in the server!")

    if rem_trick:
        lines.append(f"🎃 Trick-or-Treat available in **{format_timedelta(rem_trick)}**")
    else:
        lines.append("🎃 Trick-or-Treat: **Ready** — use `!trickortreat` in the trick thread!")

    await ctx.send(f"{ctx.author.mention}\n" + "\n".join(lines))

# ---------------- Mod commands: addcandy / removecandy (mods only, candy-log channel only) ----------------
def is_mod(ctx: commands.Context):
    return ctx.author.guild_permissions.manage_messages or ctx.author.guild_permissions.administrator

@bot.command(name="addcandy")
async def add_candy_command(ctx: commands.Context, member: discord.Member, amount: int):
    if ctx.channel.id != CANDY_LOG_CHANNEL_ID:
        await ctx.send(f"🔒 Moderation commands must be used in <#{CANDY_LOG_CHANNEL_ID}>.")
        return
    if not is_mod(ctx):
        await ctx.send("🚫 You don't have permission to use this command.")
        return
    uid = str(member.id)
    user_rec, _ = ensure_user_record(uid)
    user_rec["candy"] = user_rec.get("candy", 0) + amount
    save_data()
    await ctx.send(f"✅ Added **{amount} {CANDY_EMOJI}** to {member.mention}. (Total: **{user_rec['candy']}**)")

@bot.command(name="removecandy")
async def remove_candy_command(ctx: commands.Context, member: discord.Member, amount: int):
    if ctx.channel.id != CANDY_LOG_CHANNEL_ID:
        await ctx.send(f"🔒 Moderation commands must be used in <#{CANDY_LOG_CHANNEL_ID}>.")
        return
    if not is_mod(ctx):
        await ctx.send("🚫 You don't have permission to use this command.")
        return
    uid = str(member.id)
    user_rec, _ = ensure_user_record(uid)
    user_rec["candy"] = max(0, user_rec.get("candy", 0) - amount)
    save_data()
    await ctx.send(f"✅ Removed **{amount} {CANDY_EMOJI}** from {member.mention}. (Total: **{user_rec['candy']}**)")

# ---------------- Leaderboard: daily at 5 PM PST (embed) ----------------
@tasks.loop(minutes=1)
async def daily_leaderboard_task():
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    if now.hour == LEADERBOARD_HOUR and now.minute == 0:
        # if no users, skip
        if not DATA.get("users"):
            return
        channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if channel is None:
            return

        # sort all users by candy desc
        sorted_users = sorted(DATA["users"].items(), key=lambda x: x[1].get("candy", 0), reverse=True)
        description_lines = []
        for i, (uid, info) in enumerate(sorted_users, start=1):
            # show display name if available
            try:
                member = channel.guild.get_member(int(uid))
                name = member.display_name if member else f"<@{uid}>"
            except Exception:
                name = f"<@{uid}>"
            description_lines.append(f"**{i}.** {name} — **{info.get('candy', 0)}** {CANDY_EMOJI}")

        embed = discord.Embed(
            title="🏆 Trick-or-Treat Leaderboard 🏆",
            description="\n".join(description_lines),
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        # small banner/thumbnail (keeps it friendly, not AIish)
        embed.set_footer(text="Updated daily at Item Shop Refresh")

        await channel.send(embed=embed)

# ---------------- Run ----------------
if __name__ == "__main__":
    # ensure data file exists
    save_data()
    # start bot
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        print("ERROR: set DISCORD_TOKEN environment variable.")
    else:
        daily_leaderboard_task.start()
        bot.run(TOKEN)

