"""Web local para probar el juego.

    uvicorn web.app:app --reload            # http://127.0.0.1:8000
    uvicorn web.app:app --host 0.0.0.0      # para abrirla desde otro equipo de la red

Cada navegador tiene su propia partida (cookie "fgm_partida"): se guarda en data/partidas/<id>.sqlite.
Desde la misma PC (127.0.0.1) se usa data/partida.sqlite (o la ruta de la variable FGM_BD).
"""
import re
import time as _time
import uuid
from urllib.parse import unquote
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from web import bitacora, cuentas
from web.comun import AQUI, COOKIE_PARTIDA, ESCUDOS, ESTADIOS, PRINCIPAL, RENDERS, SILENCIOSAS
from web.rutas.cuentas import PUBLICAS

app = FastAPI(title="FutGolMaster")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
# fuente Barlow Condensed (licencia OFL, en el repositorio)
app.mount("/fuentes", StaticFiles(directory="assets/fonts"), name="fuentes")
if ESCUDOS.is_dir():
    app.mount("/escudos", StaticFiles(directory=ESCUDOS), name="escudos")
app.mount("/estadios", StaticFiles(directory=ESTADIOS), name="estadios")
app.mount("/renders", StaticFiles(directory=RENDERS), name="renders")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(AQUI / "static" / "logo" / "favicon.ico", headers={"Cache-Control": "public, max-age=604800"})


_CARPETAS_IMG = {"/renders/": RENDERS, "/escudos/": ESCUDOS, "/estadios/": ESTADIOS}
_UNA_SEMANA = "public, max-age=604800"


@app.middleware("http")
async def _imagenes_livianas(request: Request, call_next):
    """Fotos, escudos y estadios: si el navegador acepta WebP y existe la versión .webp
    (scripts/comprimir_imagenes.py), se manda esa (~10 veces más liviana) en vez del PNG/JPG.
    Y todo lo estático se guarda en el navegador para no volver a descargarlo."""
    ruta = request.url.path
    if request.method == "GET":
        for prefijo, carpeta in _CARPETAS_IMG.items():
            if ruta.startswith(prefijo) and "image/webp" in request.headers.get("accept", ""):
                nombre = unquote(ruta[len(prefijo):])
                if "/" not in nombre and not nombre.startswith("."):
                    webp = (carpeta / nombre).with_suffix(".webp")
                    if webp.is_file():
                        return FileResponse(webp, media_type="image/webp",
                                            headers={"Cache-Control": _UNA_SEMANA, "Vary": "Accept"})
                break
    respuesta = await call_next(request)
    if respuesta.status_code == 200 and request.method == "GET":
        if ruta.startswith(tuple(_CARPETAS_IMG)) or ruta.startswith(("/fuentes/", "/static/logo/", "/static/canchas/", "/static/sobres/")):
            respuesta.headers.setdefault("Cache-Control", _UNA_SEMANA)
        elif ruta.startswith("/static/"):
            # con ?v= (versión del archivo) puede guardarse mucho; sin versión, una hora
            respuesta.headers.setdefault("Cache-Control", "public, max-age=2592000, immutable" if "v=" in request.url.query else "public, max-age=3600")
    return respuesta


