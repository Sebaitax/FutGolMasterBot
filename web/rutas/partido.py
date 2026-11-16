"""Partido contra la máquina: en vivo (pausas, tácticas, jugadas clave), repetición y resumen."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego.formaciones import COORDENADAS
from juego.partida import ErrorJuego, Partida
from partidos.motor import ESPERA_TACTICA, FORMACIONES, MENTALIDADES, MINUTOS_LECTURA, PAUSAS_TACTICAS, TACTICAS, VENCE
from urllib.parse import quote
from web.comun import P, error_json, ir, pagina, plantillas, refrescar_escudos, render_url

router = APIRouter()

# ------------------------------------------------------------------ partido

def _datos_partido(p: Partida, partido) -> dict:
    lado = 0 if partido["local_id"] == p.usuario_id else 1
    return {"id": partido["id"], "local": partido["local"], "visita": partido["visita"], "lado": lado,
            "estadio": p.equipo(partido["local_id"])["estadio"] or "", "tipo": partido["tipo"] or "liga",
            "foto_estadio": (f"/estadios/{quote(p.equipo(partido['local_id'])['estadio_img'])}"
                             if p.equipo(partido["local_id"])["estadio_img"] else ""),
            "temporada": partido["temporada"], "fecha": partido["fecha"],
            "formaciones": FORMACIONES, "coordenadas": COORDENADAS, "mentalidades": list(MENTALIDADES),
            "colores": _colores_partido(p, partido, lado),
            "tacticas": {k: {"nombre": t["nombre"], "ico": t["ico"], "ayuda": t["ayuda"]} for k, t in TACTICAS.items()},
            "vence": VENCE, "minutos_lectura": MINUTOS_LECTURA,
            "pausas_max": PAUSAS_TACTICAS, "espera_tactica": ESPERA_TACTICA,
            "arena": _arena_partido(p, partido)}


def _arena_partido(p: Partida, partido) -> dict | None:
    """Cancha del partido por copas (para su diseño): la que tenías al jugarlo."""
    if (partido["tipo"] or "") != "escalera":
        return None
    try:
        indice = json.loads(partido["detalle"] or "{}").get("escalera", {}).get("cancha_antes", p.cancha)
    except ValueError:
        indice = p.cancha
    return p.info_cancha(indice)


def _rgb(h: str):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def _camiseta(e, defecto: str) -> str:
    """Color de camiseta según el escudo del club, evitando verdes (se pierden en el pasto)."""
    try:
        d = json.loads(e["escudo"]) if (e["escudo"] or "").startswith("{") else {}
    except ValueError:
        d = {}
    for c in (d.get("c1"), d.get("c2")):
        rgb = _rgb(c)
        if not rgb:
            continue
        r, g, b = rgb
        verde = g > r + 25 and g > b + 15
        if not verde and max(rgb) - min(rgb) + max(rgb) > 120:  # ni verde ni demasiado oscuro y gris
            return "#%02x%02x%02x" % rgb
    return defecto


def _colores_partido(p: Partida, partido, lado: int) -> list[str]:
    tuyo = _camiseta(p.equipo(p.usuario_id), "#f4f6f8")
    rival_id = partido["visita_id"] if lado == 0 else partido["local_id"]
    rival = _camiseta(p.equipo(rival_id), "#e5534b")
    a, b = _rgb(tuyo), _rgb(rival)
    if sum(abs(x - y) for x, y in zip(a, b)) < 160:  # muy parecidos: el rival usa la alternativa
        rival = "#2b6fd6" if rival != "#2b6fd6" and sum(abs(x - y) for x, y in zip(a, _rgb("#2b6fd6"))) >= 160 else "#e5534b"
        if rival == tuyo:
            rival = "#111111"
    return [tuyo, rival] if lado == 0 else [rival, tuyo]


@router.get("/partido/{partido_id}/vivo", response_class=HTMLResponse)
def partido_vivo(request: Request, partido_id: int, p: Partida = P):
    vivo = p.partido_en_vivo()
    if not vivo or vivo["partido"] != partido_id:
        return ir(f"/partido/{partido_id}")
    datos = _datos_partido(p, p.partido(partido_id))
    datos["modo"] = "vivo"
    datos["equipos"] = p.alineaciones_vivo()
    return pagina(request, "partido.html", p, partido=datos, datos=json.dumps(datos, ensure_ascii=False))


def _renders_pausa(r):
    """Agrega la foto de cada jugador a la pausa (cambios, entretiempo, expulsión) para dibujar sus cartas."""
    pausa = r.get("pausa") if isinstance(r, dict) else None
    if not pausa:
        return r
    est = pausa.get("estado") or {}
    for j in est.get("cancha", []) + est.get("banca", []):
        j["render"] = render_url(j.get("completo") or j["nombre"], j.get("club", ""))
    for o in pausa.get("opciones") or []:
        if isinstance(o, dict) and "entra_nombre" in o:
            o["entra_render"] = render_url(o.get("entra_completo") or o["entra_nombre"], o.get("entra_club", ""))
    return r


@router.post("/api/partido/avanzar")
async def api_avanzar(request: Request, p: Partida = P):
    cuerpo = await request.json()
    try:
        return _renders_pausa(p.avanzar_partido(cuerpo.get("decision"), int(cuerpo.get("desde", 0)), bool(cuerpo.get("terminar"))))
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)


@router.post("/api/partido/intervenir")
async def api_intervenir(request: Request, p: Partida = P):
    """Cambiar la táctica o pedir una pausa para hacer cambios, en el minuto que estás viendo."""
    cuerpo = await request.json()
    try:
        return _renders_pausa(p.intervenir_partido(int(cuerpo["tiempo"]), int(cuerpo["minuto"]), str(cuerpo["tipo"]), cuerpo.get("valor")))
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)


@router.post("/api/partido/elegir")
async def api_elegir(request: Request, p: Partida = P):
    """Tu jugada en la pausa clave: devuelve lo que eligió el rival y cómo arranca el pulso."""
    cuerpo = await request.json()
    try:
        return p.elegir_jugada(str(cuerpo.get("eleccion", "")))
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)


@router.get("/partido/{partido_id}", response_class=HTMLResponse)
def ver_partido(request: Request, partido_id: int, p: Partida = P):
    partido = p.partido(partido_id)
    if not partido or not partido["detalle"]:
        return ir("/", error="Ese partido no tiene narración.")
    detalle = json.loads(partido["detalle"])
    datos = _datos_partido(p, partido)
    datos.update(modo="repeticion", lineas=detalle["lineas"], posesion=detalle.get("posesion", []),
                 marcador=[partido["goles_local"], partido["goles_visita"]],
                 equipos=[{"formacion": a["formacion"], "jugadores": [j["nombre"] for j in a["titulares"]]}
                          for a in detalle.get("alineaciones", [])])
    return pagina(request, "partido.html", p, partido=datos, datos=json.dumps(datos, ensure_ascii=False))


@router.get("/partido/{partido_id}/resumen", response_class=HTMLResponse)
def resumen_partido(request: Request, partido_id: int, p: Partida = P):
    """Fragmento con estadísticas, alineaciones y el resto de la fecha (se carga al terminar)."""
    partido = p.partido(partido_id)
    if not partido or not partido["detalle"]:
        return HTMLResponse("")
    detalle = json.loads(partido["detalle"])
    otros = [x for x in p.partidos_fecha(partido["fecha"], partido["temporada"], partido["division"])
             if x["id"] != partido_id]
    refrescar_escudos(p)
    return plantillas.TemplateResponse(request, "_resumen.html", {"partido": partido, "detalle": detalle, "otros": otros})
