"""Inicio y escalera de copas: crear el club, buscar partido por copas y sobres por tiempo."""
import json
import random
import time as _time
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from juego import escalera as ESC
from juego.partida import ErrorJuego, Partida
from web import bitacora
from web.comun import BD, P, PRINCIPAL, _carta_json, _leer_partida, _yo, error_json, ir, pagina, sincronizar_liga
from web.rutas.imagenes import _png
from web.rutas.vivo import SALA

router = APIRouter()

# ------------------------------------------------------------------ inicio

@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, p: Partida = P):
    if not p.existe:
        return pagina(request, "crear.html", paises=[{"clave": k, "nombre": n, "bandera": b} for k, (n, b, _) in ESC.PAISES.items()])
    if p.partido_en_vivo():
        return ir(f"/partido/{p.partido_en_vivo()['partido']}/vivo")
    sincronizar_liga(p, getattr(request.state, "partida_id", PRINCIPAL))
    canchas = [p.info_cancha(i) for i in range(len(ESC.CANCHAS))]
    datos = {"copas": p.copas, "max_copas": p.max_copas, "cancha": p.info_cancha(), "canchas": canchas,
             "sobres": p.sobres_tiempo(), "espacios": ESC.ESPACIOS_SOBRES, "historial": p.historial_escalera[:8],
             "fuerza": round(p.fuerza_equipo(p.usuario_id), 1), "quimica": p.quimica_usuario()["equipo"],
             "no_disponibles": [{"nombre": f.carta.nombre_corto, "lesion": f.lesion, "suspension": f.suspension}
                                for f in p.plantel() if not f.disponible],
             "piso": ESC.piso(p.max_copas), "victoria": ESC.COPAS_VICTORIA, "derrota": ESC.COPAS_DERROTA}
    return pagina(request, "inicio.html", p, esc=datos, datos=json.dumps(datos, ensure_ascii=False))


# ------------------------------------------------------------------ escalera de copas (tipo Clash Royale)

def _jugadores_escalera(yo: str) -> list[dict]:
    """Los demás jugadores con club (para el ranking y para buscar rival)."""
    salida = []
    for pid in [PRINCIPAL] + [r.stem for r in (BD.parent / "partidas").glob("*.sqlite")]:
        if pid == yo:
            continue
        otra = _leer_partida(pid)
        if not otra:
            continue
        try:
            salida.append({"pid": pid, "nombre": otra.nombre_equipo(otra.usuario_id), "copas": otra.copas,
                           "pais": otra.pais, "cancha": otra.cancha})
        except Exception:
            continue
        finally:
            otra.con.close()
    return salida


BUSCAR_ONLINE = (5, 7)   # segundos (al azar) buscando rival online; después, un bot de tu cancha (sin avisar)


@router.get("/escalera/buscar", response_class=HTMLResponse)
def buscar_partido(request: Request, p: Partida = P):
    """Pantalla de búsqueda: primero un rival online (otro jugador buscando a la vez); si no hay, un bot."""
    if not p.existe:
        return ir("/")
    if p.partido_en_vivo():
        return ir(f"/partido/{p.partido_en_vivo()['partido']}/vivo")
    return pagina(request, "buscar.html", p, segundos=random.randint(*BUSCAR_ONLINE), cancha=p.info_cancha())


_buscando_desde: dict[str, float] = {}


@router.post("/api/escalera/buscar")
def api_buscar_partido(request: Request, p: Partida = P):
    if not p.existe:
        return error_json(ErrorJuego("Primero crea tu club."))
    datos = p.exportar_equipo()
    if len(datos["jugadores"]) < 11:
        return error_json(ErrorJuego("Necesitas al menos 11 jugadores."))
    yo = _yo(request)
    _buscando_desde.setdefault(yo, _time.time())
    mid = SALA.buscar_copas(yo, p.copas, datos)
    if mid:
        bitacora.anotar("metrica", "busqueda", detalle={"resultado": "online",
                                                        "espera": round(_time.time() - _buscando_desde.pop(yo, _time.time()), 1)})
        SALA.guardar(SALA.partido(mid), forzar=True)
        bitacora.anotar("juego", "partido por copas online encontrado", detalle={"partido": mid, "copas": p.copas})
    return {"partido": mid}


