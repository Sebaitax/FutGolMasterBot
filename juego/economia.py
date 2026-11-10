"""Monedas: premios por partido y temporada, sobres y venta rápida.

Todas las cifras están acá para poder calibrarlas con scripts/simular_carrera.py.
"""
import os

PREMIO_PARTIDO = {"victoria": 1000, "empate": 450, "derrota": 200}
PREMIO_GOL = 50
# para probar: $env:FGM_MONEDAS_INICIALES=100000 antes de lanzar la web (se aplica al crear la partida)
MONEDAS_INICIALES = int(os.environ.get("FGM_MONEDAS_INICIALES", 3000))
PREMIO_OBJETIVO = 4000          # bonus por cumplir el objetivo de la temporada


def premio_temporada(posicion: int) -> int:
    return max(1500, 15000 - 900 * (posicion - 1))


# Las divisiones de arriba pagan más (partidos y premio de temporada)
MULTIPLICADOR_DIVISION = {0: 1.0, 1: 1.5, 2: 2.0}


# Cada carta del sobre sale de un nivel según estas probabilidades (se muestran al jugador)
# "objeto": probabilidad de que cada lugar del sobre traiga un escudo o un estadio de colección
# (su rareza sale de las mismas probabilidades que las cartas)
SOBRES = {
    "bronce": {"nombre": "Sobre bronce", "precio": 1500, "cartas": 3, "objeto": 0.06,
               "probabilidades": {"bronce": 0.80, "plata": 0.19, "oro": 0.01}},
    "plata": {"nombre": "Sobre plata", "precio": 5000, "cartas": 3, "objeto": 0.12,
              "probabilidades": {"bronce": 0.25, "plata": 0.70, "oro": 0.05}},
    "oro": {"nombre": "Sobre oro", "precio": 12000, "cartas": 3, "objeto": 0.25,
            "probabilidades": {"bronce": 0.0, "plata": 0.70, "oro": 0.30}},
}

# Rareza de los estadios según capacidad
def rareza_estadio(capacidad: int) -> str:
    return "oro" if capacidad >= 40000 else "plata" if capacidad >= 20000 else "bronce"


# Carta gratis: una por hora
CARTA_GRATIS_SEGUNDOS = 8 * 3600
CARTA_GRATIS_PROBABILIDADES = {"bronce": 0.70, "plata": 0.27, "oro": 0.03}

# Mejora con cartas repetidas: cada nivel suma +1 a la media y a cada atributo
NIVEL_MAXIMO = 5


def costo_mejora(nivel_actual: int) -> int:
    """Monedas para subir del nivel actual al siguiente (además de gastar una copia repetida)."""
    return 400 * nivel_actual


def valor_venta(precio: int) -> int:
    """Venta rápida: una fracción del precio de la carta."""
    return max(50, precio // 4)
