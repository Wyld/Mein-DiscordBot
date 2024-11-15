# flask_app.py
import os
import requests
from dotenv import load_dotenv
from flask import Flask, redirect, request, session
import threading
import discord
from discord.ext import commands

# Umgebungsvariablen laden
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Konfiguration
CLIENT_ID = os.getenv('DISCORD_CLIENT_ID')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
REDIRECT_URI = 'http://localhost:5000/callback'

# Hier werden nur grundlegende Benutzer- und Bot-Scopes verwendet
SCOPE = 'identify email guilds guilds.members.read bot'

# Debugging: Überprüfung der geladenen Werte
print("CLIENT_ID:", CLIENT_ID)
print("CLIENT_SECRET:", CLIENT_SECRET)
print("DISCORD_TOKEN:", DISCORD_TOKEN)

if not DISCORD_TOKEN:
    raise ValueError("DISCORD_TOKEN ist nicht gesetzt! Überprüfe deine .env-Datei.")

@app.route('/')
def index():
    return '<a href="/login">Mit Discord einloggen</a>'

@app.route('/login')
def login():
    return redirect(
        f'https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={SCOPE}&prompt=consent'
    )

@app.route('/callback')
def callback():
    if 'error' in request.args:
        return f"Fehler: {request.args['error']}, Beschreibung: {request.args['error_description']}"

    code = request.args.get('code')

    # Token-Anfrage
    token_response = requests.post('https://discord.com/api/oauth2/token', data={
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPE,
    })

    # Drucken der gesamten Antwort für Debugging
    print(token_response.text)

    # Token-Fehlerbehandlung
    if token_response.status_code != 200:
        return f'Fehler beim Abrufen des Access Tokens: {token_response.json()}'

    access_token = token_response.json().get('access_token')
    session['token'] = access_token

    user_response = requests.get('https://discord.com/api/v10/users/@me', headers={
        'Authorization': f'Bearer {access_token}'
    })

    user_data = user_response.json()
    if 'username' in user_data:
        return f'Benutzername: {user_data["username"]}, ID: {user_data["id"]}'
    else:
        return f'Fehler beim Abrufen der Benutzerdaten: {user_data}'

def run_flask():
    app.run(port=5000)

# Discord Bot Konfiguration
intents = discord.Intents.default()
intents.presences = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def update_presence():
    activity = discord.Game(name="Spielt mit Feelings - Competitive")
    await bot.change_presence(activity=activity)

@bot.event
async def on_ready():
    print(f"Bot {bot.user} ist online.")
    await update_presence()

def run_discord_bot():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("Discord-Token ist nicht gesetzt!")
    bot.run(token)

if __name__ == '__main__':
    # Starte Flask in einem separaten Thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Starte den Discord-Bot im Hauptthread
    run_discord_bot()
