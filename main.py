# main.py
import asyncio
import os
from typing import Dict, List
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
intents.presences = True  # Aktiviert den Zugriff auf den Status
intents.voice_states = True  # Um Sprachstatus-Updates zu empfangen
intents.dm_messages = True

# Bot-Instanz erstellen
bot = commands.Bot(command_prefix='/', intents=intents)

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
            print(f"✅ Lagerdaten erfolgreich geladen: {data}")
            return data
    except FileNotFoundError:
        print("⚠️ Datei nicht gefunden. Ein neues Lager wird erstellt.")
        return {}
    except json.JSONDecodeError:
        print("❌ Fehler beim Parsen der Datei. Alte Datei könnte beschädigt sein.")
        return {}

def save_warehouses() -> None:
    """Speichert die Lagerdaten in einer JSON-Datei."""
    try:
        with open(WAREHOUSES_FILE, "w") as file:
            json.dump(warehouses, file, indent=4)
        print(f"✅ Lagerdaten erfolgreich gespeichert: {warehouses}")
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

@bot.tree.command(name="warehouse", description="Zeigt den Inhalt des Lagers an")
async def warehouse(interaction: discord.Interaction, warehouse_name: str) -> None:
    """Show the warehouse and its options."""
    if not await check_permissions(interaction, "warehouse"):
        await safe_send(interaction, "⚠️ Du hast nicht die Berechtigung, diesen Befehl auszuführen.")
        return

    content = get_warehouse_content(warehouse_name)
    view = WarehouseView(warehouse_name)
    await interaction.response.send_message(content, view=view)

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



welcome_channels = {}  # Speichert die Begrüßungskanäle der Gilden

@bot.tree.command(name='set_welcome_channel', description='Setzt den Kanal für Begrüßungsnachrichten.')
@app_commands.describe(channel="Der Kanal für Begrüßungen")
async def set_welcome_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    # Überprüfen, ob der Benutzer Administratorrechte hat
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Nur Administratoren können das tun.", ephemeral=True)
        return

    # Setze den Begrüßungskanal in der Guild
    welcome_channels[interaction.guild.id] = channel.id
    await interaction.response.send_message(f'Begrüßungskanal auf {channel.mention} gesetzt!', ephemeral=True)

@bot.event
async def on_member_join(member):
    # Hole den Begrüßungskanal anhand der ID
    channel_id = welcome_channels.get(member.guild.id)
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(f'Willkommen {member.mention}! Schön, dass du da bist!')

# Funktion für das Synchronisieren der Slash-Befehle
@bot.event
async def on_ready():
    # Optional: Guild-ID einfügen, falls du den Befehl nur für eine spezifische Guild registrieren willst
    guild = discord.Object(id=DEINE_GUILD_ID)  # Ersetze DEINE_GUILD_ID mit der tatsächlichen Guild-ID
    await bot.tree.sync(guild=guild)
    print(f"Bot ist online als {bot.user}")

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

# JSON-Datei für die Speicherung der Log-Kanäle
DATA_FILE = "log_channels.json"

# Log-Channels laden und speichern
def save_data(data, filename=DATA_FILE):
    try:
        with open(filename, "w") as file:
            json.dump(data, file, indent=4)
        print(f"✅ Log-Daten in {filename} gespeichert.")
    except Exception as e:
        print(f"❌ Fehler beim Speichern der Daten: {e}")

def load_data(filename=DATA_FILE):
    try:
        with open(filename, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"⚠️ Datei {filename} nicht gefunden. Leere Datenstruktur wird verwendet.")
    except json.JSONDecodeError:
        print(f"❌ Fehler beim Parsen der Datei {filename}. Leere Datenstruktur wird verwendet.")
    return {}

log_channels = load_data()
print(f"⚙️ Geladene Log-Kanäle: {log_channels}")

@bot.event
async def on_ready():
    print("✅ Bot ist bereit!")
    print(f"⚙️ Aktuelle Log-Channels: {log_channels}")
    for guild_id, channel_id in log_channels.items():
        guild = bot.get_guild(int(guild_id))
        if guild:
            channel = guild.get_channel(channel_id)
            if channel:
                try:
                    await channel.send("✅ Testnachricht: Bot kann in diesen Kanal senden.")
                except Exception as e:
                    print(f"⚠️ Fehler beim Senden an Kanal {channel.id}: {e}")

@bot.tree.command(name="set_log_channel", description="Setzt den Kanal für alle Log-Nachrichten.")
@app_commands.describe(channel="Der Kanal, in dem Logs gespeichert werden.")
async def set_log_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    """
    Setzt den Log-Kanal für einen Server und speichert die Änderung in einer JSON-Datei.
    """
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("⚠️ Nur Administratoren können das tun.", ephemeral=True)
        return

    guild_id = str(interaction.guild.id)  # Guild-ID als Zeichenkette speichern
    log_channels[guild_id] = channel.id  # Log-Kanal für die Guild speichern
    save_data(log_channels)  # Änderungen in der JSON-Datei sichern

    print(f"✅ Log-Kanal für Guild {guild_id} gesetzt auf Kanal-ID {channel.id}")
    await interaction.response.send_message(f"✅ Log-Kanal erfolgreich auf {channel.mention} gesetzt!", ephemeral=True)


