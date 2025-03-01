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
async def p(interaction: nextcord.Interaction, member: nextcord.Member = None):
    member = member or interaction.user  # Si no se menciona, usa el que ejecutó el comando
    
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
        avatar_url= member.avatar.url,
        saldo= saldo,
        cartas= cartas,
        plantillas=plantillas,
        copas=copas, 
    )
    
    
    
    
    await interaction.response.send_message(usuario.mostrar_info(users_collection))

# Cargar variables de entorno
load_dotenv()
token = os.getenv('TOKEN')

# Ejecutar el bot
bot.run(token)
