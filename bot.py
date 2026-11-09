"""Punto de entrada de FutGolMasterBot."""
import os

import nextcord
from dotenv import load_dotenv
from nextcord.ext import commands

load_dotenv()

COGS = ["cogs.perfil", "cogs.cartas"]

intents = nextcord.Intents.default()
intents.members = True

bot = commands.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f"Bot conectado correctamente como {bot.user}")


if __name__ == "__main__":
    for cog in COGS:
        bot.load_extension(cog)
    bot.run(os.getenv("TOKEN"))
