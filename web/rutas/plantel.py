"""Plantel: alineación, venta de cartas y alineaciones guardadas."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego.formaciones import COORDENADAS, ENLACES
from juego.partida import ErrorJuego, Partida
from partidos.motor import FORMACIONES, MENTALIDADES
from web import bitacora
from web.comun import P, _ficha_json, error_json, ir, pagina

router = APIRouter()

# ------------------------------------------------------------------ plantel

@router.get("/plantel", response_class=HTMLResponse)
def plantel(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    equipo = p.equipo(p.usuario_id)
    fichas = p.plantel()
    once = _once(p)
    datos = {
        "fichas": [_ficha_json(f) for f in fichas], "once": once, "formacion": equipo["formacion"],
        "mentalidad": equipo["mentalidad"], "formaciones": FORMACIONES, "coordenadas": COORDENADAS,
        "enlaces": ENLACES, "fuerza": round(p.fuerza_equipo(p.usuario_id), 1),
        "deshacer": p.ultima_venta is not None,
        "alineaciones": [{"id": a["id"], "nombre": a["nombre"], "activa": a["activa"]} for a in p.alineaciones()],
    }
    return pagina(request, "plantel.html", p, mentalidades=list(MENTALIDADES), datos=json.dumps(datos, ensure_ascii=False))


def _once(p: Partida) -> list:
    """18 lugares: 0-10 titulares y 11-17 suplentes."""
    once = [None] * 18
    for f in p.plantel():
        if f.puesto is not None and f.puesto < 18:
            once[f.puesto] = f.pid
    return once


@router.post("/api/alineacion")
async def api_alineacion(request: Request, p: Partida = P):
    """Guarda formación, mentalidad y once: {"formacion", "mentalidad", "once": [pid|null x 11], "auto": bool}."""
    cuerpo = await request.json()
    try:
        if cuerpo.get("auto"):
            p.alinear_auto(cuerpo["formacion"])
            cuerpo["once"] = _once(p)
        p.guardar_alineacion(cuerpo["formacion"], cuerpo["mentalidad"],
                             {i: pid for i, pid in enumerate(cuerpo["once"][:18]) if pid})
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)
    q = p.quimica_usuario()
    return {"once": _once(p), "fuerza": round(p.fuerza_equipo(p.usuario_id), 1), "quimica": q}


@router.post("/api/vender")
async def api_vender(request: Request, p: Partida = P):
    cuerpo = await request.json()
    try:
        monto = p.vender_varios([int(x) for x in cuerpo.get("pids", [])])
    except (ErrorJuego, TypeError, ValueError) as e:
        return error_json(e)
    bitacora.anotar("juego", f"Vendió {len(cuerpo.get('pids', []))} carta(s) por {monto}", detalle={"monedas": p.monedas})
    return {"monto": monto, "monedas": p.monedas}


@router.post("/api/deshacer-venta")
def api_deshacer(p: Partida = P):
    try:
        n = p.deshacer_venta()
    except ErrorJuego as e:
        return error_json(e)
    return {"cartas": n, "monedas": p.monedas}


# ------------------------------------------------------------------ alineaciones guardadas

@router.post("/api/alineaciones/{accion}")
async def api_alineaciones(accion: str, request: Request, p: Partida = P):
    cuerpo = await request.json()
    try:
        if accion == "nueva":
            p.nueva_alineacion(cuerpo.get("nombre", ""))
        elif accion == "usar":
            p.usar_alineacion(int(cuerpo["id"]))
        elif accion == "renombrar":
            p.renombrar_alineacion(int(cuerpo["id"]), cuerpo.get("nombre", ""))
        elif accion == "borrar":
            p.borrar_alineacion(int(cuerpo["id"]))
        else:
            return error_json(ErrorJuego("Acción desconocida."))
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)
    return {"ok": True}
