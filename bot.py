import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

intents = discord.Intents.default()
intents.message_content = True  # Necesario para acceder al contenido de los mensajes
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def bot_conect():
    print(f"Bot conectado como {bot.user}")

@bot.command()
async def ayuda(ctx):
    await ctx.send("¡Hola! Soy FutGolMasterBot. Usa `!start` para comenzar.")
    
@bot.command()
async def start(ctx):
    await ctx.send("¡Bienvenido al FutGolMasterBot! Usa `!collect` para ver tus cartas.")
    
    
load_dotenv()

token = os.getenv('TOKEN') 
bot.run(token)