import discord
from discord.ext import tasks, commands
import datetime
from threading import Thread
from flask import Flask
import os
import pytz
import re

# ========= CONFIG =========
TOKEN = os.environ["TOKEN"]

TRAINING_CHANNEL_ID = 1434580297206202482
LOG_CHANNEL_ID = 1434579615153913946
TESTER_CATEGORY_ID = 1330612560780857344
EINZELGESPRAECHE_CATEGORY_ID = 1330628490621354108

ROLE_NAME = "Pizzen"
VM_ROLE_NAME = "VM"
TESTER_ROLE_NAME = "Tester"

TIMEZONE = pytz.timezone("Europe/Berlin")

TRAINING_DAYS = {
    "montag": (0, "Montag"),
    "dienstag": (1, "Dienstag"),
    "donnerstag": (3, "Donnerstag")
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

# ========= HELPER =========
async def send_log(text):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"📝 {text}")

def safe_name(name: str):
    name = name.lower()
    name = re.sub(r"[^a-z0-9äöüß\-]", "-", name)
    return name[:90]

async def get_training_messages(channel):
    msgs = {}
    async for msg in channel.history(limit=50):
        if msg.author == bot.user:
            for key, (_, label) in TRAINING_DAYS.items():
                if label in msg.content:
                    msgs[key] = msg
    return msgs

async def get_votes(msg):
    voted = set()
    for reaction in msg.reactions:
        if str(reaction.emoji) in ["👍", "👎"]:
            async for user in reaction.users():
                if not user.bot:
                    voted.add(user.id)
    return voted

# ========= TRAINING POSTS =========
async def create_training_posts():
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)

    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))

    for key, (wd, label) in TRAINING_DAYS.items():
        date = monday + datetime.timedelta(days=wd)
        msg = await ch.send(
            f"🏋️ **{label}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    if role:
        await ch.send(role.mention)

    await send_log("✅ Trainingsposts erstellt")

# ========= REMINDER LOGIK =========
async def remind_members(day_key=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    pizzen_role = discord.utils.get(guild.roles, name=ROLE_NAME)
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)

    posts = await get_training_messages(ch)

    for member in guild.members:
        if member.bot or pizzen_role not in member.roles:
            continue

        missing = []

        for key, msg in posts.items():
            if day_key and key != day_key:
                continue
            if member.id not in await get_votes(msg):
                missing.append(TRAINING_DAYS[key][1])

        if not missing:
            continue

        channel_name = f"einzelgespräch-{safe_name(member.name)}"
        eg = discord.utils.get(cat.text_channels, name=channel_name)
        if not eg:
            continue

        text = (
            f"👋 Hallo {member.mention}!\n\n"
            f"Bitte stimme **hier** für folgende Trainingstage ab:\n"
            f"👉 <#{TRAINING_CHANNEL_ID}>\n\n"
        )
        for d in missing:
            text += f"• {d}\n"
        text += "\nDanke! 🏋️"

        await eg.send(text)

# ========= COMMANDS =========
@bot.command()
@commands.has_role(VM_ROLE_NAME)
async def remind(ctx, tag: str = None):
    if tag:
        tag = tag.lower()
        if tag not in TRAINING_DAYS:
            await ctx.send("❌ Ungültiger Tag. Nutze: montag, dienstag oder donnerstag.")
            return
        await remind_members(tag)
        await ctx.send(f"🔔 Erinnerungen für **{TRAINING_DAYS[tag][1]}** gesendet")
    else:
        await remind_members()
        await ctx.send("🔔 Erinnerungen für alle Tage gesendet")

@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts()
    await ctx.send("✅ Trainingsposts erstellt")

async def list_missing(ctx, key):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)
    posts = await get_training_messages(ch)
    msg = posts.get(key)

    if not msg:
        await ctx.send("❌ Kein Trainingspost gefunden.")
        return

    voted = await get_votes(msg)
    missing = [m.mention for m in ctx.guild.members if role in m.roles and m.id not in voted]

    if missing:
        await ctx.send("❌ Fehlt:\n" + ", ".join(missing))
    else:
        await ctx.send("✅ Alle abgestimmt")

@bot.command()
async def montag(ctx): await list_missing(ctx, "montag")
@bot.command()
async def dienstag(ctx): await list_missing(ctx, "dienstag")
@bot.command()
async def donnerstag(ctx): await list_missing(ctx, "donnerstag")

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
    await send_log("✅ Bot gestartet")

bot.run(TOKEN)
