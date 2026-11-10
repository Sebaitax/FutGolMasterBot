"""Identidad de los clubes: nombre, escudo (SVG generado) y estadio.

Los rivales del juego son clubes bot con nombres, escudos y estadios inventados.
Cada uno usa el plantel de un club real (las cartas conservan su club de origen).
Tu club usa el mismo formato de escudo, editable desde el perfil.
"""
from __future__ import annotations

import html
import json
import random

PREFIJOS = ["Atlético", "Deportivo", "Club", "Real", "Unión", "Sporting", "Racing", "Juventud", "Estrella",
            "Social", "Defensores de", "Academia", "Independiente", "Ferro", "Talleres de", "Atlético Club"]
NUCLEOS = ["Cóndor", "Puma", "Huemul", "Pacífico", "Austral", "Litoral", "Pampa", "Volcán", "Araucaria", "Copihue",
           "Quebracho", "Ñandú", "Hornero", "Cordillera", "Río Claro", "Costa Azul", "Valle Verde", "Cerro Alto",
           "Puerto Norte", "Bahía Sur", "Laguna", "Altiplano", "Desierto", "Patagonia", "Tamarugo", "Algarrobo",
           "Lenga", "Canelo", "Peumo", "Quillay", "Albatros", "Gaviota", "Zorro", "Guanaco", "Vicuña", "Picaflor",
           "Tero", "Chajá", "Yaguareté", "Carpincho", "Salitre", "Cobre", "Granito", "Brisa", "Aurora", "Centinela"]
ESTADIOS = ["La Caldera", "Los Aromos", "El Mirador", "Las Palmas", "Del Bosque", "La Fortaleza", "El Bastión",
            "Los Pinos", "La Olla", "El Coloso", "Las Acacias", "La Ribera", "El Faro", "Los Cerezos", "La Colina",
            "El Trébol", "Las Gaviotas", "El Gigante del Sur", "El Remanso", "Los Álamos", "El Nido",
            "La Cantera", "Las Vertientes", "El Polvorín", "La Herradura"]
# pares de colores (principal, secundario)
COLORES = [("#c8102e", "#ffffff"), ("#0b3d91", "#ffd100"), ("#006b3f", "#ffffff"), ("#111111", "#f2c94c"),
           ("#5b2a86", "#ffffff"), ("#f47b20", "#1b1b1b"), ("#0a7ea4", "#ffffff"), ("#8b0000", "#f2c94c"),
           ("#1f8a52", "#111111"), ("#ffffff", "#c8102e"), ("#ffd100", "#0b3d91"), ("#3a3a3a", "#e5534b"),
           ("#7ec8e3", "#0b3d91"), ("#ffffff", "#111111"), ("#a0522d", "#ffffff"), ("#e91e63", "#111111")]
FORMAS = ["clasico", "redondo", "hexagono", "moderno"]
SIMBOLOS = ["ninguno", "franjas", "banda", "mitad", "estrella", "balon"]


def iniciales(nombre: str) -> str:
    ignorar = {"de", "del", "la", "las", "los", "y", "club", "fc"}
    palabras = [w for w in nombre.replace("-", " ").split() if w.lower() not in ignorar] or nombre.split()
    return "".join(w[0] for w in palabras[:3]).upper()


def generar_bots(cantidad: int, semilla, prohibidos: set[str]) -> list[dict]:
    """`cantidad` identidades únicas: {"nombre", "estadio", "escudo": dict}."""
    rng = random.Random(f"{semilla}-bots")
    usados, salida = {n.lower() for n in prohibidos}, []
    combinaciones = [(p, n) for p in PREFIJOS for n in NUCLEOS]
    rng.shuffle(combinaciones)
    nucleos_usados = set()
    for prefijo, nucleo in combinaciones:
        if len(salida) >= cantidad:
            break
        nombre = f"{prefijo} {nucleo}"
        if nucleo in nucleos_usados or nombre.lower() in usados:
            continue  # un núcleo por club, para que no haya "Atlético Puma" y "Real Puma"
        nucleos_usados.add(nucleo)
        usados.add(nombre.lower())
        c1, c2 = rng.choice(COLORES)
        salida.append({
            "nombre": nombre,
            "estadio": f"Estadio {rng.choice(ESTADIOS)}" if rng.random() < 0.6 else f"Estadio {nucleo}",
            "escudo": {"forma": rng.choice(FORMAS), "c1": c1, "c2": c2, "simbolo": rng.choice(SIMBOLOS),
                       "texto": iniciales(nombre)},
        })
    return salida