# Log-Nachricht senden
async def send_embed_log(guild_id, title, description, color=0x3498db):
    """
    Sendet eine Log-Nachricht an den festgelegten Log-Kanal einer Guild.
    """
    log_channel_id = log_channels.get(str(guild_id))  # Kanal-ID für die Guild holen
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)  # Kanalobjekt holen
        if log_channel:
            embed = discord.Embed(title=title, description=description, color=color)
            try:
                await log_channel.send(embed=embed)  # Nachricht senden
                print(f"Log-Nachricht an Kanal {log_channel.name} ({log_channel.id}) gesendet.")
            except Exception as e:
                print(f"⚠️ Fehler beim Senden der Log-Nachricht: {e}")
        else:
            print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
    else:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {guild_id} gesetzt.")

# Event: Nachricht gelöscht
@bot.event
async def on_message_delete(message: discord.Message):
    print(f"Event ausgelöst: Nachricht gelöscht von {message.author} in {message.channel.name}")
    log_channel_id = log_channels.get(str(message.guild.id))
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            try:
                await log_channel.send(
                    f"Nachricht gelöscht von {message.author.mention} in {message.channel.mention}: {message.content}"
                )
                print("✅ Log gesendet.")
            except Exception as e:
                print(f"⚠️ Fehler beim Senden der Nachricht: {e}")
        else:
            print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """
    Event: Nachricht bearbeitet.
    Protokolliert Änderungen an Nachrichten und sendet eine Log-Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Nachricht bearbeitet von {after.author} in {after.channel.name}.")

    # Verhindere Wiederholungen im Log-Kanal selbst
    log_channel_id = log_channels.get(str(after.guild.id))
    if log_channel_id == after.channel.id:
        print("Bearbeitung ignoriert: Nachricht wurde im Log-Kanal bearbeitet.")
        return

    # Prüfen, ob die Nachricht tatsächlich geändert wurde
    if before.content == after.content:
        print("Bearbeitung ignoriert: Inhalt wurde nicht verändert.")
        return

    # Holen des Log-Kanals
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Log-Nachricht erstellen und senden
            try:
                await log_channel.send(
                    f"**Nachricht bearbeitet**\n"
                    f"**Autor:** {after.author.mention}\n"
                    f"**Kanal:** {after.channel.mention}\n"
                    f"**Vorher:** {before.content}\n"
                    f"**Nachher:** {after.content}"
                )
                print(f"✅ Nachricht bearbeitet: Log in {log_channel.name} ({log_channel.id}) gesendet.")
            except Exception as e:
                print(f"⚠️ Fehler beim Senden der Log-Nachricht: {e}")
        else:
            print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
    else:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {after.guild.id} gesetzt.")


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """
    Event: Timeout gesetzt oder entfernt.
    Protokolliert Timeout-Änderungen eines Mitglieds und sendet eine Log-Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Mitglied aktualisiert ({after}).")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(after.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {after.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    # Timeout-Änderung prüfen
    if before.timed_out_until != after.timed_out_until:
        print(f"Timeout geändert für {after}. Vorher: {before.timed_out_until}, Nachher: {after.timed_out_until}")

        try:
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if after.timed_out_until:  # Timeout gesetzt
                    await log_channel.send(
                        f"⏱️ **Timeout:** {after.mention}\n"
                        f"🔧 **Durchgeführt von:** {entry.user.mention}\n"
                        f"📅 **Ende:** <t:{int(after.timed_out_until.timestamp())}:F>"
                    )
                    print(f"✅ Timeout gesetzt für {after} von {entry.user}.")
                else:  # Timeout entfernt
                    await log_channel.send(
                        f"⏱️ **Timeout entfernt:** {after.mention}\n"
                        f"🔧 **Entfernt von:** {entry.user.mention}"
                    )
                    print(f"✅ Timeout entfernt für {after} von {entry.user}.")
                break
        except Exception as e:
            print(f"⚠️ Fehler beim Verarbeiten des Timeout-Logs: {e}")
    else:
        print("Keine Änderungen am Timeout festgestellt.")


