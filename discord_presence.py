# discord_presence.py
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

# Bot-Konfiguration
intents = discord.Intents.default()
intents.presences = True  # Aktiviert den Presence Intent
intents.members = True  # Aktiviert den Server Members Intent, wenn nötig
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot {bot.user} ist online.")
    await update_presence()  # Hier wird der Status gesetzt

async def update_presence():
    activity = discord.Game(name="Spielt mit Feelings - Competitive")
    print("Aktualisiere Präsenz...")
    await bot.change_presence(activity=activity)
    print("Präsenz aktualisiert.")


def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("Discord-Token ist nicht gesetzt!")
    bot.run(token)
