import csv
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

# Directorios de assets
FONTS_DIR = "assets/fonts/"
IMAGES_DIR = "assets/images/"
CARD_TEMPLATES_DIR = os.path.join(IMAGES_DIR, "card_templates/")

def obtener_logo(equipo):
    url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={equipo}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["teams"]:
            logo_url = data["teams"][0]["strBadge"]
            img_response = requests.get(logo_url)
            if img_response.status_code == 200:
                return Image.open(BytesIO(img_response.content)).convert("RGBA")
    return None

def obtener_bandera(pais):
    url = "https://www.thesportsdb.com/api/v1/json/3/all_countries.php"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if "countries" in data:
            for country in data["countries"]:
                if country["name_en"].lower() == pais.lower():
                    bandera_url = country["flag_url_32"]
                    img_response = requests.get(bandera_url)
                    if img_response.status_code == 200:
                        return Image.open(BytesIO(img_response.content)).convert("RGBA")
    return None

def obtener_foto_jugador(jugador, equipo):
    url = f"https://www.thesportsdb.com/api/v1/json/3/searchplayers.php?p={jugador}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data["player"]:
            print(f"Jugadores encontrados para {jugador}:")
            for player in data["player"]:
                print(f"Nombre: {player['strPlayer']}, Equipo: {player['strTeam']}, Nacionalidad: {player['strNationality']}")
                if equipo.lower() in player["strTeam"].lower() and player["strSport"] == "Soccer":
                    foto_url = player.get("strCutout") or player.get("strThumb")
                    if foto_url:
                        print(f"Descargando foto de {jugador}...\nURL: {foto_url}")
                        img_response = requests.get(foto_url)
                        if img_response.status_code == 200:
                            return Image.open(BytesIO(img_response.content)).convert("RGBA")
    print(f"No se encontró imagen para {jugador}")
    return None

def cargar_jugadores(csv_file):
    jugadores = []
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            jugadores.append(row)
    return jugadores

def crear_carta(jugador):
    template_path = os.path.join(CARD_TEMPLATES_DIR, "default.png")
    font_path = os.path.join(FONTS_DIR, "DINPro CondBold.otf")
    
    if not os.path.exists(template_path):
        print("Plantilla de carta no encontrada.")
        return
    
    carta = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(carta)
    font = ImageFont.truetype(font_path, 50)
    font_OVR = ImageFont.truetype(font_path, 70)
    
    # Posiciones de texto
    nombre_pos = (120, 650)
    overall_pos = (120, 150)
    posicion_pos = (120, 250)
    stats_pos = {
        "PAC": (150, 750), "SHO": (150, 820), "PAS": (150, 890),
        "DRI": (450, 750), "DEF": (450, 820), "PHY": (450, 890)
    }
    
    draw.text(nombre_pos, jugador["Alias"], fill="black", font=font)
    draw.text(overall_pos, jugador["OVR"], fill="black", font=font_OVR)
    draw.text(posicion_pos, jugador["Posición"], fill="black", font=font)
    
    for stat, pos in stats_pos.items():
        draw.text(pos, f"{stat}: {jugador[stat]}", fill="black", font=font)
    
    # Agregar logo del club
    logo = obtener_logo(jugador["Club"])
    if logo:
        logo = logo.resize((130, 130))
        carta.paste(logo, (120, 450), logo)
    
    # Agregar bandera
    bandera = obtener_bandera(jugador["Nación"])
    if bandera:
        bandera = bandera.resize((120, 80))
        carta.paste(bandera, (120, 350), bandera)
    
    # Agregar foto del jugador
    foto_jugador = obtener_foto_jugador(jugador["Alias"], jugador["Club"])
    if foto_jugador:
        foto_jugador = foto_jugador.resize((350, 550))
        carta.paste(foto_jugador, (300, 40), foto_jugador)
    else:
        print(f"No se encontró imagen para {jugador['Alias']}")
    
    # Guardar la imagen
    output_path = os.path.join(IMAGES_DIR, f"{jugador['Alias'].replace(' ', '_')}.png")
    carta.save(output_path)
    print(f"Carta creada: {output_path}")

# Cargar jugadores del CSV
jugadores = cargar_jugadores("cartas_ejemplo.csv")

# Generar cartas para todos los jugadores del archivo CSV
for jugador in jugadores:
    crear_carta(jugador)