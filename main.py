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
VM_ROLE_NAME = "VM"

TIMEZONE = pytz.timezone("Europe/Berlin")

TRAINING_DAYS = {
    0: "Montag",
    1: "Dienstag",
    3: "Donnerstag"
}

# ========= BOT =========
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ========= FLASK =========
app = Flask("")

@app.route("/")
def home():
    return "Bot läuft"

Thread(target=lambda: app.run("0.0.0.0", 5000), daemon=True).start()

# ========= HILFSFUNKTIONEN =========
async def send_log(text):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"📝 {text}")

def next_week_dates():
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    return {
        0: monday,
        1: monday + datetime.timedelta(days=1),
        3: monday + datetime.timedelta(days=3)
    }

async def get_training_messages(channel):
    msgs = {}
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            for wd, name in TRAINING_DAYS.items():
                if name in msg.content:
                    msgs[wd] = msg
    return msgs

async def get_votes(msg):
    voted = set()
    for reaction in msg.reactions:
        if str(reaction.emoji) in ["👍", "👎"]:
            async for user in reaction.users():
                if not user.bot:
                    voted.add(user.id)
    return voted

# ========= POST TRAININGS =========
async def create_training_posts():
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)

    dates = next_week_dates()

    for wd, date in dates.items():
        text = (
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        msg = await ch.send(text)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await ch.send(role.mention)
    await send_log("Trainingsposts erstellt")

# ========= REMINDER LOGIK =========
async def remind_members(target_member=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild

    pizzen = discord.utils.get(guild.roles, name=ROLE_NAME)
    training_msgs = await get_training_messages(ch)

    for member in guild.members:
        if target_member and member.id != target_member.id:
            continue
        if pizzen not in member.roles or member.bot:
            continue

        missing = []

        for wd, msg in training_msgs.items():
            voted = await get_votes(msg)
            if member.id not in voted:
                missing.append(TRAINING_DAYS[wd])

        if missing:
            text = (
                f"👋 Hallo {member.name}!\n\n"
                f"Bitte stimme noch für folgende Trainingstage ab:\n"
            )
            for d in missing:
                text += f"• {d}\n"

            text += "\nDanke! 🏋️"
            try:
                await member.send(text)
            except:
                pass

# ========= COMMANDS =========
@bot.command()
@commands.has_role(VM_ROLE_NAME)
async def remind(ctx, member: discord.Member):
    await remind_members(member)
    await ctx.send(f"🔔 Erinnerung an {member.mention} gesendet")

@bot.command()
async def montag(ctx):
    await list_missing(ctx, 0)

@bot.command()
async def dienstag(ctx):
    await list_missing(ctx, 1)

@bot.command()
async def donnerstag(ctx):
    await list_missing(ctx, 3)

async def list_missing(ctx, weekday):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)

    msgs = await get_training_messages(ch)
    msg = msgs.get(weekday)

    voted = await get_votes(msg)
    missing = [
        m.mention for m in guild.members
        if role in m.roles and m.id not in voted and not m.bot
    ]

    if missing:
        await ctx.send(
            f"❌ Nicht abgestimmt für **{TRAINING_DAYS[weekday]}**:\n" +
            ", ".join(missing)
        )
    else:
        await ctx.send(f"✅ Alle haben für {TRAINING_DAYS[weekday]} abgestimmt!")

# ========= TASKS =========
@tasks.loop(minutes=1)
async def friday_post():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 4 and now.hour == 14 and now.minute == 0:
        await create_training_posts()

@tasks.loop(minutes=1)
async def sunday_reminder():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 6 and now.hour == 12 and now.minute == 0:
        await remind_members()

@bot.event
async def on_ready():
    friday_post.start()
    sunday_reminder.start()
    await send_log("Bot gestartet")

bot.run(TOKEN)
