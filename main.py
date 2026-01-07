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
                # Prüfe Marker zuerst
                if f"\u200b[TRAINING:{wd}]\u200b" in msg.content:
                    msgs[wd] = msg
                # Fallback: alter Text enthält Wochentag
                elif name in msg.content:
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
        # Unsichtbarer Marker + sichtbarer Text
        text = f"\u200b[TRAINING:{wd}]\u200b 🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\nReagiere mit 👍 oder 👎"
        msg = await ch.send(text)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    # Ping-Rolle
    await ch.send(role.mention)
    await send_log("✅ Trainingsposts erstellt")

# ========= REMINDER =========
async def remind_members(target_member=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    pizzen = discord.utils.get(guild.roles, name=ROLE_NAME)

    msgs = await get_training_messages(ch)

    for member in guild.members:
        if member.bot or pizzen not in member.roles:
            continue
        if target_member and member.id != target_member.id:
            continue

        missing = []
        for wd, msg in msgs.items():
            if member.id not in await get_votes(msg):
                missing.append(TRAINING_DAYS[wd])

        if missing:
            text = (
                f"👋 Hallo {member.name}!\n\n"
                f"Bitte stimme **hier** für folgende Trainingstage ab:\n"
                f"👉 <#{TRAINING_CHANNEL_ID}>\n\n"
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
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts()
    await ctx.send("✅ Trainingsposts erstellt")

async def list_missing(ctx, weekday):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)

    msgs = await get_training_messages(ch)
    msg = msgs.get(weekday)
    if not msg:
        await ctx.send(f"⚠️ Keine Trainingsnachricht für {TRAINING_DAYS[weekday]} gefunden!")
        return

    voted = await get_votes(msg)
    missing = [
        m.mention for m in guild.members
        if role in m.roles and m.id not in voted and not m.bot
    ]

    if missing:
        await ctx.send(
            f"❌ Nicht abgestimmt für **{TRAINING_DAYS[weekday]}**:\n" + ", ".join(missing)
        )
    else:
        await ctx.send(f"✅ Alle haben für {TRAINING_DAYS[weekday]} abgestimmt!")

@bot.command()
async def montag(ctx): await list_missing(ctx, 0)
@bot.command()
async def dienstag(ctx): await list_missing(ctx, 1)
@bot.command()
async def donnerstag(ctx): await list_missing(ctx, 3)

# ========= TESTER-CHANNEL =========
@bot.event
async def on_member_join(member: discord.Member):
    guild = member.guild
    tester_role = discord.utils.get(guild.roles, name=TESTER_ROLE_NAME)
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    category = guild.get_channel(TESTER_CATEGORY_ID)

    if not tester_role or not category:
        await send_log("❌ Tester-Rolle oder Kategorie nicht gefunden")
        return

    await member.add_roles(tester_role, reason="Automatisch beim Join")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    }

    channel_name = f"tester-{safe_name(member.name)}"
    channel = await guild.create_text_channel(channel_name, category=category, overwrites=overwrites)
    await channel.send(
        f"👋 Willkommen {member.mention}!\nDies ist dein persönlicher Tester-Channel."
    )
    await send_log(f"🧪 Tester-Channel erstellt für {member.name}")

@bot.event
async def on_member_remove(member: discord.Member):
    guild = member.guild
    category = guild.get_channel(TESTER_CATEGORY_ID)
    if not category:
        return
    expected = f"tester-{safe_name(member.name)}"
    for ch in category.channels:
        if ch.name == expected:
            await ch.delete(reason="Tester hat Server verlassen")
            await send_log(f"🗑️ Tester-Channel gelöscht: {ch.name}")
            break

@bot.event
async def on_member_update(before, after):
    guild = after.guild
    tester_role = discord.utils.get(guild.roles, name=TESTER_ROLE_NAME)
    category = guild.get_channel(TESTER_CATEGORY_ID)
    if not tester_role or not category:
        return
    had = tester_role in before.roles
    has = tester_role in after.roles
    if had and not has:
        expected = f"tester-{safe_name(after.name)}"
        for ch in category.channels:
            if ch.name == expected:
                await ch.delete(reason="Tester-Rolle entfernt")
                await send_log(f"🗑️ Tester-Channel gelöscht (Rolle entfernt): {ch.name}")
                break

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

# ========= ON READY =========
@bot.event
async def on_ready():
    friday_post.start()
    sunday_reminder.start()
    await send_log("✅ Bot gestartet")

bot.run(TOKEN)
