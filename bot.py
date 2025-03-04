import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv
import os

from models.userModel import User
from models.paginacionModel import Paginacion


from database.conexion import users_collection,cards_collection
from datetime import datetime, timedelta



intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True



bot = commands.Bot(intents=intents)
#eventos
@bot.event
async def on_ready():
    print(f"✅ Bot conectado correctamente como {bot.user}")




#camandos
# Comando para mostrar las cartas
@bot.slash_command(name="cards", description="Mostrar cartas")
async def cards(interaction: nextcord.Interaction):
    user = interaction.user
    user_existing = users_collection.find_one({"user_id": user.id})

    if user_existing:
        cartas = user_existing.get('jugadores')
        if cartas:
            view = Paginacion(cartas, user.id)
            await view.mostrar_cartas(interaction)
        else:
            await interaction.response.send_message("No tienes cartas en tu perfil.")
    else:
        await interaction.response.send_message("No puedes utilizar este comando sin un perfil, utiliza `/p` para crear tu perfil.")



#CLAIM DE CARTAS
@bot.slash_command(name="claim", description="Reclamar cartas")
async def claim(interaction: nextcord.Interaction):
    user = interaction.user
    user_existing = users_collection.find_one({"user_id": user.id})
    
    if user_existing:
        last_claim = user_existing.get('last_claim')
        
        if last_claim:
            now = datetime.utcnow()
            time_diff = now - last_claim
            
            if time_diff < timedelta(seconds=10):
                remaining_time = timedelta(seconds=10) - time_diff
                hours, remainder = divmod(remaining_time.seconds, 3600)
                minutes, seconds = divmod(remainder, 60)

                await interaction.response.send_message(f"❌ Debes esperar {hours} hora(s), {minutes} minuto(s) y {seconds} segundo(s) antes de reclamar nuevamente.")
                return  

        carta = list(cards_collection.aggregate([{"$sample": {"size": 1}}]))
        
        if carta:
            carta = carta[0]  

            carta_nombre = carta.get('nombre', 'Carta desconocida')

            users_collection.update_one(
                {"user_id": user.id},
                {"$inc": {"cartas": 1}} 
            )

            users_collection.update_one(
                {"user_id": user.id},  
                {"$addToSet": {"jugadores": carta}}  
            )
        
            users_collection.update_one(
                {"user_id": user.id},
                {"$set": {"last_claim": datetime.utcnow()}}
            )

            await interaction.response.send_message(f"✅ ¡Has reclamado la carta: {carta_nombre}!")

    else:
        await interaction.response.send_message("No puedes utilizar este comando sin un perfil, utiliza `/p` para crear tu perfil.")





#GENERAR USUARIO
@bot.slash_command(name="p", description="Ver información de un usuario")
async def p(interaction: nextcord.Interaction):
    user = interaction.user  
    avatar_url = user.avatar.url if user.avatar else "https://cdn-icons-png.flaticon.com/512/149/149071.png"

    existing_user = users_collection.find_one({"user_id":user.id})
    if existing_user:
        saldo = existing_user['saldo']
        cartas =  existing_user['cartas']
        plantillas =  existing_user['plantillas']
        copas =  existing_user['copas']
        last_claim = existing_user['last_claim']
    else:
        saldo = 0
        cartas = 0
        plantillas = 0
        copas = 0
        last_claim= 0
    
    usuario = User(
        user_id=user.id,
        nombre=user.name,
        avatar_url= avatar_url,
        saldo= saldo,
        cartas= cartas,
        plantillas=plantillas,
        copas=copas, 
        last_claim = last_claim,
        
    )
    
    file =  file = nextcord.File(usuario.mostrar_info(users_collection), filename="perfil.png")
    
    await interaction.response.send_message(file=file)

# Cargar variables de entorno
load_dotenv()
token = os.getenv('TOKEN')

# Ejecutar el bot
bot.run(token)