@router.post("/api/escalera/cancelar")
async def api_cancelar_busqueda(request: Request):
    yo = _yo(request)
    mid = SALA.cancelar_busqueda(yo)
    try:
        motivo = (await request.json()).get("motivo", "tiempo")
    except Exception:
        motivo = "salio"
    bitacora.anotar("metrica", "busqueda", detalle={
        "resultado": "online" if mid else "bot" if motivo == "tiempo" else "cancelada",
        "espera": round(_time.time() - _buscando_desde.pop(yo, _time.time()), 1)})
    return {"ok": True, "partido": mid}


@router.post("/escalera/jugar")
def jugar_escalera(request: Request, modo: str = Form("vivo"), p: Partida = P):
    if not p.existe:
        return ir("/")
    if p.partido_en_vivo():
        return ir(f"/partido/{p.partido_en_vivo()['partido']}/vivo")
    modo = "vivo"   # juego online: los partidos por copas se juegan siempre en vivo (sin simular ni acelerar)
    # sin rival online en vivo: siempre un bot de tu cancha (nunca el equipo de alguien que no está conectado)
    rival = None
    try:
        pid = p.iniciar_escalera(rival, en_vivo=modo != "rapido")
    except ErrorJuego as e:
        return ir("/", error=str(e))
    bitacora.anotar("juego", f"partido por copas ({'jugador' if rival else 'bot'}, {modo})", detalle={"copas": p.copas})
    return ir(f"/partido/{pid}/vivo" if modo != "rapido" else f"/partido/{pid}")


@router.post("/api/sobres-tiempo/{sobre_id}/{accion}")
def api_sobre_tiempo(sobre_id: int, accion: str, p: Partida = P):
    try:
        if accion == "desbloquear":
            p.desbloquear_sobre(sobre_id)
            return {"sobres": p.sobres_tiempo()}
        if accion in ("abrir", "abrir-ya"):
            fichas = p.abrir_sobre_tiempo(sobre_id, pagar=accion == "abrir-ya")
            copias = p.copias()
            cartas = [_carta_json(f.carta, pid=f.pid, repetida=len(copias.get(f.carta_id, [])) > 1,
                                  calidad=p.calidades.get(f.pid, "normal")) for f in fichas]
            bitacora.anotar("metrica", "sobre", detalle={"origen": "tiempo", "abrir_ya": accion == "abrir-ya",
                                                         "calidades": _contar_calidades(cartas)})
            return {"cartas": cartas, "sobres": p.sobres_tiempo(), "monedas": p.monedas}
    except ErrorJuego as e:
        return error_json(e)
    return error_json(ErrorJuego("Acción desconocida."))


@router.post("/crear")
def crear(nombre_club: str = Form(...), pais: str = Form(ESC.PAIS_DEFECTO), p: Partida = P):
    try:
        p.crear(nombre_club, pais=pais)
        bitacora.anotar("metrica", "club_creado", detalle={"pais": pais})
    except (ErrorJuego, FileNotFoundError) as e:
        return ir("/", error=str(e))
    return ir("/plantel", aviso="¡Club creado! Arma tu once y sal a jugar a la Cancha del Barrio.")


@router.post("/reiniciar")
def reiniciar(p: Partida = P):
    p.borrar()
    _png.cache_clear()
    return ir("/")


@router.post("/jugar")
def jugar(request: Request, p: Partida = P):
    sincronizar_liga(p, getattr(request.state, "partida_id", PRINCIPAL))
    try:
        pid = p.iniciar_partido()
    except ErrorJuego as e:
        return ir("/", error=str(e))
    return ir(f"/partido/{pid}/vivo")


@router.post("/jugar-rapido")
def jugar_rapido(request: Request, p: Partida = P):
    sincronizar_liga(p, getattr(request.state, "partida_id", PRINCIPAL))
    try:
        pid = p.jugar_fecha()
    except ErrorJuego as e:
        return ir("/", error=str(e))
    return ir(f"/partido/{pid}")


@router.post("/nueva-temporada")
def nueva_temporada(p: Partida = P):
    try:
        p.nueva_temporada()
    except ErrorJuego as e:
        return ir("/", error=str(e))
    return ir("/", aviso="Nueva temporada. ¡Suerte!")


def _contar_calidades(cartas: list[dict]) -> dict:
    cuenta: dict[str, int] = {}
    for c in cartas:
        cuenta[c.get("calidad", "normal")] = cuenta.get(c.get("calidad", "normal"), 0) + 1
    return cuenta
