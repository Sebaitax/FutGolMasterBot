import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv
import os

# from database import funciones como f
from models import userModel

intents = nextcord.Intents.default()
intents.message_content = True  # Necesario para acceder al contenido de los mensajes
intents.members = True

bot = commands.Bot(intents=intents)  

@bot.event
async def on_ready():
    print(f"✅ Bot conectado correctamente como {bot.user}")

@bot.slash_command(name="ayuda", description="Muestra la lista de comandos disponibles")
async def ayuda(interaction: nextcord.Interaction):
    await interaction.response.send_message(
        "¡Hola! Soy FutGolMasterBot, a continuación obtendrás la lista de comandos:\n"
        "- `/start` → Iniciar bot\n"
        "- `/usuario` → Ver usuario"
    )

@bot.slash_command(name="start", description="Inicia el FutGolMasterBot")
async def start(interaction: nextcord.Interaction):
    await interaction.response.send_message("¡Bienvenido al FutGolMasterBot! Usa `/collect` para ver tus cartas.")

@bot.slash_command(name="usuario", description="Ver información de un usuario")
async def usuario(interaction: nextcord.Interaction, member: nextcord.Member = None):
    member = member or interaction.user 

    usuario = userModel.User(
        user_id=member.id,
        nombre=member.name,
        global_name=getattr(member, "global_name", "No disponible"),
        avatar_url=member.avatar.url if member.avatar else "No tiene avatar",
        fecha_union=member.joined_at
    )
    
    await interaction.response.send_message(usuario.mostrar_info())

# Cargar variables de entorno
load_dotenv()
token = os.getenv('TOKEN')

# Ejecutar el bot
bot.run(token)
