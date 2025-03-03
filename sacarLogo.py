import requests
from PIL import Image
from io import BytesIO

def obtener_logo(equipo):
    url = f"https://www.thesportsdb.com//api/v1/json/3/searchteams.php?t={equipo}"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if data["teams"]:
            logo_url = data["teams"][0]["strBadge"]
            print(f"Descargando logo de {equipo}...\nURL: {logo_url}")

            # Descargar la imagen
            img_response = requests.get(logo_url)
            if img_response.status_code == 200:
                img = Image.open(BytesIO(img_response.content))
                img.show()
            else:
                print("Error al descargar la imagen.")
        else:
            print("Equipo no encontrado.")
    else:
        print("Error al conectar con la API.")

# Define el nombre del equipo
equipo = "Arsenal"  # Puedes cambiarlo por cualquier otro equipo
obtener_logo(equipo)
