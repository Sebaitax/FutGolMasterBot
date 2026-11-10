"""Descarga los planteles de una liga desde Wikipedia en español.

Fuente: la sección "Plantilla <año>" o "Plantel <año>" de la página de cada club
(plantilla {{Jugador de fútbol}}). Usa la API pública de MediaWiki; no hace scraping de HTML.

Uso:
    python -m scraper.plantillas --liga chile        # -> data/liga_chile_2026.json
    python -m scraper.plantillas --liga argentina    # -> data/liga_argentina_2026.json

⚠️ Contiene nombres de personas reales: es solo para desarrollo local. data/ está
en .gitignore y antes de publicar la app se reemplazan por jugadores ficticios.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from scraper.ligas import archivo_planteles, liga

UA = {"User-Agent": "FutGolMasterBot/0.1 (https://github.com/Sebaitax/FutGolMasterBot)"}
WIKI = "https://es.wikipedia.org/w/api.php"
POSICIONES = {"POR": "POR", "ARQ": "POR", "DEF": "DEF", "MED": "MED", "DEL": "DEL"}  # ARQ = arquero


def _get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def _api(base: str, **params) -> dict:
    return _get(base + "?" + urllib.parse.urlencode({**params, "format": "json"}))


def wikitext(titulo: str) -> str:
    return _api(WIKI, action="parse", page=titulo, prop="wikitext", redirects=1, formatversion=2)["parse"]["wikitext"]


def _campos(texto: str) -> dict:
    campos = {}
    for parte in re.split(r"\|(?![^\[\{]*[\]\}])", texto):
        clave, sep, valor = parte.partition("=")
        if sep:
            campos[clave.strip().lower()] = valor.strip()
    return campos


def _plantillas(texto: str, nombre: str) -> list[str]:
    """Contenido de cada {{nombre|...}} contando llaves (pueden ocupar varias líneas)."""
    salida = []
    for m in re.finditer(r"\{\{\s*" + re.escape(nombre) + r"\s*\|", texto):
        i, nivel = m.end(), 2
        while i < len(texto) and nivel:
            if texto.startswith("{{", i):
                nivel += 2
                i += 2
            elif texto.startswith("}}", i):
                nivel -= 2
                i += 2
            else:
                i += 1
        salida.append(texto[m.end(): i - 2])
    return salida


def _desambiguar(clubes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Dos clubes con el mismo nombre visible: se agregan las iniciales de la ciudad
    tomadas del título ("Club Estudiantes de La Plata" -> "Estudiantes (LP)")."""
    repetidos = {n for n, _ in clubes if sum(1 for m, _ in clubes if m == n) > 1}
    salida = []
    for nombre, titulo in clubes:
        if nombre in repetidos:
            resto = titulo.split(nombre.split()[-1], 1)[-1] if nombre.split()[-1] in titulo else titulo
            iniciales = "".join(w[0] for w in re.findall(r"\w+", resto) if w[0].isupper())
            nombre = f"{nombre} ({iniciales or titulo})"
        salida.append((nombre, titulo))
    return salida


