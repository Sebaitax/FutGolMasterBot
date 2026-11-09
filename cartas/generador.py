"""Generador de cartas con diseño propio de FutGolMasterBot.

Todo el diseño se dibuja por código (sin plantillas de terceros) y usa la
fuente libre Barlow Condensed (licencia OFL, ver assets/fonts/OFL.txt).

Uso desde la terminal:
    python -m cartas.generador data/cartas_ejemplo.csv --limite 5
    python -m cartas.generador data/cartas_oro_raras.csv --rara --salida assets/cartas
"""
import argparse
import csv
import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from models.carta import ETIQUETAS, STATS, Carta

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = RAIZ / "assets" / "fonts"
RENDERS = RAIZ / "assets" / "renders"
SALIDA = RAIZ / "assets" / "cartas"

# Tamaño final de la carta. Se dibuja al doble y se reduce para suavizar bordes.
ANCHO, ALTO = 600, 860
ESCALA = 2

# Paleta por nivel: degradado (arriba, abajo), color de acento y color de texto
PALETAS = {
    "bronce": {"arriba": (176, 112, 74), "abajo": (74, 40, 24), "acento": (240, 178, 128), "texto": (255, 240, 228)},
    "plata": {"arriba": (226, 232, 238), "abajo": (112, 124, 140), "acento": (255, 255, 255), "texto": (24, 30, 42)},
    "oro": {"arriba": (250, 214, 96), "abajo": (150, 98, 16), "acento": (255, 246, 200), "texto": (40, 26, 4)},
}


def _px(valor: float) -> int:
    return int(valor * ESCALA)


def _fuente(peso: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FUENTES / f"BarlowCondensed-{peso}.ttf"), _px(tam))


def _fuente_ajustada(texto: str, peso: str, tam: int, ancho_max: int) -> ImageFont.FreeTypeFont:
    """Reduce el tamaño de la fuente hasta que el texto quepa en ancho_max."""
    while tam > 12:
        fuente = _fuente(peso, tam)
        if fuente.getlength(texto) <= _px(ancho_max):
            return fuente
        tam -= 2
    return _fuente(peso, tam)


def _silueta_carta() -> list:
    """Contorno de la carta: rectángulo con dos esquinas cortadas en diagonal."""
    c = 70  # tamaño del corte
    w, h = ANCHO - 1, ALTO - 1
    puntos = [(0, 0), (w - c, 0), (w, c), (w, h), (c, h), (0, h - c)]
    return [(_px(x), _px(y)) for x, y in puntos]


def _degradado(arriba, abajo) -> Image.Image:
    w, h = _px(ANCHO), _px(ALTO)
    franja = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        franja.putpixel((0, y), tuple(int(a + (b - a) * t) for a, b in zip(arriba, abajo)))
    return franja.resize((w, h))


def _patron_rara(acento) -> Image.Image:
    """Franjas diagonales semitransparentes para las cartas raras."""
    w, h = _px(ANCHO), _px(ALTO)
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    paso = _px(34)
    for x in range(-h, w, paso):
        d.line([(x, h), (x + h, 0)], fill=(*acento, 38), width=_px(10))
    return capa


def _silueta_jugador(acento) -> Image.Image:
    """Figura genérica cuando el jugador todavía no tiene render."""
    w, h = _px(330), _px(400)
    capa = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    color = (*acento, 90)
    cx = w // 2
    d.ellipse([cx - _px(70), _px(40), cx + _px(70), _px(190)], fill=color)
    d.pieslice([cx - _px(165), _px(210), cx + _px(165), _px(560)], 180, 360, fill=color)
    return capa


def buscar_render(carta: Carta) -> Path | None:
    """Busca el render del jugador en assets/renders (nombre_ovr.png o nombre.png)."""
    for nombre in (f"{carta.nombre}_{carta.ovr}.png", f"{carta.nombre}.png"):
        ruta = RENDERS / nombre
        if ruta.exists():
            return ruta
    return None


