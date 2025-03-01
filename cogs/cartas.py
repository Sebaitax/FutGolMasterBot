import requests
from bs4 import BeautifulSoup
import time

# URL de la página web que quieres scrapear
url = "https://www.futbin.com"

# Realizar una solicitud GET a la página web
response = requests.get(url)

if response.status_code == 200:
    print("Página cargada con éxito.")
else:
    print("Error al cargar la página.")
    exit()

# Crear un objeto BeautifulSoup para analizar el contenido HTML
soup = BeautifulSoup(response.content, "html.parser")

# Buscar todas las cartas de fútbol en la página (ajusta según el HTML)
cards = soup.find_all("div", class_="card")

# Iterar sobre las cartas y extraer la información
for card in cards:
    name = card.find("h2").text.strip()
    rarity = card.find("span", class_="rarity").text.strip()
    club = card.find("span", class_="club").text.strip()

    print(f"Nombre: {name}, Rareza: {rarity}, Club: {club}")
    
    # Pausa entre solicitudes (si tienes que hacer múltiples solicitudes)
    time.sleep(2)  # Pausa de 2 segundos entre cada extracción de carta
