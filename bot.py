import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv
import os

# from database import funciones como f
from models import userModel

intents = nextcord.Intents.default()
intents.message_content = True  # Necesario para acceder al contenido de los mensajes
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado correctamente como {bot.user}")

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
async def usuario(ctx, member: nextcord.Member = None):
    member = member or ctx.author

    usuario = userModel.User(
        user_id=member.id,
        nombre=member.name,
        global_name=member.global_name,
        avatar_url=member.avatar.url if member.avatar else "No tiene avatar",
        fecha_union=member.joined_at
    )
    
    await ctx.respond(usuario.mostrar_info())

# Cargar variables de entorno
load_dotenv()
token = os.getenv('TOKEN') 

# Ejecutar el bot
bot.run(token)
