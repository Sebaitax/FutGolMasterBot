"""Escalera de copas (tipo Clash Royale): reglas puras, sin base de datos.

- Al crear el club eliges tu país: tu plantel inicial, los bots y los sobres salen de esa liga.
- Ganas copas al ganar y las pierdes al perder; con las copas subes de cancha, desde la
  Cancha del Barrio hasta la Primera División. Al llegar a una cancha ya no bajas de ella.
- Cada cancha tiene su diseño (clase CSS `arena-<tema>`) y la fuerza de sus bots (un cuantil
  de las medias de la liga de tu país).
- Cada victoria te da un sobre por tiempo (si tienes un espacio libre): se desbloquea de a
  uno y trae jugadores de tu liga, mejores mientras más alta sea la cancha.
"""
from __future__ import annotations

import math

from juego.economia import SOBRES

PAISES = {  # clave -> nombre, bandera, valor de la columna "liga" de las cartas
    "chile": ("Chile", "🇨🇱", "Liga de Primera"),
    "argentina": ("Argentina", "🇦🇷", "Liga Profesional"),
    "brasil": ("Brasil", "🇧🇷", "Brasileirão Serie A"),
    "espana": ("España", "🇪🇸", "LaLiga"),
    "inglaterra": ("Inglaterra", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Premier League"),
    "italia": ("Italia", "🇮🇹", "Serie A"),
    "alemania": ("Alemania", "🇩🇪", "Bundesliga"),
    "francia": ("Francia", "🇫🇷", "Ligue 1"),
    "mls": ("Estados Unidos", "🇺🇸", "MLS"),
}
PAIS_DEFECTO = "chile"

# nombre, copas para llegar, cuantil de la fuerza de los bots, emoji, tema visual, descripción
CANCHAS = [
    ("Cancha del Barrio", 0, 0.05, "🏘️", "barrio", "Pichanga entre vecinos: arcos de piedra y la pelota que se va a la calle."),
    ("Cancha de Tierra", 150, 0.13, "🟫", "tierra", "Polvo, piedras y botines gastados. Acá se forja el carácter."),
    ("Estadio Municipal", 350, 0.22, "🏟️", "municipal", "Pasto a medias, una tribuna de madera y el alcalde mirando."),
    ("Décima División", 600, 0.30, "🔟", "decima", "Tu primer torneo oficial. Ya hay árbitro con silbato."),
    ("Novena División", 900, 0.37, "9️⃣", "novena", "Canchas de pasto y rivales que entrenan dos veces por semana."),
    ("Octava División", 1200, 0.44, "8️⃣", "octava", "Llegan los primeros hinchas y los camarines con agua caliente."),
    ("Séptima División", 1500, 0.51, "7️⃣", "septima", "Equipos con historia de barrio y barra propia."),
    ("Sexta División", 1800, 0.58, "6️⃣", "sexta", "Estadios con iluminación: se juega de noche."),
    ("Quinta División", 2100, 0.65, "5️⃣", "quinta", "Fútbol semiprofesional: ojeadores en la tribuna."),
    ("Cuarta División", 2400, 0.72, "4️⃣", "cuarta", "Planteles profesionales y prensa local."),
    ("Tercera División", 2700, 0.79, "3️⃣", "tercera", "Estadios llenos y televisión regional."),
    ("Segunda División", 3000, 0.87, "2️⃣", "segunda", "A un paso de la élite: cada punto vale oro."),
    ("Primera División", 3400, 0.95, "🏆", "primera", "La máxima categoría de tu país. Solo los mejores."),
]

COPAS_VICTORIA, COPAS_DERROTA, COPAS_EMPATE = 32, 26, 4

# sobres por tiempo (se ganan al ganar): se repite este ciclo
SOBRES_TIEMPO = SOBRES   # los mismos de la tienda (básico 3 h, súper 8 h, premium 12 h)
LEGADO_SOBRES = {"comun": "basico", "especial": "super", "epico": "premium"}   # nombres antiguos
CICLO_SOBRES = ["basico", "basico", "super", "basico", "basico", "super", "basico", "super", "premium"]
ESPACIOS_SOBRES = 4
MONEDAS_POR_MINUTO = 15   # abrir ya un sobre que se está desbloqueando (o bloqueado): costo por minuto restante


def cancha_de(copas: int) -> int:
    """Índice de la cancha que corresponde a esas copas."""
    return max(i for i, c in enumerate(CANCHAS) if copas >= c[1])


def info_cancha(i: int, pais: str = PAIS_DEFECTO) -> dict:
    nombre, desde, cuantil, ico, tema, texto = CANCHAS[i]
    p_nombre, bandera, _ = PAISES.get(pais, PAISES[PAIS_DEFECTO])
    hasta = CANCHAS[i + 1][1] if i + 1 < len(CANCHAS) else None
    return {"indice": i, "nombre": nombre, "desde": desde, "hasta": hasta, "cuantil": cuantil, "ico": ico,
            "tema": tema, "texto": texto, "pais": p_nombre, "bandera": bandera,
            "titulo": f"{nombre} de {p_nombre}" if i >= 3 else nombre}


def piso(max_copas: int) -> int:
    """Copas mínimas: no se baja de la cancha más alta a la que llegaste."""
    return CANCHAS[cancha_de(max_copas)][1]


def cambio_copas(mias: int, rival: int, resultado: str) -> int:
    """resultado: 'victoria' | 'empate' | 'derrota'. Ganarle a uno con más copas da más."""
    dif = max(-200, min(200, rival - mias))
    if resultado == "victoria":
        return COPAS_VICTORIA + round(dif / 25)
    if resultado == "derrota":
        return -(COPAS_DERROTA - round(dif / 25))
    return COPAS_EMPATE


def multiplicador_monedas(cancha: int) -> float:
    """Las canchas altas pagan más por partido."""
    return 1 + 0.15 * cancha


def costo_abrir_ya(segundos_restantes: float) -> int:
    return max(0, math.ceil(segundos_restantes / 60) * MONEDAS_POR_MINUTO)


def cuantil(valores_ordenados: list[int], q: float) -> int:
    if not valores_ordenados:
        return 60
    q = max(0.0, min(1.0, q))
    return valores_ordenados[round(q * (len(valores_ordenados) - 1))]


def calidad_sobre(rng, probabilidades: dict | None = None) -> str:
    """normal | buena | estrella, según las probabilidades del sobre (por defecto, las del básico)."""
    probabilidades = probabilidades or SOBRES["basico"]["probabilidades"]
    return rng.choices(list(probabilidades), weights=list(probabilidades.values()))[0]


def cuantil_calidad(rng, cancha: int, calidad: str) -> float:
    """Dónde cae la carta dentro de tu liga (cuantil de la media) según su calidad y tu cancha."""
    base = CANCHAS[cancha][2]
    if calidad == "estrella":
        q = rng.uniform(max(base + 0.22, 0.88), 1.0)
    elif calidad == "buena":
        q = rng.uniform(base + 0.06, base + 0.20)
    else:
        q = rng.uniform(base - 0.12, base + 0.04)
    return max(0.0, min(1.0, q))


def cuantil_sobre(rng, cancha: int, probabilidades: dict | None = None) -> float:
    return cuantil_calidad(rng, cancha, calidad_sobre(rng, probabilidades))
