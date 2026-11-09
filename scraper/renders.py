"""Descarga renders de jugadores desde renderz.app a assets/renders/.

Uso:
    python -m scraper.renders data/cartas_ejemplo.csv

Los renders quedan como assets/renders/<Nombre>_<OVR>.png, que es lo que
busca cartas/generador.py. La carpeta está en .gitignore: no se sube al repo.
"""
import argparse
import os
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import time

from cartas.generador import RENDERS

driver = None  # se inicializa en main()

# Lista para jugadores no encontrados
no_encontrados = []

def search_and_download_image(player_name, overall, nombre_archivo=None):
    nombre_archivo = nombre_archivo or player_name
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
        
        def buscar_jugador(nombre):
            """Función para buscar un jugador por nombre o alias."""
            search_box = wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'rounded-full w-full bg-white/5 px-4 py-4 md:py-2 placeholder:text-neutral-50/40 focus:outline-none text-neutral-50 disabled:opacity-70')]"))
            )
            search_box.clear()
            search_box.send_keys(nombre)
            time.sleep(2)
            return wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(@class, 'flex items-center px-4 h-24 md:hover:bg-white/5')]")))
        
        players = buscar_jugador(player_name)
        if not players:
            print(f"No se encontraron jugadores con el nombre {player_name}, intentando con alias...")
            return None
        
        print(f"Se encontraron {len(players)} jugadores para {player_name}.")
        
        for player in players:
            try:
                overall_elements = player.find_elements(By.XPATH, ".//span[contains(@class, 'text-3xl')]/span")
                if overall_elements and overall_elements[0].text.strip() == str(overall):
                    player.click()
                    print(f"Jugador {player_name} con overall {overall} seleccionado.")
                    break
            except Exception as e:
                print(f"Error al buscar el overall de {player_name}: {e}")
                continue
        
        time.sleep(3)
        
        # Descargar la imagen
        wait.until(EC.presence_of_element_located((By.XPATH, "//img[contains(@class, 'action-shot')]")))
        image_element = driver.find_element(By.XPATH, "//img[contains(@class, 'action-shot')]")
        image_url = image_element.get_attribute("src")
        
        os.makedirs(RENDERS, exist_ok=True)

        response = requests.get(image_url)
        if response.status_code == 200:
            image_path = os.path.join(RENDERS, f"{nombre_archivo}_{overall}.png")
            with open(image_path, "wb") as file:
                file.write(response.content)
            print(f"Imagen de {player_name} descargada correctamente en {image_path}")
        else:
            print(f"Error al descargar la imagen de {player_name}")
        
    except Exception as e:
        print(f"Error al procesar {player_name}: {e}")
        return None
    
    return True

def main():
    global driver
    parser = argparse.ArgumentParser(description="Descarga renders de los jugadores de un CSV.")
    parser.add_argument("csv", help="CSV con columnas Nombre, Alias y OVR")
    args = parser.parse_args()

    driver = uc.Chrome()
    df = pd.read_csv(args.csv)

    for _, row in df.iterrows():
        player_name = str(row["Nombre"]).strip()
        alias = str(row["Alias"]).strip()
        overall = row["OVR"]

        encontrado = search_and_download_image(player_name, overall)
        if not encontrado:
            # Se busca por alias, pero se guarda con el nombre completo
            encontrado = search_and_download_image(alias, overall, nombre_archivo=player_name)

        if not encontrado:
            no_encontrados.append([player_name, alias, overall])

    # Guardar los jugadores no encontrados en un CSV
    if no_encontrados:
        df_no_encontrados = pd.DataFrame(no_encontrados, columns=["Nombre", "Alias", "OVR"])
        df_no_encontrados.to_csv("NoEncontrados.csv", index=False)
        print("Se han guardado los jugadores no encontrados en NoEncontrados.csv")

    driver.quit()


if __name__ == "__main__":
    main()