def escudo_por_defecto(nombre: str) -> dict:
    rng = random.Random(nombre)
    c1, c2 = rng.choice(COLORES)
    return {"forma": "clasico", "c1": c1, "c2": c2, "simbolo": "banda", "texto": iniciales(nombre)}


def _contraste(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return "#ffffff"
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 160 else "#ffffff"


def _color(valor: str, defecto: str) -> str:
    valor = str(valor or "")
    return valor if len(valor) in (4, 7) and valor.startswith("#") and all(c in "0123456789abcdefABCDEF" for c in valor[1:]) else defecto


FORMA_SVG = {
    "clasico": '<path d="M8 6 H92 V58 C92 88 72 104 50 116 C28 104 8 88 8 58 Z"/>',
    "redondo": '<circle cx="50" cy="60" r="48"/>',
    "hexagono": '<polygon points="50,4 95,28 95,90 50,116 5,90 5,28"/>',
    "moderno": '<path d="M14 4 H86 L96 24 V74 L50 116 L4 74 V24 Z"/>',
}


def escudo_svg(d: dict | str) -> str:
    """SVG del escudo a partir de su diseño {"forma", "c1", "c2", "simbolo", "texto"}."""
    if isinstance(d, str):
        d = json.loads(d) if d.strip().startswith("{") else {}
    forma = FORMA_SVG.get(d.get("forma"), FORMA_SVG["clasico"])
    c1, c2 = _color(d.get("c1"), "#1f8a52"), _color(d.get("c2"), "#ffffff")
    simbolo = d.get("simbolo", "ninguno")
    texto = html.escape(str(d.get("texto", ""))[:3].upper())
    relleno = {
        "franjas": "".join(f'<rect x="{x}" y="0" width="12" height="120" fill="{c2}"/>' for x in (14, 38, 62, 86)),
        "banda": f'<polygon points="0,30 30,0 100,90 70,120" fill="{c2}"/>',
        "mitad": f'<rect x="50" y="0" width="50" height="120" fill="{c2}"/>',
        "estrella": f'<polygon fill="{c2}" points="50,14 55,28 70,28 58,37 62,51 50,42 38,51 42,37 30,28 45,28"/>',
        "balon": f'<circle cx="50" cy="30" r="13" fill="{c2}"/><polygon fill="{c1}" points="50,23 57,28 54,36 46,36 43,28"/>',
    }.get(simbolo, "")
    tinta = _contraste(c2 if simbolo == "mitad" else c1)
    # en "mitad" el texto queda sobre los dos colores: se le pone contorno
    contorno = f' stroke="{_contraste(tinta)}" stroke-width="1.5" paint-order="stroke"'
    y_texto = 82 if simbolo in ("estrella", "balon") else 72
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 120">'
            f'<defs><clipPath id="f">{forma}</clipPath></defs>'
            f'<g clip-path="url(#f)"><rect width="100" height="120" fill="{c1}"/>{relleno}</g>'
            f'<g fill="none" stroke="{c2}" stroke-width="5">{forma}</g>'
            f'<g fill="none" stroke="rgba(0,0,0,.25)" stroke-width="1.5">{forma}</g>'
            f'<text x="50" y="{y_texto}" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" '
            f'font-weight="900" font-size="{30 if len(texto) <= 2 else 26}" fill="{tinta}"{contorno}>{texto}</text></svg>')