@app.middleware("http")
async def _partida_del_navegador(request: Request, call_next):
    """Con login (servidor): tu partida es la de tu cuenta. Sin login (PC de desarrollo): una por navegador."""
    ruta = request.url.path
    token = request.cookies.get(cuentas.COOKIE)
    usuario = cuentas.usuario_de(token) if token else None
    request.state.usuario = usuario
    if cuentas.login_obligatorio() and not usuario:
        request.state.partida_id = ""
        if not ruta.startswith(PUBLICAS):
            if ruta.startswith("/api/"):
                return JSONResponse({"error": "Inicia sesión para jugar."}, status_code=401)
            return RedirectResponse("/entrar", status_code=303)
    pid = usuario["pid"] if usuario else request.cookies.get(COOKIE_PARTIDA, "")
    nueva = not usuario and not cuentas.login_obligatorio() and (not re.fullmatch(r"[0-9a-f]{32}|" + PRINCIPAL, pid) or (
        pid == PRINCIPAL and any(h in request.headers for h in ("cf-connecting-ip", "cf-ray"))))
    if nueva:
        # misma PC donde corre el servidor (por 127.0.0.1 o por su propia IP de la red)
        servidor = (request.scope.get("server") or ("",))[0]
        # lo que llega por el túnel público (cloudflared) también entra por 127.0.0.1: esas visitas
        # traen cabeceras de proxy y nunca son "la PC", así cada amigo tiene su propia partida
        por_tunel = any(h in request.headers for h in ("cf-connecting-ip", "x-forwarded-for", "cf-ray"))
        local = (not por_tunel and request.client is not None
                 and request.client.host in ("127.0.0.1", "::1", servidor))
        pid = PRINCIPAL if local else uuid.uuid4().hex
    if not (cuentas.login_obligatorio() and not usuario):
        request.state.partida_id = pid
    bitacora.contexto.set({"pid": pid, "metodo": request.method, "ruta": ruta,
                           "dispositivo": bitacora.dispositivo(request.headers.get("user-agent", "")),
                           "pais": request.headers.get("cf-ipcountry") or ("local" if pid == PRINCIPAL else "")})
    t0 = _time.perf_counter()
    try:
        respuesta = await call_next(request)
    except Exception as e:
        import traceback
        ms = int((_time.perf_counter() - t0) * 1000)
        bitacora.anotar("excepcion", f"{type(e).__name__}: {e}", "error", traceback.format_exc(), estado=500, ms=ms)
        if ruta.startswith("/api/"):
            return JSONResponse({"error": "Algo falló en el servidor. Ya quedó anotado para arreglarlo."}, status_code=500)
        return HTMLResponse("<h1>Algo falló</h1><p>Ya quedó anotado para arreglarlo. <a href='/'>Volver al inicio</a></p>",
                            status_code=500)
    ms = int((_time.perf_counter() - t0) * 1000)
    silenciosa = ruta.startswith(SILENCIOSAS) or ruta.endswith("/estado")
    if not silenciosa or respuesta.status_code >= 500 or ms >= bitacora.LENTO_MS:
        nivel = "error" if respuesta.status_code >= 500 else "aviso" if respuesta.status_code >= 400 and not silenciosa else "info"
        bitacora.anotar("peticion", request.url.query[:300], nivel, estado=respuesta.status_code, ms=ms)
    if nueva and not ruta.startswith("/volver/"):
        respuesta.set_cookie(COOKIE_PARTIDA, pid, max_age=10 * 365 * 86400, samesite="lax", httponly=True)
    return respuesta


# ------------------------------------------------------------------ secciones (un router por sección)

import web.rutas.cuentas  # noqa: E402
import web.rutas.inicio  # noqa: E402
import web.rutas.partido  # noqa: E402
import web.rutas.plantel  # noqa: E402
import web.rutas.tienda  # noqa: E402
import web.rutas.tabla  # noqa: E402
import web.rutas.imagenes  # noqa: E402
import web.rutas.perfil  # noqa: E402
import web.rutas.inventario  # noqa: E402
import web.rutas.amistosos  # noqa: E402
import web.rutas.vivo  # noqa: E402
import web.rutas.apuestas  # noqa: E402
import web.rutas.admin  # noqa: E402
import web.rutas.album  # noqa: E402


app.include_router(web.rutas.cuentas.router)
app.include_router(web.rutas.album.router)
app.include_router(web.rutas.inicio.router)
app.include_router(web.rutas.partido.router)
app.include_router(web.rutas.plantel.router)
app.include_router(web.rutas.tienda.router)
app.include_router(web.rutas.tabla.router)
app.include_router(web.rutas.imagenes.router)
app.include_router(web.rutas.perfil.router)
app.include_router(web.rutas.inventario.router)
app.include_router(web.rutas.amistosos.router)
app.include_router(web.rutas.vivo.router)
app.include_router(web.rutas.apuestas.router)
app.include_router(web.rutas.admin.router)