def crear_carta(carta: Carta, render: str | Path | None = None) -> Image.Image:
    """Dibuja la carta y devuelve la imagen (RGBA, ANCHO x ALTO)."""
    paleta = PALETAS[carta.nivel]
    acento, texto = paleta["acento"], paleta["texto"]
    w, h = _px(ANCHO), _px(ALTO)

    # --- Fondo con la forma de la carta ---
    fondo = _degradado(paleta["arriba"], paleta["abajo"]).convert("RGBA")
    if carta.rara:
        fondo = Image.alpha_composite(fondo, _patron_rara(acento))

    mascara = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mascara).polygon(_silueta_carta(), fill=255)
    lienzo = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    lienzo.paste(fondo, (0, 0), mascara)
    d = ImageDraw.Draw(lienzo)

    # Borde interior
    borde = _silueta_carta()
    d.line(borde + [borde[0]], fill=(*acento, 255), width=_px(10 if carta.rara else 6))

    # --- Imagen del jugador ---
    render = render or buscar_render(carta)
    caja = (_px(190), _px(40), _px(580), _px(500))  # x0, y0, x1, y1
    if render:
        foto = Image.open(render).convert("RGBA")
        alto_caja = caja[3] - caja[1]
        foto = foto.resize((int(foto.width * alto_caja / foto.height), alto_caja), Image.LANCZOS)
        x = caja[0] + (caja[2] - caja[0] - foto.width) // 2
        lienzo.alpha_composite(foto, (max(x, 0), caja[1]))
    else:
        silueta = _silueta_jugador(acento)
        lienzo.alpha_composite(silueta, (caja[0] + _px(30), caja[1] + _px(60)))

    # --- Valoración, posición y nivel (columna izquierda) ---
    f_ovr = _fuente("Bold", 150)
    d.text((_px(40), _px(20)), str(carta.ovr), font=f_ovr, fill=texto)
    d.text((_px(46), _px(178)), carta.posicion, font=_fuente("SemiBold", 58), fill=texto)
    d.line([(_px(46), _px(256)), (_px(150), _px(256))], fill=(*acento, 255), width=_px(4))
    etiqueta_nivel = carta.nivel.upper() + (" · RARA" if carta.rara else "")
    d.text((_px(46), _px(268)), etiqueta_nivel, font=_fuente("Medium", 30), fill=texto)

    # --- Banda del nombre ---
    banda = Image.new("RGBA", (w, _px(84)), (0, 0, 0, 70))
    lienzo.alpha_composite(banda, (0, _px(500)))
    nombre = carta.nombre_corto.upper()
    f_nombre = _fuente_ajustada(nombre, "Bold", 66, ANCHO - 80)
    d.text((w // 2, _px(542)), nombre, font=f_nombre, fill=(255, 255, 255), anchor="mm")

    # --- Estadísticas: 2 columnas x 3 filas con barra ---
    f_val = _fuente("Bold", 44)
    f_lbl = _fuente("Medium", 30)
    for i, stat in enumerate(STATS):
        col, fila = divmod(i, 3)
        x = _px(48 + col * 270)
        y = _px(605 + fila * 66)
        valor = carta.stats.get(stat, 0)
        d.text((x, y), str(valor), font=f_val, fill=texto)
        d.text((x + _px(64), y + _px(10)), ETIQUETAS[stat], font=f_lbl, fill=texto)
        bx0, by = x + _px(118), y + _px(28)
        bx1 = bx0 + _px(110)
        d.rounded_rectangle([bx0, by, bx1, by + _px(10)], radius=_px(5), fill=(0, 0, 0, 60))
        largo = int((bx1 - bx0) * max(0, min(valor, 99)) / 99)
        if largo > 0:
            d.rounded_rectangle([bx0, by, bx0 + largo, by + _px(10)], radius=_px(5), fill=(*acento, 255))

    # --- Pie: club y nación como texto ---
    pie = " · ".join(p for p in (carta.club, carta.nacion) if p)
    if pie:
        f_pie = _fuente_ajustada(pie.upper(), "Medium", 28, ANCHO - 160)
        d.text((w // 2, _px(812)), pie.upper(), font=f_pie, fill=texto, anchor="mm")

    # Marca propia
    d.text((w - _px(96), _px(16)), "FGM", font=_fuente("Bold", 26), fill=(*acento, 200))

    # Sombra suave y reducción al tamaño final
    sombra = mascara.filter(ImageFilter.GaussianBlur(_px(4)))
    resultado = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    resultado.paste((0, 0, 0, 90), (0, 0), sombra)
    resultado.alpha_composite(lienzo)
    return resultado.resize((ANCHO, ALTO), Image.LANCZOS)


def carta_a_bytes(carta: Carta) -> BytesIO:
    """Genera la carta en memoria como PNG (para enviarla por Discord)."""
    buffer = BytesIO()
    crear_carta(carta).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def nombre_archivo(carta: Carta) -> str:
    seguro = "".join(c if c.isalnum() or c in " -_" else "_" for c in carta.nombre)
    return f"{seguro.strip().replace(' ', '_')}_{carta.ovr}.png"


def main():
    parser = argparse.ArgumentParser(description="Genera imágenes de cartas desde un CSV.")
    parser.add_argument("csv", help="CSV con columnas Nombre, Alias, Posición, Club, Nación, Liga, OVR, PAC...")
    parser.add_argument("--rara", action="store_true", help="Marca todas las cartas del CSV como raras")
    parser.add_argument("--limite", type=int, default=None, help="Cantidad máxima de cartas a generar")
    parser.add_argument("--salida", default=str(SALIDA), help="Carpeta de salida")
    args = parser.parse_args()

    os.makedirs(args.salida, exist_ok=True)
    with open(args.csv, newline="", encoding="utf-8") as archivo:
        filas = list(csv.DictReader(archivo))[: args.limite]

    for fila in filas:
        carta = Carta.desde_csv(fila, rara=args.rara)
        ruta = Path(args.salida) / nombre_archivo(carta)
        crear_carta(carta).save(ruta)
        print(f"OK  {ruta}")


if __name__ == "__main__":
    main()
