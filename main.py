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
    name = re.sub(r"[^a-z0-9\-äöü]", "-", name)
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

# ========= TRAININGSPOSTS =========
async def delete_old_training_messages(channel):
    async for msg in channel.history(limit=200):
        if msg.author == bot.user and (
            "🏋️" in msg.content
            or "Test-Abstimmung" in msg.content
            or (len(msg.role_mentions) > 0 and len(msg.content) < 50)
        ):
            try:
                await msg.delete()
            except Exception:
                pass

async def create_training_posts(channel_id=None):
    ch = bot.get_channel(channel_id or TRAINING_CHANNEL_ID)
    if not ch:
        await send_log("❌ Trainingschannel nicht gefunden")
        return

    await delete_old_training_messages(ch)
    dates = next_week_dates()

    for wd, date in dates.items():
        msg = await ch.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    role = discord.utils.get(ch.guild.roles, name=ROLE_NAME)
    if role:
        await ch.send(role.mention)

    await send_log("✅ Trainingsposts erstellt")

# ========= TEST-ABSTIMMUNG =========
async def create_test_training(channel, day_names):
    await delete_old_training_messages(channel)
    for name in day_names:
        msg = await channel.send(
            f"🏋️ **Test-Abstimmung: {name}**\nReagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

# ========= TESTER-CHANNEL =========
async def create_tester_channel(member):
    guild = member.guild
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    cat = guild.get_channel(TESTER_CATEGORY_ID)
    if not cat or not vm_role:
        return

    existing = discord.utils.get(
        cat.text_channels,
        topic=f"user_id:{member.id}"
    )
    if existing:
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        vm_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True)
    }

    ch = await guild.create_text_channel(
        name=f"tester-{safe_name(member.name)}",
        category=cat,
        overwrites=overwrites,
        topic=f"user_id:{member.id}",
        reason="Tester-Channel erstellt"
    )

    await ch.send(
        f"👋 Willkommen {member.mention}!\n\n"
        "Dies ist dein persönlicher Tester-Channel.\n"
        "Bei Fragen oder anderen Anliegen melde dich gerne hier bei uns **VM´s** 👋"
    )

    await send_log(f"🧪 Tester-Channel erstellt für {member.name}")

async def delete_tester_channel(member):
    cat = member.guild.get_channel(TESTER_CATEGORY_ID)
    if not cat:
        return

    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            await ch.delete(reason="Tester-Rolle entfernt")
            await send_log(f"🗑️ Tester-Channel gelöscht: {ch.name}")
            break

# ========= EINZELGESPRÄCH =========
async def create_einzel_channel(member):
    guild = member.guild
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)
    cat = guild.get_channel(EINZELGESPRÄCHE_CATEGORY_ID)
    if not cat or not vm_role:
        return

    existing = discord.utils.get(
        cat.text_channels,
        topic=f"user_id:{member.id}"
    )
    if existing:
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
        reason="Einzelgespräch für Pizzen-Rolle"
    )

    await ch.send(
        f"Hallo {member.mention}\n\n"
        "Vielen herzlichen Dank, dass du dich unserem Projekt angeschlossen hast und auf lange und erfolgreiche Zeit mit uns zusammenarbeiten willst. "
        "Dies ist dein eigener \"Einzelgespräche\" Channel. Hier wirst du die Möglichkeit haben immer im vertrauten mit uns 3 VM's unter 8 Augen zu sprechen, wenn du mal ein Anliegen hast. "
        "Genauso werden wir zu dir in diesem Channel den Kontakt suchen, wenn wir mal ein Anliegen haben. Wichtig zu erwähnen ist, dass alles was in diesem Channel geschrieben wird auch in diesem Channel bleibt, also bitten wir dich dies anzunehmen und dem zu folgen. "
        "Natürlich erwarten wir auch, dass alles, was in diesem Channel geschrieben wird, immer in einem respektvollen und höflichen Ton geschrieben wird von deiner & selbstverständlich auch von unserer Seite.\n\n"
        "Liebe Grüße Shinez, Flo & Birdie aka dein VM Team 🍕"
    )

    await send_log(f"✅ Einzelgespräch-Channel erstellt: {ch.name}")

