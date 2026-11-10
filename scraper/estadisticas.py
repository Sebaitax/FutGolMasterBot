"""Estadísticas de la temporada y perfil de los jugadores de una liga.

Fuentes (APIs públicas, sin scraping de HTML):
- Wikipedia en español: tabla de posiciones y, si la liga tiene anexo de estadísticas,
  goles y asistencias por equipo, rendimiento de arqueros y "jugador de la fecha".
- Wikidata (CC0): posición detallada, estatura, partidos con la selección adulta y
  trayectoria (partidos por club, ponderados por el nivel de la liga).

Requiere haber corrido antes `python -m scraper.plantillas --liga <clave>`.

Uso:
    python -m scraper.estadisticas --liga chile        # -> data/liga_chile_2026_stats.json
    python -m scraper.estadisticas --liga argentina
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from scraper.ligas import archivo_planteles, archivo_stats, liga

UA = {"User-Agent": "FutGolMasterBot/0.1 (https://github.com/Sebaitax/FutGolMasterBot)",
      "Accept": "application/json"}
WIKI = "https://es.wikipedia.org/w/api.php"
WIKIDATA = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"


def _get(url: str, data: bytes | None = None, accept: str | None = None) -> dict:
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=120) as r:
        return json.load(r)


def wikitext(titulo: str) -> str:
    q = urllib.parse.urlencode({"action": "parse", "page": titulo, "prop": "wikitext", "redirects": 1,
                                "format": "json", "formatversion": 2})
    return _get(f"{WIKI}?{q}")["parse"]["wikitext"]


def _seccion(texto: str, titulo: str) -> str:
    m = re.search(rf"\n(=+)\s*{re.escape(titulo)}\s*\1", texto)
    if not m:
        return ""
    nivel = len(m.group(1))
    resto = texto[m.end():]
    fin = re.search(rf"\n={{1,{nivel}}}[^=]", resto)
    return resto[: fin.start()] if fin else resto


def _filas(tabla: str) -> list[list[str]]:
    """Filas de una tabla wiki como listas de celdas de texto."""
    filas = []
    for bloque in re.split(r"\n\|-[^\n]*", tabla)[1:]:
        celdas = []
        for linea in bloque.strip().split("\n"):
            if linea.startswith("|") and not linea.startswith("|}"):
                celdas += [c.strip() for c in linea[1:].split("||")]
        if celdas:
            filas.append(celdas)
    return filas


def _jugador(celda: str) -> tuple[str, str]:
    """(nombre visible, título del artículo) desde una celda con [[Enlace|Nombre]]."""
    celda = re.sub(r"^align=\w+\|", "", celda)
    m = re.search(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", celda)
    if m:
        return (m.group(2) or m.group(1)).strip(), m.group(1).strip()
    limpio = re.sub(r"\{\{[^}]*\}\}", "", celda).strip()
    return limpio, ""


def _num(celda: str) -> int:
    m = re.search(r"-?\d+", re.sub(r"'''", "", celda))
    return int(m.group()) if m else 0


# ------------------------------------------------------------------ temporada

def tabla_modulo(texto: str) -> dict:
    """Tabla con el módulo de Wikipedia: |nombre_COD=[[...]] y |ganados_COD=..."""
    nombres = {cod: (vis or enlace).strip()
               for cod, enlace, vis in re.findall(r"\|nombre_(\w+)\s*=\s*(?:''')?\[\[([^\]|]+)\|?([^\]]*)\]\]", texto)}
    tabla = {}
    for cod in nombres:
        datos = {k: int(v) for k, v in re.findall(rf"\|(ganados|empates|perdidos|gf|gc)_{cod}\s*=\s*(\d+)", texto)}
        if datos:
            pj = sum(datos[k] for k in ("ganados", "empates", "perdidos"))
            tabla[nombres[cod] or cod] = {**datos, "pj": pj, "puntos": 3 * datos["ganados"] + datos["empates"]}
    return tabla


def tabla_plantilla(texto: str) -> dict:
    """Tabla con {{Tabla de posiciones equipo|g=|e=|p=|gf=|gc=|eq=Nombre}}."""
    tabla = {}
    for linea in re.findall(r"\{\{Tabla de posiciones equipo\|(.*)", texto):
        campos = dict(re.findall(r"\|?(g|e|p|gf|gc)=(\d+)", linea))
        eq = re.search(r"\|eq=(.*)", linea)
        if not eq or not campos:
            continue
        nombre = re.sub(r"\{\{refn.*", "", eq.group(1))
        nombre = re.sub(r"\|color=.*|\}\}.*|'''", "", nombre)
        nombre = re.sub(r"\[\[(?:[^\]|]+\|)?([^\]]+)\]\]", r"\1", nombre).strip()
        g, e, p = int(campos["g"]), int(campos["e"]), int(campos["p"])
        tabla[nombre] = {"ganados": g, "empates": e, "perdidos": p, "gf": int(campos.get("gf", 0)),
                         "gc": int(campos.get("gc", 0)), "pj": g + e + p, "puntos": 3 * g + e}
    return tabla


def jugador_de_la_fecha(texto: str) -> dict:
    cuenta = {}
    for celda in re.findall(r"\{\{bandera\|\w*\}\}\s*([^\n{]+)", _seccion(texto, "Jugador de la fecha")):
        nombre = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", celda).strip()
        if nombre:
            cuenta[nombre] = cuenta.get(nombre, 0) + 1
    return cuenta


def goles_por_equipo(anexo: str) -> list[dict]:
    seccion = _seccion(anexo, "Goleadores y asistentes por equipo")
    salida = []
    for m in re.finditer(r"\n===\s*([^=]+?)\s*===", seccion):
        club = m.group(1)
        tabla = seccion[m.end(): seccion.find("|}", m.end())]
        for f in _filas(tabla):
            if len(f) >= 3:
                nombre, wiki = _jugador(f[0])
                salida.append({"club": club, "nombre": nombre, "wiki_es": wiki, "goles": _num(f[1]), "asistencias": _num(f[2])})
    return salida


def partidos_jugados(anexo: str) -> dict:
    """PJ de quienes aparecen en las tablas de goleadores y participación en goles."""
    pj = {}
    for titulo, col in (("Máximos goleadores", 3), ("Participación directa en goles", 5)):
        for f in _filas(_seccion(anexo, titulo)):
            if len(f) > col:
                nombre, wiki = _jugador(f[0])
                pj[wiki or nombre] = max(pj.get(wiki or nombre, 0), _num(f[col]))
    return pj


def arqueros(anexo: str) -> list[dict]:
    salida = []
    for f in _filas(_seccion(anexo, "Rendimiento de porteros")):
        if len(f) >= 6:
            nombre, wiki = _jugador(f[0])
            salida.append({"nombre": nombre, "wiki_es": wiki, "club": f[1], "goles_recibidos": _num(f[2]),
                           "pj": _num(f[3]), "vallas_invictas": _num(f[5]),
                           "penales_atajados": _num(f[6]) if len(f) > 6 else 0})
    return salida


# ------------------------------------------------------------------ Wikidata

def qids_por_titulo(titulos: list[str]) -> dict:
    qids = {}
    for i in range(0, len(titulos), 50):
        q = urllib.parse.urlencode({"action": "wbgetentities", "sites": "eswiki", "titles": "|".join(titulos[i:i + 50]),
                                    "props": "sitelinks", "sitefilter": "eswiki", "format": "json"})
        for qid, e in _get(f"{WIKIDATA}?{q}").get("entities", {}).items():
            if qid.startswith("Q"):
                qids[e["sitelinks"]["eswiki"]["title"]] = qid
        time.sleep(0.2)
    return qids


# Nivel de las ligas de primera división por país (Wikidata). El resto de primeras
# divisiones vale NIVEL_OTRAS y las segundas divisiones NIVEL_SEGUNDA.
NIVEL_PAIS = {
    "Q21": 1.0, "Q145": 1.0, "Q29": 1.0, "Q38": 1.0, "Q183": 1.0, "Q142": 1.0,   # ING, RU, ESP, ITA, ALE, FRA
    "Q45": 0.8, "Q55": 0.8, "Q155": 0.8, "Q414": 0.75, "Q31": 0.75, "Q43": 0.7,  # POR, NED, BRA, ARG, BEL, TUR
    "Q96": 0.7, "Q30": 0.65, "Q298": 0.55,                                        # MEX, USA, CHI
}
NIVEL_OTRAS, NIVEL_SEGUNDA = 0.5, 0.35


def _sparql(consulta: str) -> list[dict]:
    datos = _get(SPARQL, data=urllib.parse.urlencode({"query": consulta}).encode(),
                 accept="application/sparql-results+json")
    return datos["results"]["bindings"]


def _qid(b: dict, k: str) -> str:
    return b[k]["value"].rsplit("/", 1)[-1]


def perfiles(qids: list[str]) -> dict:
    """Posición detallada, estatura, partidos con la selección adulta y trayectoria en clubes."""
    perfil = {q: {"posiciones": [], "estatura_cm": None, "partidos_seleccion": 0,
                  "partidos_clubes": 0, "trayectoria": 0.0} for q in qids}
    paso_por = []  # (jugador, equipo, partidos)
    for i in range(0, len(qids), 150):
        valores = " ".join(f"wd:{q}" for q in qids[i:i + 150])
        for b in _sparql(f"""SELECT ?p ?posLabel ?alt WHERE {{ VALUES ?p {{ {valores} }}
              OPTIONAL {{ ?p wdt:P413 ?pos }} OPTIONAL {{ ?p p:P2048/psn:P2048/wikibase:quantityAmount ?alt }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }} }}"""):
            q = _qid(b, "p")
            if "posLabel" in b and b["posLabel"]["value"] not in perfil[q]["posiciones"]:
                perfil[q]["posiciones"].append(b["posLabel"]["value"])
            if "alt" in b:
                perfil[q]["estatura_cm"] = round(float(b["alt"]["value"]) * 100)  # psn: normalizado a metros
        for b in _sparql(f"""SELECT ?p ?eq (MAX(?n) AS ?pj) WHERE {{ VALUES ?p {{ {valores} }}
              ?p p:P54 ?st . ?st ps:P54 ?eq ; pq:P1350 ?n }} GROUP BY ?p ?eq"""):
            paso_por.append((_qid(b, "p"), _qid(b, "eq"), int(float(b["pj"]["value"]))))
        time.sleep(1)

    # Clasificar cada equipo: selección adulta, o club con el nivel de su liga
    equipos = sorted({e for _, e, _ in paso_por})
    nivel, seleccion = {}, set()
    for i in range(0, len(equipos), 200):
        valores = " ".join(f"wd:{e}" for e in equipos[i:i + 200])
        for b in _sparql(f"""SELECT ?e ?eLabel ?esSel ?pais ?nivelLiga WHERE {{ VALUES ?e {{ {valores} }}
              BIND(EXISTS {{ ?e wdt:P31/wdt:P279* wd:Q6979593 }} AS ?esSel)
              OPTIONAL {{ ?e wdt:P118 ?liga . ?liga wdt:P17 ?pais . OPTIONAL {{ ?liga wdt:P3983 ?nivelLiga }} }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "es,en". }} }}"""):
            e = _qid(b, "e")
            etiqueta = b.get("eLabel", {}).get("value", "")
            if b["esSel"]["value"] == "true":
                if not re.search(r"sub-?\d|under|olímpic|juvenil", etiqueta, re.I):
                    seleccion.add(e)
                continue
            if "pais" in b:
                lv = int(float(b["nivelLiga"]["value"])) if "nivelLiga" in b else 1
                valor = NIVEL_PAIS.get(_qid(b, "pais"), NIVEL_OTRAS) if lv <= 1 else NIVEL_SEGUNDA
                nivel[e] = max(nivel.get(e, 0), valor)
        time.sleep(1)

    for q, e, pj in paso_por:
        if e in seleccion:
            perfil[q]["partidos_seleccion"] += pj
        else:
            perfil[q]["partidos_clubes"] += pj
            perfil[q]["trayectoria"] += pj * nivel.get(e, NIVEL_OTRAS)
    for p in perfil.values():
        p["trayectoria"] = round(p["trayectoria"], 1)
    return perfil


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Estadísticas de la temporada de una liga.")
    p.add_argument("--liga", default="chile")
    p.add_argument("--anio", type=int, default=2026)
    args = p.parse_args()
    cfg = liga(args.liga)
    planteles = json.loads(Path(archivo_planteles(args.liga, args.anio)).read_text(encoding="utf-8"))

    temporada = wikitext(cfg["pagina_temporada"].format(anio=args.anio))
    anexo = wikitext(cfg["anexo"].format(anio=args.anio)) if cfg.get("anexo") else ""
    actualizado = re.search(r"Actualizado al partido entre '''(.+?)''' disputado el '''\{\{fecha\|(\d+)\|(\d+)\|(\d+)", anexo)
    if cfg["tabla"] == "modulo":
        tabla = tabla_modulo(temporada)
    else:
        tabla = tabla_plantilla(_seccion(temporada, cfg["seccion_tabla"]) or temporada)

    titulos = sorted({j["wiki_es"] for c in planteles["clubes"] for j in c["jugadores"] if j["wiki_es"]})
    qids = qids_por_titulo(titulos)
    print(f"Jugadores con artículo en Wikidata: {len(qids)}/{len(titulos)}")

    salida = {
        "liga": args.liga,
        "temporada": args.anio,
        "actualizado": (f"{actualizado.group(4)}-{int(actualizado.group(3)):02d}-{int(actualizado.group(2)):02d}"
                        if actualizado else date.today().isoformat()),
        "tabla": tabla,
        "jugador_de_la_fecha": jugador_de_la_fecha(temporada),
        "goles_asistencias": goles_por_equipo(anexo) if anexo else [],
        "partidos_jugados": partidos_jugados(anexo) if anexo else {},
        "arqueros": arqueros(anexo) if anexo else [],
        "wikidata": {t: q for t, q in qids.items()},
        "perfiles": perfiles(list(qids.values())),
    }
    destino = Path(archivo_stats(args.liga, args.anio))
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Tabla: {len(salida['tabla'])} equipos | goles/asist.: {len(salida['goles_asistencias'])} jugadores | "
          f"arqueros: {len(salida['arqueros'])} | jugador de la fecha: {len(salida['jugador_de_la_fecha'])}")
    print(f"OK -> {destino} (actualizado al {salida['actualizado']})")


if __name__ == "__main__":
    main()
