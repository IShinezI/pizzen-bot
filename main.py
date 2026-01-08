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

def safe_name(name: str):
    name = name.lower()
    name = re.sub(r"[^a-z0-9äöüß\-]", "-", name)
    return name[:90]

def find_einzel_channel(guild, member):
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)
    if not cat:
        return None

    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            return ch
    return None

# ========= TRAININGS =========
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

async def create_training_posts():
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    role = discord.utils.get(ch.guild.roles, name=ROLE_NAME)

    for wd, date in next_week_dates().items():
        msg = await ch.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await ch.send(role.mention)
    await send_log("✅ Trainingsposts erstellt")

# ========= EINZELGESPRÄCH =========
async def create_einzel_channel(member):
    guild = member.guild
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)

    if not vm_role or not cat:
        return

    if find_einzel_channel(guild, member):
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    }

    ch = await guild.create_text_channel(
        name=f"einzelgespräch-{safe_name(member.name)}",
        category=cat,
        overwrites=overwrites,
        topic=f"user_id:{member.id}",
        reason="Pizzen-Rolle erhalten"
    )

    await ch.send(
        f"👋 Willkommen {member.mention}!\n\n"
        "Dies ist dein persönlicher Einzelgespräch-Channel.\n"
        "Hier erhältst du auch deine Erinnerungen."
    )

    await send_log(f"✅ Einzelgespräch erstellt für {member.name}")

async def delete_einzel_channel(member):
    ch = find_einzel_channel(member.guild, member)
    if ch:
        await ch.delete(reason="Pizzen-Rolle entfernt")
        await send_log(f"🗑️ Einzelgespräch gelöscht für {member.name}")

# ========= EVENTS =========
@bot.event
async def on_member_update(before, after):
    role = discord.utils.get(after.guild.roles, name=ROLE_NAME)
    if not role:
        return

    if role not in before.roles and role in after.roles:
        await create_einzel_channel(after)

    if role in before.roles and role not in after.roles:
        await delete_einzel_channel(after)

# ========= REMINDER =========
async def remind_members(target=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    role = discord.utils.get(ch.guild.roles, name=ROLE_NAME)
    msgs = await get_training_messages(ch)

    for m in ch.guild.members:
        if m.bot or role not in m.roles:
            continue
        if target and m.id != target.id:
            continue

        missing = []
        for wd, msg in msgs.items():
            if m.id not in await get_votes(msg):
                missing.append(TRAINING_DAYS[wd])

        if missing:
            eg = find_einzel_channel(ch.guild, m)
            if eg:
                text = (
                    f"👋 Hallo {m.mention}!\n\n"
                    "Bitte stimme hier für folgende Trainingstage ab:\n"
                    f"👉 <#{TRAINING_CHANNEL_ID}>\n\n"
                )
                for d in missing:
                    text += f"• {d}\n"
                await eg.send(text)

# ========= COMMANDS =========
@bot.command()
@commands.has_role(VM_ROLE_NAME)
async def remind(ctx, member: discord.Member):
    await remind_members(member)
    await ctx.send(f"🔔 Erinnerung gesendet an {member.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts()
    await ctx.send("✅ Trainingsposts erstellt")

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
    await send_log("🚀 Bot gestartet")

bot.run(TOKEN)