async def delete_einzel_channel(member):
    cat = member.guild.get_channel(EINZELGESPRÄCHE_CATEGORY_ID)
    if not cat:
        return

    for ch in cat.text_channels:
        if ch.topic == f"user_id:{member.id}":
            await ch.delete(reason="Pizzen-Rolle entfernt")
            await send_log(f"🗑️ Einzelgespräch-Channel gelöscht: {ch.name}")
            break

# ========= REMINDER =========
async def remind_members(target_member=None):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    if not ch:
        return

    guild = ch.guild
    pizzen_role = discord.utils.get(guild.roles, name=ROLE_NAME)
    einzel_cat = guild.get_channel(EINZELGESPRÄCHE_CATEGORY_ID)

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
            for c in einzel_cat.text_channels:
                if c.topic == f"user_id:{member.id}":
                    text = (
                        f"👋 Hallo {member.mention}!\n\n"
                        "Bitte stimme **hier** für folgende Trainingstage ab:\n"
                        f"👉 <#{TRAINING_CHANNEL_ID}>\n\n"
                    )
                    for d in missing:
                        text += f"• {d}\n"
                    text += "\nDanke! 🏋️"
                    await c.send(text)

# ========= EVENTS =========
@bot.event
async def on_member_update(before, after):
    guild = after.guild

    pizzen_role = discord.utils.get(guild.roles, name=ROLE_NAME)
    tester_role = discord.utils.get(guild.roles, name=TESTER_ROLE_NAME)

    if pizzen_role:
        if pizzen_role not in before.roles and pizzen_role in after.roles:
            await create_einzel_channel(after)
        elif pizzen_role in before.roles and pizzen_role not in after.roles:
            await delete_einzel_channel(after)

    if tester_role:
        if tester_role not in before.roles and tester_role in after.roles:
            await create_tester_channel(after)
        elif tester_role in before.roles and tester_role not in after.roles:
            await delete_tester_channel(after)

@bot.event
async def on_member_join(member):
    tester_role = discord.utils.get(member.guild.roles, name=TESTER_ROLE_NAME)
    if tester_role:
        await member.add_roles(tester_role, reason="Automatisch beim Join")
        # FIX: KEIN create_tester_channel HIER → verhindert doppelte Channels

@bot.event
async def on_member_remove(member):
    await delete_tester_channel(member)
    await delete_einzel_channel(member)

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
@commands.has_permissions(administrator=True)
async def testtraining(ctx, day: str = None):
    ch = bot.get_channel(TEST_ABSTIMMUNG_CHANNEL_ID)
    if not ch:
        await ctx.send("❌ Test-Abstimmungs-Channel nicht gefunden")
        return

    days = {
        k: v for k, v in TRAINING_DAYS.items()
        if not day or v.lower() == day.lower()
    }

    if not days:
        await ctx.send("❌ Ungültiger Tag")
        return

    await create_test_training(ch, list(days.values()))
    await ctx.send("✅ Test-Abstimmungen erstellt!")

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
        await ctx.send(
            f"❌ Keine Trainingspost für {TRAINING_DAYS[weekday]} gefunden."
        )
        return

    voted = await get_votes(msg)
    missing = [
        m.mention for m in guild.members
        if role in m.roles and m.id not in voted and not m.bot
    ]

    if missing:
        await ctx.send(
            f"❌ Nicht abgestimmt für **{TRAINING_DAYS[weekday]}**:\n"
            + ", ".join(missing)
        )
    else:
        await ctx.send(
            f"✅ Alle haben für {TRAINING_DAYS[weekday]} abgestimmt!"
        )

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
