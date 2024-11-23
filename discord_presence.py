import discord

async def update_presence(bot: discord.Client):
    activity = discord.Game(name="mit Feelings - Competitive")
    print("Aktualisiere Präsenz...")
    await bot.change_presence(activity=activity)
    print("Präsenz aktualisiert.")
