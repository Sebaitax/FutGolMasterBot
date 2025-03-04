import csv
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os
from database.conexion import cards_collection

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
                return Image.open(BytesIO(img_response.content))
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
                        return Image.open(BytesIO(img_response.content))
    return None

def cargar_jugadores_csv(csv_file):
    jugadores = []
    with open(csv_file, newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        for row in reader:
            jugadores.append(row)
    return jugadores



def cargar_jugadores_db():
    jugadores= list(cards_collection.find())
    for jugador in jugadores:
        jugador.pop('_id',None)
    return jugadores
    
def crear_carta(jugador):
    template_path = os.path.join(CARD_TEMPLATES_DIR, "default.png")  # Ajustar según plantilla disponible
    font_path = os.path.join(FONTS_DIR, "DINPro CondBold.otf")
    
    if not os.path.exists(template_path):
        print("Plantilla de carta no encontrada.")
        return
    
    carta = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(carta)
    font = ImageFont.truetype(font_path, 50)
    font_OVR = ImageFont.truetype(font_path, 100)
    # Posiciones
    nombre_pos = (120, 650)
    overall_pos = (120, 150)
    posicion_pos = (120, 250)
    stats_pos = {
        "PAC": (150, 750), "SHO": (150, 820), "PAS": (150, 890),
        "DRI": (450, 750), "DEF": (450, 820), "PHY": (450, 890)
    }
    
    # Dibujar nombre, posición y rating
    draw.text(nombre_pos, jugador["Nombre"], fill="black", font=font)
    draw.text(overall_pos, jugador["OVR"], fill="black", font=font_OVR)
    draw.text(posicion_pos, jugador["Posición"], fill="black", font=font)
    
    # Dibujar estadísticas alineadas correctamente
    for stat, pos in stats_pos.items():
        draw.text(pos, f"{jugador[stat]} {stat}", fill="black", font=font)
    
    # Obtener logo del club
    logo = obtener_logo(jugador["Club"])
    if logo:
        logo = logo.resize((130, 130))
        carta.paste(logo, (120, 450), logo)
    
    # Obtener bandera
    bandera = obtener_bandera(jugador["Nación"])
    if bandera:
        bandera = bandera.resize((120, 80))
        carta.paste(bandera, (120, 350), bandera)
    
    # Guardar la imagen
    output_path = os.path.join(IMAGES_DIR, f"{jugador['Nombre'].replace(' ', '_')}.png")
    carta.save(output_path)
    print(f"Carta creada: {output_path}")



def crear_carta_db(jugador):
    template_path = os.path.join(CARD_TEMPLATES_DIR, "default.png")  # Ajustar según plantilla disponible
    font_path = os.path.join(FONTS_DIR, "DINPro CondBold.otf")
    
    if not os.path.exists(template_path):
        print("Plantilla de carta no encontrada.")
        return
    
    carta = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(carta)
    font = ImageFont.truetype(font_path, 50)
    font_OVR = ImageFont.truetype(font_path, 100)
    
    # Posiciones
    nombre_pos = (120, 650)
    overall_pos = (120, 150)
    posicion_pos = (120, 250)
    stats_pos = {
        "PAC": (150, 750), "SHO": (150, 820), "PAS": (150, 890),
        "DRI": (450, 750), "DEF": (450, 820), "PHY": (450, 890)
    }
    
    # Dibujar nombre, posición y rating
    draw.text(nombre_pos, jugador["nombre"], fill="black", font=font)
    draw.text(overall_pos, str(jugador["estadisticas"].get('OVR', 'N/A')), fill="black", font=font_OVR)
    draw.text(posicion_pos, jugador["posicion"], fill="black", font=font)
    
    # Dibujar estadísticas alineadas correctamente
    for stat, pos in stats_pos.items():
        # Usamos get() para evitar KeyError si la clave no está presente
        stat_value = jugador["estadisticas"].get(stat, 'N/A')  # Si no existe, pone 'N/A'
        draw.text(pos, f"{stat_value} {stat}", fill="black", font=font)
    
    # Obtener logo del club
    logo = obtener_logo(jugador["club"])
    if logo:
        logo = logo.resize((130, 130))
        carta.paste(logo, (120, 450), logo)
    
    # Obtener bandera
    bandera = obtener_bandera(jugador.get("nación", "desconocida"))  # Usar valor predeterminado si no existe
    if bandera:
        bandera = bandera.resize((120, 80))
        carta.paste(bandera, (120, 350), bandera)
    
    # Guardar la imagen
    output_path = os.path.join(IMAGES_DIR, f"{(jugador['nombre'])}.png")
    carta.save(output_path)
    print(f"Carta creada: {output_path}")









# Cargar jugadores del CSV
# jugadores = cargar_jugadores_csv("cartas_ejemplo.csv") 
jugadores = cargar_jugadores_db()
# print(jugadores[:3])
# Filtrar jugador ejemplo (Rodrigo Hernández Cascante)
# jugador_ejemplo = next((j for j in jugadores if j["nombre"] == "Aitana Bonmatí Conca"), None)
# if jugador_ejemplo:
#     crear_carta_db(jugador_ejemplo)
#     print("Jugador encontrado:", jugador_ejemplo)
# else:
#     print("Jugador no encontrado.")


for jugador in jugadores:
    crear_carta_db(jugador)