import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import time

# Configurar Chrome indetectable
driver = uc.Chrome()

def search_and_download_image(player_name, overall):
    # URL de la página principal de búsqueda
    search_url = "https://renderz.app"
    driver.get(search_url)
    
    
    try:
        wait = WebDriverWait(driver, 5)
        # Hacer clic en el botón de búsqueda
        search_button = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'fill-white/50 bg-white/5 hover:bg-white/10 hover:fill-white/60 w-10 h-10 transition-all rounded-full flex items-center justify-center')]")))
        search_button.click()
        time.sleep(2)  # Esperar a que carguen los resultados

        search_box = wait.until(
            EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'rounded-full w-full bg-white/5 px-4 py-4 md:py-2 placeholder:text-neutral-50/40 focus:outline-none text-neutral-50 disabled:opacity-70')]"))
)
        search_box.send_keys(player_name)
        time.sleep(2)  # Esperar a que carguen los resultados
        
        
        
        # Obtener la lista de resultados
        players = wait.until(EC.presence_of_all_elements_located((By.XPATH, "//button[contains(@class, 'flex items-center px-4 h-24 md:hover:bg-white/5')]")))
        
        if len(players) == 0:
            print("No se encontraron jugadores.")
            return
        
        print(f"Se encontraron {len(players)} jugadores.")
        
        # Buscar el jugador con el overall indicado
        for player in players:
            try:
                player_overall = player.find_element(By.XPATH, ".//span[contains(@class, 'text-3xl')]/span".format(overall)).text
                if player_overall == str(overall):
                    player.click()
                    break
            except:
                continue
        
        time.sleep(3)  # Esperar a que cargue la página del jugador
        
        # Descargar la imagen de la nueva página
        wait.until(EC.presence_of_element_located((By.XPATH, "//img[contains(@class, 'action-shot')]")))
        image_element = driver.find_element(By.XPATH, "//img[contains(@class, 'action-shot')]")
        image_url = image_element.get_attribute("src")
        
        # Descargar la imagen
        response = requests.get(image_url)
        if response.status_code == 200:
            image_path = "player_image.png"
            with open(image_path, "wb") as file:
                file.write(response.content)
            print(f"Imagen descargada correctamente: {image_path}")
        else:
            print("Error al descargar la imagen")
        
    except Exception as e:
        print("Error:", e)
    
    finally:
        driver.quit()

# Ejecutar la función con el ejemplo
search_and_download_image("Israel Suero Fernández", 64)
