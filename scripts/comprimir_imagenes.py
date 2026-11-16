"""Crea una versión .webp liviana al lado de cada imagen de assets (fotos de jugadores, escudos y estadios).

El juego usa la .webp si existe (si no, la original). Los originales no se tocan.
Las fotos pasan de ~140 KB a ~14 KB: es lo que más datos gasta el servidor.

    python -m scripts.comprimir_imagenes            # solo las que faltan o cambiaron
    python -m scripts.comprimir_imagenes --todas    # rehace todas
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

CARPETAS = [   # carpeta, extensiones de origen, tamaño máximo (px), calidad
    (Path("assets/renders"), (".png",), 320, 80),
    (Path("assets/escudos"), (".png",), 256, 86),
    (Path("assets/estadios"), (".jpg", ".jpeg", ".png"), 960, 74),
]


def convertir(origen: Path, maximo: int, calidad: int) -> int:
    destino = origen.with_suffix(".webp")
    with Image.open(origen) as im:
        im.load()
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "transparency" in im.info or im.mode in ("LA", "P") else "RGB")
        im.thumbnail((maximo, maximo), Image.LANCZOS)
        temporal = destino.with_suffix(".webp.tmp")
        im.save(temporal, "WEBP", quality=calidad, method=5)
    temporal.replace(destino)   # recién completa aparece (nunca se sirve una a medio escribir)
    return destino.stat().st_size


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--todas", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    for carpeta, exts, maximo, calidad in CARPETAS:
        if not carpeta.is_dir():
            continue
        antes = despues = hechas = errores = 0
        for f in sorted(carpeta.iterdir()):
            if f.suffix.lower() not in exts:
                continue
            w = f.with_suffix(".webp")
            if not a.todas and w.exists() and w.stat().st_mtime >= f.stat().st_mtime:
                continue
            try:
                despues += convertir(f, maximo, calidad)
                antes += f.stat().st_size
                hechas += 1
            except Exception as e:   # una imagen rota no frena el resto
                errores += 1
                print(f"  ! {f.name}: {e}")
        if hechas:
            print(f"{carpeta}: {hechas} convertidas · {antes / 2**20:.0f} MB -> {despues / 2**20:.0f} MB · errores {errores}")
        else:
            print(f"{carpeta}: nada nuevo")
    print(f"listo en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
