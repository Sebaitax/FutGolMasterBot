"""Descarga fotos de los jugadores de una liga desde Wikimedia Commons.

Usa la foto oficial de cada jugador en Wikidata (propiedad P18). Son imágenes con
licencia libre (CC-BY, CC-BY-SA o dominio público): el autor y la licencia quedan
en assets/renders/creditos.json. Usa las APIs públicas, sin scraping de HTML.

Con --recortar quita el fondo (requiere `pip install rembg`; la primera vez baja
un modelo de ~170 MB) para que quede como un render.

Uso:
    python -m scraper.fotos --liga chile                  # todas las que falten
    python -m scraper.fotos --liga argentina --recortar   # y además quitar el fondo
    python -m scraper.fotos --club "Colo-Colo" --forzar
    python -m scraper.fotos --liga argentina --recortar --buscar   # además busca a quienes no tienen foto oficial

Con --buscar, para los jugadores sin foto en su ficha:
  1. sin ficha en Wikidata: se busca por nombre y solo se acepta si es futbolista y nació el
     mismo año que dice el plantel;
  2. con ficha pero sin foto: se busca en Commons un archivo cuyo nombre contenga el nombre
     completo del jugador (se descartan fotos grupales, logos, firmas…).

Requiere haber corrido scraper.plantillas, scraper.estadisticas y cartas.valoracion.
"""
import argparse
import csv
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from scraper.ligas import archivo_cartas, archivo_planteles, archivo_stats, liga

UA = {"User-Agent": "FutGolMasterBot/0.1 (https://github.com/Sebaitax/FutGolMasterBot)"}
RENDERS = Path("assets/renders")
CREDITOS = RENDERS / "creditos.json"
ANCHO = 600


def _get(url: str, binario: bool = False):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read() if binario else json.load(r)


def _api(base: str, **params) -> dict:
    return _get(base + "?" + urllib.parse.urlencode({**params, "format": "json"}))


def archivos_p18(qids: list[str]) -> dict[str, str]:
    """QID -> nombre del archivo de la foto en Commons."""
    fotos = {}
    for i in range(0, len(qids), 50):
        ents = _api("https://www.wikidata.org/w/api.php", action="wbgetentities", ids="|".join(qids[i:i + 50]),
                    props="claims")["entities"]
        for qid, e in ents.items():
            p18 = e.get("claims", {}).get("P18", [])
            if p18:
                fotos[qid] = p18[0]["mainsnak"]["datavalue"]["value"]
        time.sleep(0.2)
    return fotos


def info_archivo(nombre: str) -> dict | None:
    datos = _api("https://commons.wikimedia.org/w/api.php", action="query", titles=f"File:{nombre}",
                 prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=ANCHO)
    pagina = next(iter(datos["query"]["pages"].values()))
    if "imageinfo" not in pagina:
        return None
    ii = pagina["imageinfo"][0]
    meta = ii.get("extmetadata", {})
    limpiar = lambda s: re.sub(r"<[^>]+>", "", s or "").strip()
    return {
        "url": ii.get("thumburl") or ii["url"],
        "pagina": ii.get("descriptionurl", ""),
        "autor": limpiar(meta.get("Artist", {}).get("value")),
        "licencia": limpiar(meta.get("LicenseShortName", {}).get("value")),
    }


