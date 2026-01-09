import discord
from discord.ext import commands, tasks
import datetime
import pytz
import os
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

# ========= HELPER =========
async def send_log(text):
    ch = bot.get_channel(LOG_CHANNEL_ID)
    if ch:
        await ch.send(f"📝 {text}")

def safe_name(name: str):
    name = name.lower()
    return re.sub(r"[^a-z0-9]", "-", name)[:90]

# ========= TRAINING =========
def next_week_dates():
    today = datetime.date.today()
    monday = today + datetime.timedelta(days=(7 - today.weekday()))
    return {
        0: monday,
        1: monday + datetime.timedelta(days=1),
        3: monday + datetime.timedelta(days=3)
    }

async def delete_old_training_posts(channel):
    async for msg in channel.history(limit=50):
        if msg.author == bot.user and any(day in msg.content for day in TRAINING_DAYS.values()):
            await msg.delete()

async def create_training_posts(channel_id):
    ch = bot.get_channel(channel_id)
    await delete_old_training_posts(ch)

    dates = next_week_dates()
    for wd, date in dates.items():
        msg = await ch.send(
            f"🏋️ **{TRAINING_DAYS[wd]}, {date.strftime('%d.%m.%Y')}**\n"
            "Reagiere mit 👍 oder 👎"
        )
        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    await send_log("✅ Trainingsposts erstellt")

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

# ========= EINZELGESPRÄCHE =========
async def find_einzel_channel(member):
    cat = member.guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)
    if not cat:
        return None

    for ch in cat.text_channels:
        perms = ch.permissions_for(member)
        if perms.view_channel:
            return ch
    return None

async def create_einzel_channel(member):
    guild = member.guild
    cat = guild.get_channel(EINZELGESPRAECHE_CATEGORY_ID)
    vm_role = discord.utils.get(guild.roles, name=VM_ROLE_NAME)

    if not cat or not vm_role:
        await send_log("❌ Einzelgespräch: Kategorie oder VM Rolle fehlt")
        return

    if await find_einzel_channel(member):
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
        overwrites=overwrites
    )

    await ch.send(
        f"Hallo {member.mention}\n\n"
        "Vielen herzlichen Dank, dass du dich unserem Projekt angeschlossen hast und "
        "auf lange und erfolgreiche Zeit mit uns zusammenarbeiten willst. "
        "Dies ist dein eigener **Einzelgespräche-Channel**.\n\n"
        "Hier kannst du jederzeit vertraulich mit uns 3 VM's unter 8 Augen sprechen. "
        "Alles was hier geschrieben wird, bleibt auch hier.\n\n"
        "Bitte achte auf einen respektvollen und höflichen Umgangston.\n\n"
        "Liebe Grüße\n"
        "**Shinez, Flo & Birdie** 🍕"
    )

    await send_log(f"✅ Einzelgespräch erstellt für {member.name}")

async def delete_einzel_channel(member):
    ch = await find_einzel_channel(member)
    if ch:
        await ch.delete()
        await send_log(f"🗑️ Einzelgespräch gelöscht für {member.name}")

# ========= REMINDER =========
async def remind_members(target=None):
    guild = target.guild if target else bot.guilds[0]
    pizzen = discord.utils.get(guild.roles, name=ROLE_NAME)
    ch = guild.get_channel(TRAINING_CHANNEL_ID)
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
                    f"Bitte stimme hier ab 👉 <#{TRAINING_CHANNEL_ID}>\n\n"
                )
                for d in missing:
                    text += f"• {d}\n"
                await eg.send(text)

# ========= EVENTS =========
@bot.event
async def on_member_update(before, after):
    guild = after.guild
    pizzen = discord.utils.get(guild.roles, name=ROLE_NAME)

    if pizzen not in before.roles and pizzen in after.roles:
        await create_einzel_channel(after)

    if pizzen in before.roles and pizzen not in after.roles:
        await delete_einzel_channel(after)

# ========= COMMANDS =========
@bot.command()
async def remind(ctx, member: str = None):
    if VM_ROLE_NAME not in [r.name for r in ctx.author.roles]:
        await ctx.send("❌ Keine Berechtigung")
        return

    target = None
    if member:
        mid = re.sub(r"[<@!>]", "", member)
        if mid.isdigit():
            target = ctx.guild.get_member(int(mid))

    await ctx.send("🔄 Erinnerungen werden gesendet …")
    await remind_members(target)
    await ctx.send("🔔 Fertig")

@bot.command()
@commands.has_permissions(administrator=True)
async def training(ctx):
    await create_training_posts(TRAINING_CHANNEL_ID)
    await ctx.send("✅ Trainingsposts erstellt")

@bot.command()
@commands.has_permissions(administrator=True)
async def testtraining(ctx):
    await create_training_posts(TEST_TRAINING_CHANNEL_ID)
    await ctx.send("🧪 Test-Trainingsposts erstellt")

async def list_missing(ctx, wd):
    ch = bot.get_channel(TRAINING_CHANNEL_ID)
    role = discord.utils.get(ctx.guild.roles, name=ROLE_NAME)
    msgs = await get_training_messages(ch)
    msg = msgs.get(wd)

    if not msg:
        await ctx.send("❌ Keine Trainingspost gefunden")
        return

    voted = await get_votes(msg)
    missing = [m.mention for m in ctx.guild.members if role in m.roles and m.id not in voted and not m.bot]

    if missing:
        await ctx.send(f"❌ Nicht abgestimmt für **{TRAINING_DAYS[wd]}**:\n" + ", ".join(missing))
    else:
        await ctx.send(f"✅ Alle haben für {TRAINING_DAYS[wd]} abgestimmt!")

@bot.command()
async def montag(ctx): await list_missing(ctx, 0)

@bot.command()
async def dienstag(ctx): await list_missing(ctx, 1)

@bot.command()
async def donnerstag(ctx): await list_missing(ctx, 3)

# ========= TASKS =========
@tasks.loop(minutes=1)
async def friday_post():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 4 and now.hour == 14 and now.minute == 0:
        await create_training_posts(TRAINING_CHANNEL_ID)

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
