"""Partidos en vivo entre amigos (PvP): sala de espera, apuestas entre ellos y el partido compartido."""
import json
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from juego.en_vivo import Sala, equipo_de
from juego.formaciones import COORDENADAS
from juego.partida import ErrorJuego, Partida
from partidos.motor import FORMACIONES, MINUTOS_LECTURA, TACTICAS, VENCE
from web.comun import P, _info_club, _leer_partida, _yo, error_json, ir, pagina, registro, ruta_de

router = APIRouter()

# ------------------------------------------------------------------ en vivo entre amigos

SALA = Sala()


@router.get("/vivo", response_class=HTMLResponse)
def vivo_sala(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    estado = SALA.ver(_yo(request))
    if estado["partido"]:
        return ir(f"/vivo/{estado['partido']}")
    return pagina(request, "vivo_sala.html", p)


@router.get("/api/vivo/sala")
def api_vivo_sala(request: Request, p: Partida = P):
    return SALA.ver(_yo(request))


@router.post("/api/vivo/esperar")
async def api_vivo_esperar(request: Request, p: Partida = P):
    if not p.existe:
        return error_json(ErrorJuego("Primero crea tu club."))
    if len(p.exportar_equipo()["jugadores"]) < 11:
        return error_json(ErrorJuego("Necesitas al menos 11 jugadores."))
    try:
        apuesta = int((await request.json()).get("apuesta", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        apuesta = 0
    if apuesta > p.monedas:
        return error_json(ErrorJuego("No te alcanzan las monedas para esa apuesta."))
    SALA.esperar(_yo(request), _info_club(p), apuesta)
    return SALA.ver(_yo(request))


def _cobrar_apuesta(pids: list[str], monto: int, mid: str):
    """Saca la apuesta de las dos partidas (y la anota por si el servidor se reinicia a mitad)."""
    for pid in pids:
        q = Partida.abrir(ruta_de(pid))
        try:
            if q.monedas < monto:
                raise ErrorJuego("Alguno de los dos ya no tiene monedas para la apuesta.")
        finally:
            q.con.close()
    for pid in pids:
        q = Partida.abrir(ruta_de(pid))
        try:
            q._mover_monedas(-monto, "Apuesta en vivo")
            q.con.commit()
        finally:
            q.con.close()
    reg = registro()
    try:
        reg.con.execute("CREATE TABLE IF NOT EXISTS apuestas (mid TEXT PRIMARY KEY, pids TEXT, monto INTEGER, abierta INTEGER)")
        reg.con.execute("INSERT INTO apuestas VALUES (?, ?, ?, 1)", (mid, json.dumps(pids), monto))
        reg.con.commit()
    finally:
        reg.cerrar()


def _pagar_apuesta(mid: str, pagos: dict[str, int], concepto: str):
    reg = registro()
    try:
        reg.con.execute("CREATE TABLE IF NOT EXISTS apuestas (mid TEXT PRIMARY KEY, pids TEXT, monto INTEGER, abierta INTEGER)")
        fila = reg.con.execute("SELECT abierta FROM apuestas WHERE mid = ?", (mid,)).fetchone()
        if not fila or not fila[0]:
            return
        for pid, monto in pagos.items():
            if monto:
                q = Partida.abrir(ruta_de(pid))
                try:
                    q._mover_monedas(monto, concepto)
                    q.con.commit()
                finally:
                    q.con.close()
        reg.con.execute("UPDATE apuestas SET abierta = 0 WHERE mid = ?", (mid,))
        reg.con.commit()
    finally:
        reg.cerrar()


def _devolver_apuestas_abiertas():
    """Al arrancar el servidor, los partidos en vivo se perdieron: se devuelven las apuestas."""
    reg = registro()
    try:
        reg.con.execute("CREATE TABLE IF NOT EXISTS apuestas (mid TEXT PRIMARY KEY, pids TEXT, monto INTEGER, abierta INTEGER)")
        abiertas = reg.con.execute("SELECT mid, pids, monto FROM apuestas WHERE abierta = 1").fetchall()
    finally:
        reg.cerrar()
    for mid, pids, monto in abiertas:
        _pagar_apuesta(mid, {pid: monto for pid in json.loads(pids)}, "Apuesta devuelta (se cortó el partido)")


try:
    _devolver_apuestas_abiertas()
except Exception:
    pass


@router.post("/api/vivo/cancelar")
def api_vivo_cancelar(request: Request):
    SALA.cancelar(_yo(request))
    return {"ok": True}


@router.post("/api/vivo/aceptar/{rival}")
def api_vivo_aceptar(request: Request, rival: str, p: Partida = P):
    yo = _yo(request)
    if rival == yo:
        return error_json(ErrorJuego("No puedes jugar contra ti mismo."))
    otro = _leer_partida(rival)
    if not otro:
        return error_json(ErrorJuego("Ese club ya no existe."))
    try:
        suyo = otro.exportar_equipo()
    finally:
        otro.con.close()
    apuesta = SALA.apuesta_de(rival)
    if apuesta > p.monedas:
        return error_json(ErrorJuego(f"Para aceptar necesitas {apuesta:,} monedas.".replace(",", ".")))
    try:
        mid = SALA.aceptar(yo, rival, p.exportar_equipo(), suyo)
    except ValueError as e:
        return error_json(ErrorJuego(str(e)))
    if apuesta:
        try:
            _cobrar_apuesta([rival, yo], apuesta, mid)
        except ErrorJuego as e:
            SALA.terminar(mid)
            SALA.partidos.pop(mid, None)
            return error_json(e)
    return {"partido": mid}


def _partido_vivo(request: Request, mid: str):
    vp = SALA.partido(mid)
    yo = _yo(request)
    if not vp or yo not in vp.pids:
        return None, None
    return vp, vp.pids.index(yo)


@router.get("/vivo/{mid}", response_class=HTMLResponse)
def vivo_partido(request: Request, mid: str, p: Partida = P):
    vp, lado = _partido_vivo(request, mid)
    if vp is None:
        return ir("/amistosos", error="Ese partido en vivo ya no existe.")
    datos = {"id": mid, "lado": lado, "local": vp.nombres[0], "visita": vp.nombres[1],
             "pids": vp.pids, "colores": ["#e8eef0", "#e74c3c"],
             "tacticas": {k: {"nombre": t["nombre"], "ico": t["ico"], "ayuda": t["ayuda"]} for k, t in TACTICAS.items()},
             "vence": VENCE, "minutos_lectura": MINUTOS_LECTURA,
             # para dibujar la cancha: once inicial de cada uno en orden de la formación
             "equipos": [{"formacion": e.formacion, "jugadores": [j.nombre for j in e.titulares]}
                         for e in (equipo_de(d) for d in vp.datos)],
             "formaciones": FORMACIONES, "coordenadas": COORDENADAS}
    return pagina(request, "vivo.html", p, datos=json.dumps(datos, ensure_ascii=False), vp=datos)


@router.get("/api/vivo/{mid}/estado")
def api_vivo_estado(request: Request, mid: str, desde: int = 0, t: int = 1, m: int = 0):
    vp, lado = _partido_vivo(request, mid)
    if vp is None:
        return error_json(ErrorJuego("Ese partido ya no existe."))
    r = vp.estado(lado, desde, (t, m))
    if r["final"] and not vp.anotado:
        vp.anotado = True
        res = vp.resultado
        goleadores = [[ev.jugador for ev in res.eventos if ev.tipo == "gol" and ev.equipo == eq] for eq in (0, 1)]
        reg = registro()
        try:
            reg.anotar(vp.pids[0], vp.nombres[0], vp.pids[1], vp.nombres[1],
                       {"de_local": True, "goles": res.goles[0], "goles_rival": res.goles[1],
                        "goleadores": goleadores[0], "goleadores_rival": goleadores[1]})
        finally:
            reg.cerrar()
        if vp.apuesta:
            g0, g1 = res.goles
            pagos = ({vp.pids[0]: 2 * vp.apuesta} if g0 > g1 else {vp.pids[1]: 2 * vp.apuesta} if g1 > g0
                     else {vp.pids[0]: vp.apuesta, vp.pids[1]: vp.apuesta})
            _pagar_apuesta(mid, pagos, "Apuesta en vivo ganada" if g0 != g1 else "Apuesta en vivo (empate)")
        SALA.terminar(mid)
    return r


@router.post("/api/vivo/{mid}/{accion}")
async def api_vivo_accion(request: Request, mid: str, accion: str):
    vp, lado = _partido_vivo(request, mid)
    if vp is None:
        return error_json(ErrorJuego("Ese partido ya no existe."))
    cuerpo = await request.json()
    try:
        if accion == "elegir":
            vp.elegir(lado, str(cuerpo.get("eleccion", "")))
        elif accion == "toque":
            vp.tocar(lado, int(cuerpo["ronda"]), float(cuerpo["precision"]))
        elif accion == "tactica":
            vp.tactica(lado, str(cuerpo.get("valor", "")))
        elif accion == "reaccion":
            vp.reaccionar(lado, str(cuerpo.get("emoji", "")))
        elif accion == "revancha":
            nuevo = SALA.pedir_revancha(mid, lado)
            if nuevo and vp.apuesta and not getattr(vp, "revancha_cobrada", False):
                vp.revancha_cobrada = True
                try:
                    _cobrar_apuesta(vp.pids, vp.apuesta, nuevo)
                except ErrorJuego:
                    SALA.partidos[nuevo].apuesta = 0   # alguno ya no tiene: la revancha va sin apuesta
            return {"ok": True, "partido": nuevo}
        else:
            return error_json(ErrorJuego("Acción desconocida."))
    except (KeyError, TypeError, ValueError) as e:
        return error_json(ErrorJuego(str(e)))
    return {"ok": True}


@router.post("/desafiar/{amigo}")
def desafiar(request: Request, amigo: str, de_local: str = Form("1"), p: Partida = P):
    if amigo == request.state.partida_id:
        return ir("/amistosos", error="No puedes desafiarte a ti mismo.")
    otro = _leer_partida(amigo)
    if not otro:
        return ir("/amistosos", error="Ese club ya no existe.")
    try:
        datos = otro.exportar_equipo()
    finally:
        otro.con.close()
    try:
        pid = p.desafiar(amigo, datos, de_local == "1")
    except ErrorJuego as e:
        return ir("/amistosos", error=str(e))
    return ir(f"/partido/{pid}/vivo")


@router.post("/amistoso/{rival_id}")
def jugar_amistoso(rival_id: int, de_local: str = Form("1"), p: Partida = P):
    try:
        pid = p.iniciar_amistoso(rival_id, de_local == "1")
    except ErrorJuego as e:
        return ir("/amistosos", error=str(e))
    return ir(f"/partido/{pid}/vivo")