@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    """
    Event: Mitglied gebannt.
    Protokolliert Bans und sendet eine Log-Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Mitglied gebannt ({user}).")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    # Verantwortlichen für den Ban ermitteln und loggen
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id:  # Sicherstellen, dass der Ban-Eintrag zu diesem Benutzer gehört
                await log_channel.send(
                    f"🔨 **Ban:** {user.mention} ({user.id})\n"
                    f"🔧 **Durchgeführt von:** {entry.user.mention}\n"
                    f"📄 **Grund:** {entry.reason or 'Kein Grund angegeben'}"
                )
                print(f"✅ Ban geloggt: {user} wurde von {entry.user} gebannt.")
                break
        else:
            print("⚠️ Kein passender Audit-Log-Eintrag für den Ban gefunden.")
    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Ban-Logs: {e}")


@bot.event
async def on_member_kick(member: discord.Member):
    """
    Event: Mitglied gekickt.
    Protokolliert Kicks und sendet eine Log-Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Mitglied gekickt ({member}).")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(member.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {member.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    # Verantwortlichen für den Kick ermitteln und loggen
    try:
        async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target.id == member.id:  # Sicherstellen, dass der Eintrag zu diesem Mitglied gehört
                await log_channel.send(
                    f"👢 **Kick:** {member.mention} ({member.id})\n"
                    f"🔧 **Durchgeführt von:** {entry.user.mention}\n"
                    f"📄 **Grund:** {entry.reason or 'Kein Grund angegeben'}"
                )
                print(f"✅ Kick geloggt: {member} wurde von {entry.user} gekickt.")
                break
        else:
            print("⚠️ Kein passender Audit-Log-Eintrag für den Kick gefunden.")
    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Kick-Logs: {e}")

@bot.event
async def on_member_unban(guild: discord.Guild, user: discord.User):
    """
    Event: Mitglied entbannt.
    Protokolliert Unbans und sendet eine Log-Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Mitglied entbannt ({user}).")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    # Verantwortlichen für den Unban ermitteln und loggen
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.unban):
            if entry.target.id == user.id:  # Sicherstellen, dass der Audit-Log-Eintrag passt
                await log_channel.send(
                    f"🔓 **Unban:** {user.mention} ({user.id}) wurde vom Server entbannt.\n"
                    f"🔧 **Durchgeführt von:** {entry.user.mention}\n"
                    f"📅 **Zeitpunkt:** <t:{int(entry.created_at.timestamp())}:f>"
                )
                print(f"✅ Unban geloggt: {user} wurde von {entry.user} entbannt.")
                break
        else:
            # Falls kein passender Audit-Log-Eintrag gefunden wurde
            await log_channel.send(
                f"🔓 **Unban:** {user.mention} ({user.id}) wurde vom Server entbannt, "
                "aber der Verantwortliche konnte nicht ermittelt werden."
            )
            print(f"⚠️ Kein passender Audit-Log-Eintrag für den Unban von {user} gefunden.")
    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Unban-Logs: {e}")
        await log_channel.send(
            f"⚠️ **Unban:** {user.mention} ({user.id}) wurde vom Server entbannt, aber ein Fehler ist aufgetreten."
        )

# Event: Mitglieder beitreten
@bot.event
async def on_member_join(member: discord.Member):
    """
    Event: Mitglied tritt dem Server bei.
    Protokolliert neue Mitglieder und sendet eine Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Mitglied tritt bei ({member}).")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(member.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {member.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    # Nachricht über den Beitritt senden
    try:
        await log_channel.send(f"🎉 **Neues Mitglied:** {member.mention} hat den Server betreten.")
        print(f"✅ Mitgliedsbeitritt geloggt: {member} hat den Server betreten.")
    except Exception as e:
        print(f"⚠️ Fehler beim Senden der Beitrittsnachricht: {e}")
        await log_channel.send(
            f"⚠️ **Fehler:** {member.mention} hat den Server betreten, aber eine Fehlermeldung trat auf."
        )

