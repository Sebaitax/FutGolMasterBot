import os
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import time

# Configurar Chrome indetectable
driver = uc.Chrome()

# Función para buscar y descargar la imagen de un jugador
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
        time.sleep(2)  # Esperar a que carguen los resultados

        # Escribir el nombre del jugador en la barra de búsqueda
        search_box = wait.until(
            EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'rounded-full w-full bg-white/5 px-4 py-4 md:py-2 placeholder:text-neutral-50/40 focus:outline-none text-neutral-50 disabled:opacity-70')]"))
        )
        search_box.send_keys(player_name)
        time.sleep(2)  # Esperar a que carguen los resultados
        
        # Obtener la lista de resultados
        players = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(@class, 'flex items-center px-4 h-24 md:hover:bg-white/5')]")))
        
        if not players:
            print(f"No se encontraron jugadores para {player_name}.")
            return
        
        print(f"Se encontraron {len(players)} jugadores para {player_name}.")
        
        # Buscar el jugador con el overall indicado
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
        
        time.sleep(3)  # Esperar a que cargue la página del jugador
        
        # Descargar la imagen de la nueva página
        wait.until(EC.presence_of_element_located((By.XPATH, "//img[contains(@class, 'action-shot')]")))
        image_element = driver.find_element(By.XPATH, "//img[contains(@class, 'action-shot')]")
        image_url = image_element.get_attribute("src")
        
        # Crear la carpeta si no existe
        folder_path = os.path.join("assets", "images", "FotosJugador", f"{player_name}_{overall}")
        os.makedirs(folder_path, exist_ok=True)

        # Descargar la imagen
        response = requests.get(image_url)
        if response.status_code == 200:
            image_path = os.path.join(folder_path, "player_image.png")
            with open(image_path, "wb") as file:
                file.write(response.content)
            print(f"Imagen de {player_name} descargada correctamente en {image_path}")
        else:
            print(f"Error al descargar la imagen de {player_name}")
        
    except Exception as e:
        print(f"Error al procesar {player_name}: {e}")

# Leer el archivo CSV y recorrer los jugadores
csv_file = "cartas_ejemplo.csv"
df = pd.read_csv(csv_file)

for index, row in df.iterrows():
    player_name = row["Nombre"]
    overall = row["OVR"]
    
    search_and_download_image(player_name, overall)

# Cerrar el navegador al finalizar
driver.quit()
