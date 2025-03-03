import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
from price import get_price  # Importar la función de cálculo de precios

# Configurar Chrome indetectable
driver = uc.Chrome()

# URL base de Futbin
BASE_URL = "https://www.futbin.com/players?page="

# Listas para almacenar datos
names = []
positions = []
clubs = []
nations = []
leagues = []
ovr_ratings = []
paces = []
shootings = []
passings = []
dribblings = []
defendings = []
physicalities = []
prices = []

def get_stat_value(element):
    """
    Extrae el valor de una estadística y lo convierte en entero.
    Si el texto no es un número, retorna 0.
    """
    try:
        return int(element.text.strip())
    except ValueError:
        return 0  # En caso de error, asigna 0 como valor por defecto

def scrape_page(page):
    url = BASE_URL + str(page)
    print(f"Scrapeando: {url}")
    driver.get(url)

    # Esperar hasta que la tabla de jugadores cargue
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "table-player-name"))
        )
    except:
        print(f"⚠ La página {page} no cargó correctamente. Saltando...")
        return

    # Extraer nombres de jugadores
    name_elements = driver.find_elements(By.CLASS_NAME, "table-player-name")

    # Extraer posiciones
    pos_elements = driver.find_elements(By.CLASS_NAME, "table-pos-main")

    # Extraer calificación general (OVR)
    ovr_elements = driver.find_elements(By.CLASS_NAME, "player-rating-card-text")

    # Extraer club, nación y liga desde la clase correcta
    sub_info_elements = driver.find_elements(By.CLASS_NAME, "table-player-sub-info")

    # Extraer estadísticas clave
    pace_elements = driver.find_elements(By.CLASS_NAME, "table-pace")
    shooting_elements = driver.find_elements(By.CLASS_NAME, "table-shooting")
    passing_elements = driver.find_elements(By.CLASS_NAME, "table-passing")
    dribbling_elements = driver.find_elements(By.CLASS_NAME, "table-dribbling")
    defending_elements = driver.find_elements(By.CLASS_NAME, "table-defending")
    physicality_elements = driver.find_elements(By.CLASS_NAME, "table-physicality")

    for i in range(len(name_elements)):
        # Extraer nombre
        names.append(name_elements[i].text.strip())

        # Extraer posición
        positions.append(pos_elements[i].text.strip() if i < len(pos_elements) else "N/A")

        # Extraer OVR (Calificación General)
        ovr = get_stat_value(ovr_elements[i]) if i < len(ovr_elements) else 0
        ovr_ratings.append(ovr)

        # Extraer club, nación y liga
        if i < len(sub_info_elements):
            try:
                club_elem = sub_info_elements[i].find_element(By.CLASS_NAME, "table-player-club").find_element(By.TAG_NAME, "img")
                nation_elem = sub_info_elements[i].find_element(By.CLASS_NAME, "table-player-nation").find_element(By.TAG_NAME, "img")
                league_elem = sub_info_elements[i].find_element(By.CLASS_NAME, "table-player-league").find_element(By.TAG_NAME, "img")

                clubs.append(club_elem.get_attribute("title") if club_elem else "N/A")
                nations.append(nation_elem.get_attribute("title") if nation_elem else "N/A")
                leagues.append(league_elem.get_attribute("title") if league_elem else "N/A")
            except:
                clubs.append("N/A")
                nations.append("N/A")
                leagues.append("N/A")
        else:
            clubs.append("N/A")
            nations.append("N/A")
            leagues.append("N/A")

        # Extraer estadísticas clave usando `get_stat_value()`
        pace = get_stat_value(pace_elements[i]) if i < len(pace_elements) else 0
        shooting = get_stat_value(shooting_elements[i]) if i < len(shooting_elements) else 0
        passing = get_stat_value(passing_elements[i]) if i < len(passing_elements) else 0
        dribbling = get_stat_value(dribbling_elements[i]) if i < len(dribbling_elements) else 0
        defending = get_stat_value(defending_elements[i]) if i < len(defending_elements) else 0
        physicality = get_stat_value(physicality_elements[i]) if i < len(physicality_elements) else 0

        paces.append(pace)
        shootings.append(shooting)
        passings.append(passing)
        dribblings.append(dribbling)
        defendings.append(defending)
        physicalities.append(physicality)

        # Calcular "base_rating" como la suma de las estadísticas clave
        base_rating = pace + shooting + passing + dribbling + defending + physicality

        # Calcular el precio usando `get_price()`
        price = get_price(ovr, base_rating)
        prices.append(price)

    print(f"✅ Página {page} completada.")

def scrape_all(pages=5):
    for i in range(1, pages + 1):
        scrape_page(i)
        time.sleep(3)  # Pausa entre páginas para evitar bloqueos

    print("Scrapeo completado.")

    # Guardar en CSV
    df = pd.DataFrame({
        "Nombre": names,
        "Posición": positions,
        "Club": clubs,
        "Nación": nations,
        "Liga": leagues,
        "OVR": ovr_ratings,
        "PAC": paces,
        "SHO": shootings,
        "PAS": passings,
        "DRI": dribblings,
        "DEF": defendings,
        "PHY": physicalities,
        "Precio": prices
    })
    df.to_csv("cartas.csv", index=False)
    print("✅ Datos guardados en 'cartas.csv'.")

# Ejecutar el scraper con 5 páginas de prueba
scrape_all(pages=5)

# Cerrar el navegador
driver.quit()