# Event: Mitglieder den Server verlassen
@bot.event
async def on_member_remove(member: discord.Member):
    """
    Event: Mitglied verlässt den Server.
    Protokolliert das Verlassen von Mitgliedern und sendet eine Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Mitglied verlässt den Server ({member}).")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(member.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {member.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    # Nachricht über das Verlassen senden
    try:
        await log_channel.send(f"👋 **Mitglied verlassen:** {member.mention} hat den Server verlassen.")
        print(f"✅ Verlassen des Mitglieds geloggt: {member} hat den Server verlassen.")
    except Exception as e:
        print(f"⚠️ Fehler beim Senden der Verlassensnachricht: {e}")
        await log_channel.send(
            f"⚠️ **Fehler:** {member.mention} hat den Server verlassen, aber eine Fehlermeldung trat auf."
        )


# Voice Channel
@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """
    Event: Änderungen im Sprachkanal eines Mitglieds.
    Protokolliert, wenn ein Mitglied Sprachkanäle betritt, verlässt oder wechselt.
    Auch Änderungen an Mute/Deaf-Status werden protokolliert.
    """
    print(f"Event ausgelöst: Sprachkanal-Update für {member}. Vorher: {before.channel}, Nachher: {after.channel}")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(member.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {member.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    try:
        # Sprachkanal Betreten
        if before.channel is None and after.channel is not None:
            await log_channel.send(f"{member.mention} ist in den Sprachkanal {after.channel.mention} beigetreten.")

        # Sprachkanal Verlassen
        elif before.channel is not None and after.channel is None:
            await log_channel.send(f"{member.mention} hat den Sprachkanal {before.channel.mention} verlassen.")

        # Sprachkanal Wechsel
        elif before.channel != after.channel:
            await log_channel.send(
                f"{member.mention} hat den Sprachkanal von {before.channel.mention} zu {after.channel.mention} gewechselt.")

        # Selbst-Mute Änderungen
        if before.self_mute != after.self_mute:
            if after.self_mute:
                await log_channel.send(f"{member.mention} hat sich selbst stummgeschaltet in {after.channel.mention}.")
            else:
                await log_channel.send(f"{member.mention} hat sich selbst entmutet in {after.channel.mention}.")

        # Selbst-Deafen Änderungen
        if before.self_deaf != after.self_deaf:
            if after.self_deaf:
                await log_channel.send(
                    f"{member.mention} hat sich selbst entmutet (deafen) in {after.channel.mention}.")
            else:
                await log_channel.send(
                    f"{member.mention} hat sich selbst entmutet (undeafen) in {after.channel.mention}.")

        # Mute durch Moderatoren/Administratoren
        if before.mute != after.mute:
            executor = "ein Moderator" if not member.bot else "der Bot"
            if after.mute:
                await log_channel.send(
                    f"{member.mention} wurde von {executor} stummgeschaltet in {after.channel.mention}.")
            else:
                await log_channel.send(f"{member.mention} wurde von {executor} entmutet in {after.channel.mention}.")

        # Deafen durch Moderatoren/Administratoren
        if before.deaf != after.deaf:
            executor = "ein Moderator" if not member.bot else "der Bot"
            if after.deaf:
                await log_channel.send(
                    f"{member.mention} wurde von {executor} entmutet (deafen) in {after.channel.mention}.")
            else:
                await log_channel.send(
                    f"{member.mention} wurde von {executor} entmutet (undeafen) in {after.channel.mention}.")

        print(f"✅ Sprachkanaländerung für {member} protokolliert.")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Sprachkanal-Updates für {member}: {e}")
        await log_channel.send(
            f"⚠️ **Fehler:** Änderungen im Sprachkanal für {member.mention} konnten nicht protokolliert werden.")


# Event: Rollenänderungen
@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    """
    Event: Rollenänderungen eines Mitglieds.
    Protokolliert, wenn einem Mitglied eine Rolle hinzugefügt oder entfernt wird.
    Auch der Executor (wer die Änderung vorgenommen hat) wird erfasst.
    """
    print(f"Event ausgelöst: Rollenänderung für {after}. Vorher: {before.roles}, Nachher: {after.roles}")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(after.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {after.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    try:
        # Rollen, die hinzugefügt wurden
        added_roles = [role for role in after.roles if role not in before.roles]
        # Rollen, die entfernt wurden
        removed_roles = [role for role in before.roles if role not in after.roles]

        # Rollen hinzugefügt
        for role in added_roles:
            async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                if entry.target == after and role in entry.after.roles:
                    executor = entry.user  # Der User, der die Rolle hinzugefügt hat
                    await log_channel.send(f"{after.mention} hat die Rolle {role.mention} erhalten von {executor.mention}.")

        # Rollen entfernt
        for role in removed_roles:
            async for entry in after.guild.audit_logs(action=discord.AuditLogAction.member_role_update, limit=1):
                if entry.target == after and role in entry.before.roles:
                    executor = entry.user  # Der User, der die Rolle entfernt hat
                    await log_channel.send(f"{after.mention} hat die Rolle {role.mention} verloren von {executor.mention}.")

        print(f"✅ Rollenänderungen für {after} protokolliert.")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten der Rollenänderungen für {after}: {e}")
        await log_channel.send(f"⚠️ **Fehler:** Rollenänderungen für {after.mention} konnten nicht protokolliert werden.")


# Event: Kanal erstellen
@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    """
    Event: Kanal wird erstellt.
    Protokolliert das Erstellen eines Kanals und sendet eine Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Kanal erstellt ({channel.name}, {channel.type})")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(channel.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {channel.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    try:
        # Hole den Audit-Log-Eintrag für das Erstellen von Kanälen
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
            if entry.target.id == channel.id:  # Sicherstellen, dass der Eintrag zum erstellten Kanal gehört
                await log_channel.send(
                    f"📂 **Kanal erstellt:** {channel.name} ({channel.type})\n"
                    f"🔧 **Erstellt von:** {entry.user.mention}\n"
                    f"📅 **Zeitpunkt:** <t:{int(entry.created_at.timestamp())}:f>"
                )
                print(f"✅ Kanal-Erstellung geloggt: {channel.name} erstellt von {entry.user}")
                break
        else:
            # Falls kein passender Audit-Log-Eintrag gefunden wurde
            await log_channel.send(
                f"📂 **Kanal erstellt:** {channel.name} ({channel.type})\n"
                "Aber der Ersteller konnte nicht ermittelt werden."
            )
            print(f"⚠️ Kein Audit-Log-Eintrag für den Kanal {channel.name} gefunden.")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Kanal-Erstellungs-Logs: {e}")
        await log_channel.send(
            f"⚠️ **Kanal erstellt:** {channel.name} ({channel.type})\n"
            "Es trat ein Fehler bei der Erfassung der Ersteller-Informationen auf."
        )