def plantel(titulo_es: str, anio: int) -> tuple[str, list[dict]]:
    w = wikitext(titulo_es)
    m = (re.search(rf"==+\s*(?:Plantilla|Plantel)[^=\n]*{anio}[^=\n]*==+", w)
         or re.search(r"==+\s*(?:Plantilla|Plantel)( actual)?\s*==+", w))
    if not m:
        return "", []
    bloque = w[m.end():]
    fin = re.search(r"\{\{\s*Equipo de fútbol fin", bloque)
    bloque = bloque[: fin.start()] if fin else bloque[:25000]

    jugadores = []
    for t in _plantillas(bloque, "Jugador de fútbol"):
        c = _campos(t.replace("\n", " "))
        # algunas páginas usan nombre/num/nac en vez de name/no/nat
        for ingles, espanol in (("name", "nombre"), ("no", "num"), ("nat", "nac")):
            if not c.get(ingles) and c.get(espanol):
                c[ingles] = c[espanol]
        enlace = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", c.get("name", ""))
        edad = re.search(r"edad\|(\d+)\|(\d+)\|(\d{4})", c.get("edad", ""))
        nombre = (enlace.group(2) or enlace.group(1)) if enlace else re.sub(r"\{\{[^}]*\}\}", "", c.get("name", "")).strip()
        nombre = re.sub(r"'{2,}", "", nombre).strip()  # negritas/cursivas del wikitexto ("Mateo '''Aimar'''")
        if not nombre:
            continue
        jugadores.append({
            "nombre": nombre,
            "wiki_es": enlace.group(1) if enlace else "",
            "dorsal": re.sub(r"\D", "", c.get("no", "")),
            "nacionalidad": c.get("nat", "").upper(),
            "posicion": POSICIONES.get(c.get("pos", "").upper(), c.get("pos", "").upper()),
            "nacimiento": f"{edad.group(3)}-{int(edad.group(2)):02d}-{int(edad.group(1)):02d}" if edad else "",
        })
    return m.group(0).strip("= "), jugadores


def clubes_desde_wikidata(qids: list[str]) -> list[tuple[str, str]]:
    """[(nombre corto, título en es.wikipedia)] a partir de IDs de Wikidata."""
    ents = _api("https://www.wikidata.org/w/api.php", action="wbgetentities", ids="|".join(qids),
                props="sitelinks|labels", sitefilter="eswiki", languages="es")["entities"]
    return [(ents[q]["labels"]["es"]["value"], ents[q]["sitelinks"]["eswiki"]["title"]) for q in qids]


def clubes_desde_temporada(pagina: str, seccion: str) -> list[tuple[str, str]]:
    """Primera columna de la tabla de equipos participantes: [[Título|Nombre]]."""
    w = wikitext(pagina)
    m = re.search(rf"\n(=+)\s*{re.escape(seccion)}\s*\1", w)
    fin = re.search(r"\n\|\}", w[m.end():]) if m else None  # el cierre va al inicio de línea ("|}}" de las refs no cuenta)
    tabla = w[m.end(): m.end() + fin.start()] if fin else ""
    clubes = []
    for fila in re.split(r"\n\|-[^\n]*", tabla)[1:]:
        celda = next((l for l in fila.strip().split("\n") if l.startswith("|")), "")
        e = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", celda)
        if e:
            clubes.append(((e.group(2) or e.group(1)).strip(), e.group(1).strip()))
    return clubes


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Descarga planteles de una liga.")
    p.add_argument("--liga", default="chile")
    p.add_argument("--anio", type=int, default=2026)
    p.add_argument("--salida", default=None)
    args = p.parse_args()
    cfg = liga(args.liga)
    salida = Path(args.salida or archivo_planteles(args.liga, args.anio))

    if cfg.get("clubes_wikidata"):
        lista = clubes_desde_wikidata(cfg["clubes_wikidata"])
    else:
        lista = clubes_desde_temporada(cfg["pagina_temporada"].format(anio=args.anio), cfg["seccion_equipos"])
    renombrar = cfg.get("renombrar", {})
    lista = [(renombrar.get(t, n), t) for n, t in _desambiguar(lista)]
    print(f"{len(lista)} clubes en {cfg['nombre']} {args.anio}")

    clubes = []
    for nombre, titulo in lista:
        seccion, jugadores = plantel(titulo, args.anio)
        clubes.append({"club": nombre, "wiki_es": titulo, "seccion": seccion, "jugadores": jugadores})
        print(f"{nombre[:40]:40} {len(jugadores):3} jugadores ({seccion or 'SIN PLANTEL'})")
        time.sleep(0.3)  # no saturar la API

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps({"liga": args.liga, "temporada": args.anio, "clubes": clubes}, ensure_ascii=False, indent=1),
                      encoding="utf-8")
    print(f"OK: {sum(len(c['jugadores']) for c in clubes)} jugadores -> {salida}")


if __name__ == "__main__":
    main()
