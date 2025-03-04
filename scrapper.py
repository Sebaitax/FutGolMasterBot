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
aliases = []  # Nueva lista para almacenar alias

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
            EC.presence_of_element_located((By.CLASS_NAME, "player-row"))
        )
    except:
        print(f"⚠ La página {page} no cargó correctamente. Saltando...")
        return

    # Obtener todas las filas de jugadores
    player_rows = driver.find_elements(By.CLASS_NAME, "player-row")

    for row in player_rows:
        try:
            # Extraer nombre del jugador
            name_elem = row.find_element(By.CLASS_NAME, "table-player-name")
            name = name_elem.text.strip()

            # Extraer alias del jugador
            alias = "N/A"
            try:
                img_elem = row.find_element(By.CLASS_NAME, "playersquare-special-img")
                alias = img_elem.get_attribute("alt").strip() if img_elem else "N/A"
            except:
                pass

            # Si el alias sigue siendo "N/A", intentar obtenerlo desde otro lugar
            if alias == "N/A":
                try:
                    alias_elem = row.find_element(By.CLASS_NAME, "table-player-name")
                    alias = alias_elem.text.strip() if alias_elem else "N/A"
                except:
                    pass

            # Extraer posición
            try:
                position_elem = row.find_element(By.CLASS_NAME, "table-pos-main")
                position = position_elem.text.strip()
            except:
                position = "N/A"

            # Extraer OVR (Calificación General)
            try:
                ovr_elem = row.find_element(By.CLASS_NAME, "player-rating-card-text")
                ovr = get_stat_value(ovr_elem)
            except:
                ovr = 0

            # Extraer club, nación y liga
            try:
                club_elem = row.find_element(By.CLASS_NAME, "table-player-club").find_element(By.TAG_NAME, "img")
                nation_elem = row.find_element(By.CLASS_NAME, "table-player-nation").find_element(By.TAG_NAME, "img")
                league_elem = row.find_element(By.CLASS_NAME, "table-player-league").find_element(By.TAG_NAME, "img")

                club = club_elem.get_attribute("title") if club_elem else "N/A"
                nation = nation_elem.get_attribute("title") if nation_elem else "N/A"
                league = league_elem.get_attribute("title") if league_elem else "N/A"
            except:
                club, nation, league = "N/A", "N/A", "N/A"

            # Extraer estadísticas clave (PAC, SHO, PAS, DRI, DEF, PHY)
            try:
                pace = get_stat_value(row.find_element(By.CLASS_NAME, "table-pace"))
                shooting = get_stat_value(row.find_element(By.CLASS_NAME, "table-shooting"))
                passing = get_stat_value(row.find_element(By.CLASS_NAME, "table-passing"))
                dribbling = get_stat_value(row.find_element(By.CLASS_NAME, "table-dribbling"))
                defending = get_stat_value(row.find_element(By.CLASS_NAME, "table-defending"))
                physicality = get_stat_value(row.find_element(By.CLASS_NAME, "table-physicality"))
            except:
                pace, shooting, passing, dribbling, defending, physicality = 0, 0, 0, 0, 0, 0

            # Calcular "base_rating" como la suma de las estadísticas clave
            base_rating = pace + shooting + passing + dribbling + defending + physicality

            # Calcular el precio usando `get_price()`
            price = get_price(ovr, base_rating)

            # Guardar los datos
            names.append(name)
            aliases.append(alias)
            positions.append(position)
            ovr_ratings.append(ovr)
            clubs.append(club)
            nations.append(nation)
            leagues.append(league)
            paces.append(pace)
            shootings.append(shooting)
            passings.append(passing)
            dribblings.append(dribbling)
            defendings.append(defending)
            physicalities.append(physicality)
            prices.append(price)

        except Exception as e:
            print(f"❌ Error procesando un jugador: {e}")

    print(f"✅ Página {page} completada.")

def scrape_all(pages=5):
    for i in range(1, pages + 1):
        scrape_page(i)
        time.sleep(3)  # Pausa entre páginas para evitar bloqueos

    print("Scrapeo completado.")

    # Guardar en CSV
    df = pd.DataFrame({
        "Nombre": names,
        "Alias": aliases,
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

# Ejecutar el scraper con 1 página de prueba
scrape_all(pages=2)

# Cerrar el navegador
driver.quit()
