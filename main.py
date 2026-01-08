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
    print(f"[LOG] {text}")

def safe_name(name: str):
    name = name.lower()
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    return name[:90]

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

# ========= TRAININGSPOSTS =========
async def create_training_posts():
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    dates = next_week_dates()

    for wd, date in dates.items():
        msg = await ch.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await ch.send(role.mention)
    await send_log("✅ Trainingsposts erstellt")

# ========= EINZELGESPRÄCH-CHANNEL =========
async def create_einzel_channel(member):
    guild = member.guild
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)
    if not vm_role or not cat:
        await send_log("❌ VM-Rolle oder Einzelgespräche Kategorie fehlt")
        return

    channel_name = f"einzelgespraech-{safe_name(member.name)}"
    existing = discord.utils.get(cat.text_channels, name=channel_name)
    if existing:
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    }

    ch = await guild.create_text_channel(
        name=channel_name,
        category=cat,
        overwrites=overwrites,
        reason="Einzelgespräch-Channel für Pizzen-Rolle"
    )

    await ch.send(
        f"👋 Hallo {member.mention}!\n"
        "Dies ist dein persönlicher Einzelgespräch-Channel.\n"
        "Die VM-Rolle kann hier ebenfalls schreiben."
    )
    await send_log(f"✅ Einzelgespräch-Channel erstellt: {channel_name}")

async def delete_einzel_channel(member):
    guild = member.guild
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)
    if not cat:
        return

    channel_name = f"einzelgespraech-{safe_name(member.name)}"
    for ch in cat.text_channels:
        if ch.name == channel_name:
            await ch.delete(reason="Pizzen-Rolle entfernt")
            await send_log(f"🗑️ Einzelgespräch-Channel gelöscht: {channel_name}")
            break

# ========= REMINDER =========
async def remind_members(target_member=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    pizzen_role = discord.utils.get(guild.roles, name=ROLE_NAME)
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    einzel_cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)

    if not pizzen_role or not vm_role or not einzel_cat:
        await send_log("❌ Rolle oder Kategorie für Erinnerungen fehlt")
        return

    msgs = await get_training_messages(ch)

    for member in guild.members:
        if member.bot or pizzen_role not in member.roles:
            continue
        if target_member and member.id != target_member.id:
            continue

        missing = []
        for wd, msg in msgs.items():
            if member.id not in await get_votes(msg):
                missing.append(TRAINING_DAYS[wd])

        if missing:
            # Einzelgespräch-Channel finden
            channel_name = f"einzelgespraech-{safe_name(member.name)}"
            eg_ch = discord.utils.get(einzel_cat.text_channels, name=channel_name)
            if eg_ch:
                text = (
                    f"👋 Hallo {member.mention}!\n\n"
                    f"Bitte stimme **hier** für folgende Trainingstage ab:\n"
                    f"👉 <#{TRAINING_CHANNEL_ID}>\n\n"
                )
                for d in missing:
                    text += f"• {d}\n"
                text += "\nDanke! 🏋️"
                await eg_ch.send(text)

# ========= EVENTS =========
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    pizzen_role = discord.utils.get(guild.roles, name="Pizzen")
    if not pizzen_role:
        await send_log("❌ Rolle 'Pizzen' nicht gefunden")
        return

    had_role_before = pizzen_role in before.roles
    has_role_now = pizzen_role in after.roles

    if not had_role_before and has_role_now:
        # Rolle hinzugefügt → Channel erstellen
        await create_einzel_channel(after)
    elif had_role_before and not has_role_now:
        # Rolle entfernt → Channel löschen
        await delete_einzel_channel(after)

# ========= COMMANDS =========
@bot.command()
@commands.has_role(VM_ROLE_NAME)
async def remind(ctx, member: discord.Member):
    await remind_members(member)
    await ctx.send(f"🔔 Erinnerung an {member.mention} gesendet")

@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts()
    await ctx.send("✅ Trainingsposts erstellt")

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
    if not msg:
        await ctx.send(f"❌ Keine Trainingspost für {TRAINING_DAYS[weekday]} gefunden.")
        return

    voted = await get_votes(msg)
    missing = [m.mention for m in guild.members if role in m.roles and m.id not in voted and not m.bot]

    if missing:
        await ctx.send(f"❌ Nicht abgestimmt für **{TRAINING_DAYS[weekday]}**:\n" + ", ".join(missing))
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

# ========= ON_READY =========
@bot.event
async def on_ready():
    friday_post.start()
    sunday_reminder.start()
    await send_log("✅ Bot gestartet")

bot.run(TOKEN)
