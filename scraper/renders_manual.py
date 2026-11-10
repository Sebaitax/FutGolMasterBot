"""Renders bajados a mano: lista de faltantes e importación.

1) Ver quién no tiene render (abre el HTML en tu navegador, con enlaces de búsqueda):
       python -m scraper.renders_manual pendientes
       python -m scraper.renders_manual pendientes --club "Universidad Católica" --min-ovr 70

2) Guarda en assets/renders/entrada/ las imágenes que bajes (el nombre del archivo
   debe parecerse al del jugador, p. ej. "arturo-vidal-render.png").

3) Importarlas (las empareja con el jugador, las convierte a PNG y las renombra):
       python -m scraper.renders_manual importar
       python -m scraper.renders_manual importar --recortar      # además quita el fondo (rembg)

Las cartas usan assets/renders/<Nombre>.png. Todo queda solo en tu PC (assets/renders/
está en .gitignore).
"""
import argparse
import csv
import difflib
import html
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

from PIL import Image

RENDERS = Path("assets/renders")
ENTRADA = RENDERS / "entrada"
CATALOGOS = "data/cartas_liga_*_2026.csv"  # todas las ligas descargadas
EXTENSIONES = {".png", ".webp", ".jpg", ".jpeg"}
# palabras que suelen venir en los nombres de archivo y no son del jugador
RUIDO = {"render", "renders", "png", "fc", "fifa", "ea", "full", "hd", "pro", "futboleros", "prorendersfutboleros",
         "transparent", "transparente", "sin", "fondo", "liga", "chilena", "footyrenders", "card", "carta"}


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.split(r"[^a-z0-9]+", t) if w and w not in RUIDO and not w.isdigit())


def cargar_cartas(patron: str = CATALOGOS) -> list[dict]:
    import glob
    cartas = []
    for ruta in sorted(glob.glob(patron)):
        with open(ruta, newline="", encoding="utf-8") as f:
            cartas += list(csv.DictReader(f))
    return cartas


def tiene_render(nombre: str, club: str = "") -> bool:
    return (RENDERS / f"{nombre} ({club}).png").exists() or (RENDERS / f"{nombre}.png").exists()


def pendientes(args):
    cartas = [c for c in cargar_cartas() if not tiene_render(c["Nombre"], c["Club"])
              and int(c["OVR"]) >= args.min_ovr and (not args.club or c["Club"].lower() == args.club.lower())]
    cartas.sort(key=lambda c: (c["Club"], -int(c["OVR"])))
    total = len(cargar_cartas())
    filas = []
    club_actual = None
    for c in cartas:
        if c["Club"] != club_actual:
            club_actual = c["Club"]
            filas.append(f'<tr class="club"><td colspan="4">{html.escape(club_actual)}</td></tr>')
        consulta = f'{c["Nombre"]} {c["Club"]}'
        buscar = lambda base, q: base + urllib.parse.quote_plus(q)
        enlaces = " · ".join([
            f'<a href="{buscar("https://www.google.com/search?tbm=isch&q=", consulta + " render png")}" target="_blank">Google</a>',
            f'<a href="{buscar("https://duckduckgo.com/?iax=images&ia=images&q=", consulta + " png transparente")}" target="_blank">DuckDuckGo</a>',
            f'<a href="{buscar("https://www.footyrenders.com/?s=", c["Nombre"])}" target="_blank">FootyRenders</a>',
        ])
        archivo = re.sub(r"[^\w]+", "-", _plano(c["Nombre"])) + ".png"
        filas.append(f'<tr><td><b>{c["OVR"]}</b></td><td>{html.escape(c["Nombre"])}<br><small>{c["Posición"]}</small></td>'
                     f'<td><code>{archivo}</code></td><td>{enlaces}</td></tr>')
    salida = Path("data/renders_pendientes.html")
    salida.parent.mkdir(exist_ok=True)
    salida.write_text(f"""<!doctype html><meta charset="utf-8"><title>Renders pendientes</title>
<style>body{{font:15px system-ui;margin:24px;background:#0d1512;color:#e6eee9}}a{{color:#2fbf71}}
td{{padding:6px 10px;border-bottom:1px solid #26352f}}tr.club td{{background:#16211d;font-weight:700;padding-top:14px}}
small{{color:#8fa39a}}code{{color:#e3b947}}</style>
<h1>Renders pendientes: {len(cartas)} de {total}</h1>
<p>Guarda cada imagen en <code>{ENTRADA.resolve()}</code> con un nombre parecido al sugerido y luego corre
<code>python -m scraper.renders_manual importar</code>.</p>
<table>{''.join(filas)}</table>""", encoding="utf-8")
    ENTRADA.mkdir(parents=True, exist_ok=True)
    print(f"{len(cartas)} jugadores sin render -> abre {salida.resolve()}")
    print(f"Guarda las imágenes en {ENTRADA.resolve()}")


def emparejar(archivo: Path, cartas: list[dict], club: str | None) -> dict | None:
    buscado = _plano(archivo.stem)
    if not buscado:
        return None
    candidatos = [c for c in cartas if not club or c["Club"].lower() == club.lower()]
    nombres = {_plano(c["Nombre"]): c for c in candidatos}
    if buscado in nombres:
        return nombres[buscado]
    # todas las palabras del jugador aparecen en el archivo (p. ej. "arturo vidal colo colo")
    contenidos = [c for k, c in nombres.items() if set(k.split()) <= set(buscado.split())]
    if len(contenidos) == 1:
        return contenidos[0]
    parecido = difflib.get_close_matches(buscado, list(nombres), n=1, cutoff=0.72)
    return nombres[parecido[0]] if parecido else None


def importar(args):
    from scraper.fotos import cargar_recortador, preparar
    cartas = cargar_cartas()
    archivos = sorted(p for p in ENTRADA.glob("*") if p.suffix.lower() in EXTENSIONES)
    if not archivos:
        print(f"No hay imágenes en {ENTRADA.resolve()}")
        return
    recortar = cargar_recortador() if args.recortar else None
    hechos, sin_par = 0, []
    for archivo in archivos:
        carta = emparejar(archivo, cartas, args.club)
        if not carta:
            sin_par.append(archivo.name)
            continue
        imagen = Image.open(archivo).convert("RGBA")
        if recortar:
            imagen = preparar(imagen, recortar)
        else:
            caja = imagen.getchannel("A").getbbox()  # los renders ya vienen sin fondo: solo se ajusta
            imagen = imagen.crop(caja) if caja else imagen
        destino = RENDERS / f"{carta['Nombre']}.png"
        imagen.save(destino, optimize=True)
        (ENTRADA / "importados").mkdir(exist_ok=True)
        archivo.replace(ENTRADA / "importados" / archivo.name)
        hechos += 1
        print(f"  ✓ {archivo.name} -> {destino.name} ({carta['Club']}, {carta['OVR']})")
    print(f"OK: {hechos} importados")
    if sin_par:
        print("Sin emparejar (renómbralos con el nombre del jugador):")
        for n in sin_par:
            print("  ·", n)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Renders bajados a mano.")
    sub = p.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("pendientes", help="Genera data/renders_pendientes.html")
    a.add_argument("--club")
    a.add_argument("--min-ovr", type=int, default=0)
    b = sub.add_parser("importar", help="Importa las imágenes de assets/renders/entrada/")
    b.add_argument("--club", help="Ayuda a emparejar si hay apellidos repetidos")
    b.add_argument("--recortar", action="store_true", help="Quitar el fondo con rembg")
    args = p.parse_args()
    {"pendientes": pendientes, "importar": importar}[args.comando](args)


if __name__ == "__main__":
    main()
