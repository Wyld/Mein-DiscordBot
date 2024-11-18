import sqlite3
import time

def initialize_database():
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()

        # Tabelle für Bankkonten erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS bank_accounts (
            account_name TEXT PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
        ''')

        # Tabelle für Lagerinhalte erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS warehouses (
            warehouse_name TEXT,
            item_name TEXT,
            quantity INTEGER,
            PRIMARY KEY (warehouse_name, item_name)
        )
        ''')

        # Tabelle für Giveaways erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS giveaways (
            giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            message_id INTEGER,
            prize TEXT,
            end_time INTEGER
        )
        ''')

        # Tabelle für Reaktionskanäle erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reaction_channels (
            channel_id INTEGER PRIMARY KEY,
            emojis TEXT
        )
        ''')

        # Tabelle für Countdown-Timer erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS countdowns (
            timer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            channel_id INTEGER,
            end_time INTEGER
        )
        ''')

        # Tabelle für Reaction Roles erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reaction_roles (
            message_id INTEGER PRIMARY KEY,
            role_id INTEGER,
            emoji TEXT
        )
        ''')

        # Tabelle für Log-Kanäle erstellen
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS log_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        )
        ''')

        connection.commit()

# Bankkonto erstellen
def create_bank_account(account_name):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('INSERT INTO bank_accounts (account_name) VALUES (?)', (account_name,))
        connection.commit()

# Kontostand aktualisieren
def update_balance(account_name, amount):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('UPDATE bank_accounts SET balance = balance + ? WHERE account_name = ?', (amount, account_name))
        connection.commit()

# Kontostand abrufen
def get_balance(account_name):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT balance FROM bank_accounts WHERE account_name = ?', (account_name,))
        result = cursor.fetchone()
        return result[0] if result else None

# Items zum Lager hinzufügen oder deren Menge aktualisieren
def add_item_to_warehouse(warehouse_name, item_name, quantity):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('''
        INSERT INTO warehouses (warehouse_name, item_name, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(warehouse_name, item_name)
        DO UPDATE SET quantity = quantity + ?
        ''', (warehouse_name, item_name, quantity, quantity))
        connection.commit()

# Item aus dem Lager entfernen oder Menge reduzieren
def remove_item_from_warehouse(warehouse_name, item_name, quantity):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('''
        UPDATE warehouses
        SET quantity = quantity - ?
        WHERE warehouse_name = ? AND item_name = ? AND quantity >= ?
        ''', (quantity, warehouse_name, item_name, quantity))
        connection.commit()

# Alle Inhalte eines Lagers abrufen
def get_warehouse_content_from_db(warehouse_name):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT item_name, quantity FROM warehouses WHERE warehouse_name = ?', (warehouse_name,))
        return cursor.fetchall()

# Lager leeren
def clear_warehouse(warehouse_name):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('DELETE FROM warehouses WHERE warehouse_name = ?', (warehouse_name,))
        connection.commit()

# Giveaway speichern
def create_giveaway(channel_id, message_id, prize, duration_seconds):
    end_time = int(time.time()) + duration_seconds
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('''
        INSERT INTO giveaways (channel_id, message_id, prize, end_time)
        VALUES (?, ?, ?, ?)
        ''', (channel_id, message_id, prize, end_time))
        connection.commit()

# Aktive Giveaways abrufen
def get_active_giveaways():
    current_time = int(time.time())
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT giveaway_id, channel_id, message_id, prize, end_time FROM giveaways WHERE end_time > ?', (current_time,))
        return cursor.fetchall()

# Giveaway löschen
def delete_giveaway(giveaway_id):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('DELETE FROM giveaways WHERE giveaway_id = ?', (giveaway_id,))
        connection.commit()

# Reaktionskanal speichern
def save_reaction_channel(channel_id, emojis):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('''
        INSERT INTO reaction_channels (channel_id, emojis)
        VALUES (?, ?)
        ON CONFLICT(channel_id) DO UPDATE SET emojis = ?
        ''', (channel_id, ','.join(emojis), ','.join(emojis)))
        connection.commit()

# Reaktionskanal entfernen
def remove_reaction_channel(channel_id):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('DELETE FROM reaction_channels WHERE channel_id = ?', (channel_id,))
        connection.commit()

# Alle Reaktionskanäle abrufen
def get_all_reaction_channels():
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT channel_id, emojis FROM reaction_channels')
        return {row[0]: row[1].split(',') for row in cursor.fetchall()}

# Timer speichern
def create_countdown(user_id, channel_id, duration_seconds):
    end_time = int(time.time()) + duration_seconds
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('''
        INSERT INTO countdowns (user_id, channel_id, end_time)
        VALUES (?, ?, ?)
        ''', (user_id, channel_id, end_time))
        connection.commit()
        return cursor.lastrowid

# Aktive Timer abrufen
def get_active_countdowns():
    current_time = int(time.time())
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('SELECT timer_id, user_id, channel_id, end_time FROM countdowns WHERE end_time > ?', (current_time,))
        return cursor.fetchall()

# Timer löschen
def delete_countdown(timer_id):
    with sqlite3.connect('bot_data.db') as connection:
        cursor = connection.cursor()
        cursor.execute('DELETE FROM countdowns WHERE timer_id = ?', (timer_id,))
        connection.commit()

# Log Channel
def get_log_channel(guild_id):
    connection = sqlite3.connect("bot_data.db")
    cursor = connection.cursor()
    cursor.execute("SELECT channel_id FROM log_channels WHERE guild_id = ?", (guild_id,))
    result = cursor.fetchone()
    connection.close()
    return result[0] if result else None