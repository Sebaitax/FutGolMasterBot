"""Perfil del club: nombre, estadio, escudo y logo propio."""
import json
import time as _time
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from juego.identidad import COLORES, FORMAS, SIMBOLOS
from juego.partida import ErrorJuego, Partida
from pathlib import Path
from urllib.parse import quote
from web.comun import P, PRINCIPAL, error_json, ir, pagina
from web.rutas.tienda import objeto_json

router = APIRouter()

# ------------------------------------------------------------------ perfil

LOGOS_USUARIO = Path("data/logos")


@router.get("/perfil", response_class=HTMLResponse)
def perfil(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    e = p.equipo(p.usuario_id)
    diseno = json.loads(e["escudo"]) if (e["escudo"] or "").startswith("{") else None
    coleccion = [objeto_json(o) for o in p.coleccion() if o["tengo"]]
    return pagina(request, "perfil.html", p, equipo=e, diseno=diseno or {}, logo_subido=(e["escudo"] or "").startswith("archivo:"),
                  mis_escudos=[o for o in coleccion if o["tipo"] == "escudo"],
                  mis_estadios=[o for o in coleccion if o["tipo"] == "estadio"],
                  foto_estadio=f"/estadios/{quote(e['estadio_img'])}" if e["estadio_img"] else None,
                  formas=FORMAS, simbolos=SIMBOLOS, colores=COLORES, stats=p.estadisticas_club(), historial=p.historial)


@router.post("/api/perfil")
async def api_perfil(request: Request, p: Partida = P):
    cuerpo = await request.json()
    try:
        escudo_nuevo = None
        if "escudo" in cuerpo:
            d = cuerpo["escudo"]
            escudo_nuevo = {"forma": d.get("forma") if d.get("forma") in FORMAS else "clasico",
                            "c1": str(d.get("c1", ""))[:7], "c2": str(d.get("c2", ""))[:7],
                            "simbolo": d.get("simbolo") if d.get("simbolo") in SIMBOLOS else "ninguno",
                            "texto": str(d.get("texto", ""))[:3]}
        p.actualizar_perfil(eslogan=cuerpo.get("eslogan"), estadio=cuerpo.get("estadio"), escudo=escudo_nuevo,
                            nombre=cuerpo.get("nombre"))
    except (ErrorJuego, TypeError, AttributeError) as e:
        return error_json(e)
    return {"ok": True}


@router.post("/api/perfil/logo")
async def api_logo(request: Request, archivo: UploadFile = File(...), p: Partida = P):
    """Sube una imagen como escudo de tu club (se guarda en data/logos, solo local)."""
    from io import BytesIO
    from PIL import Image
    datos = await archivo.read()
    if len(datos) > 5_000_000:
        return error_json(ErrorJuego("La imagen pesa más de 5 MB."))
    try:
        img = Image.open(BytesIO(datos)).convert("RGBA")
    except Exception:
        return error_json(ErrorJuego("No pude leer esa imagen."))
    img.thumbnail((256, 256))
    LOGOS_USUARIO.mkdir(parents=True, exist_ok=True)
    # un archivo por partida (todas las partidas tienen el mismo id de club, así no se pisan)
    nombre = f"club_{getattr(request.state, 'partida_id', PRINCIPAL)}.png"
    img.save(LOGOS_USUARIO / nombre)
    # "#<hora>" cambia el valor guardado, así el navegador no reutiliza el escudo anterior
    p.actualizar_perfil(escudo=f"archivo:{nombre}#{int(_time.time())}")
    return {"ok": True}
