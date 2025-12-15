import discord
from discord.ext import tasks, commands
import datetime
from threading import Thread
from flask import Flask
import os
import pytz

# ========= CONFIG =========
TOKEN = os.environ["TOKEN"]

TRAINING_CHANNEL_ID = 1434580297206202482
LOG_CHANNEL_ID = 1434579615153913946
ROLE_NAME = "Pizzen"

TIMEZONE = pytz.timezone("Europe/Berlin")

TRAINING_DAYS = {
    "Montag": 0,
    "Dienstag": 1,
    "Donnerstag": 3
}

# ========= BOT =========
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ========= FLASK =========
app = Flask("")

@app.route("/")
def home():
    return "Bot läuft!"

def run_flask():
    app.run(host="0.0.0.0", port=5000)

Thread(target=run_flask, daemon=True).start()

# ========= HILFSFUNKTIONEN =========
def get_next_week_dates():
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    dates = {}
    for name, wd in TRAINING_DAYS.items():
        dates[name] = monday + datetime.timedelta(days=wd)
    return dates

async def send_log(text):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"📝 {text}")

async def delete_old_posts(channel):
    async for msg in channel.history(limit=200):
        if msg.author == bot.user and "🏋️" in msg.content:
            await msg.delete()

# ========= TRAININGSPOSTS =========
async def create_training_posts():
    channel = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = channel.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)

    await delete_old_posts(channel)

    dates = get_next_week_dates()

    for day, date in dates.items():
        msg = await channel.send(
            f"🏋️ **{day}, {date.strftime('%d.%m.%Y')}**\n"
            "👍 = dabei | 👎 = nicht dabei"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await channel.send(role.mention)
    await send_log("Neue Trainingsabstimmungen erstellt")

# ========= AUSWERTUNG =========
async def get_votes_per_day():
    channel = bot.get_channel(TRAINING_CHANNEL_ID)
    votes = {}

    async for msg in channel.history(limit=50):
        for day in TRAINING_DAYS:
            if day in msg.content:
                voted = set()
                for reaction in msg.reactions:
                    if str(reaction.emoji) in ["👍", "👎"]:
                        async for user in reaction.users():
                            if not user.bot:
                                voted.add(user.id)
                votes[day] = voted
    return votes

# ========= ERINNERUNGEN =========
async def send_reminders():
    channel = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = channel.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)

    votes = await get_votes_per_day()

    for member in role.members:
        missing_days = []
        for day in TRAINING_DAYS:
            if day not in votes or member.id not in votes[day]:
                missing_days.append(day)

        if missing_days:
            await member.send(
                f"👋 Hallo {member.name}\n\n"
                f"Du hast noch nicht abgestimmt für:\n"
                f"➡️ {', '.join(missing_days)}\n\n"
                f"Bitte hole das im Channel nach 👍👎"
            )

    await send_log("Erinnerungen versendet")

# ========= AUTOMATIK =========
@tasks.loop(minutes=1)
async def training_task():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 4 and now.hour == 14 and now.minute == 0:
        await create_training_posts()

@tasks.loop(minutes=1)
async def reminder_task():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 6 and now.hour == 12 and now.minute == 0:
        await send_reminders()

# ========= COMMANDS =========
async def missing_for_day(ctx, day):
    guild = ctx.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    votes = await get_votes_per_day()

    missing = []
    for member in role.members:
        if day not in votes or member.id not in votes[day]:
            missing.append(member.mention)

    if missing:
        await ctx.send(f"❌ **Nicht abgestimmt für {day}:**\n" + "\n".join(missing))
    else:
        await ctx.send(f"✅ Alle haben für **{day}** abgestimmt!")

@bot.command()
async def montag(ctx):
    await missing_for_day(ctx, "Montag")

@bot.command()
async def dienstag(ctx):
    await missing_for_day(ctx, "Dienstag")

@bot.command()
async def donnerstag(ctx):
    await missing_for_day(ctx, "Donnerstag")

@bot.command()
@commands.has_permissions(administrator=True)
async def reminder(ctx):
    await send_reminders()
    await ctx.send("✅ Erinnerungen versendet")

# ========= START =========
@bot.event
async def on_ready():
    print(f"Online als {bot.user}")
    training_task.start()
    reminder_task.start()
    await send_log("Bot gestartet")

bot.run(TOKEN)
