"""Bitácora privada y página de administración."""
import html
import json
import time as _time
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from urllib.parse import urlencode
from web import bitacora, cuentas
from web.comun import _es_la_pc, _nombre_club

router = APIRouter()

# ------------------------------------------------------------------ bitácora privada

_cupo_js: dict[str, list[float]] = {}


@router.post("/api/log")
async def api_log(request: Request):
    """Errores de JavaScript del navegador de cada jugador (máximo 40 cada 10 minutos por jugador)."""
    pid = getattr(request.state, "partida_id", "")
    ahora = _time.time()
    cupo = [t for t in _cupo_js.get(pid, []) if ahora - t < 600]
    if len(cupo) >= 40:
        return {"ok": False}
    _cupo_js[pid] = cupo + [ahora]
    try:
        d = json.loads((await request.body())[:20000] or b"{}")
    except ValueError:
        return {"ok": False}
    if not isinstance(d, dict):
        return {"ok": False}
    bitacora.anotar("js", str(d.get("mensaje", ""))[:1000], "error" if d.get("tipo") not in ("api", "aviso") else "aviso",
                    detalle={k: str(d.get(k, ""))[:4000] for k in ("pagina", "fuente", "linea", "pila", "tipo", "url", "estado", "datos")},
                    ruta=str(d.get("pagina", ""))[:300])
    return {"ok": True}


