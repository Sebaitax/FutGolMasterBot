"""Álbum: todas las cartas que alguna vez tuviste, por liga y por club (aunque después las vendas).

- Cada carta que entra a tu plantel queda anotada en la tabla `album` (un trigger de SQLite en juego/bd.py,
  así no se escapa ningún camino: sobres, carta gratis, premios, regalos del admin...).
- Premios por club, una sola vez cada uno: al tener la MITAD de sus cartas y al COMPLETARLO.
  Los clubes fuertes son mucho más difíciles de completar (sus figuras casi solo salen como estrella o crack),
  así que el premio crece con la media del club.
- Las cartas exclusivas (no salen en sobres) no cuentan.
"""
from __future__ import annotations

import time

from juego import escalera as ESC
from juego.partida import EXCLUSIVAS, ErrorJuego, Partida, _carta

NIVELES = (50, 100)   # % del club para cada premio


def _registrar_actuales(p: Partida):
    """Las cartas que ya tenías antes de existir el álbum (o si algo se escapó del trigger)."""
    p.con.execute("INSERT OR IGNORE INTO album (carta_id, desde) SELECT DISTINCT carta_id, ? FROM plantilla WHERE equipo_id = ?",
                  (time.time(), p.usuario_id))


def _pais_de_liga(liga: str) -> tuple[str, str]:
    for nombre, bandera, l in ESC.PAISES.values():
        if l == liga:
            return nombre, bandera
    return "", ""


def premio(total: int, media: float, nivel: int) -> dict:
    """Mitad: monedas. Completo: el doble de monedas + un sobre premium listo para abrir + el escudo del club."""
    dificultad = (max(media, 55) / 65) ** 3            # Palestino ~1, Arsenal ~1,9
    monedas = int(round(total * media * 0.6 * dificultad / 50) * 50)
    if nivel >= 100:
        return {"monedas": monedas * 2, "sobre": "premium", "escudo": True}
    return {"monedas": monedas, "sobre": None, "escudo": False}


def _cobrados(p: Partida) -> set[str]:
    return {r["clave"] for r in p.con.execute("SELECT clave FROM album_premios")}


def _clave(liga: str, club: str, nivel: int) -> str:
    return f"{liga}|{club}|{nivel}"


def resumen(p: Partida) -> list[dict]:
    """Ligas con sus clubes y el avance de cada uno."""
    _registrar_actuales(p)
    tengo = {r["carta_id"] for r in p.con.execute("SELECT carta_id FROM album")}
    cobrados = _cobrados(p)
    clubes: dict[tuple[str, str], dict] = {}
    for r in p.con.execute("SELECT id, liga, club, nombre, ovr FROM cartas"):
        if r["nombre"] in EXCLUSIVAS or not r["club"]:
            continue
        c = clubes.setdefault((r["liga"], r["club"]), {"liga": r["liga"], "club": r["club"], "total": 0, "tengo": 0, "suma": 0})
        c["total"] += 1
        c["suma"] += r["ovr"]
        c["tengo"] += r["id"] in tengo
    # escudos y estadios de colección de cada club (salen en los sobres; el escudo también al completar el club)
    p._asegurar_coleccionables()
    propios = {r["coleccionable_id"] for r in p.con.execute("SELECT coleccionable_id FROM objetos")}
    objetos: dict[str, list[dict]] = {}
    for r in p.con.execute("SELECT id, tipo, club FROM coleccionables"):
        objetos.setdefault(r["club"], []).append({"tipo": r["tipo"], "tengo": r["id"] in propios})
    ligas: dict[str, dict] = {}
    for c in clubes.values():
        c["objetos"] = sorted(objetos.get(c["club"], []), key=lambda o: o["tipo"] != "escudo")
        c["obj_tengo"] = sum(o["tengo"] for o in c["objetos"])
        c["media"] = round(c.pop("suma") / c["total"], 1)
        c["pct"] = round(100 * c["tengo"] / c["total"])
        c["premios"] = [{"nivel": n, "logrado": c["pct"] >= n, "cobrado": _clave(c["liga"], c["club"], n) in cobrados,
                         **premio(c["total"], c["media"], n)} for n in NIVELES]
        c["por_cobrar"] = sum(1 for x in c["premios"] if x["logrado"] and not x["cobrado"])
        pais, bandera = _pais_de_liga(c["liga"])
        lg = ligas.setdefault(c["liga"], {"liga": c["liga"], "pais": pais, "bandera": bandera, "clubes": [], "total": 0, "tengo": 0,
                                          "por_cobrar": 0, "obj_total": 0, "obj_tengo": 0})
        lg["obj_total"] += len(c["objetos"])
        lg["obj_tengo"] += c["obj_tengo"]
        lg["clubes"].append(c)
        lg["total"] += c["total"]
        lg["tengo"] += c["tengo"]
        lg["por_cobrar"] += c["por_cobrar"]
    mi_liga = ESC.PAISES.get(p.pais, ESC.PAISES[ESC.PAIS_DEFECTO])[2]
    for lg in ligas.values():
        lg["pct"] = round(100 * lg["tengo"] / lg["total"]) if lg["total"] else 0
        lg["clubes"].sort(key=lambda c: (-c["pct"], c["club"]))
    # tu liga primero, después las que más avanzaste
    return sorted(ligas.values(), key=lambda lg: (lg["liga"] != mi_liga, -lg["tengo"], lg["liga"]))


