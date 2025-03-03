import requests
from PIL import Image
from io import BytesIO

def obtener_bandera(pais):
    url = "https://www.thesportsdb.com/api/v1/json/3/all_countries.php"
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        if "countries" in data:
            for country in data["countries"]:
                if country["name_en"].lower() == pais.lower():
                    nombre_pais = country["name_en"]
                    bandera_url = country["flag_url_32"]
                    print(f"{nombre_pais}: {bandera_url}")
                    
                    # Descargar y mostrar la bandera
                    img_response = requests.get(bandera_url)
                    if img_response.status_code == 200:
                        img = Image.open(BytesIO(img_response.content))
                        img.show()
                    else:
                        print(f"Error al descargar la bandera de {nombre_pais}.")
                    return
            print("País no encontrado.")
        else:
            print("No se encontraron países en la respuesta de la API.")
    else:
        print("Error al conectar con la API.")

# Define el país a buscar
pais = "Chile"  # Puedes cambiarlo por cualquier otro país
obtener_bandera(pais)