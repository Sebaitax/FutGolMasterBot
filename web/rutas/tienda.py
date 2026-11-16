"""Tienda de sobres, objetos de colección y mercado de transferencias."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego import economia
from juego.economia import SOBRES
from juego.partida import ErrorJuego, Partida
from urllib.parse import quote
from web import bitacora
from web.comun import P, _carta_json, _ficha_json, error_json, escudo_url, ir, pagina

router = APIRouter()

# ------------------------------------------------------------------ tienda y mercado

@router.get("/tienda", response_class=HTMLResponse)
def tienda(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    sobres = {k: {**s, "precio": economia.precio_sobre(k, p.cancha)} for k, s in SOBRES.items()}
    return pagina(request, "tienda.html", p, sobres=sobres, espera_gratis=p.segundos_para_carta_gratis(),
                  objetos_tengo=sum(1 for o in p.coleccion() if o["tengo"]), objetos_total=len(p.coleccion()),
                  prob_gratis=economia.CARTA_GRATIS_PROBABILIDADES, calidades=economia.CALIDADES, cancha=p.info_cancha())


def objeto_json(o: dict) -> dict:
    if o["tipo"] == "escudo":
        imagen = escudo_url(o["club"])
    else:
        imagen = f"/estadios/{quote(o['archivo'])}" if o.get("archivo") else None
    return {"id": o["id"], "tipo": o["tipo"], "club": o["club"], "nombre": o["nombre"], "nivel": o["rareza"],
            "capacidad": o.get("capacidad") or 0, "imagen": imagen, "tengo": o.get("tengo", True),
            "nuevo": o.get("nuevo", False), "en_uso": o.get("en_uso", False)}


@router.post("/api/sobre/{clave}")
def api_sobre(clave: str, p: Partida = P):
    try:
        r = p.abrir_sobre_completo(clave)
    except ErrorJuego as e:
        return error_json(e)
    bitacora.anotar("juego", f"Sobre {clave}", detalle={
        "cartas": [f"{f.carta.nombre} {f.carta.ovr}" for f in r["cartas"]], "objetos": [o["nombre"] for o in r["objetos"]],
        "monedas": p.monedas})
    return {"cartas": [_ficha_json(f) for f in r["cartas"]], "objetos": [objeto_json(o) for o in r["objetos"]],
            "monedas": p.monedas}


@router.post("/api/objeto/{coleccionable_id}/usar")
def api_usar_objeto(coleccionable_id: int, p: Partida = P):
    try:
        p.usar_objeto(coleccionable_id)
    except ErrorJuego as e:
        return error_json(e)
    return {"ok": True}


# mercado de transferencias: desactivado por ahora (el código queda listo para volver a prenderlo)
MERCADO_ACTIVO = False


@router.get("/mercado", response_class=HTMLResponse)
def mercado(request: Request, p: Partida = P):
    if not MERCADO_ACTIVO:
        return ir("/", aviso="El mercado de transferencias está cerrado por ahora.")
    if not p.existe:
        return ir("/")
    return pagina(request, "mercado.html", p, fecha=p.fecha, en_venta=len(p.ofertas()), **p.opciones_busqueda())


def _oferta_json(o: dict) -> dict:
    return _carta_json(o["carta"], carta_id=o["carta_id"], en_mercado=o["en_mercado"], precio=o["precio"],
                       vendedor=o["vendedor"], quedan=o["quedan"], vendida=o["vendida"], tuya=o["tuya"],
                       edad=o.get("edad") or None, liga=o["carta"].liga, valor=o["carta"].precio)


@router.get("/api/buscar")
def api_buscar(q: str = "", club: str = "", nacion: str = "", pos: str = "", venta: int = 1, ovr_min: int = 0,
               ovr_max: int = 99, precio_max: int = 0, orden: str = "ovr", p: Partida = P):
    """venta=1: lo que está en venta en el mercado; venta=0: todos los jugadores del juego."""
    if not MERCADO_ACTIVO:
        return error_json(ErrorJuego("El mercado está cerrado por ahora."))
    if not p.existe:
        return error_json(ErrorJuego("Primero crea una partida."))
    resultados = p.buscar(q[:60], club=club, nacion=nacion, posicion=pos[:4], solo_venta=bool(venta),
                          ovr_min=ovr_min, ovr_max=ovr_max, precio_max=precio_max, orden=orden[:12])
    return {"resultados": [_oferta_json(o) for o in resultados]}


@router.get("/api/mercado/jugador/{carta_id}")
def api_en_venta(carta_id: int, p: Partida = P):
    """¿Alguien vende a este jugador? (para el botón "Buscar en el mercado")."""
    if not MERCADO_ACTIVO:
        return error_json(ErrorJuego("El mercado está cerrado por ahora."))
    if not p.existe:
        return error_json(ErrorJuego("Primero crea una partida."))
    return {"publicaciones": [_oferta_json(o) for o in p.en_venta(carta_id)], "monedas": p.monedas}


@router.post("/api/comprar/{carta_id}")
def api_comprar(carta_id: int, p: Partida = P):
    if not MERCADO_ACTIVO:
        return error_json(ErrorJuego("El mercado está cerrado por ahora."))
    try:
        f = p.comprar(carta_id)
    except ErrorJuego as e:
        return error_json(e)
    return {"carta": _ficha_json(f), "monedas": p.monedas}
