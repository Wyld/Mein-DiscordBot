# main.py
import asyncio
import os
from typing import Dict, List, Optional
import audioop
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from dotenv import load_dotenv
import random
import wikipedia
import time
import requests
import wavelink
import re
import datetime
from collections import defaultdict
from discord import Embed
import traceback
import typing
from discord import Role, Interaction
from flask_app import keep_alive
from discord_presence import update_presence
from flask import Flask
import threading
import json
from datetime import datetime
import datetime


keep_alive()



# Lade Umgebungsvariablen aus .env-Datei
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')  # OpenWeatherMap API-Schlüssel
LAVALINK_HOST = '127.0.0.1'  # Standardmäßig auf deinem Computer
LAVALINK_PORT = 2333
LAVALINK_PASSWORD = 'youshallnotpass'

# Discord Intents konfigurieren
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.reactions = True
intents.members = True  # Berechtigung für Mitglieder aktivieren
intents.guilds = True # Um mit Gilden zu arbeiten
intents.guild_messages = True
intents.guild_reactions = True
intents.presences = True  # Aktiviert den Zugriff auf den Status
intents.voice_states = True  # Um Sprachstatus-Updates zu empfangen
intents.dm_messages = True

# Bot-Instanz erstellen
bot = commands.Bot(command_prefix='/', intents=intents
                   )


# Strukturen für Bankkonten, Lagerhäuser und Befehlsberechtigungen
bank_accounts: Dict[str, int] = {}
warehouses: Dict[str, Dict[str, int]] = {}
command_permissions: Dict[str, List[str]] = {}

@bot.event
async def on_ready():
    print(f'{bot.user.name} is ready!')
    try:
        await bot.tree.sync()
        print("Slash-Befehle erfolgreich synchronisiert.")
    except Exception as e:
        print(f"Fehler beim Synchronisieren der Slash-Befehle: {e}")


async def check_permissions(interaction: discord.Interaction, command_name: str) -> bool:
    """Überprüfen, ob der Benutzer Berechtigungen für den Befehl hat."""
    role_names = command_permissions.get(command_name, [])
    return not role_names or any(role.name in role_names for role in interaction.user.roles)

async def safe_send(interaction: discord.Interaction, message: str, ephemeral: bool = True) -> None:
    """Sende eine Nachricht sicher, um Ratenbegrenzungen zu berücksichtigen."""
    try:
        await interaction.response.send_message(message, ephemeral=ephemeral)
    except discord.HTTPException as e:
        if e.status == 429:
            print("Ratenbegrenzung erreicht. Wiederholen...")
            await asyncio.sleep(5)
            await safe_send(interaction, message, ephemeral)
        else:
            print(f"Ein Fehler ist aufgetreten: {e}")

async def safe_send(interaction: discord.Interaction, content: str, ephemeral: bool = True):
    """Sends a message safely."""
    if interaction.response.is_done():
        return await interaction.followup.send(content, ephemeral=ephemeral)
    else:
        return await interaction.response.send_message(content, ephemeral=ephemeral)

@bot.tree.command(name="set_permission", description="Set permissions for a command")
@app_commands.describe(command_name="Name of the command", role_name="Name of the role to grant permission")
async def set_permission(interaction: discord.Interaction, command_name: str, role_name: str) -> None:
    if not interaction.user.guild_permissions.administrator:
        await safe_send(interaction, "⚠️ Nur Administratoren können Berechtigungen setzen.")
        return

    command_permissions.setdefault(command_name, [])

    if role_name not in command_permissions[command_name]:
        command_permissions[command_name].append(role_name)
        await safe_send(interaction, f"✅ Berechtigung für '{command_name}' auf Rolle '{role_name}' gesetzt.")
    else:
        await safe_send(interaction, f"⚠️ Die Rolle '{role_name}' hat bereits Berechtigung für '{command_name}'.")

@set_permission.autocomplete("command_name")
async def command_name_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    command_choices = ["fullclear", "kick", "ban", "set_permission", "remove_permission", "permission_overview", "check_permission"]
    return [app_commands.Choice(name=cmd, value=cmd) for cmd in command_choices if current.lower() in cmd.lower()]

@set_permission.autocomplete("role_name")
async def role_name_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    roles = interaction.guild.roles
    return [app_commands.Choice(name=role.name, value=role.name) for role in roles if current.lower() in role.name.lower()]

@bot.tree.command(name="remove_permission", description="Remove permissions for a command")
@app_commands.describe(command_name="Name of the command", role_name="Name of the role to remove permission")
async def remove_permission(interaction: discord.Interaction, command_name: str, role_name: str) -> None:
    if not interaction.user.guild_permissions.administrator:
        await safe_send(interaction, "⚠️ Nur Administratoren können Berechtigungen entfernen.")
        return

    if command_name in command_permissions and role_name in command_permissions[command_name]:
        command_permissions[command_name].remove(role_name)
        await safe_send(interaction, f"✅ Berechtigung für '{role_name}' auf '{command_name}' entfernt.")
    else:
        await safe_send(interaction, f"⚠️ Die Rolle '{role_name}' hat keine Berechtigung für '{command_name}'.")

