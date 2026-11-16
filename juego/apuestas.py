"""Apuestas a partidos reales con las monedas del juego.

- Partidos y resultados de las ligas del juego salen de 365Scores (la misma fuente de los planteles).
  Un hilo los refresca cada pocos minutos y los deja en memoria (y en data/apuestas/cache.json).
- Cuotas propias: modelo de Poisson con la tabla real de cada liga (goles a favor/en contra por
  partido y ventaja de local), con un pequeño margen de la casa.
- La apuesta se cierra cuando empieza el partido (lo controla el servidor) y la cuota queda fija
  al apostar. Al terminar el partido se paga sola; si se suspende o posterga, se devuelve.
- Las apuestas viven en data/apuestas/apuestas.sqlite (compartida: sirve para el ranking).
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

CARPETA = Path("data/apuestas")
BD = CARPETA / "apuestas.sqlite"
CACHE = CARPETA / "cache.json"

LIGAS = {  # clave -> (nombre, bandera, id de competición en 365Scores)
    "chile": ("Primera Chile", "🇨🇱", 135),
    "argentina": ("Liga Argentina", "🇦🇷", 72),
    "brasil": ("Brasileirão", "🇧🇷", 113),
    "inglaterra": ("Premier League", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", 7),
    "espana": ("LaLiga", "🇪🇸", 11),
    "italia": ("Serie A", "🇮🇹", 17),
    "alemania": ("Bundesliga", "🇩🇪", 25),
    "francia": ("Ligue 1", "🇫🇷", 35),
    "mls": ("MLS", "🇺🇸", 104),
}
MARGEN = 0.05                 # margen de la casa sobre las probabilidades
MEZCLA = 0.3                  # peso de las probabilidades típicas (1: 45 %, X: 27 %, 2: 28 %)
CUOTA_MIN, CUOTA_MAX = 1.05, 15.0
APUESTA_MINIMA = 100
REFRESCO = 5 * 60             # cada cuánto se piden partidos y resultados
REFRESCO_TABLAS = 60 * 60
DIAS_ADELANTE = 10            # se muestran los partidos de los próximos días
DEVOLVER_TRAS = 7 * 86400     # si en una semana no hay resultado, se devuelve
ESCUDO = ("https://imagecache.365scores.com/image/upload/f_png,w_64,h_64,c_limit,q_auto:eco,"
          "d_Competitors:default1.png/v{v}/Competitors/{id}")
SUSPENDIDO = re.compile(r"suspend|posterg|aplaz|cancel|abandon|interrump", re.I)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS apuestas (
    id INTEGER PRIMARY KEY,
    pid TEXT NOT NULL,
    club TEXT,
    partido INTEGER NOT NULL,
    liga TEXT, local TEXT, visita TEXT, inicio REAL,
    eleccion TEXT NOT NULL,      -- 1, X, 2
    cuota REAL NOT NULL,
    monto INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'abierta',   -- abierta, ganada, perdida, devuelta
    pago INTEGER DEFAULT 0,
    marcador TEXT,
    creada REAL NOT NULL,
    resuelta REAL
);
CREATE INDEX IF NOT EXISTS apuestas_pid ON apuestas (pid, creada);
CREATE INDEX IF NOT EXISTS apuestas_estado ON apuestas (estado, inicio);
"""


class ErrorApuesta(Exception):
    pass


def conectar() -> sqlite3.Connection:
    CARPETA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BD, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


# ------------------------------------------------------------------ cuotas

def _poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def cuotas(tabla: dict, local: str, visita: str) -> dict[str, float]:
    """Cuotas 1/X/2 con un Poisson: goles esperados según ataque y defensa de cada uno en la tabla real."""
    filas = [f for f in tabla.values() if f.get("pj")]
    pj = sum(f["pj"] for f in filas)
    media = (sum(f["gf"] for f in filas) / pj) if pj else 1.3   # goles por equipo y partido en la liga
    media = max(media, 0.6)

    def fuerza(nombre: str) -> tuple[float, float]:
        f = tabla.get(nombre)
        if not f or f.get("pj", 0) < 3:
            return 1.0, 1.0
        # se suaviza con 3 partidos "promedio" para que una racha corta no dispare las cuotas
        ata = (f["gf"] + 3 * media) / (f["pj"] + 3) / media
        dfn = (f["gc"] + 3 * media) / (f["pj"] + 3) / media
        return ata, dfn

    ah, dh = fuerza(local)
    aa, da = fuerza(visita)
    lh, la = media * ah * da * 1.15, media * aa * dh * 0.87   # ventaja de jugar de local
    p1 = px = p2 = 0.0
    for i in range(11):
        for j in range(11):
            p = _poisson(i, lh) * _poisson(j, la)
            if i > j:
                p1 += p
            elif i == j:
                px += p
            else:
                p2 += p
    total = p1 + px + p2
    # el Poisson solo exagera los partidos desparejos (y achica el empate): se mezcla con lo típico del fútbol
    base = {"1": 0.45, "X": 0.27, "2": 0.28}
    probs = {k: (1 - MEZCLA) * p / total + MEZCLA * base[k] for k, p in (("1", p1), ("X", px), ("2", p2))}
    return {k: round(min(CUOTA_MAX, max(CUOTA_MIN, 1 / (p * (1 + MARGEN)))), 2) for k, p in probs.items()}


