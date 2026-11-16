"""Bitácora privada del servidor: qué hace cada jugador y qué falla, para encontrar problemas.

Se guarda en data/logs/bitacora.sqlite (solo local, nunca en el repo) y solo se ve desde la
PC del servidor en /admin/logs (o con `python -m web.bitacora`).

Qué se anota:
- cada visita/acción (ruta, estado, cuánto tardó, dispositivo); las consultas repetitivas
  (estado de un partido en vivo) solo si fallan o son lentas
- errores del servidor con su traceback completo
- errores de juego que ve el jugador ("No tienes monedas…")
- errores de JavaScript en el navegador de cada jugador
- eventos de juego importantes (sobres, partidos, ventas…)

No se anotan IPs: solo el país que informa Cloudflare y un resumen del navegador.
"""
from __future__ import annotations

import contextvars
import json
import queue
import sqlite3
import sys
import threading
import time
from pathlib import Path

RUTA = Path("data/logs/bitacora.sqlite")
DIAS_GUARDADOS = 30
LENTO_MS = 1500

# quién está haciendo la petición actual (lo llena el middleware)
contexto: contextvars.ContextVar[dict] = contextvars.ContextVar("bitacora", default={})

_cola: queue.Queue = queue.Queue(maxsize=20000)
_hilo: threading.Thread | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    nivel TEXT NOT NULL,          -- info, aviso, error
    tipo TEXT NOT NULL,           -- peticion, excepcion, error_juego, js, juego
    pid TEXT,
    metodo TEXT,
    ruta TEXT,
    estado INTEGER,
    ms INTEGER,
    dispositivo TEXT,
    pais TEXT,
    mensaje TEXT,
    detalle TEXT
);
CREATE INDEX IF NOT EXISTS eventos_ts ON eventos (ts);
CREATE INDEX IF NOT EXISTS eventos_pid ON eventos (pid, ts);
CREATE INDEX IF NOT EXISTS eventos_nivel ON eventos (nivel, ts);
"""


def conectar(ruta: Path = RUTA) -> sqlite3.Connection:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, timeout=10)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def _escritor():
    con = conectar()
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("DELETE FROM eventos WHERE ts < ?", (time.time() - DIAS_GUARDADOS * 86400,))
    con.commit()
    while True:
        filas = [_cola.get()]
        # junta lo que haya en la cola para escribir de una vez
        while len(filas) < 500:
            try:
                filas.append(_cola.get_nowait())
            except queue.Empty:
                break
        try:
            con.executemany(
                "INSERT INTO eventos (ts, nivel, tipo, pid, metodo, ruta, estado, ms, dispositivo, pais, mensaje, detalle)"
                " VALUES (:ts, :nivel, :tipo, :pid, :metodo, :ruta, :estado, :ms, :dispositivo, :pais, :mensaje, :detalle)", filas)
            con.commit()
        except sqlite3.Error as e:  # la bitácora nunca debe botar el juego
            print("bitácora:", e, file=sys.stderr)


def _iniciar():
    global _hilo
    if _hilo is None or not _hilo.is_alive():
        _hilo = threading.Thread(target=_escritor, name="bitacora", daemon=True)
        _hilo.start()


def anotar(tipo: str, mensaje: str = "", nivel: str = "info", detalle: dict | str | None = None, **campos):
    """Agrega un evento (no bloquea: lo escribe un hilo aparte)."""
    _iniciar()
    ctx = contexto.get()
    fila = {
        "ts": time.time(), "nivel": nivel, "tipo": tipo,
        "pid": campos.get("pid", ctx.get("pid")), "metodo": campos.get("metodo", ctx.get("metodo")),
        "ruta": campos.get("ruta", ctx.get("ruta")), "estado": campos.get("estado"), "ms": campos.get("ms"),
        "dispositivo": campos.get("dispositivo", ctx.get("dispositivo")), "pais": campos.get("pais", ctx.get("pais")),
        "mensaje": (mensaje or "")[:2000],
        "detalle": detalle if isinstance(detalle, str) or detalle is None else json.dumps(detalle, ensure_ascii=False, default=str)[:20000],
    }
    try:
        _cola.put_nowait(fila)
    except queue.Full:
        pass


def dispositivo(ua: str) -> str:
    """Resumen corto del navegador: 'Android · Chrome', 'iPhone · Safari'…"""
    ua = ua or ""
    so = next((n for k, n in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"),
                              ("Mac OS", "Mac"), ("Linux", "Linux")) if k in ua), "?")
    nav = next((n for k, n in (("Edg/", "Edge"), ("OPR/", "Opera"), ("SamsungBrowser", "Samsung"), ("CriOS", "Chrome"),
                               ("Chrome/", "Chrome"), ("Firefox/", "Firefox"), ("Safari/", "Safari")) if k in ua), "?")
    if "HeadlessChrome" in ua:
        nav = "Headless"
    return f"{so} · {nav}"


# ------------------------------------------------------------------ consultas (página admin / consola)

def resumen(horas: float = 24, pid: str | None = None, nivel: str | None = None, tipo: str | None = None,
            limite: int = 300, ruta: Path = RUTA) -> dict:
    if not ruta.exists():
        return {"eventos": [], "jugadores": [], "errores": [], "lentas": [], "totales": {}}
    con = conectar(ruta)
    desde = time.time() - horas * 3600
    filtro, args = "ts >= ?", [desde]
    if pid:
        filtro += " AND pid = ?"; args.append(pid)
    if nivel:
        filtro += " AND nivel = ?"; args.append(nivel)
    if tipo:
        filtro += " AND tipo = ?"; args.append(tipo)
    eventos = [dict(r) for r in con.execute(f"SELECT * FROM eventos WHERE {filtro} ORDER BY ts DESC LIMIT ?", (*args, limite))]
    jugadores = [dict(r) for r in con.execute(
        "SELECT pid, COUNT(*) n, SUM(nivel='error') errores, SUM(nivel='aviso') avisos, MAX(ts) ultimo, MIN(ts) primero,"
        " GROUP_CONCAT(DISTINCT dispositivo) dispositivos, MAX(pais) pais"
        " FROM eventos WHERE ts >= ? AND pid IS NOT NULL GROUP BY pid ORDER BY ultimo DESC", (desde,))]
    errores = [dict(r) for r in con.execute(
        "SELECT tipo, nivel, CASE WHEN tipo = 'peticion' THEN 'HTTP ' || estado ELSE mensaje END mensaje, COUNT(*) n, COUNT(DISTINCT pid) jugadores, MAX(ts) ultimo, MAX(ruta) ruta"
        " FROM eventos WHERE ts >= ? AND nivel IN ('error', 'aviso')"
        " GROUP BY tipo, mensaje, CASE WHEN tipo = 'peticion' THEN ruta || ' ' || estado END ORDER BY n DESC LIMIT 60", (desde,))]
    lentas = [dict(r) for r in con.execute(
        "SELECT metodo, ruta, COUNT(*) n, CAST(AVG(ms) AS INT) prom, MAX(ms) max FROM eventos"
        " WHERE ts >= ? AND tipo = 'peticion' AND ms >= ? GROUP BY metodo, ruta ORDER BY n DESC LIMIT 30", (desde, LENTO_MS))]
    totales = dict(con.execute(
        "SELECT COUNT(*) eventos, SUM(nivel='error') errores, SUM(nivel='aviso') avisos, COUNT(DISTINCT pid) jugadores"
        " FROM eventos WHERE ts >= ?", (desde,)).fetchone())
    con.close()
    return {"eventos": eventos, "jugadores": jugadores, "errores": errores, "lentas": lentas, "totales": totales}


def metricas(horas: float = 24, ruta: Path = RUTA) -> dict:
    """Números clave del juego (eventos tipo 'metrica' + actividad), para el panel de administración."""
    if not ruta.exists():
        return {}
    con = conectar(ruta)
    desde = time.time() - horas * 3600
    uno = lambda sql, *a: con.execute(sql, (desde, *a)).fetchone()[0]
    m = {
        "activos": uno("SELECT COUNT(DISTINCT pid) FROM eventos WHERE ts >= ? AND pid IS NOT NULL AND pid != ''"),
        "cuentas_nuevas": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND tipo = 'cuenta' AND mensaje LIKE 'cuenta nueva%'"),
        "clubes_nuevos": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND tipo = 'metrica' AND mensaje = 'club_creado'"),
        "errores": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND nivel = 'error'"),
        "errores_js": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND tipo = 'js' AND nivel = 'error'"),
        "pegados": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND tipo = 'js' AND mensaje LIKE 'posible pegado%'"),
        "reconexiones": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND tipo = 'js' AND mensaje LIKE 'reconect%'"),
        "trampas": uno("SELECT COUNT(*) FROM eventos WHERE ts >= ? AND tipo = 'trampa'"),
    }
    m["partidos"] = [dict(r) for r in con.execute(
        "SELECT json_extract(detalle, '$.modo') modo, COUNT(*) n, CAST(AVG(json_extract(detalle, '$.duracion')) AS INT) duracion,"
        " SUM(json_extract(detalle, '$.resultado') = 'victoria') victorias, SUM(json_extract(detalle, '$.resultado') = 'derrota') derrotas"
        " FROM eventos WHERE ts >= ? AND tipo = 'metrica' AND mensaje = 'partido_fin' GROUP BY modo", (desde,))]
    m["busquedas"] = [dict(r) for r in con.execute(
        "SELECT json_extract(detalle, '$.resultado') resultado, COUNT(*) n, ROUND(AVG(json_extract(detalle, '$.espera')), 1) espera"
        " FROM eventos WHERE ts >= ? AND tipo = 'metrica' AND mensaje = 'busqueda' GROUP BY resultado", (desde,))]
    m["sobres"] = dict(con.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(json_extract(detalle, '$.calidades.estrella')), 0) estrellas,"
        " COALESCE(SUM(json_extract(detalle, '$.calidades.crack')), 0) cracks"
        " FROM eventos WHERE ts >= ? AND tipo = 'metrica' AND mensaje = 'sobre'", (desde,)).fetchone())
    con.close()
    return m


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Resumen de la bitácora del servidor")
    ap.add_argument("--horas", type=float, default=24)
    ap.add_argument("--pid")
    ap.add_argument("--errores", action="store_true", help="solo errores y avisos")
    a = ap.parse_args()
    r = resumen(a.horas, a.pid)
    print(f"Últimas {a.horas:g} h: {r['totales']}")
    print("\n== Errores más repetidos")
    for e in r["errores"]:
        print(f"  [{e['nivel']}/{e['tipo']}] x{e['n']} ({e['jugadores']} jug.) {e['ruta']}: {e['mensaje'][:140]}")
    print("\n== Rutas lentas")
    for e in r["lentas"]:
        print(f"  {e['metodo']} {e['ruta']} x{e['n']} prom {e['prom']} ms, máx {e['max']} ms")
    if not a.errores:
        print("\n== Jugadores")
        for j in r["jugadores"]:
            print(f"  {j['pid'][:8]} {j['n']} eventos, {j['errores']} errores · {j['dispositivos']} · {time.strftime('%d/%m %H:%M', time.localtime(j['ultimo']))}")
