import requests
from PIL import Image
from io import BytesIO

def obtener_foto_jugador(jugador, equipo):
    url = f"https://www.thesportsdb.com/api/v1/json/3/searchplayers.php?p={jugador}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data["player"]:
            for player in data["player"]:
                # Filtramos por equipo, deporte y nacionalidad
                if player["strTeam"] == equipo and player["strSport"] == "Soccer" and player["strNationality"] == "Spain":
                    foto_url = player.get("strCutout")
                    if foto_url:
                        print(f"Descargando foto de {jugador}...\nURL: {foto_url}")
                        img_response = requests.get(foto_url)
                        if img_response.status_code == 200:
                            img = Image.open(BytesIO(img_response.content))
                            img.show()
                        else:
                            print("Error al descargar la imagen.")
                    else:
                        print("No se encontró imagen del jugador.")
                    return
            
            print("Jugador no encontrado en el equipo especificado.")
        else:
            print("No se encontraron jugadores con ese nombre.")
    else:
        print("Error al conectar con la API.")

# Buscar a Rodrigo Hernández en el Manchester City
obtener_foto_jugador("Rodri", "Manchester City")
