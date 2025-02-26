import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

#funciones locales
from database import funciones

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


@bot.command()
async def ver_inventario(ctx):
    await ctx.send("Aquí está tu inventario de cartas.")

@bot.command()
async def crear_plantilla(ctx, nombre, *jugadores):
    await ctx.send(f"Plantilla {nombre} creada con los jugadores: {', '.join(jugadores)}")

@bot.command()
async def simular_partido(ctx, plantilla_1, plantilla_2):
    eventos = simular_partido(plantilla_1, plantilla_2)
    for evento in eventos:
        await ctx.send(evento)
    

load_dotenv()

token = os.getenv('TOKEN') 
bot.run(token)