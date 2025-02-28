import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# from database import funciones as f
from models import userModel

intents = discord.Intents.default()
intents.message_content = True  # Necesario para acceder al contenido de los mensajes
intents.members = True
bot = commands.Bot(command_prefix="-", intents=intents)

@bot.event
async def bot_conect():
    print(f"Bot conectado como {bot.user}")

@bot.command()
async def ayuda(ctx):
    await ctx.send("""¡Hola! Soy FutGolMasterBot, a continucación obtendras la lista de comandos:\n
Inicio: -start 
Ver usuario: -u
                   """)
    
@bot.command()
async def start(ctx):
    await ctx.send("¡Bienvenido al FutGolMasterBot! Usa `-collect` para ver tus cartas.")


@bot.command(name="u")
async def u(ctx, member: discord.Member = None):
    member = member or ctx.author

    
    usuario = userModel.User(
        user_id=member.id,
        nombre=member.name,
        global_name=member.global_name,
        avatar_url=member.avatar.url,
        fecha_union=member.joined_at
        )
    
    await ctx.send(usuario.mostrar_info())
load_dotenv()

token = os.getenv('TOKEN') 
bot.run(token)