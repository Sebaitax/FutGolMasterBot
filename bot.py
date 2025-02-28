import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

from database import funciones as f


intents = discord.Intents.default()
intents.message_content = True  # Necesario para acceder al contenido de los mensajes
intents.members = True
bot = commands.Bot(command_prefix="-", intents=intents)

@bot.event
async def bot_conect():
    print(f"Bot conectado como {bot.user}")

@bot.command()
async def ayuda(ctx):
    await ctx.send("¡Hola! Soy FutGolMasterBot. Usa `!start` para comenzar.")
    
@bot.command()
async def start(ctx):
    await ctx.send("¡Bienvenido al FutGolMasterBot! Usa `!collect` para ver tus cartas.")
    usuario_ex = False
    if usuario_ex:
        f.obtener_usuario()
    else:
        f.crear_usuario()




@bot.command()
async def ver_inventario(ctx):
    await ctx.send("Aquí está tu inventario de cartas.")

@bot.command()
async def crear_plantilla(ctx, nombre, *jugadores):
    await ctx.send(f"Plantilla {nombre} creada con los jugadores: {', '.join(jugadores)}")


load_dotenv()

token = os.getenv('TOKEN') 
bot.run(token)