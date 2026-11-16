"""Álbum: cartas que tuviste por liga y club, y premios al llegar a la mitad y al completar cada club."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego import album
from juego.partida import ErrorJuego, Partida
from web import bitacora
from web.comun import P, _carta_json, error_json, ir, pagina
from web.rutas.tienda import objeto_json

router = APIRouter()


@router.get("/album", response_class=HTMLResponse)
def ver_album(request: Request, liga: str = "", club: str = "", p: Partida = P):
    if not p.existe:
        return ir("/")
    ligas = album.resumen(p)
    if liga and club:
        try:
            c = album.club(p, liga, club)
        except ErrorJuego as e:
            return ir("/album", error=str(e))
        cartas = [_carta_json(carta, tengo=tengo) for carta, tengo in c.pop("cartas")]
        objetos = [objeto_json(o) for o in p.coleccion() if o["club"] == club]
        objetos.sort(key=lambda o: o["tipo"] != "escudo")
        return pagina(request, "album.html", p, vista="club", c=c, cartas=cartas, objetos=objetos)
    if liga:
        lg = next((x for x in ligas if x["liga"] == liga), None)
        if not lg:
            return ir("/album")
        return pagina(request, "album.html", p, vista="liga", lg=lg)
    total = sum(x["total"] for x in ligas)
    tengo = sum(x["tengo"] for x in ligas)
    return pagina(request, "album.html", p, vista="ligas", ligas=ligas, total=total, tengo=tengo)


@router.post("/api/album/premio")
async def cobrar_premio(request: Request, p: Partida = P):
    try:
        d = await request.json()
        r = album.cobrar(p, str(d.get("liga", "")), str(d.get("club", "")), int(d.get("nivel", 0)))
    except ErrorJuego as e:
        return error_json(e)
    except (ValueError, TypeError):
        return error_json(ErrorJuego("Pedido inválido."))
    bitacora.anotar("metrica", "album_premio", detalle={"club": d.get("club"), "nivel": d.get("nivel")})
    return {**r, "monedas_total": p.monedas}
