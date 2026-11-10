"""Descarga el estadio de cada club real (nombre, capacidad y foto) desde Wikidata/Commons.

Para cada club de los planteles busca su estadio (Wikidata P115), la capacidad (P1083)
y la foto (P18) en Wikimedia Commons, que tiene licencias libres. El autor y la licencia
quedan en data/estadios.json. Las fotos van a assets/estadios/ (solo local).

Uso:
    python -m scraper.estadios                  # todas las ligas descargadas
    python -m scraper.estadios --forzar         # volver a bajar las fotos
"""
import argparse
import csv
import glob
import io
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

from PIL import Image

from scraper.estadisticas import qids_por_titulo
from scraper.fotos import _api, _get, info_archivo

DESTINO = Path("assets/estadios")
SALIDA = Path("data/estadios.json")


def slug(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plano).strip("-")


def club_de_cartas() -> dict[str, str]:
    """nombre del jugador -> club tal como figura en las cartas (para emparejar planteles y cartas)."""
    salida = {}
    for ruta in glob.glob("data/cartas_liga_*_2026.csv"):
        with open(ruta, newline="", encoding="utf-8") as f:
            for fila in csv.DictReader(f):
                salida[fila["Nombre"]] = fila["Club"]
    return salida


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Estadios de los clubes (Wikidata + Commons).")
    p.add_argument("--forzar", action="store_true")
    args = p.parse_args()

    jugador_club = club_de_cartas()
    clubes = []  # (título del club en es.wikipedia, club como figura en las cartas)
    for ruta in glob.glob("data/liga_*_2026.json"):
        if ruta.endswith("_stats.json"):
            continue
        for c in json.loads(Path(ruta).read_text(encoding="utf-8"))["clubes"]:
            votos = Counter(jugador_club[j["nombre"].split("(")[0].strip()] for j in c["jugadores"]
                            if j["nombre"].split("(")[0].strip() in jugador_club)
            if votos:
                clubes.append((c["wiki_es"], votos.most_common(1)[0][0]))
    print(f"{len(clubes)} clubes")

    qid_club = qids_por_titulo([t for t, _ in clubes])
    ents = {}
    qids = [qid_club[t] for t, _ in clubes if t in qid_club]
    for i in range(0, len(qids), 50):
        ents.update(_api("https://www.wikidata.org/w/api.php", action="wbgetentities", ids="|".join(qids[i:i + 50]),
                         props="claims")["entities"])
    sede = {}
    for titulo, club in clubes:
        reclamos = ents.get(qid_club.get(titulo, ""), {}).get("claims", {}).get("P115", [])
        # el estadio vigente: el que no tiene fecha de fin
        vigentes = [r for r in reclamos if "P582" not in r.get("qualifiers", {})] or reclamos
        if vigentes and "datavalue" in vigentes[0]["mainsnak"]:
            sede[club] = vigentes[0]["mainsnak"]["datavalue"]["value"]["id"]
    estadios = {}
    lista = sorted(set(sede.values()))
    for i in range(0, len(lista), 50):
        estadios.update(_api("https://www.wikidata.org/w/api.php", action="wbgetentities", ids="|".join(lista[i:i + 50]),
                             props="claims|labels", languages="es|en")["entities"])

    DESTINO.mkdir(parents=True, exist_ok=True)
    anteriores = {e["club"]: e for e in json.loads(SALIDA.read_text(encoding="utf-8"))} if SALIDA.exists() else {}
    salida = []
    for club, qid in sorted(sede.items()):
        e = estadios.get(qid, {})
        etiquetas = e.get("labels", {})
        nombre = (etiquetas.get("es") or etiquetas.get("en") or {}).get("value", "")
        cap = e.get("claims", {}).get("P1083", [])
        capacidad = max((int(float(r["mainsnak"]["datavalue"]["value"]["amount"])) for r in cap
                         if "datavalue" in r["mainsnak"]), default=0)
        foto = e.get("claims", {}).get("P18", [])
        registro = {"club": club, "estadio": nombre, "capacidad": capacidad, "wikidata": qid,
                    "archivo": "", "autor": "", "licencia": "", "fuente": ""}
        archivo = DESTINO / f"{slug(club)}.jpg"
        if foto and "datavalue" in foto[0]["mainsnak"]:
            if archivo.exists() and not args.forzar and club in anteriores:
                registro.update({k: anteriores[club][k] for k in ("archivo", "autor", "licencia", "fuente")})
            else:
                try:
                    info = info_archivo(foto[0]["mainsnak"]["datavalue"]["value"])
                    if info:
                        img = Image.open(io.BytesIO(_get(info["url"], binario=True)))
                        img.convert("RGB").save(archivo, quality=85)
                        registro.update(archivo=archivo.name, autor=info["autor"], licencia=info["licencia"], fuente=info["pagina"])
                    time.sleep(0.3)
                except Exception as err:
                    print(f"  ✗ {club}: {err}")
        salida.append(registro)
        print(f"  {'📷' if registro['archivo'] else '  '} {club[:28]:28} {nombre[:40]:40} {capacidad:>7,}")
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(salida)} estadios, {sum(1 for s in salida if s['archivo'])} con foto -> {SALIDA}")


if __name__ == "__main__":
    main()
