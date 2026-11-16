"""Monedas: premios por partido y temporada, sobres y venta rápida.

Todas las cifras están acá para poder calibrarlas con scripts/simular_carrera.py.
"""
import os

PREMIO_PARTIDO = {"victoria": 1000, "empate": 450, "derrota": 200}
PREMIO_GOL = 50
# para probar: $env:FGM_MONEDAS_INICIALES=100000 antes de lanzar la web (se aplica al crear la partida)
MONEDAS_INICIALES = int(os.environ.get("FGM_MONEDAS_INICIALES", 3000))   # dos sobres básicos
PREMIO_OBJETIVO = 4000          # bonus por cumplir el objetivo de la temporada


def premio_temporada(posicion: int) -> int:
    return max(1500, 15000 - 900 * (posicion - 1))


# Las divisiones de arriba pagan más (partidos y premio de temporada)
MULTIPLICADOR_DIVISION = {0: 1.0, 1: 1.5, 2: 2.0}


# Sobres: cada carta sale de la liga de tu país y su calidad depende de tu cancha (escalera de copas):
#   normal = del nivel de tu cancha · buena = mejor que tu cancha · estrella = de las mejores de tu liga
# Los mismos tres sobres se compran en la tienda o se ganan al ganar partidos (sobres por tiempo).
# "objeto": probabilidad de que cada lugar traiga un escudo o estadio de colección.
CALIDADES = {
    "normal": "Del nivel de tu cancha",
    "buena": "Mejor que tu cancha",
    "estrella": "De las mejores de tu liga",
}
SOBRES = {
    "basico": {"nombre": "Sobre básico", "precio": 1500, "cartas": 3, "horas": 3, "ico": "📦", "objeto": 0.05,
               "probabilidades": {"normal": 0.80, "buena": 0.18, "estrella": 0.02}},
    "super": {"nombre": "Súper sobre", "precio": 4000, "cartas": 5, "horas": 8, "ico": "🎁", "objeto": 0.10,
              "probabilidades": {"normal": 0.65, "buena": 0.30, "estrella": 0.05}},
    "premium": {"nombre": "Sobre premium", "precio": 9000, "cartas": 7, "horas": 12, "ico": "💎", "objeto": 0.18,
                "probabilidades": {"normal": 0.45, "buena": 0.42, "estrella": 0.13}},
}
RAREZA_OBJETO = {"normal": "bronce", "buena": "plata", "estrella": "oro"}


def precio_sobre(clave: str, cancha: int = 0) -> int:
    """Mientras más alta tu cancha, mejores cartas trae el sobre y más cuesta (+35 % por cancha)."""
    return int(round(SOBRES[clave]["precio"] * (1 + 0.35 * cancha), -2))

# Rareza de los estadios según capacidad
def rareza_estadio(capacidad: int) -> str:
    return "oro" if capacidad >= 40000 else "plata" if capacidad >= 20000 else "bronce"


# Carta gratis: una cada 8 horas (de tu liga, con la calidad de un sobre básico)
CARTA_GRATIS_SEGUNDOS = 8 * 3600
CARTA_GRATIS_PROBABILIDADES = SOBRES["basico"]["probabilidades"]

# Mejora con cartas repetidas: cada nivel suma +1 a la media y a cada atributo
NIVEL_MAXIMO = 5


def costo_mejora(nivel_actual: int) -> int:
    """Monedas para subir del nivel actual al siguiente (además de gastar una copia repetida)."""
    return 400 * nivel_actual


def valor_venta(precio: int) -> int:
    """Venta rápida: un 4 % del precio de la carta, con tope de 1.500. Así abrir sobres para venderlas
    siempre pierde monedas (en cualquier cancha) y la venta es solo para limpiar el plantel."""
    return max(25, min(1500, precio // 25))
