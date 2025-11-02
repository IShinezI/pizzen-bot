import discord
from discord.ext import tasks, commands
import datetime
from threading import Thread
from flask import Flask
import os
import pytz

# === CONFIG ===
TOKEN = os.environ['TOKEN']  # Token als Secret auf Replit speichern
TRAINING_CHANNEL_ID = 1434580297206202482  # Channel für Abstimmungen
LOG_CHANNEL_ID = 1434579615153913946       # Channel für Logs
ROLE_NAME = "Pizzen"                       # Rolle, die erwähnt wird
TIMEZONE = pytz.timezone("Europe/Berlin")  # Deutsche Zeitzone

# Deutsche Wochentage
WEEKDAYS_DE = {
    0: "Montag",
    1: "Dienstag",
    2: "Mittwoch",
    3: "Donnerstag",
    4: "Freitag",
    5: "Samstag",
    6: "Sonntag"
}

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

TRAINING_DAYS = [0, 1, 3]  # Montag=0, Dienstag=1, Donnerstag=3

# === FLASK KEEP-ALIVE ===
app = Flask('')

@app.route('/')
def home():
    return "Bot läuft!"

def run():
    app.run(host='0.0.0.0', port=5000)

Thread(target=run, daemon=True).start()

# === HILFSFUNKTIONEN ===
def get_next_week_dates():
    today = datetime.date.today()
    next_monday = today + datetime.timedelta(days=(7 - today.weekday()))
    return [next_monday + datetime.timedelta(days=offset) for offset in [0, 1, 3]]

async def delete_old_training_messages(channel):
    deleted_count = 0
    async for msg in channel.history(limit=200):
        if msg.author == bot.user and "Training?" in msg.content:
            try:
                await msg.delete()
                deleted_count += 1
            except Exception as e:
                print(f"Fehler beim Löschen: {e}")
    return deleted_count

async def send_log(message: str):
    log_channel = bot.get_channel(LOG_CHANNEL_ID)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        try:
            await log_channel.send(f"📝 {message}")
        except discord.errors.Forbidden:
            print(f"[LOG-FEHLER] Keine Berechtigung zum Senden in Log-Channel: {message}")
        except Exception as e:
            print(f"[LOG-FEHLER] Fehler beim Senden der Log-Nachricht: {e} | {message}")
    else:
        print(f"[LOG-FEHLER] {message}")

async def create_training_posts():
    training_channel = bot.get_channel(TRAINING_CHANNEL_ID)
    if not isinstance(training_channel, discord.TextChannel):
        await send_log("❌ Trainingskanal nicht gefunden oder falscher Typ!")
        return

    guild = training_channel.guild
    role = discord.utils.get(guild.roles, name=ROLE_NAME)
    role_mention = role.mention if role else "@Pizzen (Rolle nicht gefunden!)"

    # Alte Posts löschen
    deleted = await delete_old_training_messages(training_channel)
    await send_log(f"🧹 {deleted} alte Trainingsnachrichten gelöscht.")

    # Neue Trainingsposts posten
    next_week_dates = get_next_week_dates()
    for date in next_week_dates:
        weekday_name = WEEKDAYS_DE[date.weekday()]
        formatted_date = date.strftime("%d.%m.%Y")

        try:
            msg = await training_channel.send(
                f"{role_mention}\n"
                f"🏋️ **{weekday_name}, {formatted_date} – Training?**\n"
                "Reagiere mit 👍 wenn du kommst, oder 👎 wenn nicht."
            )
            try:
                await msg.add_reaction("👍")
                await msg.add_reaction("👎")
            except Exception as e:
                await send_log(f"⚠️ Fehler beim Hinzufügen von Reaktionen für {formatted_date}: {e}")
        except Exception as e:
            await send_log(f"❌ Fehler beim Senden der Trainingsnachricht für {formatted_date}: {e}")

    await send_log("✅ Neue Trainingsposts für nächste Woche wurden erstellt.")

# === AUTOMATISCHER TASK ===
@tasks.loop(minutes=1)
async def send_training_messages():
    now = datetime.datetime.now(TIMEZONE)
    if now.weekday() == 4 and now.hour == 12 and now.minute == 0:  # Freitag 12 Uhr
        await create_training_posts()

@send_training_messages.before_loop
async def before_send_loop():
    await bot.wait_until_ready()
    print("⏳ Bot bereit, warte auf Freitag 12:00 Uhr...")
    await send_log("🕒 Timer gestartet – warte auf Freitag 12:00 Uhr.")

# === MANUELLER BEFEHL ===
@bot.command(name="training")
@commands.has_permissions(administrator=True)
async def manual_training(ctx):
    await send_log(f"🧑‍💻 Manuelle Erstellung durch {ctx.author} ausgelöst.")
    await create_training_posts()
    await ctx.send("✅ Trainingsposts wurden manuell erstellt!")

@manual_training.error
async def training_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Du brauchst Administratorrechte, um diesen Befehl zu verwenden.")
    else:
        await send_log(f"❌ Fehler beim manuellen Erstellen von Trainingsposts: {error}")
        await ctx.send("❌ Ein Fehler ist aufgetreten. Bitte prüfe die Logs.")

# === START ===
@bot.event
async def on_ready():
    print(f"✅ Bot online als {bot.user}")
    if not send_training_messages.is_running():
        send_training_messages.start()
    await send_log(f"Bot gestartet und bereit. Eingeloggt als **{bot.user}**.")

bot.run(TOKEN)
