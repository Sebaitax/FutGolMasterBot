"""Apuestas a partidos reales con las monedas del juego."""
import json
import time as _time
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego import apuestas
from juego.partida import ErrorJuego, Partida
from web import bitacora
from web.comun import P, _nombre_club, _yo, error_json, ir, pagina, ruta_de

from web.iconos import bandera_url as _bandera_url  # noqa: E402

router = APIRouter()

# ------------------------------------------------------------------ apuestas a partidos reales

def _pagar_apuesta_real(pid: str, monto: int, concepto: str):
    q = Partida.abrir(ruta_de(pid))
    try:
        q._mover_monedas(monto, concepto)
        q.con.commit()
    finally:
        q.con.close()
    bitacora.anotar("juego", concepto, pid=pid, detalle={"monto": monto})


apuestas.iniciar(_pagar_apuesta_real, lambda m: bitacora.anotar("apuestas", m, "aviso"))


@router.get("/apuestas", response_class=HTMLResponse)
def ver_apuestas(request: Request, liga: str = "chile", p: Partida = P):
    if not p.existe:
        return ir("/")
    if liga not in apuestas.LIGAS:
        liga = "chile"
    yo = _yo(request)
    minuto = int(_time.time() // 60)
    ranking = [{**r, "club": _nombre_club(r["pid"], minuto) or r["club"], "yo": r["pid"] == yo} for r in apuestas.ranking()]
    for r in ranking:
        del r["pid"]
    datos = {"liga": liga, "ligas": [{"clave": k, "nombre": n, "bandera": b, "bandera_img": _bandera_url(b), "partidos": len(apuestas.proximos(k))}
                                     for k, (n, b, _) in apuestas.LIGAS.items()],
             "proximos": apuestas.proximos(liga), "recientes": apuestas.recientes(liga),
             "mias": apuestas.mis_apuestas(yo), "ranking": ranking, "minima": apuestas.APUESTA_MINIMA,
             "actualizado": apuestas.info()["actualizado"]}
    return pagina(request, "apuestas.html", p, datos=json.dumps(datos, ensure_ascii=False))


@router.post("/api/apuestas")
async def api_apostar(request: Request, p: Partida = P):
    if not p.existe:
        return error_json(ErrorJuego("Primero crea tu club."))
    try:
        cuerpo = await request.json()
        partido_id, eleccion, monto = int(cuerpo["partido"]), str(cuerpo["eleccion"]), int(cuerpo["monto"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return error_json(ErrorJuego("Apuesta inválida."))

    def cobrar(monto: int, concepto: str):
        if monto > p.monedas:
            raise apuestas.ErrorApuesta("No te alcanzan las monedas para esa apuesta.")
        p._mover_monedas(-monto, concepto)
        p.con.commit()

    try:
        r = apuestas.apostar(_yo(request), p.nombre_equipo(p.usuario_id), partido_id, eleccion, monto, cobrar)
    except apuestas.ErrorApuesta as e:
        return error_json(ErrorJuego(str(e)))
    bitacora.anotar("juego", f"apuesta {eleccion} x{r['cuota']}", detalle={"partido": partido_id, "monto": monto})
    return {**r, "monedas": p.monedas, "mias": apuestas.mis_apuestas(_yo(request))}
