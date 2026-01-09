import discord
from discord.ext import commands, tasks
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

EINZELGESPRAECHE_CATEGORY_ID = 1330628490621354108

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

def safe_name(name: str):
    name = name.lower()
    name = name.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    return name[:90]

async def get_training_messages(channel):
    msgs = {}
    async for msg in channel.history(limit=100):
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

# ========= TRAININGSPOSTS =========
async def clear_training_posts(channel):
    async for msg in channel.history(limit=100):
        if msg.author == bot.user:
            await msg.delete()

async def create_training_posts(channel):
    await clear_training_posts(channel)

    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))

    dates = {
        0: monday,
        1: monday + datetime.timedelta(days=1),
        3: monday + datetime.timedelta(days=3)
    }

    for wd, date in dates.items():
        msg = await channel.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await send_log("✅ Trainingsposts erstellt")

# ========= EINZELGESPRÄCH =========
async def find_einzel_channel(member):
    cat = member.guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)
    if not cat:
        return None

    for ch in cat.text_channels:
        if member.id in [o.id for o in ch.overwrites if isinstance(o, discord.Member)]:
            return ch
    return None

async def create_einzel_channel(member):
    guild = member.guild
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)

    if not vm_role or not cat:
        await send_log("❌ VM-Rolle oder Kategorie fehlt")
        return

    if await find_einzel_channel(member):
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True)
    }

    channel = await guild.create_text_channel(
        name=f"einzelgespräch-{safe_name(member.name)}",
        category=cat,
        overwrites=overwrites
    )

    await channel.send(
        f"Hallo {member.mention}\n\n"
        "Vielen herzlichen Dank, dass du dich unserem Projekt angeschlossen hast "
        "und auf lange und erfolgreiche Zeit mit uns zusammenarbeiten willst.\n\n"
        "Dies ist dein eigener **Einzelgespräche-Channel**. "
        "Hier kannst du jederzeit vertraulich mit uns 3 VM's unter 8 Augen sprechen.\n\n"
        "Alles was hier geschrieben wird, bleibt auch hier. "
        "Wir bitten dich, dies zu respektieren.\n\n"
        "Natürlich erwarten wir einen respektvollen und höflichen Umgang "
        "– von dir wie auch von unserer Seite.\n\n"
        "Liebe Grüße\n"
        "Shinez, Flo & Birdie 🍕"
    )

    await send_log(f"✅ Einzelgespräch erstellt für {member.name}")

async def delete_einzel_channel(member):
    ch = await find_einzel_channel(member)
    if ch:
        await ch.delete()
        await send_log(f"🗑️ Einzelgespräch gelöscht für {member.name}")

# ========= EVENTS =========
@bot.event
async def on_member_update(before, after):
    pizzen = discord.utils.get(after.guild.roles, name=ROLE_NAME)

    if pizzen not in before.roles and pizzen in after.roles:
        await create_einzel_channel(after)

    if pizzen in before.roles and pizzen not in after.roles:
        await delete_einzel_channel(after)

# ========= REMINDER =========
async def remind_members(target=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    pizzen = discord.utils.get(guild.roles, name=ROLE_NAME)

    msgs = await get_training_messages(ch)

    for member in guild.members:
        if member.bot or pizzen not in member.roles:
            continue
        if target and member.id != target.id:
            continue

        missing = []
        for wd, msg in msgs.items():
            if member.id not in await get_votes(msg):
                missing.append(TRAINING_DAYS[wd])

        if missing:
            eg = await find_einzel_channel(member)
            if eg:
                text = (
                    f"👋 Hallo {member.mention}\n\n"
                    f"Bitte stimme **hier** ab:\n"
                    f"👉 <#{TRAINING_CHANNEL_ID}>\n\n"
                )
                for d in missing:
                    text += f"• {d}\n"
                await eg.send(text)

# ========= COMMANDS =========
@bot.command()
async def remind(ctx, member: discord.Member = None):
    vm = discord.utils.get(ctx.guild.roles, name=VM_ROLE_NAME)
    if vm not in ctx.author.roles:
        await ctx.send("❌ Keine Berechtigung.")
        return

    await ctx.send("🔄 Erinnerungen werden geprüft …")
    await remind_members(member)
    await ctx.send("🔔 Erinnerung(en) gesendet.")

@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts(ctx.channel)
    await ctx.send("✅ Trainingsposts erstellt")

@bot.command()
async def testtraining(ctx):
    ch = bot.get_channel(TEST_TRAINING_CHANNEL_ID)
    await create_training_posts(ch)
    await ctx.send("🧪 Test-Trainingsposts erstellt")

# ========= TASKS =========
@tasks.loop(minutes=1)
async def sunday_reminder():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 6 and now.hour == 12 and now.minute == 0:
        await remind_members()

# ========= ERROR HANDLING =========
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"❌ Fehler: {error}")
    await send_log(str(error))

# ========= READY =========
@bot.event
async def on_ready():
    sunday_reminder.start()
    await send_log("✅ Bot gestartet")

bot.run(TOKEN)