# Event: Kanal löschen
@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    """
    Event: Kanal wird gelöscht.
    Protokolliert das Löschen eines Kanals und sendet eine Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Kanal gelöscht ({channel.name}, {channel.type})")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(channel.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {channel.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    try:
        # Hole den Audit-Log-Eintrag für das Löschen von Kanälen
        async for entry in channel.guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
            if entry.target.id == channel.id:  # Sicherstellen, dass der Eintrag zum gelöschten Kanal gehört
                await log_channel.send(
                    f"❌ **Kanal gelöscht:** {channel.name} ({channel.type})\n"
                    f"🔧 **Gelöscht von:** {entry.user.mention}\n"
                    f"📅 **Zeitpunkt:** <t:{int(entry.created_at.timestamp())}:f>"
                )
                print(f"✅ Kanal-Löschung geloggt: {channel.name} gelöscht von {entry.user}")
                break
        else:
            # Falls kein passender Audit-Log-Eintrag gefunden wurde
            await log_channel.send(
                f"❌ **Kanal gelöscht:** {channel.name} ({channel.type})\n"
                "Aber der Löschende konnte nicht ermittelt werden."
            )
            print(f"⚠️ Kein Audit-Log-Eintrag für den Kanal {channel.name} gefunden.")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Kanal-Lösch-Logs: {e}")
        await log_channel.send(
            f"⚠️ **Kanal gelöscht:** {channel.name} ({channel.type})\n"
            "Es trat ein Fehler bei der Erfassung der Lösch-Informationen auf."
        )


# Event: Kanal bearbeiten (Name, Beschreibung etc.)
@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    """
    Event: Kanal wird bearbeitet (z. B. Name, Berechtigungen, Position, Kategorie).
    Protokolliert Änderungen an Kanälen und sendet Nachrichten in den Log-Kanal.
    """
    print(f"Event ausgelöst: Kanalbearbeitung ({before.name})")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(before.guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {before.guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    try:
        # Überprüfen, ob der Kanalname geändert wurde
        if before.name != after.name:
            async for entry in before.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                executor = entry.user  # Der Benutzer, der die Änderung vorgenommen hat
                await log_channel.send(
                    f"Der Kanal **{before.name}** wurde von {executor.mention} umbenannt in **{after.name}**. ({after.name})"
                )
                print(f"✅ Kanalname geändert: {before.name} -> {after.name}")

        # Überprüfen, ob Berechtigungen geändert wurden
        if before.overwrites != after.overwrites:
            changed_permissions = []
            for target, before_overwrite in before.overwrites.items():
                after_overwrite = after.overwrites.get(target)
                if after_overwrite != before_overwrite:
                    change_desc = f"{target}: "
                    if after_overwrite.read_messages != before_overwrite.read_messages:
                        change_desc += f"Leserechte geändert ({'erlaubt' if after_overwrite.read_messages else 'nicht erlaubt'}), "
                    if after_overwrite.send_messages != before_overwrite.send_messages:
                        change_desc += f"Schreibrechte geändert ({'erlaubt' if after_overwrite.send_messages else 'nicht erlaubt'}), "
                    changed_permissions.append(change_desc.rstrip(", "))

            if changed_permissions:
                async for entry in before.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                    executor = entry.user  # Der Benutzer, der die Änderung vorgenommen hat
                    await log_channel.send(
                        f"Die Berechtigungen für {after.mention} wurden von {executor.mention} geändert: {', '.join(changed_permissions)}."
                    )
                    print(f"✅ Berechtigungen geändert für {after.name}")

        # Überprüfen, ob die Kanalposition geändert wurde (nur innerhalb der gleichen Kategorie)
        if before.position != after.position and before.category == after.category:
            async for entry in before.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                executor = entry.user  # Der Benutzer, der die Änderung vorgenommen hat
                await log_channel.send(
                    f"Die Kanalposition von {after.mention} wurde von Position {before.position} auf {after.position} geändert von {executor.mention}."
                )
                print(f"✅ Kanalposition geändert: {before.position} -> {after.position}")

        # Überprüfen, ob der Kanal die Kategorie gewechselt hat
        if before.category != after.category:
            async for entry in before.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
                executor = entry.user  # Der Benutzer, der die Änderung vorgenommen hat
                await log_channel.send(
                    f"Der Kanal {after.mention} wurde von {executor.mention} von der Kategorie **{before.category.name}** in **{after.category.name}** verschoben."
                )
                print(f"✅ Kanal verschoben: {before.category.name} -> {after.category.name}")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten des Kanalbearbeitungs-Logs: {e}")
        await log_channel.send(
            f"⚠️ **Kanalbearbeitung:** Es trat ein Fehler bei der Erfassung der Änderungen für den Kanal {before.name} auf."
        )


# Event: Emoji-Hinzufügen und Entfernen
@bot.event
async def on_guild_emojis_update(guild: discord.Guild, before: list, after: list):
    """
    Event: Emojis werden auf dem Server hinzugefügt oder entfernt.
    Protokolliert das Hinzufügen und Entfernen von Emojis und sendet eine Nachricht in den Log-Kanal.
    """
    print(f"Event ausgelöst: Emoji-Update in {guild.name}")

    # Prüfen, ob ein Log-Kanal für die Guild gesetzt ist
    log_channel_id = log_channels.get(str(guild.id))
    if not log_channel_id:
        print(f"⚠️ Kein Log-Kanal für Guild-ID {guild.id} gesetzt.")
        return

    # Kanalobjekt holen
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        print(f"⚠️ Log-Kanal mit ID {log_channel_id} nicht gefunden.")
        return

    try:
        added_emojis = [emoji for emoji in after if emoji not in before]
        removed_emojis = [emoji for emoji in before if emoji not in after]

        # Hinzugefügte Emojis protokollieren
        for emoji in added_emojis:
            await log_channel.send(f"✨ Neues Emoji hinzugefügt: {emoji} zu **{guild.name}**.")

        # Entfernte Emojis protokollieren
        for emoji in removed_emojis:
            remover = None
            # Audit-Log für das Entfernen von Emojis durchsuchen
            audit_logs = await guild.audit_logs(limit=1, action=discord.AuditLogAction.emoji_delete).flatten()
            if audit_logs:
                remover = audit_logs[0].user  # Der Benutzer, der das Emoji entfernt hat

            remover_info = f" von {remover.mention}" if remover else ""  # Information über den Entfernenden
            await log_channel.send(f"❌ Emoji entfernt: **{emoji.name}**{remover_info}.")

    except Exception as e:
        print(f"⚠️ Fehler beim Verarbeiten der Emoji-Änderungen: {e}")
        await log_channel.send(f"⚠️ **Emoji-Änderung:** Es trat ein Fehler bei der Erfassung der Emoji-Änderungen auf.")

# Event: Reaktionen hinzufügen und entfernen
@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
    """
    Event: Eine Reaktion wird auf eine Nachricht hinzugefügt.
    Protokolliert das Hinzufügen von Reaktionen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(reaction.message.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"{user.mention} hat mit {reaction.emoji} auf die Nachricht reagiert.")