@router.get("/admin/logs", response_class=HTMLResponse)
def admin_logs(request: Request, horas: float = 24, pid: str = "", nivel: str = "", tipo: str = ""):
    usuario = getattr(request.state, "usuario", None)
    if not (_es_la_pc(request) or (usuario and usuario["admin"])):
        return HTMLResponse("No encontrado", status_code=404)
    r = bitacora.resumen(horas, pid or None, nivel or None, tipo or None)
    minuto = int(_time.time() // 600)
    club = lambda x: _nombre_club(x, minuto) if x else ""
    e = html.escape
    fecha = lambda ts: _time.strftime("%d/%m %H:%M:%S", _time.localtime(ts))
    link = lambda **k: "?" + urlencode({"horas": horas, "pid": pid, "nivel": nivel, "tipo": tipo, **k})
    t = r["totales"]
    met = bitacora.metricas(horas)
    pedidos = cuentas.pedidos()
    filas_c = "".join(
        f"<tr><td>{e(u['email'])}</td><td>{_time.strftime('%d/%m %H:%M', _time.localtime(u['ultimo_ingreso'])) if u.get('ultimo_ingreso') else '—'}</td>"
        f"<td>{'pidió recuperar' if u['email'] in pedidos else ''}</td><td><form method='post' action='/admin/restablecer' style='margin:0'>"
        f"<input type='hidden' name='email' value='{e(u['email'])}'><button>Generar link</button></form></td></tr>"
        for u in sorted(cuentas.lista(), key=lambda u: (u['email'] not in pedidos, u['email'])))
    fila_m = lambda etiqueta, valor: f"<tr><td>{etiqueta}</td><td><b>{valor}</b></td></tr>"
    partidos = "".join(fila_m(f"Partidos {e(x['modo'] or '?')}", f"{x['n']} · {x['victorias'] or 0}G/{x['derrotas'] or 0}P · {x['duracion'] or '?'} s promedio")
                       for x in met.get("partidos", []))
    busquedas = "".join(fila_m(f"Búsquedas → {e(x['resultado'] or '?')}", f"{x['n']} · espera {x['espera']} s") for x in met.get("busquedas", []))
    sob = met.get("sobres") or {}
    tabla_metricas = (fila_m("Jugadores activos", met.get("activos", 0)) + fila_m("Cuentas nuevas", met.get("cuentas_nuevas", 0))
                      + fila_m("Clubes creados", met.get("clubes_nuevos", 0)) + partidos + busquedas
                      + fila_m("Sobres abiertos", f"{sob.get('n', 0)} · estrellas {sob.get('estrellas', 0)} · cracks {sob.get('cracks', 0)}")
                      + fila_m("Errores (servidor + navegador)", f"{met.get('errores', 0)} · JS {met.get('errores_js', 0)}")
                      + fila_m("Posibles pegados / reconexiones", f"{met.get('pegados', 0)} / {met.get('reconexiones', 0)}")
                      + fila_m("Sospechas de trampa", met.get("trampas", 0)))
    filas_j = "".join(
        f"<tr><td><a href='{link(pid=j['pid'])}'>{e(club(j['pid']) or j['pid'][:8])}</a></td><td>{j['n']}</td>"
        f"<td class='{'malo' if j['errores'] else ''}'>{j['errores'] or 0}</td><td>{j['avisos'] or 0}</td>"
        f"<td>{e(j['dispositivos'] or '')}</td><td>{e(j['pais'] or '')}</td><td>{fecha(j['ultimo'])}</td></tr>" for j in r["jugadores"])
    filas_e = "".join(
        f"<tr><td>{e(x['nivel'])}/{e(x['tipo'])}</td><td>{x['n']}</td><td>{x['jugadores']}</td><td>{e(x['ruta'] or '')}</td>"
        f"<td>{e((x['mensaje'] or '')[:200])}</td><td>{fecha(x['ultimo'])}</td></tr>" for x in r["errores"])
    filas_l = "".join(f"<tr><td>{e(x['metodo'])} {e(x['ruta'])}</td><td>{x['n']}</td><td>{x['prom']} ms</td><td>{x['max']} ms</td></tr>"
                      for x in r["lentas"])
    filas_ev = "".join(
        f"<tr class='{e(x['nivel'])}'><td>{fecha(x['ts'])}</td><td><a href='{link(pid=x['pid'] or '')}'>{e(club(x['pid']) or (x['pid'] or '')[:8])}</a></td>"
        f"<td>{e(x['tipo'])}</td><td>{e(x['metodo'] or '')} {e(x['ruta'] or '')}</td><td>{x['estado'] or ''}</td><td>{x['ms'] if x['ms'] is not None else ''}</td>"
        f"<td>{e(x['mensaje'] or '')}{'<details><summary>detalle</summary><pre>' + e(x['detalle']) + '</pre></details>' if x['detalle'] else ''}</td></tr>"
        for x in r["eventos"])
    filtros = " · ".join(f"<a href='{link(**{k: v})}'>{n}</a>" for k, v, n in (
        ("horas", 1, "1 h"), ("horas", 24, "24 h"), ("horas", 168, "7 días"), ("nivel", "error", "solo errores"),
        ("nivel", "aviso", "solo avisos"), ("tipo", "js", "errores JS"), ("tipo", "juego", "eventos de juego"),
        ("tipo", "excepcion", "excepciones")))
    return HTMLResponse(f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bitácora FGM</title><style>
body{{font:14px system-ui,sans-serif;margin:16px;background:#0f1512;color:#e7efe9}} a{{color:#5ee08a}} h2{{margin-top:28px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}} td,th{{border-bottom:1px solid #263129;padding:4px 6px;text-align:left;vertical-align:top}}
.malo,.error td:first-child{{color:#ff7b6b;font-weight:700}} tr.aviso td:first-child{{color:#f3c74b}}
pre{{white-space:pre-wrap;max-width:900px;font-size:11.5px;background:#18211b;padding:8px}} .caja{{overflow-x:auto}}
.tot b{{font-size:1.3em;margin-right:14px}}</style></head><body>
<h1>Bitácora privada</h1>
<p class="tot">Últimas {horas:g} h{' · jugador ' + e(club(pid) or pid) if pid else ''}{' · ' + e(nivel) if nivel else ''}{' · ' + e(tipo) if tipo else ''}:
<b>{t.get('eventos') or 0}</b> eventos <b class="malo">{t.get('errores') or 0}</b> errores <b>{t.get('avisos') or 0}</b> avisos <b>{t.get('jugadores') or 0}</b> jugadores</p>
<p>{filtros} · <a href="/admin/logs">limpiar filtros</a></p>
<h2>Cuentas ({len(cuentas.lista())})</h2><div class="caja"><table><tr><th>correo</th><th>último ingreso</th><th></th><th>contraseña</th></tr>{filas_c}</table></div>
<h2>Métricas</h2><div class="caja"><table>{tabla_metricas}</table></div>
<h2>Problemas más repetidos</h2><div class="caja"><table><tr><th>tipo</th><th>veces</th><th>jugadores</th><th>ruta</th><th>mensaje</th><th>último</th></tr>{filas_e or '<tr><td colspan=6>Nada</td></tr>'}</table></div>
<h2>Jugadores</h2><div class="caja"><table><tr><th>club</th><th>eventos</th><th>errores</th><th>avisos</th><th>dispositivo</th><th>país</th><th>última vez</th></tr>{filas_j}</table></div>
<h2>Respuestas lentas (≥ {bitacora.LENTO_MS} ms)</h2><div class="caja"><table><tr><th>ruta</th><th>veces</th><th>promedio</th><th>máx</th></tr>{filas_l or '<tr><td colspan=4>Ninguna</td></tr>'}</table></div>
<h2>Últimos eventos</h2><div class="caja"><table><tr><th>hora</th><th>club</th><th>tipo</th><th>ruta</th><th>estado</th><th>ms</th><th>mensaje</th></tr>{filas_ev}</table></div>
</body></html>""")
