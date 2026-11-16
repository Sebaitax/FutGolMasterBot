"""Planteles y estadísticas de una liga desde 365Scores (reemplaza a Wikipedia/Wikidata).

Para cada club de la liga baja su plantel actual (sin el cuerpo técnico) y la ficha completa
de cada jugador: puesto, altura, pie, nacimiento, partidos con la selección, si tiene foto y
sus estadísticas de la temporada en la liga (puntaje promedio, partidos, goles, asistencias,
tiros; arqueros: vallas invictas, atajadas y goles recibidos). También la tabla de posiciones.

Escribe los mismos archivos que antes (los usa cartas.valoracion):
    data/liga_<liga>_<año>.json         planteles  ("fuente": "365")
    data/liga_<liga>_<año>_stats.json   tabla de posiciones

Las fichas se guardan en data/cache_365/ para no volver a pedirlas (--refrescar las renueva).
Los jugadores que ya tenían carta conservan su nombre (y así su foto); los nuevos entran con el
nombre de 365Scores.

Uso:
    python -m scraper.liga_365 --liga chile
    python -m scraper.liga_365 --liga brasil --refrescar
Después:
    python -m cartas.valoracion --liga chile
    python -m scraper.fotos_365 --liga chile      # fotos de los jugadores nuevos
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from scraper.fotos_365 import (ALIAS_CLUB, COMPETICION, UA, _api, _plano, _texto, clubes, emparejar,
                               plantel)
from scraper.ligas import archivo_cartas, archivo_planteles, archivo_stats, liga

CACHE = Path("data/cache_365/atletas")
DIAS_CACHE = 3
FOTO = "https://imagecache.365scores.com/image/upload/w_8/Athletes/{id}"

LINEA = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL"}
PUESTO = {"portero": "GK", "defensa central": "CB", "defensa lateral derecho": "RB",
          "defensa lateral izquierdo": "LB", "centrocampista defensivo": "CDM", "mediocampista central": "CM",
          "mediocampista ofensivo": "CAM", "volante derecho": "RM", "volante izquierdo": "LM",
          "delantero derecho": "RW", "delantero izquierdo": "LW", "centro delantero": "ST",
          "segundo delantero": "ST"}
PUESTO_POR_LINEA = {"POR": "GK", "DEF": "CB", "MED": "CM", "DEL": "ST"}

# nombre de la estadística en 365Scores -> clave nuestra
STATS = {"apariciones": "pj", "goles": "goles", "asistencias": "asistencias", "puntaje": "puntaje",
         "tarjetas amarillas": "amarillas", "tarjetas rojas": "rojas", "total de tiros": "tiros",
         "tiros al arco": "tiros_arco", "grandes chances creadas": "chances_creadas", "toques": "toques",
         "minutos jugados": "minutos", "vallas invictas": "vallas_invictas", "salvadas": "atajadas",
         "penales atajados": "penales_atajados", "goles recibidos": "goles_recibidos"}


def _numero(valor: str):
    """'25/27' -> (25, 27); '3(2Pen)' -> 3; '6.8' -> 6.8; '-' -> None."""
    valor = str(valor).strip()
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", valor)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^-?\d+(\.\d+)?", valor)
    if not m:
        return None
    return float(m.group()) if m.group(1) else int(m.group())


def _con_reintentos(funcion, *args, **kwargs):
    """365Scores a veces tarda o corta la conexión: hasta 4 intentos con espera creciente."""
    for intento in range(4):
        try:
            return funcion(*args, **kwargs)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            if intento == 3:
                raise
            print(f"  … reintentando ({e.__class__.__name__})", flush=True)
            time.sleep(2 * (intento + 1))


def ficha(atleta_id: int, refrescar: bool = False) -> dict:
    """Ficha completa del jugador (con caché en disco)."""
    ruta = CACHE / f"{atleta_id}.json"
    if ruta.exists() and not refrescar and (time.time() - ruta.stat().st_mtime) < DIAS_CACHE * 86400:
        return json.loads(ruta.read_text(encoding="utf-8"))
    datos = _con_reintentos(_api, "athletes", athletes=atleta_id, fullDetails="true")
    a = (datos.get("athletes") or [{}])[0]
    CACHE.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(a, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.12)
    return a


def tiene_foto(atleta: dict) -> bool:
    try:
        url = FOTO.format(id=atleta["id"])
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20):
            return True
    except urllib.error.HTTPError as e:
        return e.code != 404
    except Exception:
        return True  # ante la duda (red caída), no se descarta al jugador


def estadisticas(f: dict, competicion: int) -> dict:
    """Estadísticas de la temporada en la liga. Si no jugó en ella (llegó hace poco), las de
    la competición donde más partidos tenga, marcadas como 'otra_competicion'."""
    bloques = f.get("highlightStats") or []
    de_la_liga = [b for b in bloques if b.get("competitionId") == competicion]
    elegido, otra = None, ""
    if de_la_liga:
        elegido = max(de_la_liga, key=lambda b: b.get("seasonNum") or 0)
    sin_partidos = elegido is None or not any(_plano(_texto(s["name"])) == "apariciones" and _numero(s["value"])
                                              for s in elegido["stats"])
    if sin_partidos:
        def partidos(b):
            v = next((_numero(s["value"]) for s in b["stats"] if _plano(_texto(s["name"])) == "apariciones"), None)
            return (v[0] if isinstance(v, tuple) else v) or 0
        otros = [b for b in bloques if b is not elegido and partidos(b) >= 3
                 and any(_plano(_texto(s["name"])) == "puntaje" for s in b["stats"])]
        if otros:
            elegido = max(otros, key=partidos)
            otra = _texto(elegido.get("name", ""))
    salida = {}
    if elegido:
        for s in elegido["stats"]:
            clave = STATS.get(_plano(_texto(s["name"])))
            v = _numero(s["value"])
            if clave and v is not None:
                if isinstance(v, tuple):
                    salida[clave], salida[clave + "_equipo"] = v
                else:
                    salida[clave] = v
    if otra:
        salida["otra_competicion"] = otra
    return salida


def _detalle(f: dict, titulo: str) -> str:
    return next((_texto(d["value"]) for d in f.get("playerDetails") or [] if _plano(_texto(d["title"])) == titulo), "")


def jugador(a: dict, f: dict, competicion: int) -> dict:
    linea = LINEA.get((a.get("position") or {}).get("id"), "MED")
    detallado = _plano(_texto((a.get("formationPosition") or {}).get("name", "")))
    altura = _detalle(f, "altura").replace(",", ".")
    seleccion = re.search(r"Partidos\s*\((\d+)\)", f.get("nationalTeamStatsText") or "")
    return {
        "nombre": " ".join(_texto(a["name"]).split()),
        "wiki_es": "",
        "id_365": a["id"],
        "dorsal": str(a.get("jerseyNum") or ""),
        "nacionalidad": _texto(f.get("nationalityName") or ""),
        "posicion": linea,
        "puesto": PUESTO.get(detallado) or PUESTO_POR_LINEA[linea],
        "nacimiento": (a.get("birthdate") or "")[:10],
        "altura_cm": int(round(float(altura) * 100)) if re.match(r"^\d\.\d+$", altura) else None,
        "pie": _detalle(f, "pie habil"),
        "partidos_seleccion": int(seleccion.group(1)) if seleccion else 0,
        "stats": estadisticas(f, competicion),
    }


def agregar_manuales(salida: list[dict], liga_clave: str, anio: int, competicion: int) -> int:
    """Jugadores que 365Scores ya no pone en el plantel pero queremos en el juego
    (data/ovr_manual_<liga>_<anio>.json con "club": {"<id_365>": {"ovr": 79, "club": "Boca Juniors"}})."""
    ruta = Path(f"data/ovr_manual_{liga_clave}_{anio}.json")
    if not ruta.exists():
        return 0
    presentes = {j["id_365"] for c in salida for j in c["jugadores"]}
    agregados = 0
    for id_365, cfg in json.loads(ruta.read_text(encoding="utf-8")).items():
        club = next((c for c in salida if c["club"] == cfg.get("club")), None)
        if not club or int(id_365) in presentes:
            continue
        if cfg.get("personalizado"):
            # jugador inventado (no existe en 365Scores): sus datos vienen del propio archivo
            club["jugadores"].append({"nombre": cfg["nombre"], "wiki_es": "", "id_365": int(id_365), "dorsal": cfg.get("dorsal", ""),
                                      "nacionalidad": cfg.get("nacionalidad", ""), "posicion": cfg["posicion"],
                                      "puesto": cfg["puesto"], "nacimiento": cfg.get("nacimiento", ""), "altura_cm": cfg.get("altura_cm"),
                                      "pie": cfg.get("pie", ""), "partidos_seleccion": 0, "stats": {}, "tiene_foto": True,
                                      "manual": True})
            agregados += 1
            continue
        f = ficha(int(id_365))
        nacimiento = next((datetime.strptime(_texto(d["title"]), "%d/%m/%Y").date().isoformat()
                           for d in f.get("playerDetails") or [] if re.fullmatch(r"\d{2}/\d{2}/\d{4}", _texto(d["title"]))), "")
        j = jugador({**f, "birthdate": f.get("birthdate") or nacimiento, "jerseyNum": cfg.get("dorsal", "")}, f, competicion)
        if cfg.get("nombre"):
            j["nombre"] = cfg["nombre"]
        j["tiene_foto"] = tiene_foto(f)
        j["manual"] = True
        club["jugadores"].append(j)
        agregados += 1
    return agregados


def tabla(competicion: int) -> dict:
    """Tabla de posiciones (si hay grupos o fases, una fila por club)."""
    salida = {}
    for s in _con_reintentos(_api, "standings", competitions=competicion).get("standings", []):
        for r in s.get("rows", []):
            g, e, p = r.get("gamesWon", 0), r.get("gamesEven", 0), r.get("gamesLost", 0)
            salida[_texto(r["competitor"]["name"])] = {"ganados": g, "empates": e, "perdidos": p,
                                                      "gf": int(r.get("for", 0)), "gc": int(r.get("against", 0)),
                                                      "pj": g + e + p, "puntos": int(r.get("points", 3 * g + e))}
    return salida


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Planteles y estadísticas de una liga desde 365Scores.")
    p.add_argument("--liga", required=True)
    p.add_argument("--anio", type=int, default=2026)
    p.add_argument("--refrescar", action="store_true", help="Volver a pedir las fichas aunque estén en caché")
    args = p.parse_args()
    cfg = liga(args.liga)
    competicion = COMPETICION[args.liga]

    # nombres de club y de jugador que ya usa el juego (para no perder escudos, estadios ni fotos)
    cartas = []
    if Path(archivo_cartas(args.liga, args.anio)).exists():
        with open(archivo_cartas(args.liga, args.anio), newline="", encoding="utf-8") as fh:
            cartas = list(csv.DictReader(fh))
    nombre_club = {_plano(ALIAS_CLUB.get(c["Club"], c["Club"])): c["Club"] for c in cartas}

    # respaldo de los planteles de Wikipedia (por si se quiere comparar)
    ruta_planteles = Path(archivo_planteles(args.liga, args.anio))
    if ruta_planteles.exists():
        viejo = json.loads(ruta_planteles.read_text(encoding="utf-8"))
        if viejo.get("fuente") != "365":
            ruta_planteles.with_suffix(".wiki.json").write_text(json.dumps(viejo, ensure_ascii=False, indent=1),
                                                                encoding="utf-8")

    hoy = date.today()
    salida, nuevos, total = [], 0, 0
    for nombre_365, club_id in sorted(_con_reintentos(clubes, competicion).items()):
        club = nombre_club.get(_plano(_texto(nombre_365)), _texto(nombre_365))
        de_mi_club = [c for c in cartas if c["Club"] == club]
        jugadores = []
        for a in _con_reintentos(plantel, club_id):
            f = ficha(a["id"], args.refrescar)
            j = jugador(a, f, competicion)
            j["tiene_foto"] = tiene_foto(a)
            # si ya tenía carta, conserva su nombre (con tildes) y así su foto
            edad = ""
            if j["nacimiento"]:
                n = date.fromisoformat(j["nacimiento"])
                edad = str(hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day)))
            carta = emparejar({"Nombre": j["nombre"], "Edad": edad, "Dorsal": j["dorsal"]},
                              [{"name": c["Nombre"], "age": int(c["Edad"]) if c["Edad"] else None,
                                "jerseyNum": c["Dorsal"], "_carta": c} for c in de_mi_club])
            if carta:
                j["nombre"] = carta["_carta"]["Nombre"]
            else:
                nuevos += 1
            jugadores.append(j)
        total += len(jugadores)
        salida.append({"club": club, "id_365": club_id, "jugadores": jugadores})
        print(f"{club[:30]:30} {len(jugadores):3} jugadores", flush=True)
        time.sleep(0.2)

    total += agregar_manuales(salida, args.liga, args.anio, competicion)
    ruta_planteles.write_text(json.dumps({"liga": args.liga, "temporada": args.anio, "fuente": "365",
                                          "actualizado": hoy.isoformat(), "clubes": salida},
                                         ensure_ascii=False, indent=1), encoding="utf-8")
    tabla_365 = {nombre_club.get(_plano(k), k): v for k, v in tabla(competicion).items()}
    Path(archivo_stats(args.liga, args.anio)).write_text(
        json.dumps({"liga": args.liga, "temporada": args.anio, "fuente": "365", "actualizado": hoy.isoformat(),
                    "tabla": tabla_365}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {total} jugadores ({nuevos} nuevos) de {len(salida)} clubes de {cfg['nombre']} -> {ruta_planteles}")
    print(f"Ahora corre: python -m cartas.valoracion --liga {args.liga}")


if __name__ == "__main__":
    main()
