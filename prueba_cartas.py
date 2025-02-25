from database.conexion import db
from database.funciones import agregar_carta

# Referencia a la colección de cartas
cards_collection = db["cards"]

# Definir los datos de la carta de Mbappé
mbappe_stats = {
    "overall": 90,
    "posicion": "ST",
    "velocidad": 96,
    "disparo": 86,
    "pase": 78,
    "dribbling": 91,
    "defensa": 39,
    "fisico": 76
}

# Llamar a la función para agregar la carta
resultado = agregar_carta(
    cards_collection,
    nombre="Kylian Mbappé",
    tipo="oro",
    stats=mbappe_stats,
    precio_venta_rapida=20000,
    liga="La Liga",
    equipo="Real Madrid",
    pais="Francia",
    imagen="url_imagen_mbappe"
)

print(f"Carta de Mbappé agregada con ID: {resultado}")