# ------------------------------------------------------------------ partidos (365Scores)

_lock = threading.RLock()
_estado: dict = {"partidos": {}, "tablas": {}, "actualizado": 0, "tablas_actualizadas": 0, "error": ""}


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _partido(g: dict, liga: str) -> dict:
    h, a = g["homeCompetitor"], g["awayCompetitor"]
    goles = [h.get("score", -1), a.get("score", -1)]
    return {
        "id": g["id"], "liga": liga, "inicio": g["startTime"], "ts": _ts(g["startTime"]),
        "ronda": g.get("roundName", "") + (f" {g['roundNum']}" if g.get("roundNum") else ""),
        "local": h["name"], "visita": a["name"],
        "escudos": [ESCUDO.format(v=h.get("imageVersion", 1), id=h["id"]), ESCUDO.format(v=a.get("imageVersion", 1), id=a["id"])],
        "grupo": g.get("statusGroup"), "texto": g.get("statusText", ""),
        "goles": [int(x) if x is not None and x >= 0 else None for x in goles],
    }


def _cargar_cache():
    try:
        datos = json.loads(CACHE.read_text(encoding="utf-8"))
        with _lock:
            _estado.update(partidos={int(k): v for k, v in datos.get("partidos", {}).items()},
                           tablas=datos.get("tablas", {}), actualizado=datos.get("actualizado", 0),
                           tablas_actualizadas=datos.get("tablas_actualizadas", 0))
    except (OSError, ValueError):
        pass


def refrescar(forzar_tablas: bool = False):
    """Pide partidos y resultados de todas las ligas (y las tablas cada hora)."""
    from scraper.fotos_365 import _api
    from scraper.liga_365 import tabla
    ahora = time.time()
    nuevas_tablas = forzar_tablas or ahora - _estado["tablas_actualizadas"] > REFRESCO_TABLAS
    partidos, tablas, errores = {}, dict(_estado["tablas"]), []
    for clave, (_, _, comp) in LIGAS.items():
        try:
            for ruta in ("games/fixtures", "games/results"):
                for g in _api(ruta, competitions=comp).get("games", []):
                    partidos[g["id"]] = _partido(g, clave)
            if nuevas_tablas or clave not in tablas:
                tablas[clave] = tabla(comp)
        except Exception as e:   # una liga caída no bota las demás
            errores.append(f"{clave}: {e}")
    with _lock:
        viejos = _estado["partidos"]
        # se guardan los partidos ya conocidos de la última semana (para pagar aunque salgan de la lista)
        for pid, p in viejos.items():
            if pid not in partidos and ahora - p["ts"] < DEVOLVER_TRAS:
                partidos[pid] = p
        for p in partidos.values():
            if p["grupo"] == 2:
                p["cuotas"] = cuotas(tablas.get(p["liga"], {}), p["local"], p["visita"])
        _estado.update(partidos=partidos, tablas=tablas, actualizado=ahora, error="; ".join(errores))
        if nuevas_tablas:
            _estado["tablas_actualizadas"] = ahora
        CARPETA.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({**_estado, "partidos": {str(k): v for k, v in partidos.items()}}, ensure_ascii=False),
                         encoding="utf-8")


def proximos(liga: str) -> list[dict]:
    """Partidos de la liga que todavía no empiezan (con cuotas), del más cercano al más lejano."""
    ahora = time.time()
    with _lock:
        return sorted((p for p in _estado["partidos"].values()
                       if p["liga"] == liga and p["grupo"] == 2 and p.get("cuotas")
                       and ahora < p["ts"] < ahora + DIAS_ADELANTE * 86400), key=lambda p: p["ts"])


def recientes(liga: str, n: int = 12) -> list[dict]:
    """En vivo y terminados hace poco (para ver cómo van las apuestas)."""
    with _lock:
        lista = [p for p in _estado["partidos"].values() if p["liga"] == liga and p["grupo"] in (3, 4)]
    return sorted(lista, key=lambda p: -p["ts"])[:n]


def partido(pid: int) -> dict | None:
    with _lock:
        return _estado["partidos"].get(pid)


def info() -> dict:
    with _lock:
        return {"actualizado": _estado["actualizado"], "error": _estado["error"]}


# ------------------------------------------------------------------ apostar y pagar

