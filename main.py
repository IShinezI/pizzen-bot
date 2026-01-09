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
TEST_TRAINING_CHANNEL_ID = 1459256713994571938
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

def next_week_dates():
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    return {
        0: monday,
        1: monday + datetime.timedelta(days=1),
        3: monday + datetime.timedelta(days=3)
    }

# ========= TRAINING HELPERS =========
async def delete_old_training_posts(channel):
    deleted = 0
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            if any(str(r.emoji) in ["👍", "👎"] for r in msg.reactions):
                await msg.delete()
                deleted += 1
    return deleted

async def post_training(channel):
    deleted = await delete_old_training_posts(channel)
    await send_log(f"🧹 {deleted} alte Trainingsposts gelöscht in #{channel.name}")

    for wd, date in next_week_dates().items():
        msg = await channel.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

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
        f"Hallo {member.mention}\n\n"
        "Vielen herzlichen Dank, dass du dich unserem Projekt angeschlossen hast und "
        "auf lange und erfolgreiche Zeit mit uns zusammenarbeiten willst. "
        "Dies ist dein eigener **Einzelgespräche-Channel**.\n\n"
        "Hier hast du die Möglichkeit, immer vertraulich mit uns 3 VM's unter 8 Augen "
        "zu sprechen, wenn du ein Anliegen hast. Ebenso werden wir dich hier kontaktieren, "
        "falls wir einmal ein Anliegen haben.\n\n"
        "Wichtig: Alles, was in diesem Channel geschrieben wird, bleibt auch hier. "
        "Wir bitten dich, dies zu respektieren. Selbstverständlich erwarten wir einen "
        "respektvollen und höflichen Umgangston – von deiner wie auch von unserer Seite.\n\n"
        "Liebe Grüße\n"
        "**Shinez, Flo & Birdie**\n"
        "*aka dein VM-Team* 🍕"
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

# ========= COMMANDS =========
@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    await post_training(ch)
    await ctx.send("✅ Trainingsposts erstellt")

@bot.command()
@commands.has_permissions(administrator=True)
async def testtraining(ctx):
    ch = bot.get_channel(TEST_TRAINING_CHANNEL_ID)
    await post_training(ch)
    await ctx.send("🧪 Test-Trainingsposts erstellt")

# ========= TASKS =========
@tasks.loop(minutes=1)
async def friday_post():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 4 and now.hour == 14 and now.minute == 0:
        await post_training(bot.get_channel(TRAINING_CHANNEL_ID))

@bot.event
async def on_ready():
    friday_post.start()
    await send_log("🚀 Bot gestartet")

bot.run(TOKEN)
