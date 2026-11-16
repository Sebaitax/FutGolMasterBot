"""Imágenes generadas: cartas en PNG y escudos."""
from cartas.generador import carta_a_bytes
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, Response
from functools import lru_cache
from juego.identidad import escudo_svg
from juego.partida import Partida
from pathlib import Path
from web.comun import ESCUDOS, P, _leer_partida, escudo_url, ruta_partida
from web.rutas.perfil import LOGOS_USUARIO

router = APIRouter()

@lru_cache(maxsize=256)
def _png(ruta: Path, carta_id: int) -> bytes:
    p = Partida.abrir(ruta)
    try:
        carta = p.carta(carta_id)
    finally:
        p.con.close()
    return carta_a_bytes(carta).getvalue() if carta else b""


@router.get("/carta/{carta_id}.png")
def imagen_carta(request: Request, carta_id: int):
    datos = _png(ruta_partida(request), carta_id)
    if not datos:
        return Response(status_code=404)
    return Response(datos, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


# ------------------------------------------------------------------ escudos de los clubes del juego

@router.get("/escudo/equipo/{equipo_id}")
def escudo_equipo(equipo_id: int, p: Partida = P):
    e = p.equipo(equipo_id)
    if not e:
        return Response(status_code=404)
    return _respuesta_escudo(e["escudo"] or "")


@router.get("/escudo/amigo/{pid}")
def escudo_amigo(pid: str):
    otro = _leer_partida(pid)
    if not otro:
        return Response(status_code=404)
    try:
        valor = otro.equipo(otro.usuario_id)["escudo"] or ""
    finally:
        otro.con.close()
    return _respuesta_escudo(valor)


def _respuesta_escudo(valor: str) -> Response:
    if valor.startswith("real:"):  # escudo de colección (club real)
        url = escudo_url(valor[5:])
        if url:
            return FileResponse(ESCUDOS / Path(url).name, media_type="image/png", headers={"Cache-Control": "max-age=31536000"})
    if valor.startswith("archivo:"):
        ruta = LOGOS_USUARIO / valor.split(":", 1)[1].split("#")[0]
        if ruta.is_file():
            return FileResponse(ruta, media_type="image/png", headers={"Cache-Control": "max-age=31536000"})
    return Response(escudo_svg(valor), media_type="image/svg+xml", headers={"Cache-Control": "max-age=31536000"})


@router.get("/api/escudo/vista")
def escudo_vista(forma: str = "clasico", c1: str = "#1f8a52", c2: str = "#ffffff", simbolo: str = "ninguno",
                 texto: str = ""):
    """Vista previa del diseñador de escudos del perfil."""
    return Response(escudo_svg({"forma": forma, "c1": c1, "c2": c2, "simbolo": simbolo, "texto": texto}),
                    media_type="image/svg+xml")
