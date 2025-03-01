import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv
import os
from models.userModel import User
from database.conexion import users_collection



intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True



bot = commands.Bot(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado correctamente como {bot.user}")

@bot.slash_command(name="p", description="Ver información de un usuario")
async def p(interaction: nextcord.Interaction):
    member = interaction.user  
    avatar_url = member.avatar.url if member.avatar else "https://cdn-icons-png.flaticon.com/512/149/149071.png"

    existing_user = users_collection.find_one(member.id)
    if existing_user:
        saldo = existing_user['saldo']
        cartas =  existing_user['cartas']
        plantillas =  existing_user['plantillas']
        copas =  existing_user['copas']
    else:
        saldo = 0
        cartas = 0
        plantillas = 0
        copas = 0
        
    
    usuario = User(
        user_id=member.id,
        nombre=member.name,
        avatar_url= avatar_url,
        saldo= saldo,
        cartas= cartas,
        plantillas=plantillas,
        copas=copas, 
    )
    
    
    file =  file = nextcord.File(usuario.mostrar_info(users_collection), filename="perfil.png")
    
    await interaction.response.send_message(file=file)

# Cargar variables de entorno
load_dotenv()
token = os.getenv('TOKEN')

# Ejecutar el bot
bot.run(token)