def apostar(pid: str, club: str, partido_id: int, eleccion: str, monto: int,
            cobrar: Callable[[int, str], None]) -> dict:
    """Valida, cobra (con `cobrar(monto, concepto)`, que lanza si no alcanza) y registra la apuesta."""
    p = partido(partido_id)
    if eleccion not in ("1", "X", "2"):
        raise ErrorApuesta("Elige local, empate o visita.")
    if not p or p["grupo"] != 2 or not p.get("cuotas"):
        raise ErrorApuesta("Ese partido ya no acepta apuestas.")
    if time.time() >= p["ts"]:
        raise ErrorApuesta("El partido ya empezó: las apuestas están cerradas.")
    if monto < APUESTA_MINIMA:
        raise ErrorApuesta(f"La apuesta mínima es de {APUESTA_MINIMA} monedas.")
    cuota = p["cuotas"][eleccion]
    que = {"1": p["local"], "X": "empate", "2": p["visita"]}[eleccion]
    cobrar(monto, f"Apuesta: {que} en {p['local']} vs {p['visita']}")
    con = conectar()
    try:
        cur = con.execute("INSERT INTO apuestas (pid, club, partido, liga, local, visita, inicio, eleccion, cuota, monto, creada)"
                          " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (pid, club, partido_id, p["liga"], p["local"], p["visita"], p["ts"], eleccion, cuota, monto, time.time()))
        con.commit()
        return {"id": cur.lastrowid, "cuota": cuota, "premio": int(monto * cuota)}
    finally:
        con.close()


def liquidar(pagar: Callable[[str, int, str], None]) -> int:
    """Paga o devuelve las apuestas de partidos terminados. `pagar(pid, monto, concepto)`. Devuelve cuántas resolvió."""
    from scraper.fotos_365 import _api
    con = conectar()
    resueltas = 0
    try:
        abiertas = con.execute("SELECT * FROM apuestas WHERE estado = 'abierta' AND inicio < ?", (time.time(),)).fetchall()
        consultados: dict[int, dict | None] = {}
        for a in abiertas:
            p = partido(a["partido"])
            if (not p or p["grupo"] not in (4,)) and a["partido"] not in consultados and time.time() - a["inicio"] > 3 * 3600:
                try:   # ya no está en la lista: se pregunta por ese partido
                    consultados[a["partido"]] = _partido(_api("game", gameId=a["partido"])["game"], a["liga"])
                except Exception:
                    consultados[a["partido"]] = None
            p = consultados.get(a["partido"]) or p
            vs = f"{a['local']} vs {a['visita']}"
            if p and (SUSPENDIDO.search(p["texto"] or "") or (p["grupo"] == 4 and None in p["goles"])):
                estado, pago, marcador, concepto = "devuelta", a["monto"], p["texto"], f"Apuesta devuelta ({p['texto']}): {vs}"
            elif p and p["grupo"] == 4:
                g1, g2 = p["goles"]
                gano = {"1": g1 > g2, "X": g1 == g2, "2": g1 < g2}[a["eleccion"]]
                marcador = f"{g1}-{g2}"
                estado, pago = ("ganada", int(a["monto"] * a["cuota"])) if gano else ("perdida", 0)
                concepto = f"Apuesta ganada: {vs} {marcador}"
            elif time.time() - a["inicio"] > DEVOLVER_TRAS:
                estado, pago, marcador, concepto = "devuelta", a["monto"], "sin resultado", f"Apuesta devuelta (sin resultado): {vs}"
            else:
                continue
            # primero se marca (así un error al pagar no paga dos veces), después se paga
            n = con.execute("UPDATE apuestas SET estado = ?, pago = ?, marcador = ?, resuelta = ? WHERE id = ? AND estado = 'abierta'",
                            (estado, pago, marcador, time.time(), a["id"])).rowcount
            con.commit()
            if n and pago:
                try:
                    pagar(a["pid"], pago, concepto)
                except Exception:
                    con.execute("UPDATE apuestas SET estado = 'abierta', pago = 0, resuelta = NULL WHERE id = ?", (a["id"],))
                    con.commit()
                    continue
            resueltas += n
    finally:
        con.close()
    return resueltas


def mis_apuestas(pid: str, n: int = 40) -> list[dict]:
    con = conectar()
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM apuestas WHERE pid = ? ORDER BY estado != 'abierta', creada DESC LIMIT ?", (pid, n))]
    finally:
        con.close()


def ranking() -> list[dict]:
    """Ganancia neta de cada jugador con las apuestas ya resueltas."""
    con = conectar()
    try:
        return [dict(r) for r in con.execute(
            "SELECT pid, MAX(club) club, COUNT(*) apuestas, SUM(estado = 'ganada') ganadas,"
            " SUM(CASE WHEN estado = 'devuelta' THEN 0 ELSE pago - monto END) neto"
            " FROM apuestas WHERE estado != 'abierta' GROUP BY pid ORDER BY neto DESC")]
    finally:
        con.close()


# ------------------------------------------------------------------ hilo de fondo

_hilo: threading.Thread | None = None


def iniciar(pagar: Callable[[str, int, str], None], anotar: Callable[[str], None] = print):
    """Arranca el hilo que refresca partidos y paga apuestas cada REFRESCO segundos."""
    global _hilo
    if _hilo and _hilo.is_alive():
        return
    _cargar_cache()

    def ciclo():
        while True:
            try:
                refrescar()
                liquidar(pagar)
                if _estado["error"]:
                    anotar(f"apuestas: {_estado['error']}")
            except Exception as e:   # el hilo nunca debe morir
                anotar(f"apuestas: {type(e).__name__}: {e}")
            time.sleep(REFRESCO)

    _hilo = threading.Thread(target=ciclo, name="apuestas", daemon=True)
    _hilo.start()