def _solo_figura_central(imagen: Image.Image) -> Image.Image:
    """Tras quitar el fondo, deja solo la figura que toca el centro de la imagen
    (en fotos grupales elimina a los compañeros que no están pegados al jugador)."""
    alfa = imagen.getchannel("A")
    chico = alfa.resize((max(1, alfa.width // 4), max(1, alfa.height // 4)))
    w, h = chico.size
    px = chico.load()
    lleno = lambda x, y: px[x, y] > 128
    # punto de partida: el pixel opaco más cercano al centro (algo arriba: torso/cara)
    cx, cy = w // 2, int(h * 0.45)
    inicio = min(((x, y) for x in range(w) for y in range(h) if lleno(x, y)),
                 key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2, default=None)
    if inicio is None:
        return imagen
    visto, pila = {inicio}, [inicio]
    while pila:
        x, y = pila.pop()
        for v in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= v[0] < w and 0 <= v[1] < h and v not in visto and lleno(*v):
                visto.add(v)
                pila.append(v)
    mascara = Image.new("L", (w, h), 0)
    mp = mascara.load()
    for x, y in visto:
        mp[x, y] = 255
    mascara = mascara.resize(alfa.size)
    imagen.putalpha(Image.composite(alfa, Image.new("L", alfa.size, 0), mascara))
    return imagen


def _encuadre_vertical(imagen: Image.Image) -> Image.Image:
    """Recorte 3:4 centrado, cargado hacia arriba (donde suele estar la cara)."""
    w, h = imagen.size
    objetivo = 3 / 4
    if w / h > objetivo:
        nuevo_w = int(h * objetivo)
        x = (w - nuevo_w) // 2
        imagen = imagen.crop((x, 0, x + nuevo_w, h))
    else:
        nuevo_h = int(w / objetivo)
        imagen = imagen.crop((0, 0, w, min(h, nuevo_h)))
    return imagen


import unicodedata

FUTBOLISTA = "Q937857"
DESCARTAR = ("team", "equipo", "plantel", "plantilla", "squad", "formacion", "formación", "logo", "escudo",
             "firma", "signature", "autograph", "camiseta", "shirt", " vs ", " vs.", " and ", " y ", " e ", "estadio",
             "stadium", "trophy", "trofeo", "selfie", "con ")


def _plano(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _palabras(texto: str) -> str:
    """Texto plano con signos convertidos en espacios ("O'Higgins." -> " o higgins ")."""
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", _plano(texto)).split()) + " "


def buscar_qid(nombre: str, anio: str) -> str | None:
    """Ficha de Wikidata de un futbolista por nombre, validada por año de nacimiento."""
    if not anio:
        return None
    try:
        r = _api("https://www.wikidata.org/w/api.php", action="wbsearchentities", search=nombre, language="es",
                 type="item", limit=7)
        ids = [x["id"] for x in r.get("search", [])]
        if not ids:
            return None
        ents = _api("https://www.wikidata.org/w/api.php", action="wbgetentities", ids="|".join(ids), props="claims")["entities"]
    except Exception:
        return None
    for qid in ids:
        c = ents.get(qid, {}).get("claims", {})
        ocupaciones = {x["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for x in c.get("P106", [])}
        nacido = [x["mainsnak"].get("datavalue", {}).get("value", {}).get("time", "") for x in c.get("P569", [])]
        if FUTBOLISTA in ocupaciones and any(n[1:5] == anio for n in nacido):
            return qid
    return None


def buscar_en_commons(nombre: str) -> str | None:
    """Archivo de Commons cuyo nombre contiene el nombre completo del jugador (sin fotos grupales)."""
    palabras = [w for w in _plano(nombre).replace("-", " ").split() if len(w) > 1]
    if len(palabras) < 2:
        return None  # un solo nombre (p. ej. "Vozinha") es demasiado ambiguo
    try:
        r = _api("https://commons.wikimedia.org/w/api.php", action="query", list="search", srnamespace=6,
                 srsearch=f'"{nombre}"', srlimit=10)
    except Exception:
        return None
    for x in r.get("query", {}).get("search", []):
        titulo = x["title"].split(":", 1)[-1]
        plano = " " + _plano(titulo).replace("_", " ").replace("-", " ") + " "
        if not titulo.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        if all(f" {w}" in plano or f"{w} " in plano for w in palabras) and not any(d in plano for d in DESCARTAR):
            if es_de_futbol(titulo):  # evita homónimos (p. ej. un político con el mismo nombre)
                return titulo
    return None


FUTBOL = ("futbol", "football", "soccer", "calcio", "futebol", "fussball")
_CLUBES: list[str] = []


def clubes_conocidos() -> list[str]:
    """Nombres de los clubes de nuestras ligas (normalizados), p. ej. "coquimbo unido", "colo colo"."""
    if not _CLUBES:
        import glob
        for ruta in glob.glob("data/cartas_liga_*_2026.csv"):
            with open(ruta, newline="", encoding="utf-8") as f:
                for fila in csv.DictReader(f):
                    nombre = _palabras(fila["Club"].split("(")[0]).strip()
                    if len(nombre) >= 5 and nombre not in _CLUBES:
                        _CLUBES.append(nombre)
    return _CLUBES


def es_de_futbol(titulo: str) -> bool:
    """True si el nombre del archivo o sus categorías mencionan un club de nuestras ligas
    (evita homónimos: políticos, actores u otros futbolistas que se llaman igual)."""
    try:
        r = _api("https://commons.wikimedia.org/w/api.php", action="query", titles=f"File:{titulo}",
                 prop="categories", cllimit=50)
    except Exception:
        return False
    textos = [_palabras(titulo)]
    for pagina in r.get("query", {}).get("pages", {}).values():
        textos += [_palabras(c["title"]) for c in pagina.get("categories", [])]
    # una categoría de fútbol genérica no basta: puede ser otro futbolista con el mismo nombre
    # (p. ej. Luis Díaz, el colombiano). Tiene que mencionar un club de nuestras ligas.
    return any(f" {club} " in t for t in textos for club in clubes_conocidos())


def preparar(imagen: Image.Image, recortar) -> Image.Image:
    """Encuadra en vertical y, si hay rembg, quita el fondo y a los demás jugadores."""
    imagen = _encuadre_vertical(imagen.convert("RGBA"))
    if recortar:
        imagen = _solo_figura_central(recortar(imagen))
        caja = imagen.getchannel("A").getbbox()
        if caja:
            imagen = imagen.crop(caja)
    return imagen


def cargar_recortador():
    try:
        from rembg import new_session, remove
    except ImportError:
        sys.exit("Para --recortar instala rembg:  pip install rembg")
    sesion = new_session("u2net_human_seg")
    return lambda img: remove(img, session=sesion)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Fotos libres de jugadores (Wikimedia Commons).")
    p.add_argument("--liga", default="chile")
    p.add_argument("--anio", type=int, default=2026)
    p.add_argument("--club", help="Solo un club (nombre como en el CSV de cartas)")
    p.add_argument("--recortar", action="store_true", help="Quitar el fondo con rembg")
    p.add_argument("--forzar", action="store_true", help="Volver a bajar aunque ya exista")
    p.add_argument("--buscar", action="store_true", help="Buscar también a quienes no tienen foto oficial")
    args = p.parse_args()

    liga(args.liga)
    planteles = json.loads(Path(archivo_planteles(args.liga, args.anio)).read_text(encoding="utf-8"))
    stats = json.loads(Path(archivo_stats(args.liga, args.anio)).read_text(encoding="utf-8"))
    with open(archivo_cartas(args.liga, args.anio), newline="", encoding="utf-8") as f:
        cartas = list(csv.DictReader(f))

    # nombre de la carta -> artículo de Wikipedia -> QID; y año de nacimiento (para validar búsquedas)
    articulo, nacimiento = {}, {}
    for club in planteles["clubes"]:
        for j in club["jugadores"]:
            clave = j["nombre"].split("(")[0].strip()
            if j.get("wiki_es"):
                articulo[clave] = j["wiki_es"]
            nacimiento[clave] = (j.get("nacimiento") or "")[:4]
    qid_por_articulo = stats.get("wikidata", {})

    objetivo = []  # (nombre, qid o None), los mejores primero
    for c in sorted(cartas, key=lambda c: -int(c["OVR"])):
        if args.club and c["Club"].lower() != args.club.lower():
            continue
        if not args.forzar and (RENDERS / f"{c['Nombre']}.png").exists():
            continue
        qid = qid_por_articulo.get(articulo.get(c["Nombre"], ""))
        if qid or args.buscar:
            objetivo.append((c["Nombre"], qid))
    print(f"{len(objetivo)} jugadores sin foto todavía")

    fotos = archivos_p18([q for _, q in objetivo if q])
    print(f"{len(fotos)} tienen foto oficial en su ficha")
    recortar = cargar_recortador() if args.recortar else None
    RENDERS.mkdir(parents=True, exist_ok=True)
    creditos = json.loads(CREDITOS.read_text(encoding="utf-8")) if CREDITOS.exists() else {}

    bajadas = 0
    for nombre, qid in objetivo:
        origen = "ficha"
        if not qid and args.buscar:
            qid = buscar_qid(nombre, nacimiento.get(nombre, ""))
            if qid:
                fotos.update(archivos_p18([qid]))
                origen = "ficha encontrada por nombre y año"
        archivo = fotos.get(qid) if qid else None
        if not archivo and args.buscar:
            archivo = buscar_en_commons(nombre)
            origen = "búsqueda en Commons"
        if not archivo:
            continue
        try:
            info = info_archivo(archivo)
            if not info:
                continue
            imagen = Image.open(io.BytesIO(_get(info["url"], binario=True)))
            preparar(imagen, recortar).save(RENDERS / f"{nombre}.png", optimize=True)
        except Exception as e:  # una foto rota no corta el resto
            print(f"  ✗ {nombre}: {e}")
            continue
        creditos[nombre] = {"archivo": archivo, "autor": info["autor"], "licencia": info["licencia"],
                            "fuente": info["pagina"], "recortada": bool(recortar), "origen": origen}
        bajadas += 1
        print(f"  ✓ {nombre} ({info['licencia']}, {origen})", flush=True)
        if bajadas % 20 == 0:  # guardar avances por si se corta
            CREDITOS.write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(0.3)  # no saturar Commons

    CREDITOS.write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {bajadas} fotos nuevas en {RENDERS}/ · créditos en {CREDITOS}")


if __name__ == "__main__":
    main()
