import discord
from discord.ext import commands, tasks
import datetime
import os
import pytz
from flask import Flask
from threading import Thread

# ========= CONFIG =========
TOKEN = os.environ["TOKEN"]

TRAINING_CHANNEL_ID = 1434580297206202482
LOG_CHANNEL_ID = 1434579615153913946
TESTER_CATEGORY_ID = 1330612560780857344

ROLE_PIZZEN = "Pizzen"
ROLE_VM = "VM"
ROLE_TESTER = "Tester"

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

# ========= LOG =========
async def send_log(text):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"📝 {text}")

# ========= TRAINING =========
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
    async for msg in channel.history(limit=100):
        if msg.author != bot.user:
            continue
        for wd in TRAINING_DAYS:
            if f"[TRAINING:{wd}]" in msg.content:
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
    guild = ch.guild
    pizzen = discord.utils.get(guild.roles, name=ROLE_PIZZEN)

    dates = next_week_dates()

    for wd, date in dates.items():
        text = (
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            f"[TRAINING:{wd}]\n"
            "Reagiere mit 👍 oder 👎"
        )
        msg = await ch.send(text)
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await ch.send(pizzen.mention)
    await send_log("Trainingsposts erstellt")

# ========= REMINDER =========
async def remind_members(target=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    pizzen = discord.utils.get(guild.roles, name=ROLE_PIZZEN)

    msgs = await get_training_messages(ch)

    for member in guild.members:
        if target and member.id != target.id:
            continue
        if pizzen not in member.roles or member.bot:
            continue

        missing = []
        for wd, msg in msgs.items():
            voted = await get_votes(msg)
            if member.id not in voted:
                missing.append(TRAINING_DAYS[wd])

        if missing:
            text = (
                f"👋 Hallo {member.name}!\n\n"
                f"Bitte stimme für folgende Trainingstage hier ab:\n"
                f"<#{TRAINING_CHANNEL_ID}>\n\n"
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
@commands.has_role(ROLE_VM)
async def remind(ctx, member: discord.Member):
    await remind_members(member)
    await ctx.send(f"🔔 Erinnerung an {member.mention} gesendet")

async def list_missing(ctx, wd):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    guild = ch.guild
    pizzen = discord.utils.get(guild.roles, name=ROLE_PIZZEN)

    msgs = await get_training_messages(ch)
    msg = msgs.get(wd)

    if not msg:
        await ctx.send("❌ Kein Trainingspost gefunden.")
        return

    voted = await get_votes(msg)

    missing = [
        m.mention for m in guild.members
        if pizzen in m.roles and m.id not in voted and not m.bot
    ]

    if missing:
        await ctx.send(
            f"❌ Nicht abgestimmt für **{TRAINING_DAYS[wd]}**:\n" +
            ", ".join(missing)
        )
    else:
        await ctx.send(f"✅ Alle haben für {TRAINING_DAYS[wd]} abgestimmt!")

@bot.command()
async def montag(ctx):
    await list_missing(ctx, 0)

@bot.command()
async def dienstag(ctx):
    await list_missing(ctx, 1)

@bot.command()
async def donnerstag(ctx):
    await list_missing(ctx, 3)

# ========= TESTER SYSTEM =========
@bot.event
async def on_member_join(member):
    role = discord.utils.get(member.guild.roles, name=ROLE_TESTER)
    if role:
        await member.add_roles(role)

@bot.event
async def on_member_update(before, after):
    tester_role = discord.utils.get(after.guild.roles, name=ROLE_TESTER)
    category = bot.get_channel(TESTER_CATEGORY_ID)

    before_has = tester_role in before.roles
    after_has = tester_role in after.roles

    # ROLE ADDED → CREATE CHANNEL
    if not before_has and after_has:
        overwrites = {
            after.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            after: discord.PermissionOverwrite(read_messages=True),
            discord.utils.get(after.guild.roles, name=ROLE_VM):
                discord.PermissionOverwrite(read_messages=True),
        }
        await after.guild.create_text_channel(
            name=f"tester-{after.name.lower()}",
            category=category,
            overwrites=overwrites
        )

    # ROLE REMOVED → DELETE CHANNEL
    if before_has and not after_has:
        for ch in category.channels:
            if ch.name == f"tester-{after.name.lower()}":
                await ch.delete()

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
