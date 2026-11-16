"""Inventario: mejoras con cartas repetidas y la carta gratis."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego import economia
from juego.partida import ErrorJuego, Partida
from web import bitacora
from web.comun import P, _ficha_json, error_json, ir, pagina
from web.rutas.tienda import objeto_json

router = APIRouter()

# ------------------------------------------------------------------ inventario y mejoras

@router.get("/inventario", response_class=HTMLResponse)
def inventario(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    copias = p.copias()
    fichas = []
    for f in p.plantel():
        j = _ficha_json(f)
        j.update(copias=len(copias[f.carta_id]), puede_mejorar=p.puede_mejorar(f, copias),
                 costo_mejora=economia.costo_mejora(f.nivel), en_once=f.puesto is not None and f.puesto < 11,
                 en_banca=f.puesto is not None and f.puesto >= 11)
        fichas.append(j)
    coleccion = [objeto_json(o) for o in p.coleccion()]
    p.marcar_objetos_vistos()
    return pagina(request, "inventario.html", p, datos=json.dumps({"fichas": fichas, "maximo": economia.NIVEL_MAXIMO,
                                                                   "coleccion": coleccion}, ensure_ascii=False))


@router.post("/api/mejorar/{pid}")
def api_mejorar(pid: int, p: Partida = P):
    try:
        f = p.mejorar(pid)
    except ErrorJuego as e:
        return error_json(e)
    return {"carta": _ficha_json(f), "monedas": p.monedas}


@router.post("/api/carta-gratis")
def api_carta_gratis(p: Partida = P):
    try:
        f = p.reclamar_carta_gratis()
    except ErrorJuego as e:
        return error_json(e)
    bitacora.anotar("juego", f"Carta gratis: {f.carta.nombre} {f.carta.ovr}")
    return {"cartas": [_ficha_json(f)], "monedas": p.monedas, "espera": p.segundos_para_carta_gratis()}
