import discord
from discord.ext import commands
from dotenv import load_dotenv
import os

# from database import funciones como f
from models import userModel

intents = discord.Intents.default()
intents.message_content = True  # Necesario para acceder al contenido de los mensajes
intents.members = True
bot = commands.Bot(intents=intents)

@bot.event
async def bot_conect():
    print(f"Bot conectado como {bot.user}")

@bot.slash_command(name="ayuda", description="Muestra la lista de comandos disponibles")
async def ayuda(ctx):
    await ctx.respond("""¡Hola! Soy FutGolMasterBot, a continuación obtendrás la lista de comandos:\n
    - `/start` → Iniciar bot
    - `/usuario` → Ver usuario
    """)

@bot.slash_command(name="start", description="Inicia el FutGolMasterBot")
async def start(ctx):
    await ctx.respond("¡Bienvenido al FutGolMasterBot! Usa `/collect` para ver tus cartas.")

@bot.slash_command(name="usuario", description="Ver información de un usuario")
async def usuario(ctx, member: discord.Member = None):
    member = member or ctx.author

    usuario = userModel.User(
        user_id=member.id,
        nombre=member.name,
        global_name=member.global_name,
        avatar_url=member.avatar.url,
        fecha_union=member.joined_at
    )
    
    await ctx.respond(usuario.mostrar_info())

load_dotenv()

token = os.getenv('TOKEN') 
bot.run(token)
