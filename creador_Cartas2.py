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
RENDERS_DIR = os.path.join(IMAGES_DIR, "FotosJugador")

# Configurar Chrome indetectable
driver = uc.Chrome()

# Lista para jugadores no encontrados
no_encontrados = []

def search_and_download_image(player_name, overall):
    search_url = "https://renderz.app"
    driver.get(search_url)
    
    try:
        wait = WebDriverWait(driver, 5)
        
        # Hacer clic en el botón de búsqueda
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
            return None
        
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
        
        folder_path = os.path.join(RENDERS_DIR, f"{player_name}_{overall}")
        os.makedirs(folder_path, exist_ok=True)

        response = requests.get(image_url)
        if response.status_code == 200:
            image_path = os.path.join(folder_path, f"{player_name}.png")
            with open(image_path, "wb") as file:
                file.write(response.content)
            return image_path
    except:
        return None
    
    return None

def cargar_jugadores(csv_file):
    return pd.read_csv(csv_file).to_dict(orient='records')

def crear_carta(jugador):
    template_path = os.path.join(CARD_TEMPLATES_DIR, "default.png")
    font_path = os.path.join(FONTS_DIR, "CruyffSans-Bold.ttf")
    
    if not os.path.exists(template_path):
        return
    
    carta = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(carta)
    font = ImageFont.truetype(font_path, 50)
    font_OVR = ImageFont.truetype(font_path, 70)
    
    nombre_pos = (120, 650)
    overall_pos = (120, 150)
    posicion_pos = (120, 250)
    stats_pos = {
        "PAC": (150, 750), "SHO": (150, 820), "PAS": (150, 890),
        "DRI": (450, 750), "DEF": (450, 820), "PHY": (450, 890)
    }
    
    draw.text(nombre_pos, jugador["Alias"], fill="black", font=font)
    draw.text(overall_pos, str(jugador["OVR"]), fill="black", font=font_OVR)
    draw.text(posicion_pos, jugador["Posición"], fill="black", font=font)
    
    for stat, pos in stats_pos.items():
        draw.text(pos, f"{stat}: {jugador[stat]}", fill="black", font=font)
    
    foto_jugador = search_and_download_image(jugador["Alias"], jugador["OVR"])
    if foto_jugador:
        foto = Image.open(foto_jugador).convert("RGBA")
        foto = foto.resize((350, 550))
        carta.paste(foto, (300, 40), foto)
    else:
        no_encontrados.append([jugador["Nombre"], jugador["Alias"], jugador["OVR"]])
    
    output_path = os.path.join(IMAGES_DIR, f"{jugador['Alias'].replace(' ', '_')}.png")
    carta.save(output_path)

def main():
    jugadores = cargar_jugadores("CSV/cartas_bronce.csv")
    
    for jugador in jugadores:
        crear_carta(jugador)
    
    if no_encontrados:
        df_no_encontrados = pd.DataFrame(no_encontrados, columns=["Nombre", "Alias", "OVR"])
        df_no_encontrados.to_csv("NoEncontrados.csv", index=False)
    
    driver.quit()

if __name__ == "__main__":
    main()