@bot.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    """
    Event: Eine Reaktion wird von einer Nachricht entfernt.
    Protokolliert das Entfernen von Reaktionen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(reaction.message.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            await log_channel.send(f"{user.mention} hat die Reaktion {reaction.emoji} von der Nachricht entfernt.")

# Event: Rollen erstellen, löschen und bearbeiten
@bot.event
async def on_guild_role_create(role: discord.Role):
    """
    Event: Eine neue Rolle wird auf dem Server erstellt.
    Protokolliert das Erstellen von Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(role.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Prüfen, wer die Aktion durchgeführt hat
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
                await log_channel.send(f"🎭 **Neue Rolle erstellt:** {role.name}\n🔧 **Erstellt von:** {entry.user.mention}")
                break


@bot.event
async def on_guild_role_delete(role: discord.Role):
    """
    Event: Eine Rolle wird auf dem Server gelöscht.
    Protokolliert das Löschen von Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(role.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Prüfen, wer die Aktion durchgeführt hat
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                await log_channel.send(f"❌ **Rolle gelöscht:** {role.name}\n🔧 **Gelöscht von:** {entry.user.mention}")
                break


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    """
    Event: Eine Rolle wird auf dem Server bearbeitet (z.B. Name oder Berechtigungen geändert).
    Protokolliert die Änderungen an Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(after.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Prüfen, ob der Rollenname geändert wurde
            if before.name != after.name:
                async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                    await log_channel.send(
                        f"🎭 **Rolle umbenannt:** {before.name} → {after.name}\n🔧 **Ändert von:** {entry.user.mention}")

            # Prüfen, ob Berechtigungen geändert wurden
            if before.permissions != after.permissions:
                async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                    await log_channel.send(
                        f"🎭 **Berechtigungen geändert für die Rolle:** {after.name}\n🔧 **Ändert von:** {entry.user.mention}")


@bot.event
async def on_guild_role_delete(role: discord.Role):
    """
    Event: Eine Rolle wird auf dem Server gelöscht.
    Protokolliert das Löschen von Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(role.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Prüfen, wer die Aktion durchgeführt hat
            async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                await log_channel.send(f"❌ **Rolle gelöscht:** {role.name}\n🔧 **Gelöscht von:** {entry.user.mention}")
                break


@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    """
    Event: Eine Rolle wird auf dem Server bearbeitet (z.B. Name oder Berechtigungen geändert).
    Protokolliert die Änderungen an Rollen und sendet eine Nachricht in den Log-Kanal.
    """
    log_channel_id = log_channels.get(after.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Holen des Audit-Log-Eintrags für die Bearbeitung der Rolle
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                changes = []
                if before.name != after.name:
                    changes.append(f"**Name:** {before.name} → {after.name}")
                if before.permissions != after.permissions:
                    changes.append("**Berechtigungen geändert**")
                if before.color != after.color:
                    changes.append(f"**Farbe:** {before.color} → {after.color}")

                # Wenn Änderungen erkannt wurden, sende die Protokollnachricht
                if changes:
                    await log_channel.send(
                        f"✏️ **Rolle bearbeitet:** {after.name}\n🔧 **Bearbeitet von:** {entry.user.mention}\n" +
                        "\n".join(changes)
                    )
                break

@bot.event
async def on_reaction_remove(reaction: discord.Reaction, user: discord.User):
    """
    Event: Ein Benutzer entfernt eine Reaktion von einer Nachricht.
    Protokolliert das Entfernen von Reaktionen und sendet eine Nachricht in den Log-Kanal.
    """
    # Holen des Log-Kanals für die Guild
    log_channel_id = log_channels.get(reaction.message.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Log-Nachricht senden, wenn der Benutzer eine Reaktion entfernt
            await log_channel.send(f"{user.mention} hat seine Reaktion {reaction.emoji} von der Nachricht entfernt.")


@bot.event
async def on_guild_member_update(before: discord.Member, after: discord.Member):
    """
    Event: Nitro Boost des Mitglieds (Serverboost).
    Protokolliert das Aktivieren und Zurücknehmen des Serverboosts.
    """
    log_channel_id = log_channels.get(after.guild.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Prüfen, ob der Benutzer den Serverboost aktiviert hat
            if before.premium_since is None and after.premium_since is not None:
                # Serverboost aktiviert
                await log_channel.send(f"{after.mention} hat den Server geboostet! 🎉")

            # Prüfen, ob der Benutzer den Serverboost zurückgenommen hat
            elif before.premium_since is not None and after.premium_since is None:
                # Serverboost zurückgenommen
                await log_channel.send(f"{after.mention} hat den Serverboost zurückgenommen. 😢")

            # Optional: Audit-Log-Einträge abfragen und den Executor protokollieren
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id and entry.changes:
                    # Durchsuchen der Änderungen für den Boost-Status
                    for change in entry.changes:
                        if change.key == "premium_since":
                            executor = entry.user
                            if after.premium_since:
                                await log_channel.send(
                                    f"✅ Boost wurde von {executor.mention} aktiviert für {after.mention}.")
                            else:
                                await log_channel.send(
                                    f"❌ Boost wurde von {executor.mention} entfernt für {after.mention}.")
                            break


@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """
    Event: Servername geändert.
    Protokolliert Änderungen des Servernamens.
    """
    log_channel_id = log_channels.get(after.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            if before.name != after.name:
                # Hole den Audit-Log-Eintrag für die Änderung des Servernamens
                async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
                    if entry.target.id == after.id:
                        executor = entry.user
                        await log_channel.send(f"Servername geändert: {before.name} → {after.name} durch {executor.mention}")
                        break

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    """
    Event: Servereinstellungen geändert.
    Protokolliert Änderungen wie Server-Icon, Region, AFK-Channel und andere Einstellungen.
    """
    log_channel_id = log_channels.get(after.id)
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            # Server-Icon geändert
            if before.icon != after.icon:
                await log_channel.send(f"**Server-Icon wurde geändert.** Neuer Icon-Link: {after.icon.url}.")

            # Server-Region geändert
            if before.region != after.region:
                await log_channel.send(f"**Server-Region wurde geändert.** Neue Region: {after.region}.")

            # AFK-Channel geändert
            if before.afk_channel != after.afk_channel:
                if after.afk_channel:
                    await log_channel.send(f"**AFK-Channel wurde geändert.** Neuer AFK-Channel: {after.afk_channel.mention}.")
                else:
                    await log_channel.send(f"**AFK-Channel wurde entfernt.**")

            # Hole den Audit-Log-Eintrag für Änderungen der Servereinstellungen
            async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
                # Der Benutzer, der die Änderung vorgenommen hat
                executor = entry.user
                await log_channel.send(f"Änderung durchgeführt von **{executor.mention}** (Administrator/Bot).")

# Event: Event Handler
@bot.event
async def on_error(event, *args, **kwargs):
    log_channel_id = log_channels.get(args[0].guild.id) if args and hasattr(args[0], 'guild') else None
    if log_channel_id:
        log_channel = bot.get_channel(log_channel_id)
        if log_channel:
            await send_embed_log(
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

# JSON-Datei zum Speichern der Reaction Roles
REACTION_ROLES_FILE = "reaction_roles.json"

# Daten speichern
def save_reaction_roles(data, filename=REACTION_ROLES_FILE):
    with open(filename, "w") as file:
        json.dump(data, file, indent=4)

# Daten laden
def load_reaction_roles(filename=REACTION_ROLES_FILE):
    try:
        with open(filename, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}  # Gibt ein leeres Dict zurück, falls die Datei nicht existiert

reaction_roles_data = load_reaction_roles()

class ReactionRolesView(discord.ui.View):
    def __init__(self, roles: list[discord.Role], emojis: list[str]):
        super().__init__(timeout=None)
        self.roles = roles
        self.emojis = emojis
        for role, emoji in zip(roles, emojis):
            self.add_item(RoleButton(role, emoji))


class RoleButton(discord.ui.Button):
    def __init__(self, role: discord.Role, emoji: str):
        super().__init__(label=role.name, style=discord.ButtonStyle.primary, emoji=emoji)
        self.role = role

    async def callback(self, interaction: Interaction):
        member = interaction.user
        if self.role in member.roles:
            await member.remove_roles(self.role)
            await interaction.response.send_message(
                f"🔴 Rolle {self.role.mention} wurde entfernt.", ephemeral=True
            )
        else:
            await member.add_roles(self.role)
            await interaction.response.send_message(
                f"🟢 Rolle {self.role.mention} wurde hinzugefügt.", ephemeral=True
            )


@bot.tree.command(name="reactionroles", description="Erstellt eine Reaktionsrollen-Auswahl mit Buttons.")
async def reactionroles(interaction: discord.Interaction, roles: str, emojis: str):
    # Zerlege die Rollen und Emojis in Listen
    role_mentions = roles.split()  # Trenne Rollen durch Leerzeichen
    emoji_list = emojis.split()   # Trenne Emojis durch Leerzeichen

    # Überprüfe, ob die Anzahl der Rollen mit der Anzahl der Emojis übereinstimmt
    if len(role_mentions) != len(emoji_list):
        await interaction.response.send_message(
            "⚠️ Die Anzahl der Rollen muss mit der Anzahl der Emojis übereinstimmen.",
            ephemeral=True
        )
        return

    # Liste der tatsächlichen discord.Role-Objekte
    role_objects = []
    for role_str in role_mentions:
        try:
            # Entferne die Zeichen "<@&>" und konvertiere die ID zu einer Zahl
            role_id = int(role_str.strip("<@&>"))
            role = interaction.guild.get_role(role_id)
            if not role:
                raise ValueError(f"Die Rolle mit der ID {role_id} wurde nicht gefunden.")
            role_objects.append(role)
        except ValueError as e:
            await interaction.response.send_message(
                f"⚠️ Fehler bei der Verarbeitung der Rolle '{role_str}': {e}",
                ephemeral=True
            )
            return

    # Erstelle die View mit den Buttons
    view = ReactionRolesView(role_objects, emoji_list)
    message = await interaction.response.send_message(
        "Reaktionsrollen: Klicke auf die Buttons, um Rollen zu erhalten oder zu entfernen.",
        view=view
    )

    # Nachricht-ID speichern
    message_id = (await message.original_response()).id
    reaction_roles_data[str(message_id)] = {
        "roles": [role.id for role in role_objects],
        "emojis": emoji_list
    }
    save_reaction_roles(reaction_roles_data)

@bot.event
async def on_ready():
    print(f"Bot ist bereit! Eingeloggt als {bot.user}")

    # Reaction Roles wiederherstellen
    for message_id, data in reaction_roles_data.items():
        try:
            channel = bot.get_channel(int(data.get("channel_id")))  # Optional, falls channel gespeichert
            if not channel:
                continue
            message = await channel.fetch_message(int(message_id))
            roles = [message.guild.get_role(role_id) for role_id in data["roles"]]
            emojis = data["emojis"]

            # View wiederherstellen
            view = ReactionRolesView(roles, emojis)
            await message.edit(view=view)
        except Exception as e:
            print(f"Fehler beim Wiederherstellen von Reaction Roles für Nachricht {message_id}: {e}")


# Event: Synchronisiere den Command-Tree beim Start des Bots
@bot.event
async def on_ready():
    print(f'Bot ist eingeloggt als {bot.user}!')
    try:
        # Synchronisiere die Befehle mit dem Discord-Server
        await bot.tree.sync()
        print("Slash-Commands synchronisiert.")
    except Exception as e:
        print(f"Fehler beim Synchronisieren der Slash-Commands: {e}")

@bot.event
async def on_ready():
    print(f'{bot.user} ist online und bereit!')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong!')

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