def por_cobrar(p: Partida) -> int:
    """Premios del álbum listos para reclamar (para el aviso del menú)."""
    try:
        return sum(lg["por_cobrar"] for lg in resumen(p))
    except Exception:
        return 0


def club(p: Partida, liga: str, nombre: str) -> dict:
    """Todas las cartas de un club (las que tuviste y las que faltan) y sus premios."""
    lg = next((x for x in resumen(p) if x["liga"] == liga), None)
    c = lg and next((x for x in lg["clubes"] if x["club"] == nombre), None)
    if not c:
        raise ErrorJuego("No encontré ese club en el álbum.")
    tengo = {r["carta_id"] for r in p.con.execute("SELECT carta_id FROM album")}
    filas = [r for r in p.con.execute("SELECT * FROM cartas WHERE liga = ? AND club = ? ORDER BY ovr DESC, nombre", (liga, nombre))
             if r["nombre"] not in EXCLUSIVAS]
    return {**c, "pais": lg["pais"], "bandera": lg["bandera"],
            "cartas": [(_carta(r), r["id"] in tengo) for r in filas]}


def cobrar(p: Partida, liga: str, nombre: str, nivel: int) -> dict:
    if nivel not in NIVELES:
        raise ErrorJuego("Ese premio no existe.")
    c = club(p, liga, nombre)
    if c["pct"] < nivel:
        raise ErrorJuego(f"Te falta llegar al {nivel}% de {nombre}.")
    clave = _clave(liga, nombre, nivel)
    if p.con.execute("SELECT 1 FROM album_premios WHERE clave = ?", (clave,)).fetchone():
        raise ErrorJuego("Ese premio ya lo cobraste.")
    dar = premio(c["total"], c["media"], nivel)
    p.con.execute("INSERT INTO album_premios (clave, cobrado) VALUES (?, ?)", (clave, time.time()))
    p._mover_monedas(dar["monedas"], f"Álbum: {nombre} al {nivel}%")
    salida = {"monedas": dar["monedas"], "sobre": None, "escudo": None}
    if dar["sobre"]:   # listo para abrir (los de regalo pueden pasar de los 4 espacios)
        sobres = p._get("sobres_tiempo") or []
        sobres.append({"id": int(time.time() * 1000), "tipo": dar["sobre"], "cancha": p.cancha, "desbloqueo": time.time() - 13 * 3600})
        p._set("sobres_tiempo", sobres)
        salida["sobre"] = dar["sobre"]
    if dar["escudo"]:
        obj = p.con.execute("SELECT id, nombre FROM coleccionables WHERE tipo = 'escudo' AND club = ?", (nombre,)).fetchone()
        if obj and not p.con.execute("SELECT 1 FROM objetos WHERE coleccionable_id = ?", (obj["id"],)).fetchone():
            p.con.execute("INSERT INTO objetos (coleccionable_id) VALUES (?)", (obj["id"],))
            salida["escudo"] = obj["nombre"]
    p.con.commit()
    return salida
