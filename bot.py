import nextcord
from nextcord.ext import commands
from dotenv import load_dotenv
import os
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True


bot = commands.Bot(intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado correctamente como {bot.user}")

@bot.slash_command(name="perfil", description="Ver información de un usuario")
async def perfil(interaction: nextcord.Interaction, member: nextcord.Member = None):
    member = member or interaction.user  # Si no se menciona, usa el que ejecutó el comando

    # Obtener avatar del usuario
    avatar_url = member.avatar.url if member.avatar else "https://cdn-icons-png.flaticon.com/512/149/149071.png"

    # Ruta de la imagen del estadio en la raíz
    FONDO_ESTADIO_PATH = "estadio.png"  

    # Verificar si la imagen de fondo existe
    if not os.path.exists(FONDO_ESTADIO_PATH):
        await interaction.response.send_message("❌ No se encontró la imagen de fondo `estadio.png`.")
        return

    try:
        fondo = Image.open(FONDO_ESTADIO_PATH).convert("RGBA")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error al abrir la imagen de fondo: {e}")
        return

    # Crear un lienzo en blanco con el tamaño adecuado
    width, height = 700, 400
    img = Image.new("RGBA", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Redimensionar el fondo del estadio para que cubra solo la parte superior
    fondo = fondo.resize((width, 150))
    img.paste(fondo, (0, 0))


    # Descargar y redimensionar la imagen de perfil
    response = requests.get(avatar_url)
    try:
        avatar = Image.open(BytesIO(response.content)).convert("RGBA")
        avatar = avatar.resize((100, 100))
        img.paste(avatar, (width - 125, 25), avatar)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error al cargar el avatar: {e}")
        return

    # Configurar fuente
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_text = ImageFont.truetype("arial.ttf", 22)
    except IOError:
        await interaction.response.send_message("❌ No se encontró la fuente 'arial.ttf'.")
        return

    # Dibujar el nombre de usuario
    draw.text((30, 160), f"Nombre: {member.name}", fill="black", font=font_title)

    # Dibujar la caja de información abajo
    info_x, info_y = 30, 200
    draw.text((info_x, info_y), f"Saldo: 0$", fill="black", font=font_text)
    draw.text((info_x, info_y + 30), f"Jugadores: 13/100", fill="black", font=font_text)
    draw.text((info_x, info_y + 60), f"Estadio: Monumental Colo Colo", fill="black", font=font_text)
    draw.text((info_x, info_y + 90), f"Plantillas: 3/5", fill="black", font=font_text)
    draw.text((info_x, info_y + 120), f"Copas: 2", fill="black", font=font_text)

    # Guardar la imagen generada en memoria
    image_stream = BytesIO()
    img.save(image_stream, format="PNG")
    image_stream.seek(0)

    # Enviar la imagen en Discord
    file = nextcord.File(image_stream, filename="perfil.png")
    await interaction.response.send_message(file=file)

# Cargar variables de entorno
load_dotenv()
token = os.getenv('TOKEN')

# Ejecutar el bot
bot.run(token)
