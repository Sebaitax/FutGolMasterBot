import os
import csv
import requests
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

# Directorios de assets
FONTS_DIR = "assets/fonts/"
IMAGES_DIR = "assets/images/"
CARD_TEMPLATES_DIR = os.path.join(IMAGES_DIR, "card_templates/")
RENDERS_DIR = os.path.join(IMAGES_DIR, "BronceRara/FotosJugador")
CARTAS_DIR = os.path.join(IMAGES_DIR, "BronceRara/Cartas")

# Configurar Chrome indetectable
driver = uc.Chrome()

# Lista para jugadores no encontrados
no_encontrados = []

def search_and_download_image(player_name, overall):
    print(f"Buscando render para {player_name} con OVR {overall}...")
    search_url = "https://renderz.app"
    driver.get(search_url)
    
    try:
        wait = WebDriverWait(driver, 5)
        
        search_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'fill-white/50 bg-white/5 hover:bg-white/10 hover:fill-white/60 w-10 h-10 transition-all rounded-full flex items-center justify-center')]"))
        )
        search_button.click()
        time.sleep(2)
        
        search_box = wait.until(
            EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'rounded-full w-full bg-white/5 px-4 py-4 md:py-2 placeholder:text-neutral-50/40 focus:outline-none text-neutral-50 disabled:opacity-70')]"))
        )
        search_box.clear()
        search_box.send_keys(player_name)
        time.sleep(2)
        
        players = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(@class, 'flex items-center px-4 h-24 md:hover:bg-white/5')]")))
        
        if not players:
            print(f"No se encontró render para {player_name}.")
            return None, None, None, None
        
        for player in players:
            try:
                overall_elements = player.find_elements(By.XPATH, ".//span[contains(@class, 'text-3xl')]/span")
                if overall_elements and overall_elements[0].text.strip() == str(overall):
                    player.click()
                    break
            except:
                continue
        
        time.sleep(3)
        
        image_element = driver.find_element(By.XPATH, "//img[contains(@class, 'action-shot')]")
        image_url = image_element.get_attribute("src")
        
        nation_element = driver.find_element(By.XPATH, "//img[contains(@class, 'nation')]")
        nation_url = nation_element.get_attribute("src")
        
        league_element = driver.find_element(By.XPATH, "//img[contains(@class, 'league')]")
        league_url = league_element.get_attribute("src")
        
        club_element = driver.find_element(By.XPATH, "//img[contains(@class, 'club')]")
        club_url = club_element.get_attribute("src")
        
        folder_path = os.path.join(RENDERS_DIR, player_name)
        os.makedirs(folder_path, exist_ok=True)

        def download_image(url, filename):
            response = requests.get(url)
            if response.status_code == 200:
                image_path = os.path.join(folder_path, filename)
                with open(image_path, "wb") as file:
                    file.write(response.content)
                return image_path
            return None
        
        render_path = download_image(image_url, f"{player_name}.png")
        nation_path = download_image(nation_url, "nation.png")
        league_path = download_image(league_url, "league.png")
        club_path = download_image(club_url, "club.png")
        
        return render_path, nation_path, league_path, club_path
    except:
        print(f"Error al descargar el render de {player_name}.")
        return None, None, None, None

def cargar_jugadores(csv_file):
    return pd.read_csv(csv_file).to_dict(orient='records')

def crear_carta(jugador):
    print(f"Procesando carta para {jugador['Nombre']}...")
    
    folder_path = os.path.join(CARTAS_DIR, jugador["Nombre"])
    os.makedirs(folder_path, exist_ok=True)
    
    template_path = os.path.join(CARD_TEMPLATES_DIR, "bronze_rare.png")
    font_pathBold = os.path.join(FONTS_DIR, "CruyffSans-Bold.ttf")
    font_pathRegular = os.path.join(FONTS_DIR, "CruyffSans-Regular.ttf")
    font_pathMedium = os.path.join(FONTS_DIR, "CruyffSans-Medium.ttf")
    if not os.path.exists(template_path):
        print("Plantilla de carta no encontrada.")
        return
    
    carta = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(carta)
    fontPos = ImageFont.truetype(font_pathMedium, int(1 * 16))
    fontStat = ImageFont.truetype(font_pathMedium, int(1.2 * 16))
    fontStatName = ImageFont.truetype(font_pathRegular, int(0.77 * 16))
    font_OVR = ImageFont.truetype(font_pathBold, int(2.1373 * 16))
    font_nombre = ImageFont.truetype(font_pathMedium, int(1.8 * 16))
    

    text_width = draw.textbbox((0, 0), jugador["Alias"].title(), font=font_nombre)[2]
    nombre_pos = ((carta.width - text_width) // 2, 225)
    overall_pos = (45, 65)
    posicion_pos = (55, 95)
    stats_names_pos = {
    "PAC": (45, 255), "SHO": (75, 255), "PAS": (105, 255),
    "DRI": (135, 255), "DEF": (165, 255), "PHY": (195, 255)
    }
    stats_pos = {
    "PAC": (45, 265), "SHO": (75, 265), "PAS": (105, 265),
    "DRI": (135, 265), "DEF": (165, 265), "PHY": (195, 265)
    }
    
    draw.text(nombre_pos, jugador["Alias"].capitalize(), fill="#3e281c", font=font_nombre)
    draw.text(overall_pos, str(jugador["OVR"]), fill="#3e281c", font=font_OVR)
    draw.text(posicion_pos, jugador["Posición"].replace("++", ""), fill="#3e281c", font=fontPos)

    for stat, pos in stats_names_pos.items():
        draw.text(pos, stat, fill="#3e281c", font=fontStatName)

    for stat, pos in stats_pos.items():
        draw.text(pos, str(jugador[stat]), fill="#3e281c", font=fontStat)  
    
    foto_jugador, nation, league, club = search_and_download_image(jugador["Nombre"], jugador["OVR"])
    if foto_jugador:
        foto = Image.open(foto_jugador).convert("RGBA")
        carta.paste(foto, (0, 60), foto)
    
    if nation:
        nation_img = Image.open(nation).convert("RGBA")
        nation_img = nation_img.resize((22, 22))
        carta.paste(nation_img, (90, 287), nation_img)
    
    if league:
        league_img = Image.open(league).convert("RGBA")
        league_img = league_img.resize((22, 22))
        carta.paste(league_img, (115, 287), league_img)
    
    if club:
        club_img = Image.open(club).convert("RGBA")
        club_img = club_img.resize((22, 22))
        carta.paste(club_img, (140, 287), club_img)
    else:
        print(f"No se encontró render para {jugador['Nombre']}, agregando a NoEncontrados.csv.")
        no_encontrados.append([jugador["Nombre"], jugador["Alias"], jugador["OVR"]])
    
    output_path = os.path.join(folder_path, f"{jugador['Nombre'].replace(' ', '_')}.png")
    carta.save(output_path)
    print(f"Carta guardada en {output_path}")

def main():
    jugadores = cargar_jugadores("CSV/cartas_bronze_raras.csv")
    
    for jugador in jugadores:
        crear_carta(jugador)
    
    if no_encontrados:
        df_no_encontrados = pd.DataFrame(no_encontrados, columns=["Nombre", "Alias", "OVR"])
        df_no_encontrados.to_csv("NoEncontrados.csv", index=False)
        print("Se ha generado NoEncontrados.csv con jugadores sin render.")
    
    driver.quit()
    print("Proceso finalizado.")

if __name__ == "__main__":
    main()