@remove_permission.autocomplete("command_name")
async def remove_command_name_autocomplete(interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
    command_choices = ["fullclear", "kick", "ban", "unban", "perma", "giveaway", "set_permission", "remove_permission", "permission_overview", "check_permission"]
    return [app_commands.Choice(name=cmd, value=cmd) for cmd in command_choices if current.lower() in cmd.lower()]

@remove_permission.autocomplete("role_name")
async def remove_role_name_autocomplete(interaction: discord.Interaction, command_name: str) -> List[app_commands.Choice[str]]:
    roles = interaction.guild.roles
    roles_with_permission = command_permissions.get(command_name, [])
    return [app_commands.Choice(name=role, value=role) for role in roles_with_permission if role in [r.name for r in roles]]

@bot.tree.command(name="permission_overview", description="Show role access for commands")
async def permission_overview(interaction: discord.Interaction) -> None:
    if not interaction.user.guild_permissions.administrator:
        await safe_send(interaction, "⚠️ Nur Administratoren können die Berechtigungen anzeigen.")
        return

    overview_message = "🔍 **Berechtigungen Übersicht**:\n"
    if not command_permissions:
        overview_message += "Keine Berechtigungen gesetzt."
    else:
        for command, roles in command_permissions.items():
            role_list = ", ".join(roles) if roles else "Keine"
            overview_message += f"**{command}**: {role_list}\n"

    await safe_send(interaction, overview_message, ephemeral=False)

@bot.tree.command(name="check_permission", description="Check permissions for a command")
@app_commands.describe(command_name="Name of the command to check")
async def check_permission(interaction: discord.Interaction, command_name: str) -> None:
    if await check_permissions(interaction, command_name):
        await safe_send(interaction, f"✅ Du hast Berechtigungen für den Befehl '{command_name}'.")
    else:
        await safe_send(interaction, f"⚠️ Du hast keine Berechtigungen für den Befehl '{command_name}'.")

# Funktion zum Prüfen der Benutzerberechtigungen
async def check_permissions(interaction: discord.Interaction, command_name: str) -> bool:
    role_names = command_permissions.get(command_name, [])
    return not role_names or any(role.name in role_names for role in interaction.user.roles)

# Berechtigungsprüfung
async def check_permissions(interaction: discord.Interaction, command_name: str) -> bool:
    # Diese Funktion kann später angepasst werden, um Berechtigungen tatsächlich zu prüfen
    return True

async def safe_send(interaction: discord.Interaction, message: str, ephemeral: bool = True) -> None:
    try:
        await interaction.response.send_message(message, ephemeral=ephemeral)
    except discord.HTTPException as e:
        print(f"Error sending message: {e}")

BANK_ACCOUNTS_FILE = "bank_accounts.json"

def load_bank_accounts() -> Dict[str, int]:
    """Lädt die Bankkonten aus der JSON-Datei."""
    try:
        with open(BANK_ACCOUNTS_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}  # Falls die Datei nicht existiert, zurückgeben, dass keine Konten vorhanden sind
    except json.JSONDecodeError:
        print("⚠️ Fehler beim Laden der Bankkonten. Datei ist beschädigt.")
        return {}

def save_bank_accounts() -> None:
    """Speichert die Bankkonten in der JSON-Datei."""
    with open(BANK_ACCOUNTS_FILE, "w") as file:
        json.dump(bank_accounts, file, indent=4)

# Bankkonten laden
bank_accounts = load_bank_accounts()

# Beim Erstellen eines Bankkontos speichern
@bot.tree.command(name="create_account", description="Creates a bank account with a name")
async def create_account(interaction: discord.Interaction, account_name: str) -> None:
    if not await check_permissions(interaction, "create_account"):
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, diesen Befehl auszuführen.")
        return

    if account_name in bank_accounts:
        await safe_send(interaction, "⚠️ Ein Konto mit diesem Namen existiert bereits!")
        return

    bank_accounts[account_name] = 0
    save_bank_accounts()  # Nach der Erstellung speichern
    view = BankView(account_name, interaction.user.roles)
    await interaction.response.send_message(
        f"💳 Bankkonto '{account_name}' erfolgreich erstellt! Aktueller Kontostand: {bank_accounts[account_name]}€",
        view=view
    )

# Beim Einzahlen speichern
async def on_deposit(interaction: discord.Interaction, amount: int, account_name: str) -> None:
    bank_accounts[account_name] += amount
    save_bank_accounts()  # Nach der Einzahlung speichern
    await interaction.response.send_message(
        f"💵 {amount}€ in '{account_name}' eingezahlt! Neuer Kontostand: {bank_accounts[account_name]}€", ephemeral=True
    )

# Beim Abheben speichern
async def on_withdraw(interaction: discord.Interaction, amount: int, account_name: str) -> None:
    bank_accounts[account_name] -= amount
    save_bank_accounts()  # Nach dem Abheben speichern
    await interaction.response.send_message(
        f"💵 {amount}€ von '{account_name}' abgehoben! Neuer Kontostand: {bank_accounts[account_name]}€", ephemeral=True
    )

class AmountModal(discord.ui.Modal):
    def __init__(self, action: str, account_name: str) -> None:
        super().__init__(title=action)
        self.account_name = account_name
        self.amount_input = discord.ui.TextInput(label="Betrag", placeholder="Geben Sie den Betrag ein", required=True)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            amount = int(self.amount_input.value)
            if amount <= 0:
                await interaction.response.send_message("⚠️ Bitte geben Sie einen Betrag größer als 0 ein.", ephemeral=True)
                return

            if self.title == "Einzahlen":
                await on_deposit(interaction, amount, self.account_name)
            else:
                if bank_accounts[self.account_name] < amount:
                    await interaction.response.send_message("⚠️ Nicht genügend Mittel auf dem Konto.", ephemeral=True)
                    return
                await on_withdraw(interaction, amount, self.account_name)

            await interaction.message.edit(
                content=f"💳 Kontostand von '{self.account_name}': {bank_accounts[self.account_name]}€", view=BankView(self.account_name, interaction.user.roles)
            )

        except ValueError:
            await interaction.response.send_message("⚠️ Bitte geben Sie eine gültige Menge ein (nur Zahlen).", ephemeral=True)

@bot.tree.command(name="account", description="Zeigt ein Bankkonto an und ermöglicht Einzahlungen/Auszahlungen")
async def account(interaction: discord.Interaction, account_name: str) -> None:
    if not await check_permissions(interaction, "account"):
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, diesen Befehl auszuführen.")
        return

    if account_name not in bank_accounts:
        await safe_send(interaction, "⚠️ Dieses Konto existiert nicht. Erstellen Sie es zuerst mit /create_account.")
        return

    balance = bank_accounts[account_name]
    view = BankView(account_name, interaction.user.roles)
    await interaction.response.send_message(
        f"💰 Kontostand von '{account_name}': {balance}€", view=view
    )

WAREHOUSES_FILE = "warehouses.json"

def load_warehouses() -> Dict[str, Dict[str, int]]:
    """Lädt die Lagerdaten aus der JSON-Datei."""
    try:
        with open(WAREHOUSES_FILE, "r") as file:
            data = json.load(file)
            print(f"✅ Lagerdaten erfolgreich geladen aus Datei: {data}")  # Debug-Ausgabe
            return data
    except FileNotFoundError:
        print("⚠️ Keine Lagerdaten gefunden. Erstelle neue Datei.")
        return {}  # Falls die Datei nicht existiert
    except json.JSONDecodeError:
        print("⚠️ Fehler: Lagerdaten konnten nicht geladen werden. JSON-Datei ist beschädigt.")
        return {}


def save_warehouses() -> None:
    """Speichert die Lagerdaten in einer JSON-Datei."""
    try:
        # Überprüfe den aktuellen Arbeitsordner
        print(f"Speicherort der Datei: {os.getcwd()}/{WAREHOUSES_FILE}")

        # Datei im Schreibmodus öffnen
        with open(WAREHOUSES_FILE, "w", encoding="utf-8") as file:
            json.dump(warehouses, file, indent=4)
        print(f"✅ Lagerdaten erfolgreich gespeichert: {warehouses}")  # Debug-Ausgabe
    except Exception as e:
        print(f"❌ Fehler beim Speichern der Lagerdaten: {e}")

# Initiales Laden der Lagerdaten
warehouses = load_warehouses()


def get_warehouse_content(warehouse_name: str) -> str:
    """Zeigt den Inhalt des angegebenen Lagers an."""
    warehouse = warehouses.get(warehouse_name, {})
    if not warehouse:
        return "📦 Das Lager ist leer."
    return "\n".join([f"{name}: {quantity}x" for name, quantity in warehouse.items()])

@bot.tree.command(name="warehouse", description="Zeigt den Inhalt des Lagers an.")
async def warehouse(interaction: discord.Interaction, warehouse_name: str) -> None:
    """Zeigt das Lager und die möglichen Aktionen."""
    if not await check_permissions(interaction, "warehouse"):
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, diesen Befehl auszuführen.")
        return

    content = get_warehouse_content(warehouse_name)
    view = WarehouseView(warehouse_name)
    await interaction.response.send_message(content, view=view)

class WarehouseView(discord.ui.View):
    """UI-View für die Lager-Aktionen."""
    def __init__(self, warehouse_name: str) -> None:
        super().__init__(timeout=180)
        self.warehouse_name = warehouse_name

    @discord.ui.button(label="Item hinzufügen", style=discord.ButtonStyle.green)
    async def add_item_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = ItemModal("Item hinzufügen", self.warehouse_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Item entfernen", style=discord.ButtonStyle.red)
    async def remove_item_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = ItemModal("Item entfernen", self.warehouse_name)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Lager leeren", style=discord.ButtonStyle.gray)
    async def clear_warehouse_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        warehouses[self.warehouse_name] = {}
        save_warehouses()  # Lagerdaten speichern
        await interaction.response.send_message(f"🗑️ Das Lager '{self.warehouse_name}' wurde geleert.")
        await interaction.message.edit(content="📦 Das Lager ist leer.", view=self)

class ItemModal(discord.ui.Modal):
    """Modal für das Hinzufügen oder Entfernen von Items im Lager."""
    def __init__(self, action: str, warehouse_name: str) -> None:
        super().__init__(title=action)
        self.warehouse_name = warehouse_name
        self.item_name_input = discord.ui.TextInput(label="Item Name", placeholder="Geben Sie den Item-Namen ein", required=True)
        self.quantity_input = discord.ui.TextInput(label="Menge", placeholder="Geben Sie die Menge ein", required=True)
        self.add_item(self.item_name_input)
        self.add_item(self.quantity_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Bearbeitet das Hinzufügen oder Entfernen von Items."""
        item_name = self.item_name_input.value
        try:
            quantity = int(self.quantity_input.value)
            if quantity <= 0:
                await interaction.response.send_message("⚠️ Bitte geben Sie eine Menge größer als 0 ein.", ephemeral=True)
                return

            if self.title == "Item hinzufügen":
                if self.warehouse_name not in warehouses:
                    warehouses[self.warehouse_name] = {}
                warehouses[self.warehouse_name][item_name] = warehouses[self.warehouse_name].get(item_name, 0) + quantity
                save_warehouses()
                await interaction.response.send_message(
                    f"✅ {quantity}x '{item_name}' wurde dem Lager '{self.warehouse_name}' hinzugefügt.",
                    ephemeral=True
                )
            else:
                if item_name not in warehouses.get(self.warehouse_name, {}):
                    await interaction.response.send_message("⚠️ Item nicht im Lager gefunden.", ephemeral=True)
                    return
                if warehouses[self.warehouse_name][item_name] < quantity:
                    await interaction.response.send_message("⚠️ Nicht genügend Items im Lager.", ephemeral=True)
                    return
                warehouses[self.warehouse_name][item_name] -= quantity
                save_warehouses()
                await interaction.response.send_message(
                    f"✅ {quantity}x '{item_name}' wurde aus dem Lager '{self.warehouse_name}' entfernt.",
                    ephemeral=True
                )

            # Aktualisiere die Nachricht im Kanal
            content = get_warehouse_content(self.warehouse_name)
            await interaction.message.edit(content=content, view=WarehouseView(self.warehouse_name))

        except ValueError:
            await interaction.response.send_message("⚠️ Bitte geben Sie eine gültige Menge ein (nur Zahlen).", ephemeral=True)

@bot.event
async def on_ready():
    global warehouses
    warehouses = load_warehouses()  # Lade die Lagerdaten beim Start des Bots
    print("Bot ist bereit und Lagerdaten wurden geladen.")


@bot.tree.command(name="weather", description="Zeigt das aktuelle Wetter für eine Stadt an.")
@app_commands.describe(city="Die Stadt, für die Sie das Wetter sehen möchten.")
async def weather(interaction: discord.Interaction, city: str) -> None:
    """Show current weather for the specified city."""
    if not await check_permissions(interaction, "weather"):
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, diesen Befehl auszuführen.")
        return

    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        response = requests.get(url)
        data = response.json()

        if response.status_code == 200:
            weather_info = (
                f"🌤 Wetter in {data['name']}:\n"
                f"Temperatur: {data['main']['temp']}°C\n"
                f"Wetter: {data['weather'][0]['description']}\n"
                f"🌧️ Niederschlag: {data['rain']['1h'] if 'rain' in data else 0} mm\n"
            )
            await safe_send(interaction, weather_info)
        else:
            await safe_send(interaction, f"⚠️ Fehler beim Abrufen der Wetterdaten: {data.get('message', 'Unbekannter Fehler')}")

    except Exception as e:
        await safe_send(interaction, f"⚠️ Ein Fehler ist aufgetreten: {str(e)}")

@bot.tree.command(name="poll", description="Erstellt eine Umfrage.")
@app_commands.describe(question="Die Frage der Umfrage", option1="Erste Option", option2="Zweite Option")
async def poll(interaction: discord.Interaction, question: str, option1: str, option2: str) -> None:
    """Create a poll."""
    embed = discord.Embed(title=question, color=discord.Color.blue())
    embed.add_field(name=option1, value="React with 👍", inline=True)
    embed.add_field(name=option2, value="React with 👎", inline=True)
    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("👍")
    await message.add_reaction("👎")
    await safe_send(interaction, "✅ Umfrage erstellt!", ephemeral=True)

@bot.tree.command(name="reminder", description="Erstellt eine Erinnerung.")
@app_commands.describe(time="Die Zeit in Sekunden, nach der Sie erinnert werden möchten", message="Die Nachricht der Erinnerung")
async def reminder(interaction: discord.Interaction, time: int, message: str) -> None:
    """Set a reminder."""
    await interaction.response.send_message(f"⏳ Erinnerung gesetzt! Du wirst in {time} Sekunden erinnert.")
    await asyncio.sleep(time)
    await interaction.user.send(f"🕒 Erinnerung: {message}")

@bot.tree.command(name="guess", description="Spiel: Rate die Zahl!")
async def guess(interaction: discord.Interaction) -> None:
    """Play a guessing game."""
    await interaction.response.send_message("🎲 Ich habe eine Zahl zwischen 1 und 10 gewählt. Rate sie!", ephemeral=True)

    number_to_guess = random.randint(1, 10)

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        guess = await bot.wait_for('message', check=check, timeout=30.0)
        if int(guess.content) == number_to_guess:
            await interaction.followup.send("✅ Richtig geraten! Du hast gewonnen!")
        else:
            await interaction.followup.send(f"❌ Falsch! Die richtige Zahl war {number_to_guess}.")
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ Zeit abgelaufen! Du hast nicht rechtzeitig geraten.")

@bot.tree.command(name="server_stats", description="Zeigt Statistiken über den Server an.")
async def server_stats(interaction: discord.Interaction) -> None:
    """Show server statistics."""
    guild = interaction.guild
    total_members = guild.member_count
    online_members = sum(1 for member in guild.members if member.status in (discord.Status.online, discord.Status.idle, discord.Status.dnd))

    stats = (
        f"📊 Serverstatistiken für **{guild.name}**:\n"
        f"👥 Gesamtmitglieder: {total_members}\n"
        f"🟢 Online Mitglieder: {online_members}"
    )

    await safe_send(interaction, stats)

@bot.tree.command(name="clear", description="Löscht eine bestimmte Anzahl von Nachrichten im Kanal.")
@app_commands.describe(amount="Anzahl der zu löschenden Nachrichten")
async def clear(interaction: discord.Interaction, amount: int) -> None:
    """Delete a specified number of messages in the channel."""
    if not interaction.user.guild_permissions.manage_messages:
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, Nachrichten zu löschen.")
        return

    if amount < 1 or amount > 100:
        await safe_send(interaction, "⚠️ Bitte gebe eine Anzahl zwischen 1 und 100 ein.", ephemeral=True)
        return

    # Sende eine Bestätigungsmeldung
    confirmation_msg = await safe_send(interaction, f"🔄 Lösche {amount} Nachrichten...", ephemeral=False)

    # Lösche die Nachrichten im Hintergrund
    deleted = await interaction.channel.purge(limit=amount)

    # Update the confirmation message with the number of deleted messages
    await confirmation_msg.edit(content=f"✅ {len(deleted)} Nachrichten gelöscht.")

@bot.tree.command(name="fullclear", description="Löscht alle Nachrichten im Kanal.")
async def fullclear(interaction: discord.Interaction) -> None:
    """Delete all messages in the channel."""
    if not interaction.user.guild_permissions.manage_messages:
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, Nachrichten zu löschen.")
        return

    # Sende eine Bestätigungsmeldung und speichere die Nachricht
    confirmation_msg = await safe_send(interaction, "🔄 Lösche alle Nachrichten...", ephemeral=False)

    # Lösche alle Nachrichten im Hintergrund
    deleted = await interaction.channel.purge()

    # Update die Bestätigungsmeldung mit der Anzahl der gelöschten Nachrichten
    await confirmation_msg.edit(content=f"✅ {len(deleted)} Nachrichten wurden gelöscht.")


# Pfad zur JSON-Datei für das Giveaway-Log
GIVEAWAY_LOG_FILE = "giveaway_log.json"

# Funktion zum Laden des Giveaway-Logs
def load_giveaway_log() -> list:
    if os.path.exists(GIVEAWAY_LOG_FILE):
        with open(GIVEAWAY_LOG_FILE, "r") as file:
            return json.load(file)
    else:
        return []

# Funktion zum Speichern des Giveaway-Logs
def save_giveaway_log(log_data: list) -> None:
    with open(GIVEAWAY_LOG_FILE, "w") as file:
        json.dump(log_data, file, indent=4)

# Laden des bestehenden Logs beim Start
giveaway_log = load_giveaway_log()

# Funktion zum Loggen von Giveaway-Ereignissen
def log_giveaway_event(action: str, prize: str, duration: str, winner: str, participants: list) -> None:
    event = {
        "action": action,
        "prize": prize,
        "duration": duration,
        "winner": winner,
        "participants": [user.name for user in participants],
        "timestamp": discord.utils.utcnow().isoformat()
    }
    giveaway_log.append(event)
    save_giveaway_log(giveaway_log)

@bot.tree.command(name="giveaway", description="Starte ein Giveaway im aktuellen Kanal")
async def giveaway(interaction: discord.Interaction, prize: str, duration: str) -> None:
    # Überprüfen der Berechtigungen
    if not await check_permissions(interaction, "giveaway"):
        await safe_send(interaction, "⚠️ Du hast keine Berechtigung, ein Giveaway zu starten.")
        return

    """
    Startet ein Giveaway im aktuellen Kanal und zeigt die verbleibende Zeit an.

    Parameter:
    - prize: Der Preis des Giveaways
    - duration: Die Dauer des Giveaways als Zeichenkette (z. B. "1h", "30m", "2h 30m")
    """

    # Parse the duration input with regex to support complex formats like "2h 30m"
    match = re.match(r"((?P<hours>\d+)h)?\s*((?P<minutes>\d+)m)?\s*((?P<seconds>\d+)s)?", duration)
    if not match:
        await interaction.response.send_message("⚠️ Bitte gebe die Dauer in einem gültigen Format an (z. B. '1h', '30m', '2h 30m', '45s').")
        return

    # Extrahiere Stunden, Minuten und Sekunden und konvertiere in Sekunden
    duration_seconds = (
        int(match.group("hours") or 0) * 3600 +
        int(match.group("minutes") or 0) * 60 +
        int(match.group("seconds") or 0)
    )

    # Überprüfen, ob die Dauer größer als 0 ist
    if duration_seconds <= 0:
        await interaction.response.send_message("⚠️ Die Dauer muss positiv sein.")
        return

    # Sendet die initiale Nachricht, um das Giveaway zu starten
    await interaction.response.send_message(
        f"🎉 **Giveaway gestartet!** 🎉\nPreis: **{prize}**\nDauer: **{duration}**\nReagiere mit 🎉, um teilzunehmen!",
        ephemeral=False
    )

    # Holt die gesendete Nachricht, um sie für das Countdown-Update zu verwenden
    giveaway_message = await interaction.original_response()
    await giveaway_message.add_reaction("🎉")

    # Countdown-Schleife
    while duration_seconds > 0:
        hours, remainder = divmod(duration_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_left = f"{hours}h {minutes}m {seconds}s" if hours > 0 else f"{minutes}m {seconds}s"

        # Aktualisiere die Nachricht mit der verbleibenden Zeit
        await giveaway_message.edit(content=f"🎉 **Giveaway gestartet!** 🎉\nPreis: **{prize}**\nZeit verbleibend: **{time_left}**\nReagiere mit 🎉, um teilzunehmen!")

        # Warte eine Sekunde und verringere die Dauer
        await asyncio.sleep(1)
        duration_seconds -= 1

    # Hole und benachrichtige den Gewinner nach Ablauf des Countdowns
    giveaway_message = await interaction.channel.fetch_message(giveaway_message.id)

    # Benutzer abrufen und in einer Liste sammeln
    users = [user async for user in giveaway_message.reactions[0].users() if not user.bot]

    if not users:
        await interaction.followup.send("Es gab keine Teilnehmer am Giveaway.")
        return

    winner = random.choice(users)
    await interaction.followup.send(f"🎉 **Herzlichen Glückwunsch** {winner.mention}! Du hast **{prize}** gewonnen! 🎉")

    # Logge das Giveaway-Ereignis
    log_giveaway_event("giveaway_ended", prize, duration, winner.name, users)


@bot.tree.command(name="kick", description="Kicke einen Benutzer vom Server")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Kein Grund angegeben") -> None:
    if not await check_permissions(interaction, "kick"):
        await safe_send(interaction, "⚠️ Du hast keine Berechtigung, Mitglieder zu kicken.")
        return

    await member.kick(reason=reason)
    await interaction.response.send_message(f"🔨 {member.mention} wurde gekickt. Grund: {reason}")

@bot.tree.command(name="perma", description="Banne einen Benutzer dauerhaft vom Server")
async def perma_ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Kein Grund angegeben") -> None:
    # Überprüfen der Berechtigungen
    if not await check_permissions(interaction, "perma"):
        await safe_send(interaction, "⚠️ Du hast keine Berechtigung, Mitglieder dauerhaft zu bannen.")
        return

    await member.ban(reason=reason)
    await interaction.response.send_message(f"🔨 {member.mention} wurde dauerhaft gebannt. Grund: {reason}")

# Temp-Ban-Befehl
@bot.tree.command(name="ban", description="Banne einen Benutzer vom Server für eine bestimmte Dauer")
@app_commands.describe(member="Der Benutzer, der gebannt werden soll", duration="Die Dauer des Banns", reason="Der Grund für den Bann")
async def temp_ban(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Kein Grund angegeben") -> None:
    # Prüfen, ob der Benutzer Berechtigungen hat
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("⚠️ Du hast keine Berechtigung, Mitglieder zu bannen.", ephemeral=True)
        return

    # Regex für die Dauer
    match = re.match(r"((?P<days>\d+)d)?\s*((?P<hours>\d+)h)?\s*((?P<minutes>\d+)m)?", duration)
    if not match:
        await interaction.response.send_message("⚠️ Bitte gebe die Dauer in einem gültigen Format an (z. B. '1d', '2h', '30m').", ephemeral=True)
        return

    # Berechne die Dauer in Sekunden
    ban_duration_seconds = (
        int(match.group("days") or 0) * 86400 +
        int(match.group("hours") or 0) * 3600 +
        int(match.group("minutes") or 0) * 60
    )

    if ban_duration_seconds <= 0:
        await interaction.response.send_message("⚠️ Die Dauer muss positiv sein.", ephemeral=True)
        return

    # Ban
    await member.ban(reason=reason)
    await interaction.response.send_message(
        f"🔨 {member.mention} wurde für {duration} gebannt. Grund: {reason}"
    )

    # Warte und entbanne
    await asyncio.sleep(ban_duration_seconds)
    await interaction.guild.unban(member)
    await interaction.followup.send(f"🔓 {member.mention} wurde wieder entbannt.")

@bot.event
async def on_ready():
    # Synchronisiere Slash-Befehle
    await bot.tree.sync()
    print(f"Bot ist online als {bot.user}")

games = {}  # Speichert aktive Spiele in Kanälen

class TicTacToeView(View):
    def __init__(self, player1, player2, game_id, is_bot_game):
        super().__init__()
        self.players = [player1, player2]
        self.current_turn = player1
        self.board = [" "] * 9
        self.game_id = game_id
        self.message = None
        self.is_bot_game = is_bot_game  # Gibt an, ob das Spiel gegen den Bot ist

    async def button_click(self, interaction: discord.Interaction, pos: int):
        # Defere die Antwort, um die Fehlermeldung zu vermeiden
        await interaction.response.defer()

        # Überprüfen, ob der richtige Spieler am Zug ist
        if interaction.user != self.current_turn:
            await interaction.followup.send("Es ist nicht dein Zug!", ephemeral=True)
            return

        # Überprüfen, ob das Feld bereits belegt ist
        if self.board[pos] != " ":
            await interaction.followup.send("Dieses Feld ist bereits belegt!", ephemeral=True)
            return

        # Setze das Symbol für den Spieler
        symbol = "X" if self.current_turn == self.players[0] else "O"
        self.board[pos] = symbol
        self.current_turn = self.players[1] if self.current_turn == self.players[0] else self.players[0]

        await self.display_board()

        # Überprüfen, ob jemand gewonnen hat
        winner = self.check_winner()
        if winner:
            await self.message.edit(content=f"{winner.mention} hat gewonnen!", view=None)
            games.pop(self.game_id, None)
            return
        elif " " not in self.board:  # Unentschieden
            await self.message.edit(content="Unentschieden!", view=None)
            games.pop(self.game_id, None)
            return

        # Wenn der Bot spielt und es sein Zug ist
        if self.is_bot_game and self.current_turn == bot.user:
            await self.bot_move()

    async def bot_move(self):
        # Finde die erste freie Position für den Bot (einfacher Spielzug)
        for i in range(9):
            if self.board[i] == " ":
                self.board[i] = "O"  # Bot verwendet 'O' als Symbol
                break

        self.current_turn = self.players[0]  # Wechsel zum Spieler nach dem Zug
        await self.display_board()

        # Überprüfen, ob der Bot gewonnen hat
        winner = self.check_winner()
        if winner:
            await self.message.edit(content=f"{bot.user.mention} hat gewonnen!", view=None)
            games.pop(self.game_id, None)
        elif " " not in self.board:  # Unentschieden
            await self.message.edit(content="Unentschieden!", view=None)
            games.pop(self.game_id, None)

    async def display_board(self):
        board_view = "\n".join([" | ".join(self.board[i:i + 3]) for i in range(0, 9, 3)])
        await self.message.edit(content=f"```\n{board_view}\n```", view=self)

    def check_winner(self):
        winning_combinations = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
                                (0, 3, 6), (1, 4, 7), (2, 5, 8),
                                (0, 4, 8), (2, 4, 6)]
        for combo in winning_combinations:
            if self.board[combo[0]] == self.board[combo[1]] == self.board[combo[2]] != " ":
                return self.players[0] if self.board[combo[0]] == "X" else self.players[1]
        return None

@bot.tree.command(name="tic_tac_toe", description="Starte ein Tic-Tac-Toe-Spiel.")
@app_commands.describe(opponent="Wähle deinen Gegner.")
async def tic_tac_toe(interaction: discord.Interaction, opponent: discord.User):
    game_id = interaction.channel.id
    if game_id in games:
        await interaction.response.send_message("Ein Spiel läuft bereits in diesem Kanal!", ephemeral=True)
        return

    # Wenn der Gegner der Bot ist, wird is_bot_game auf True gesetzt
    players = [interaction.user, opponent]
    is_bot_game = opponent == bot.user

    if is_bot_game:
        await interaction.response.send_message(
            f"{interaction.user.mention} vs {bot.user.mention} - Das Spiel beginnt!"
        )
    else:
        if opponent == interaction.user:
            await interaction.response.send_message("Du kannst nicht gegen dich selbst spielen!", ephemeral=True)
            return
        await interaction.response.send_message(
            f"{interaction.user.mention} vs {opponent.mention} - Das Spiel beginnt!"
        )

    # Initialisiere das TicTacToe-View und speichere das Spiel
    view = TicTacToeView(*players, game_id, is_bot_game)
    games[game_id] = view  # Spiel speichern, um Mehrfachspiele zu verhindern

    # Erstelle die Buttons mit spezifischen Positionen
    for i in range(9):
        button = Button(label=str(i + 1), style=discord.ButtonStyle.secondary)
        button.callback = lambda interaction, pos=i: view.button_click(interaction, pos)
        view.add_item(button)

    # Zeige die Anfangsnachricht und das Spielbrett
    view.message = await interaction.followup.send(content="```\n1 | 2 | 3\n4 | 5 | 6\n7 | 8 | 9\n```", view=view)


@bot.tree.command(name='unban', description='Entbannt einen Benutzer vom Server.')
@app_commands.describe(user_id='Die ID des Benutzers, den du entbannen möchtest.')
async def unban(interaction: discord.Interaction, user_id: str):
    # Überprüfen, ob die Eingabe eine gültige 18-stellige ID ist
    if not user_id.isdigit() or len(user_id) not in (17, 18):
        await interaction.response.send_message("⚠️ Gib eine gültige 17- oder 18-stellige Benutzer-ID ein.", ephemeral=True)
        return

    # Berechtigungsprüfung
    if not await check_permissions(interaction, "unban"):
        await interaction.response.send_message("⚠️ Du hast keine Berechtigung, Mitglieder zu entbannen.", ephemeral=True)
        return

    try:
        # Benutzer abrufen und unbannen
        user = await bot.fetch_user(int(user_id))  # Konvertiere in int, nachdem die ID als gültig überprüft wurde
        await interaction.guild.unban(user)
        await interaction.response.send_message(f'Benutzer {user} wurde entbannt!', ephemeral=True)

    except discord.NotFound:
        await interaction.response.send_message('Benutzer nicht gefunden! Stelle sicher, dass die ID korrekt ist.', ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message('Ich kann diesen Benutzer nicht entbannen!', ephemeral=True)
    except discord.HTTPException:
        await interaction.response.send_message('Ein Fehler ist beim Entbannen des Benutzers aufgetreten.', ephemeral=True)

# Synchronisieren der Slash-Befehle
@bot.event
async def setup_hook():
    await bot.tree.sync()

@bot.tree.command(name='role', description='Weist einem Benutzer eine Rolle zu oder entfernt sie.')
@app_commands.describe(user='Der Benutzer, dem eine Rolle zugewiesen oder von dem eine Rolle entfernt werden soll.', role='Die Rolle, die zugewiesen oder entfernt werden soll.')
async def role(interaction: discord.Interaction, user: discord.User, role: discord.Role):
    if interaction.user.guild_permissions.manage_roles:  # Berechtigungen überprüfen
        if role in user.roles:
            await user.remove_roles(role)
            await interaction.response.send_message(f'Rolle {role.name} von {user} entfernt!', ephemeral=True)
        else:
            await user.add_roles(role)
            await interaction.response.send_message(f'Rolle {role.name} zu {user} hinzugefügt!', ephemeral=True)
    else:
        await interaction.response.send_message('Du hast nicht die Berechtigung, Rollen zu verwalten!', ephemeral=True)


@bot.tree.command(name='userinfo', description='Zeigt Informationen über einen Benutzer an.')
@app_commands.describe(user='Der Benutzer, über den Informationen angezeigt werden sollen.')
async def userinfo(interaction: discord.Interaction, user: discord.Member):
    # Status des Benutzers abrufen
    status = user.status

    # Aktivität des Benutzers abrufen
    activity = user.activity
    activity_status = activity.name if activity else "Keine Aktivität"

    user_info = f"""
    **Benutzername:** {user.name}
    **ID:** {user.id}
    **Erstellt am:** {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}
    **Aktueller Status:** {status}
    **Aktivität:** {activity_status}
    """

    await interaction.response.send_message(user_info, ephemeral=True)


@bot.tree.command(name='serverinfo', description='Zeigt Informationen über den Server an.')
async def serverinfo(interaction: discord.Interaction):
    server = interaction.guild
    server_info = f"""
    **Servername:** {server.name}
    **Server-ID:** {server.id}
    **Erstellt am:** {server.created_at.strftime('%Y-%m-%d %H:%M:%S')}
    **Mitglieder:** {server.member_count}
    **Ersteller:** {server.owner}  # optional: zeigt den Serverbesitzer an
    **Boost-Level:** {server.premium_tier}  # optional: zeigt den Boost-Level an
    **Emoji:** {len(server.emojis)}  # optional: zeigt die Anzahl der benutzerdefinierten Emojis an
    """
    await interaction.response.send_message(server_info, ephemeral=True)


@bot.tree.command(name='dice', description='Würfelt einen Würfel (1d6).')
async def dice(interaction: discord.Interaction):
    result = random.randint(1, 6)
    await interaction.response.send_message(f'Du hast eine {result} geworfen!', ephemeral=True)

@bot.tree.command(name='rules', description='Zeigt die Regeln des Servers an.')
async def rules(interaction: discord.Interaction):
    rules_text = """
    **Server Regeln:**
    1. Sei respektvoll zu anderen Mitgliedern.
    2. Keine Beleidigungen oder Belästigungen.
    3. Halte dich an die Themen des Servers.
    4. Spamming ist nicht erlaubt.
    5. Folge den Anweisungen der Moderatoren.
    """
    await interaction.response.send_message(rules_text, ephemeral=True)

@bot.tree.command(name='quote', description='Zitiert eine Nachricht.')
@app_commands.describe(message_id='Die ID der Nachricht, die zitiert werden soll.')
async def quote(interaction: discord.Interaction, message_id: str):
    try:
        # Konvertiere die ID in einen Integer
        message_id = int(message_id)

        # Überprüfen, ob die ID positiv ist
        if message_id < 0:
            await interaction.response.send_message('🚫 Die Nachricht-ID muss eine positive Zahl sein.', ephemeral=True)
            return

        # Überprüfen, ob der Bot die Berechtigung hat, Nachrichten zu lesen
        if not interaction.channel.permissions_for(interaction.guild.me).read_message_history:
            await interaction.response.send_message('🔒 Ich habe nicht die Berechtigung, Nachrichtenhistorie zu lesen.', ephemeral=True)
            return

        # Versuche die Nachricht anhand der ID abzurufen
        message = await interaction.channel.fetch_message(message_id)
        await interaction.response.send_message(f'"{message.content}" - {message.author.name}', ephemeral=True)
    except ValueError:
        await interaction.response.send_message('🚫 Ungültige Nachricht-ID. Bitte gib eine gültige Zahl ein.', ephemeral=True)
    except discord.NotFound:
        await interaction.response.send_message('🚫 Nachricht nicht gefunden. Bitte stelle sicher, dass die ID korrekt ist.', ephemeral=True)
    except discord.HTTPException:
        await interaction.response.send_message('⚠️ Ein Fehler ist aufgetreten, während ich die Nachricht abgerufen habe.', ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f'❌ Ein unerwarteter Fehler ist aufgetreten: {str(e)}', ephemeral=True)



# Pfad zur JSON-Datei für das Countdown-Log
COUNTDOWN_LOG_FILE = "countdown_log.json"

# Funktion zum Laden des Countdown-Logs
def load_countdown_log() -> list:
    if os.path.exists(COUNTDOWN_LOG_FILE):
        with open(COUNTDOWN_LOG_FILE, "r") as file:
            return json.load(file)
    else:
        return []

# Funktion zum Speichern des Countdown-Logs
def save_countdown_log(log_data: list) -> None:
    with open(COUNTDOWN_LOG_FILE, "w") as file:
        json.dump(log_data, file, indent=4)

# Laden des bestehenden Logs beim Start
countdown_log = load_countdown_log()

# Funktion zum Loggen von Countdown-Ereignissen
def log_countdown_event(action: str, user: str, seconds: int, start_time: str, end_time: str) -> None:
    event = {
        "action": action,
        "user": user,
        "seconds": seconds,
        "start_time": start_time,
        "end_time": end_time,
        "timestamp": datetime.utcnow().isoformat()
    }
    countdown_log.append(event)
    save_countdown_log(countdown_log)

@bot.tree.command(name='countdown', description='Setze einen Countdown-Timer.')
@app_commands.describe(seconds='Die Anzahl der Sekunden für den Countdown.')
async def countdown(interaction: discord.Interaction, seconds: int):
    if seconds <= 0:
        await interaction.response.send_message("⏰ Die Zeit muss eine positive Zahl sein!")
        return

    # Initiale Nachricht
    await interaction.response.send_message(f"⏰ Countdown gestartet für {seconds} Sekunden...")

    # Startzeit des Countdowns
    start_time = datetime.utcnow().isoformat()

    # Countdown loop mit laufendem Update
    for remaining in range(seconds, 0, -1):
        await interaction.edit_original_response(content=f"⏳ Verbleibende Zeit: {remaining} Sekunden")
        await asyncio.sleep(1)

    # Endzeit des Countdowns
    end_time = datetime.utcnow().isoformat()

    # Sendet eine neue Nachricht, sobald der Countdown endet, und pingt den Benutzer
    await interaction.followup.send(f"⏰ Der Countdown ist abgelaufen! {interaction.user.mention}")

    # Logge das Countdown-Ereignis
    log_countdown_event("countdown_ended", interaction.user.name, seconds, start_time, end_time)

# Setze die Sprache für Wikipedia auf Deutsch
wikipedia.set_lang('de')

@bot.tree.command(name='search', description='Durchsuche Wikipedia nach einem Begriff.')
@app_commands.describe(query='Der Suchbegriff.')
async def search(interaction: discord.Interaction, query: str):
    try:
        summary = wikipedia.summary(query, sentences=2)
        await interaction.response.send_message(summary)
    except wikipedia.exceptions.DisambiguationError as e:
        await interaction.response.send_message(f"Bitte präzisiere deinen Suchbegriff. Mögliche Optionen: {', '.join(e.options)}")
    except wikipedia.exceptions.PageError:
        await interaction.response.send_message("Es wurde keine Seite zu diesem Begriff gefunden.")
    except Exception as e:
        await interaction.response.send_message(f"Ein Fehler ist aufgetreten: {e}")

@bot.tree.command(name='createrole', description='Erstellt eine neue Rolle im Server.')
@app_commands.describe(role_name='Der Name der neuen Rolle.')
async def create_role(interaction: discord.Interaction, role_name: str):
    # Prüfe, ob der Benutzer die Berechtigung zum Verwalten von Rollen hat
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message(
            "Du hast keine Berechtigung, Rollen zu erstellen.", ephemeral=True
        )
        return

    # Erstelle die neue Rolle
    guild = interaction.guild
    await guild.create_role(name=role_name)
    await interaction.response.send_message(f'Die Rolle "{role_name}" wurde erstellt!')



DATA_FILE = "log_channels.json"

class Logger:
    """
    Klasse zur Verwaltung der Log-Kanäle und des Loggings.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log_channels = self.load_data()
        print(f"⚙️ Geladene Log-Kanäle: {self.log_channels}")

    @staticmethod
    def load_data(filename=DATA_FILE):
        """
        Lädt die Log-Daten aus einer JSON-Datei.
        """
        try:
            with open(filename, "r") as file:
                return json.load(file)
        except FileNotFoundError:
            print(f"⚠️ Datei {filename} nicht gefunden. Leere Datenstruktur wird verwendet.")
        except json.JSONDecodeError as e:
            print(f"❌ Fehler beim Parsen der Datei {filename}: {e}")
        return {}

    @staticmethod
    def save_data(data, filename=DATA_FILE):
        """
        Speichert die Log-Daten in einer JSON-Datei.
        """
        try:
            with open(filename, "w") as file:
                json.dump(data, file, indent=4)
            print(f"✅ Log-Daten in {filename} gespeichert.")
        except Exception as e:
            print(f"❌ Fehler beim Speichern der Daten: {e}")

    async def validate_channels(self):
        """
        Validiert die gespeicherten Log-Kanäle und entfernt ungültige Einträge.
        """
        invalid_guilds = []
        for guild_id, channel_id in self.log_channels.items():
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                print(f"⚠️ Guild {guild_id} nicht gefunden. Eintrag wird entfernt.")
                invalid_guilds.append(guild_id)
                continue

            channel = guild.get_channel(channel_id)
            if not channel:
                print(f"⚠️ Log-Kanal {channel_id} in Guild {guild_id} nicht gefunden. Eintrag wird entfernt.")
                invalid_guilds.append(guild_id)

        # Entferne ungültige Einträge
        for guild_id in invalid_guilds:
            del self.log_channels[guild_id]
        self.save_data(self.log_channels)

    async def send_embed_log(self, guild_id, title, description=None, color=0x3498db, footer=None, fields=None,
                             timestamp=True):
        """
        Sendet eine Log-Nachricht an den festgelegten Log-Kanal einer Guild.
        """
        log_channel_id = self.log_channels.get(str(guild_id))
        if log_channel_id:
            log_channel = self.bot.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(title=title, description=description, color=color)

                # Optional: Füge Felder hinzu
                if fields:
                    for field in fields:
                        embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", True))

                # Optional: Füge Footer oder Timestamp hinzu
                if footer:
                    embed.set_footer(text=footer)
                if timestamp:
                    embed.timestamp = discord.utils.utcnow()

                try:
                    await log_channel.send(embed=embed)
                    print(f"✅ Log-Nachricht an Kanal {log_channel.name} ({log_channel.id}) gesendet.")
                except discord.Forbidden:
                    print(f"⚠️ Bot hat keine Berechtigung, in Kanal {log_channel.name} zu schreiben.")
                except Exception as e:
                    print(f"⚠️ Fehler beim Senden der Log-Nachricht: {e}")
            else:
                print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        else:
            print(f"⚠️ Kein Log-Kanal für Guild-ID {guild_id} gesetzt.")


logger = Logger(bot)

@bot.event
async def on_ready():
    print("✅ Bot ist bereit!")
    await logger.validate_channels()
    print(f"⚙️ Validierte Log-Kanäle: {logger.log_channels}")

@bot.tree.command(name="set_log_channel", description="Setzt den Kanal für alle Log-Nachrichten.")
@app_commands.describe(channel="Der Kanal, in dem Logs gespeichert werden.")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """
    Setzt den Log-Kanal für einen Server und speichert die Änderung in der JSON-Datei.
    """
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Nur Administratoren können das tun.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)
    logger.log_channels[guild_id] = channel.id
    logger.save_data(logger.log_channels)

    print(f"✅ Log-Kanal für Guild {guild_id} gesetzt auf Kanal-ID {channel.id}")
    await interaction.response.send_message(f"✅ Log-Kanal erfolgreich auf {channel.mention} gesetzt!", ephemeral=True)


@bot.event
async def on_message_delete(message: discord.Message):
    guild_id = message.guild.id
    fields = [
        {"name": "Kanal", "value": message.channel.mention, "inline": True},
        {"name": "Inhalt", "value": message.content or "*Kein Inhalt*", "inline": False}
    ]
    await logger.send_embed_log(
        guild_id,
        title="🗑️ Nachricht gelöscht",
        description=f"{message.author.mention}",
        fields=fields,
        footer="Nachricht gelöscht"
    )


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """
    Event: Nachricht bearbeitet.
    """
    print(f"Event ausgelöst: Nachricht bearbeitet von {after.author} in {after.channel.name}.")
    guild_id = after.guild.id

    # Prüfen, ob Inhalt tatsächlich verändert wurde
    if before.content != after.content:
        description = (
            f"**Autor:** {after.author.mention}\n"
            f"**Kanal:** {after.channel.mention}\n"
            f"**Vorher:** {before.content}\n"
            f"**Nachher:** {after.content}"
        )

        await logger.send_embed_log(
            guild_id,
            title="✏️ Nachricht bearbeitet",
            description=description
        )


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    """
    Event: Mitglied gebannt.
    """
    print(f"Event ausgelöst: Mitglied gebannt ({user}).")
    guild_id = guild.id
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
        if entry.target.id == user.id:
            description = (
                f"**Mitglied:** {user.mention} ({user.id})\n"
                f"🔧 **Durchgeführt von:** {entry.user.mention}\n"
                f"📄 **Grund:** {entry.reason or 'Kein Grund angegeben'}"
            )
            await logger.send_embed_log(
                guild_id,
                title="🔨 Mitglied gebannt",
                description=description
            )
            break


@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    """
    Event: Mitglied entbannt.
    """
    print(f"Event ausgelöst: Mitglied entbannt ({user}).")
    guild_id = guild.id
    async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
        if entry.target.id == user.id:
            description = (
                f"**Mitglied:** {user.mention} ({user.id})\n"
                f"🔧 **Durchgeführt von:** {entry.user.mention}"
            )
            await logger.send_embed_log(
                guild_id,
                title="🔓 Mitglied entbannt",
                description=description
            )
            break


@bot.event
async def on_member_join(member: discord.Member):
    """
    Event: Ein Mitglied tritt dem Server bei.
    Protokolliert die verwendete Einladung.
    """
    guild = member.guild
    guild_id = guild.id

    # Speichere aktuelle Einladungen vor dem Join
    if not hasattr(bot, 'invites'):
        bot.invites = {}

    before_invites = bot.invites.get(guild.id, [])
    after_invites = await guild.invites()

    # Vergleiche Einladungen, um die genutzte zu finden
    used_invite = None
    for invite in after_invites:
        for before_invite in before_invites:
            if invite.code == before_invite.code and invite.uses > before_invite.uses:
                used_invite = invite
                break

    bot.invites[guild.id] = after_invites  # Update die gespeicherten Einladungen

    # Loggen, wenn eine Einladung gefunden wurde
    if used_invite:
        description = (
            f"**Mitglied:** {member.mention} ({member.id})\n"
            f"**Einladungscode:** {used_invite.code}\n"
            f"**Erstellt von:** {used_invite.inviter.mention} ({used_invite.inviter.id})\n"
            f"**Verwendungen:** {used_invite.uses}"
        )
        await logger.send_embed_log(
            guild_id,
            title="📥 Neues Mitglied über Einladung beigetreten",
            description=description
        )
    else:
        # Falls keine Einladung gefunden wurde
        await logger.send_embed_log(
            guild_id,
            title="📥 Neues Mitglied beigetreten",
            description=f"**Mitglied:** {member.mention} ({member.id})\nEinladung konnte nicht ermittelt werden."
        )


@bot.event
async def on_member_remove(member: discord.Member):
    """
    Event: Mitglied hat den Server verlassen oder wurde gekickt.
    Prüft, ob der Benutzer gekickt wurde, indem die Audit-Logs analysiert werden.
    """
    print(f"Event ausgelöst: Mitglied entfernt ({member}).")
    guild_id = member.guild.id

    # Audit-Logs analysieren, um festzustellen, ob der Benutzer gekickt wurde
    async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
        if entry.target.id == member.id:
            # Benutzer wurde gekickt
            description = (
                f"**Mitglied:** {member.mention} ({member.id})\n"
                f"🔧 **Durchgeführt von:** {entry.user.mention}\n"
                f"📄 **Grund:** {entry.reason or 'Kein Grund angegeben'}"
            )
            await logger.send_embed_log(
                guild_id,
                title="👢 Mitglied gekickt",
                description=description
            )
            return  # Log für Kick abgeschlossen, Event hier beenden

    # Wenn kein Kick in den Audit-Logs gefunden wurde, hat das Mitglied freiwillig verlassen
    description = f"**Mitglied:** {member.mention} ({member.id})"
    await logger.send_embed_log(
        guild_id,
        title="👋 Mitglied verlassen",
        description=description
    )


# Voice Channel
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    Event: Änderungen im Sprachkanal eines Mitglieds, einschließlich Mute/Deafen durch andere und eigene Aktionen.
    """
    changes = []
    guild_id = member.guild.id

    # Sprachkanal Betreten
    if before.channel is None and after.channel is not None:
        changes.append(f"🔊 **Beigetreten:** {after.channel.mention}")

    # Sprachkanal Verlassen
    if before.channel is not None and after.channel is None:
        changes.append(f"🔇 **Verlassen:** {before.channel.mention}")

    # Sprachkanal Wechsel
    if before.channel and after.channel and before.channel != after.channel:
        changes.append(f"🔄 **Gewechselt:** {before.channel.mention} → {after.channel.mention}")

    # Bildschirmübertragung (self_video)
    if before.self_video != after.self_video:
        if after.self_video:
            changes.append(f"📹 **Bildschirmübertragung gestartet in:** {after.channel.mention}")
        else:
            changes.append(f"📹 **Bildschirmübertragung beendet in:** {after.channel.mention}")

    # Streaming (self_stream)
    if before.self_stream != after.self_stream:
        if after.self_stream:
            changes.append(f"🎥 **Streaming gestartet in:** {after.channel.mention}")
        else:
            changes.append(f"🎥 **Streaming beendet in:** {after.channel.mention}")

    # Selbst-Stummschalten (self_mute)
    if before.self_mute != after.self_mute:
        if after.self_mute:
            changes.append(f"🔇 **Selbst stummgeschaltet in:** {after.channel.mention}")
        else:
            changes.append(f"🔊 **Selbst entstummt in:** {after.channel.mention}")

    # Selbst-Deafen (self_deaf)
    if before.self_deaf != after.self_deaf:
        if after.self_deaf:
            changes.append(f"🔇 **Selbst deafened in:** {after.channel.mention}")
        else:
            changes.append(f"🔊 **Selbst undeafened in:** {after.channel.mention}")

    # Mute durch Moderatoren/Administratoren
    if before.mute != after.mute:
        if after.mute:
            changes.append(f"🔇 **Stummgeschaltet durch einen Moderator oder Bot in:** {after.channel.mention}")
        else:
            changes.append(f"🔊 **Entstummt durch einen Moderator oder Bot in:** {after.channel.mention}")

    # Deafen durch Moderatoren/Administratoren
    if before.deaf != after.deaf:
        if after.deaf:
            changes.append(f"🔇 **Deafened durch einen Moderator oder Bot in:** {after.channel.mention}")
        else:
            changes.append(f"🔊 **Undeafened durch einen Moderator oder Bot in:** {after.channel.mention}")

    # Protokollieren der Änderungen
    if changes:
        description = f"{member.mention}\n" + "\n".join(changes)
        await logger.send_embed_log(guild_id, "🔊 Sprachkanal-Update", description)


@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    """
    Event: Kanal wird erstellt.
    Protokolliert das Erstellen eines Kanals und sendet eine Nachricht in den Log-Kanal.
    """
    guild_id = channel.guild.id

    try:
        # Hole den Audit-Log-Eintrag für das Erstellen von Kanälen
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
            if entry.target.id == channel.id:
                await logger.send_embed_log(
                    guild_id,
                    title="📂 Kanal erstellt",
                    description=f"**Kanal:** {channel.name} ({channel.type})\n"
                                f"🔧 **Erstellt von:** {entry.user.mention}\n"
                                f"📅 **Zeitpunkt:** <t:{int(entry.created_at.timestamp())}:f>"
                )
                print(f"✅ Kanal-Erstellung geloggt: {channel.name} erstellt von {entry.user}")
                break
        else:
            # Falls kein passender Audit-Log-Eintrag gefunden wurde
            await logger.send_embed_log(
                guild_id,
                title="📂 Kanal erstellt",
                description=f"**Kanal:** {channel.name} ({channel.type})\n"
                            "⚠️ **Ersteller konnte nicht ermittelt werden.**"
            )
            print(f"⚠️ Kein Audit-Log-Eintrag für den Kanal {channel.name} gefunden.")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Kanal-Erstellungs-Logs: {e}")
        await logger.send_embed_log(
            guild_id,
            title="⚠️ Fehler bei Kanalerstellung",
            description=f"Es trat ein Fehler bei der Protokollierung der Kanalerstellung von {channel.name} auf."
        )


@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    """
    Event: Kanal wird gelöscht.
    """
    guild_id = channel.guild.id
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
        executor = entry.user
        await logger.send_embed_log(
            guild_id,
            title="❌ Kanal gelöscht",
            description=f"**Name:** {channel.name}\n"
                        f"**Typ:** {channel.type}\n"
                        f"🔧 **Gelöscht von:** {executor.mention}"
        )
        break


@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    """
    Event: Änderungen an einem Kanal in der Guild.
    Wird ausgelöst, wenn sich ein Kanal aktualisiert (z. B. Name, Berechtigungen, Position, Kategorie).
    """
    guild_id = after.guild.id
    changes = []

    # Überprüfen, ob der Kanalname geändert wurde
    if before.name != after.name:
        changes.append(f"**Name:** {before.name} → {after.name}")

    # Überprüfen, ob die Kanalposition geändert wurde
    if before.position != after.position:
        changes.append(f"**Position:** {before.position} → {after.position}")

    # Überprüfen, ob der Kanal die Kategorie gewechselt hat
    if before.category != after.category:
        before_category = before.category.name if before.category else "Keine"
        after_category = after.category.name if after.category else "Keine"
        changes.append(f"**Kategorie:** {before_category} → {after_category}")

    # Überprüfen, ob der Kanaltyp geändert wurde
    if before.type != after.type:
        changes.append(f"**Kanaltyp:** {before.type} → {after.type}")

    # Überprüfen, ob Berechtigungen geändert wurden
    if before.overwrites != after.overwrites:  # Berechtigungen haben sich geändert
        channel_name = after.name
        changes.append(f"🔧 **Berechtigungsänderungen im Kanal:** {channel_name}")

        perm_changes = []

        # Prüfe jede Rolle/Benutzer auf Änderungen
        for target, perms_before in before.overwrites.items():
            perms_after = after.overwrites.get(target)
            if perms_before != perms_after:
                diff = compare_overwrites(perms_before, perms_after)
                perm_changes.append(f"**{target}**:\n{diff}")

        # Hinzufügen neuer Berechtigungen
        for target, perms_after in after.overwrites.items():
            if target not in before.overwrites:
                diff = compare_overwrites(None, perms_after)
                perm_changes.append(f"**{target}** (neu hinzugefügt):\n{diff}")

        # Nur Berechtigungsänderungen hinzufügen, wenn vorhanden
        if perm_changes:
            changes.append("\n\n".join(perm_changes))

    # Protokoll nur senden, wenn Änderungen vorliegen
    if changes:
        async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
            executor = entry.user
            description = "\n".join(changes)
            await logger.send_embed_log(
                guild_id,
                title="✏️ Kanal bearbeitet",
                description=f"{description}\n🔧 **Bearbeitet von:** {executor.mention}"
            )
            print(f"✅ Änderungen am Kanal {after.name} protokolliert.")
            break


def compare_overwrites(before: discord.PermissionOverwrite, after: discord.PermissionOverwrite) -> str:
    """
    Vergleichsfunktion für Kanalberechtigungen.
    Gibt die Änderungen in den Berechtigungen als Text zurück.
    """
    diff = []
    perms = [
        "view_channel", "send_messages", "read_messages", "connect", "speak",
        "manage_channels", "manage_permissions", "manage_messages", "priority_speaker",
        "stream", "add_reactions", "attach_files", "embed_links", "mention_everyone"
    ]

    before_dict = before.pair() if before else (None, None)
    after_dict = after.pair() if after else (None, None)

    for perm in perms:
        before_value = getattr(before_dict[0], perm, None) or getattr(before_dict[1], perm, None)
        after_value = getattr(after_dict[0], perm, None) or getattr(after_dict[1], perm, None)

        if before_value != after_value:
            diff.append(f"🔸 {perm.replace('_', ' ').title()}: {before_value} → {after_value}")

    return "\n".join(diff) if diff else "Keine Änderungen."


def compare_overwrites(before: discord.PermissionOverwrite, after: discord.PermissionOverwrite) -> str:
    """
    Vergleicht zwei PermissionOverwrite-Objekte und gibt eine lesbare Liste der Änderungen zurück.
    """
    changes = []

    # Falls vorher keine Berechtigungen existieren
    if before is None:
        before_perms = {}
    else:
        before_perms = {perm: value for perm, value in before}

    # Falls nachher keine Berechtigungen existieren
    if after is None:
        after_perms = {}
    else:
        after_perms = {perm: value for perm, value in after}

    # Vergleiche Berechtigungen
    all_keys = set(before_perms.keys()).union(after_perms.keys())
    for perm in all_keys:
        before_value = before_perms.get(perm, None)
        after_value = after_perms.get(perm, None)
        if before_value != after_value:
            changes.append(f"- `{perm}`: {before_value} → {after_value}")

    return "\n".join(changes)


@bot.event
async def on_guild_emojis_update(guild: discord.Guild, before: list, after: list):
    """
    Event: Emojis wurden hinzugefügt, entfernt oder bearbeitet.
    """
    guild_id = guild.id
    added_emojis = [emoji for emoji in after if emoji not in before]
    removed_emojis = [emoji for emoji in before if emoji not in after]
    changes = []

    # Hinzugefügte Emojis
    for emoji in added_emojis:
        changes.append(f"➕ **Emoji hinzugefügt:** {emoji} (`:{emoji.name}:`)")

    # Entfernte Emojis
    for emoji in removed_emojis:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.emoji_delete):
            if entry.target == emoji:
                executor = entry.user
                changes.append(f"❌ **Emoji entfernt:** `{emoji.name}` (von {executor.mention})")
                break
        else:
            changes.append(f"❌ **Emoji entfernt:** `{emoji.name}` (Executor unbekannt)")

    # Geänderte Emojis (Name oder Bild geändert)
    for emoji in before:
        for updated_emoji in after:
            if emoji.id == updated_emoji.id and (emoji.name != updated_emoji.name or emoji.url != updated_emoji.url):
                changes.append(f"🛠️ **Emoji geändert:** `{emoji.name}` → `{updated_emoji.name}`")

    # Protokollieren, wenn Änderungen vorhanden sind
    if changes:
        description = "\n".join(changes)
        await logger.send_embed_log(
            guild_id,
            title="😃 Emoji-Änderungen",
            description=description
        )
        print(f"✅ Emoji-Änderungen in {guild.name} protokolliert.")


@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    """
    Event: Reaktion hinzugefügt.
    """
    guild_id = reaction.message.guild.id
    await logger.send_embed_log(
        guild_id,
        title="➕ Reaktion hinzugefügt",
        description=f"{user.mention} hat mit {reaction.emoji} auf eine Nachricht reagiert."
    )


@bot.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    """
    Event: Ein Benutzer entfernt eine Reaktion von einer Nachricht.
    """
    guild_id = reaction.message.guild.id

    # Nachricht und Kanalinformationen
    channel = reaction.message.channel
    message_url = f"https://discord.com/channels/{guild_id}/{channel.id}/{reaction.message.id}"

    # Beschreibung für die Log-Nachricht
    description = (
        f"**Benutzer:** {user.mention}\n"
        f"**Emoji:** {reaction.emoji}\n"
        f"**Nachricht:** [Hier klicken]({message_url}) im Kanal {channel.mention}\n"
        f"**Nachrichteninhalt:** {reaction.message.content or '*Kein Textinhalt*'}"
    )

    # Senden der Log-Nachricht
    await logger.send_embed_log(
        guild_id,
        title="➖ Reaktion entfernt",
        description=description
    )
    print(f"✅ Reaktion {reaction.emoji} von {user} entfernt und protokolliert.")


@bot.event
async def on_guild_role_create(role: discord.Role):
    """
    Event: Eine neue Rolle wird auf dem Server erstellt.
    Protokolliert das Erstellen von Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    guild_id = role.guild.id
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
        executor = entry.user
        await logger.send_embed_log(
            guild_id,
            title="🎭 Rolle erstellt",
            description=f"**Rolle:** {role.name}\n🔧 **Erstellt von:** {executor.mention}"
        )
        break


@bot.event
async def on_guild_role_delete(role: discord.Role):
    """
    Event: Eine Rolle wird auf dem Server gelöscht.
    Protokolliert das Löschen von Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    guild_id = role.guild.id
    async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
        executor = entry.user
        await logger.send_embed_log(
            guild_id,
            title="❌ Rolle gelöscht",
            description=f"**Rolle:** {role.name}\n🔧 **Gelöscht von:** {executor.mention}"
        )
        break


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    """
    Event: Änderungen an einer Rolle (z.B. Name, Berechtigungen, Farbe).
    Protokolliert die Änderungen und sendet eine Log-Nachricht.
    """
    guild_id = after.guild.id
    changes = []

    # Prüfen, ob der Rollenname geändert wurde
    if before.name != after.name:
        changes.append(f"**Name:** {before.name} → {after.name}")

    # Prüfen, ob Berechtigungen geändert wurden
    if before.permissions != after.permissions:
        changes.append("**Berechtigungen geändert**")

    # Prüfen, ob die Farbe geändert wurde
    if before.color != after.color:
        changes.append(f"**Farbe:** {before.color} → {after.color}")

    if changes:
        # Hole den letzten Audit-Log-Eintrag für Rollenänderungen
        async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
            executor = entry.user
            description = "\n".join(changes)
            await logger.send_embed_log(
                guild_id,
                title="✏️ Rolle bearbeitet",
                description=f"{description}\n🔧 **Bearbeitet von:** {executor.mention}"
            )
            print(f"✅ Änderungen an der Rolle {after.name} protokolliert.")
            break

@bot.event
async def on_guild_member_update(before: discord.Member, after: discord.Member):
    """
    Event: Nitro Boost des Mitglieds (Serverboost).
    """
    guild_id = after.guild.id

    # Prüfen, ob der Benutzer den Serverboost aktiviert hat
    if before.premium_since is None and after.premium_since is not None:
        description = f"{after.mention} hat den Server geboostet! 🎉"
        await logger.send_embed_log(guild_id, "🚀 Serverboost aktiviert", description)

    # Prüfen, ob der Benutzer den Serverboost zurückgenommen hat
    elif before.premium_since is not None and after.premium_since is None:
        description = f"{after.mention} hat den Serverboost zurückgenommen. 😢"
        await logger.send_embed_log(guild_id, "🚀 Serverboost zurückgenommen", description)


@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """
    Event: Änderungen am Servernamen oder an Servereinstellungen.
    """
    guild_id = after.id
    changes = []

    # Server-Icon geändert
    if before.icon != after.icon:
        changes.append(f"**Neues Icon:** [Hier klicken]({after.icon.url})")

    # Server-Region geändert
    if before.region != after.region:
        changes.append(f"**Neue Region:** {after.region}")

    # AFK-Channel geändert
    if before.afk_channel != after.afk_channel:
        if after.afk_channel:
            changes.append(f"**AFK-Channel:** {after.afk_channel.mention}")
        else:
            changes.append(f"**AFK-Channel entfernt**")

    # Servername geändert
    if before.name != after.name:
        changes.append(f"**Name:** {before.name} → {after.name}")

    if changes:
        # Hole Audit-Log-Eintrag
        async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
            executor = entry.user
            description = "\n".join(changes)
            await logger.send_embed_log(guild_id, "⚙️ Server aktualisiert", f"{description}\n🔧 Bearbeitet von: {executor.mention}")
            break

# Zusätzliche
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """
    Protokolliert Änderungen eines Mitglieds:
    - Timeout gesetzt/entfernt
    - Rollen hinzugefügt/entfernt
    - Nickname, Aktivitäten, Avatar
    """
    guild_id = after.guild.id
    changes = []

    # Timeout-Änderungen
    if before.timed_out_until != after.timed_out_until:
        if after.timed_out_until:  # Timeout gesetzt
            changes.append(
                f"⏱️ **Timeout gesetzt:** Bis <t:{int(after.timed_out_until.timestamp())}:F>"
            )
        else:  # Timeout entfernt
            changes.append("⏱️ **Timeout entfernt**")

    # Rollenänderungen
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    try:
        # Rollen hinzugefügt
        for role in added_roles:
            async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                if entry.target == after and role in entry.after.roles:
                    executor = entry.user
                    changes.append(f"➕ **Rolle hinzugefügt:** {role.mention} (von {executor.mention})")
                    break

        # Rollen entfernt
        for role in removed_roles:
            async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                if entry.target == after and role in entry.before.roles:
                    executor = entry.user
                    changes.append(f"➖ **Rolle entfernt:** {role.mention} (von {executor.mention})")
                    break

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten der Rollenänderungen für {after}: {e}")
        changes.append("⚠️ Fehler bei der Protokollierung von Rollenänderungen")

    # Nickname-Änderungen
    if before.nick != after.nick:
        changes.append(f"📝 **Nickname geändert:** {before.nick or 'Keiner'} → {after.nick or 'Keiner'}")

    # Avatar-Änderungen
    if before.avatar != after.avatar:
        changes.append("🖼️ **Avatar geändert**")

    # Aktivitätsänderungen
    if before.activities != after.activities:
        added_activities = [str(a.name) for a in after.activities if a not in before.activities]
        removed_activities = [str(a.name) for a in before.activities if a not in after.activities]

        if added_activities:
            changes.append(f"➕ **Neue Aktivitäten:** {', '.join(added_activities)}")
        if removed_activities:
            changes.append(f"➖ **Beendete Aktivitäten:** {', '.join(removed_activities)}")

    # Log-Nachricht senden, wenn Änderungen vorhanden
    if changes:
        description = "\n".join(changes)
        await logger.send_embed_log(
            guild_id,
            title=f"🔄 Änderungen an {after}",
            description=f"{after.mention}\n{description}"
        )



@bot.event
async def on_invite_create(invite: discord.Invite):
    """
    Protokolliert die Erstellung eines Einladungslinks.
    """
    description = (
        f"🔗 **Einladender:** {invite.inviter.mention}\n"
        f"🌐 **Kanal:** {invite.channel.mention}\n"
        f"📆 **Ablaufdatum:** {invite.expires_at or 'Nie'}"
    )
    await logger.send_embed_log(invite.guild.id, "✉️ Einladungslink erstellt", description)


@bot.event
async def on_invite_delete(invite: discord.Invite):
    """
    Protokolliert das Löschen eines Einladungslinks.
    """
    description = f"🔗 **Kanal:** {invite.channel.mention if invite.channel else 'Unbekannt'}"
    await logger.send_embed_log(invite.guild.id, "❌ Einladungslink gelöscht", description)


@bot.event
async def on_webhooks_update(channel: discord.TextChannel):
    """
    Protokolliert Änderungen an Webhooks.
    """
    description = f"📌 **Kanal:** {channel.mention}"
    await logger.send_embed_log(channel.guild.id, "⚙️ Webhook aktualisiert", description)


@bot.event
async def on_guild_channel_pins_update(channel: discord.TextChannel, last_pin: Optional[datetime.datetime]):
    """
    Protokolliert Änderungen an gepinnten Nachrichten in einem Kanal.
    """
    description = f"📌 **Kanal:** {channel.mention}\n🕒 **Letzter Pin:** {last_pin or 'Keine Änderungen'}"
    await logger.send_embed_log(channel.guild.id, "📌 Pins geändert", description)


@bot.event
async def on_guild_stickers_update(guild: discord.Guild, before, after):
    """
    Protokolliert Änderungen an Stickern in einer Guild.
    """
    description = f"🎨 Vorher: {len(before)} Sticker\nNachher: {len(after)} Sticker"
    await logger.send_embed_log(guild.id, "🎨 Sticker-Änderungen", description)


@bot.event
async def on_member_activity_update(before: discord.Member, after: discord.Member):
    """
    Protokolliert Änderungen an Aktivitäten eines Mitglieds.
    """
    if before.activity != after.activity:
        description = (
            f"🎮 **Mitglied:** {after.mention}\n"
            f"Vorher: {before.activity or 'Keine'}\nNachher: {after.activity or 'Keine'}"
        )
        await logger.send_embed_log(after.guild.id, "🎮 Aktivität geändert", description)


@bot.event
async def on_thread_update(before: discord.Thread, after: discord.Thread):
    """
    Protokolliert Änderungen an Threads.
    """
    description = (
        f"🧵 **Thread:** {after.name}\n"
        f"📌 **Kanal:** {after.parent.mention}\n"
        f"🕒 **Letzter Beitrag:** {after.last_message_id}"
    )
    await logger.send_embed_log(after.guild.id, "🧵 Thread geändert", description)


@bot.event
async def on_interaction(interaction: discord.Interaction):
    """
    Protokolliert Interaktionen wie Slash-Commands oder Button-Klicks.
    """
    description = (
        f"⚡ **Benutzer:** {interaction.user.mention}\n"
        f"📝 **Typ:** {interaction.type.name}\n"
        f"🖱️ **Daten:** {interaction.data}"
    )
    await logger.send_embed_log(interaction.guild.id, "🔘 Interaktion ausgelöst", description)



# Event: Event Handler
@bot.event
async def on_error(event, *args, **kwargs):
    log_channel_id = log_channels.get(args[0].guild.id) if args and hasattr(args[0], 'guild') else None
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            await logger.send_embed_log(
                log_channel,
                title="⚠️ Fehler",
                description=f"Ein Fehler ist im Event **{event}** aufgetreten.\n```{traceback.format_exc()}```",
                color=0xe74c3c  # Rot für Fehler
            )
    # Fehler auch in der Konsole ausgeben
    print(f"Fehler im Event {event}: {traceback.format_exc()}")


# /lockdown Command (nur für Administratoren)
@bot.tree.command(name="lockdown")
@app_commands.describe(channel="Der Kanal, der gesperrt werden soll")
async def lockdown(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Nur Administratoren können das tun.", ephemeral=True)
        return

    await channel.set_permissions(interaction.guild.default_role, send_messages=False)
    await interaction.response.send_message(f"Der Kanal {channel.mention} wurde gesperrt.", ephemeral=True)

# /slowmode Command (nur für Administratoren)
@bot.tree.command(name="slowmode")
@app_commands.describe(seconds="Die Dauer des Slowmodes in Sekunden")
async def slowmode(interaction: discord.Interaction, seconds: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Nur Administratoren können das tun.", ephemeral=True)
        return

    await interaction.channel.edit(slowmode_delay=seconds)
    await interaction.response.send_message(f"Slowmode wurde auf {seconds} Sekunden gesetzt.", ephemeral=True)

# /unlock Command (nur für Administratoren)
@bot.tree.command(name="unlock")
@app_commands.describe(channel="Der Kanal, der entsperrt werden soll")
async def unlock(interaction: discord.Interaction, channel: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Nur Administratoren können das tun.", ephemeral=True)
        return

    await channel.set_permissions(interaction.guild.default_role, send_messages=True)
    await interaction.response.send_message(f"Der Kanal {channel.mention} wurde entsperrt.", ephemeral=True)

# /botinfo Command (für alle Benutzer)
@bot.tree.command(name="botinfo")
async def botinfo(interaction: discord.Interaction):
    bot_uptime = (discord.utils.utcnow() - bot.user.created_at).total_seconds()
    bot_info = f"Bot Name: {bot.user.name}\nVersion: 1.0.0\nErsteller: oneearjoe\nBot Uptime: {bot_uptime:.2f} Sekunden"
    await interaction.response.send_message(bot_info, ephemeral=True)

# /ping Command (für alle Benutzer)
@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)  # Reaktionszeit in ms
    await interaction.response.send_message(f"Ping: {latency} ms", ephemeral=True)

# /stats Command (für alle Benutzer)
@bot.tree.command(name="stats")
async def stats(interaction: discord.Interaction):
    guild = interaction.guild
    total_members = len(guild.members)
    bot_uptime = (discord.utils.utcnow() - bot.user.created_at).total_seconds()
    stats = f"Mitglieder: {total_members}\nBot Uptime: {bot_uptime:.2f} Sekunden"
    await interaction.response.send_message(stats, ephemeral=True)

# /hug Command (für alle Benutzer)
@bot.tree.command(name="hug")
@app_commands.describe(user="Der Benutzer, dem du eine Umarmung schicken möchtest")
async def hug(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} schickt {user.mention} eine virtuelle Umarmung! 🤗")

# /kiss Command (für alle Benutzer)
@bot.tree.command(name="kiss")
@app_commands.describe(user="Der Benutzer, dem du einen Kuss schicken möchtest")
async def kiss(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} schickt {user.mention} einen virtuellen Kuss! 💋")

# /slap Command (für alle Benutzer)
@bot.tree.command(name="slap")
@app_commands.describe(user="Der Benutzer, den du schlagen möchtest")
async def slap(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} schlägt {user.mention} virtuell! 🖐️")

# /dance Command (für alle Benutzer)
@bot.tree.command(name="dance")
async def dance(interaction: discord.Interaction):
    await interaction.response.send_message(f"{interaction.user.mention} tanzt! 💃🕺")




# Flask Setup
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot ist online!"

def run_flask():
    app.run(port=10000)

# Bot und Flask in separaten Threads ausführen
def run_discord_bot():
    bot.run(os.getenv("DISCORD_TOKEN"))

@bot.event
async def on_ready():
    print(f"Bot {bot.user} ist online.")
    await update_presence(bot)


if __name__ == '__main__':
    # Starte Flask in einem Thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Starte den Discord Bot
    run_discord_bot()
