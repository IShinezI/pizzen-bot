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
EINZELGESPRÄCHE_CATEGORY_ID = 1330628490621354108
TEST_ABSTIMMUNG_CHANNEL_ID = 1459256713994571938

ROLE_NAME = "Pizzen"
VM_ROLE_NAME = "VM"
TESTER_ROLE_NAME = "Tester"

TIMEZONE = pytz.timezone("Europe/Berlin")
TRAINING_DAYS = {0: "Montag", 1: "Dienstag", 3: "Donnerstag"}

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
    name = name.replace("ae", "ä")
    name = re.sub(r"[^a-z0-9äöü\-]", "-", name)
    return name[:90]

def next_week_dates():
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    return {0: monday, 1: monday + datetime.timedelta(days=1), 3: monday + datetime.timedelta(days=3)}

async def get_training_messages(channel):
    msgs = {}
    async for msg in channel.history(limit=200):
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

# ========= TRAINING =========
async def delete_old_training_messages(channel):
    async for msg in channel.history(limit=200):
        if msg.author == bot.user:
            try:
                await msg.delete()
            except:
                pass

async def create_training_posts(channel_id=None):
    ch = bot.get_channel(channel_id or TRAINING_CHANNEL_ID)
    if not ch:
        return

    await delete_old_training_messages(ch)
    dates = next_week_dates()

    for wd, date in dates.items():
        msg = await ch.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\nReagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    role = discord.utils.get(ch.guild.roles, name=ROLE_NAME)
    if role:
        await ch.send(role.mention)

# ========= TESTER CHANNEL =========
async def create_tester_channel(member):
    guild = member.guild
    cat = guild.get_channel(TESTER_CATEGORY_ID)
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)

    if not cat or not vm_role:
        return

    # ❗ WICHTIGER FIX: manuelles Finden
    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
    }

    ch = await guild.create_text_channel(
        name=f"tester-{safe_name(member.name)}",
        category=cat,
        overwrites=overwrites,
        topic=f"user_id:{member.id}",
    )

    await ch.send(
        f"👋 Willkommen {member.mention}!\n\n"
        "Dies ist dein persönlicher Tester-Channel.\n"
        "Bei Fragen melde dich gerne bei den **VMs**."
    )

    await send_log(f"🧪 Tester-Channel erstellt für {member.name}")

async def delete_tester_channel(member):
    guild = member.guild
    cat = guild.get_channel(TESTER_CATEGORY_ID)
    if not cat:
        return

    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            await ch.delete()
            await send_log(f"🗑️ Tester-Channel gelöscht: {ch.name}")
            break

# ========= EINZELGESPRÄCH =========
async def create_einzel_channel(member):
    guild = member.guild
    cat = guild.get_channel(EINZELGESPRÄCHE_CATEGORY_ID)
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)

    if not cat or not vm_role:
        return

    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True),
    }

    ch = await guild.create_text_channel(
        name=f"einzelgespräch-{safe_name(member.name)}",
        category=cat,
        overwrites=overwrites,
        topic=f"user_id:{member.id}",
    )

    await ch.send(
        f"Hallo {member.mention}\n\n"
        "Dies ist dein persönlicher Einzelgespräch-Channel."
    )

async def delete_einzel_channel(member):
    guild = member.guild
    cat = guild.get_channel(EINZELGESPRÄCHE_CATEGORY_ID)
    if not cat:
        return

    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            await ch.delete()
            break

# ========= EVENTS =========
@bot.event
async def on_member_update(before, after):
    guild = after.guild

    pizzen = discord.utils.get(guild.roles, name=ROLE_NAME)
    tester = discord.utils.get(guild.roles, name=TESTER_ROLE_NAME)

    if pizzen:
        if pizzen not in before.roles and pizzen in after.roles:
            await create_einzel_channel(after)
        elif pizzen in before.roles and pizzen not in after.roles:
            await delete_einzel_channel(after)

    if tester:
        if tester not in before.roles and tester in after.roles:
            await create_tester_channel(after)
        elif tester in before.roles and tester not in after.roles:
            await delete_tester_channel(after)

@bot.event
async def on_member_join(member):
    tester = discord.utils.get(member.guild.roles, name=TESTER_ROLE_NAME)
    if tester:
        await member.add_roles(tester)
        await create_tester_channel(member)

@bot.event
async def on_member_remove(member):
    await delete_tester_channel(member)
    await delete_einzel_channel(member)

# ========= COMMANDS =========
@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts()
    await ctx.send("✅ Trainingsposts erstellt")

@bot.command()
@commands.has_permissions(administrator=True)
async def testtraining(ctx):
    ch = bot.get_channel(TEST_ABSTIMMUNG_CHANNEL_ID)
    if not ch:
        return
    await delete_old_training_messages(ch)
    for d in TRAINING_DAYS.values():
        msg = await ch.send(f"🏋️ **Test-Abstimmung: {d}**")
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

# ========= TASKS =========
@tasks.loop(minutes=1)
async def friday_post():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 4 and now.hour == 14 and now.minute == 0:
        await create_training_posts()

@bot.event
async def on_ready():
    friday_post.start()
    await send_log("✅ Bot gestartet")

bot.run(TOKEN)
