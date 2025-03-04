import nextcord
from nextcord.ext import commands
from nextcord import File
from dotenv import load_dotenv
import os

from models.userModel import User
from models.paginationModel import Pagination

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

@bot.slash_command(name="cartas", description="Muestra tus cartas obtenidas")
async def cartas(interaction: nextcord.Interaction):
    user = interaction.user
    user_existing = users_collection.find_one({"user_id": user.id})

    if user_existing:
        cartas = user_existing.get("jugadores", [])

        if cartas:
            # Crear la vista de paginación y el embed inicial
            pagination = Pagination(cartas, user.id)
            embed = pagination.create_embed()

            # Enviar el mensaje con la paginación
            await interaction.response.send_message(embed=embed, view=pagination)
        else:
            await interaction.response.send_message("No tienes cartas en tu inventario.")
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

            # Actualizar la colección de usuarios
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
            
            # Inicializar el embed antes de cualquier comprobación
            embed = nextcord.Embed(
                title="¡Has reclamado una carta!",
                description=f"Has obtenido la carta: {carta_nombre}",
                color=nextcord.Color.green()
            )

            image_path = f"assets/images/{carta_nombre}.png"
            if not os.path.exists(image_path):  #
                image_path = f"assets/images/{carta_nombre}.jpg"
            
            print(image_path)
            # Verificar si la imagen existe y enviarla como archivo adjunto
            if os.path.exists(image_path):
                image_file = File(image_path, filename=f"{carta_nombre}.png")  # Enviar como archivo adjunto
                embed.set_image(url=f"attachment://{carta_nombre}.png")
                
                # Enviar el mensaje con el embed y la imagen
                await interaction.response.send_message(embed=embed, file=image_file)
            else:
                # Si no se encuentra la imagen, simplemente enviamos el embed sin imagen
                await interaction.response.send_message(embed=embed)




#GENERAR USUARIO
@bot.slash_command(name="p", description="Ver información del perfil")
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
