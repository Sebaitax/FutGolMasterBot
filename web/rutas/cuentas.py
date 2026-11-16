"""Cuentas: entrar con correo y contraseña o con Google, registrarse y salir."""
import re
import secrets
import time as _time
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from web import bitacora, cuentas
from web.comun import COOKIE_PARTIDA, ir, pagina, ruta_de

router = APIRouter()

# ------------------------------------------------------------------ cuentas: correo + contraseña o Google

PUBLICAS = ("/entrar", "/registro", "/salir", "/auth/", "/static", "/fuentes", "/favicon", "/api/log")
_intentos: dict[str, list[float]] = {}


def _demasiados_intentos(request: Request) -> bool:
    """Máximo 10 intentos de entrar o registrarse cada 10 minutos por IP (frena a los robots)."""
    ip = request.client.host if request.client else "?"
    ahora = _time.time()
    lista = [t for t in _intentos.get(ip, []) if ahora - t < 600]
    lista.append(ahora)
    _intentos[ip] = lista
    return len(lista) > 10


def _con_sesion(request: Request, usuario: dict, destino: str = "/") -> RedirectResponse:
    token = cuentas.crear_sesion(usuario["id"], bitacora.dispositivo(request.headers.get("user-agent", "")))
    bitacora.anotar("cuenta", "inició sesión", pid=usuario["pid"])
    r = RedirectResponse(destino, status_code=303)
    r.set_cookie(cuentas.COOKIE, token, max_age=cuentas.DIAS_SESION * 86400, httponly=True, samesite="lax",
                 secure=request.url.scheme == "https")
    return r


@router.get("/entrar", response_class=HTMLResponse)
def ver_entrar(request: Request, modo: str = "entrar"):
    if getattr(request.state, "usuario", None):
        return ir("/")
    return pagina(request, "entrar.html", modo="registro" if modo == "registro" else "entrar",
                  google=cuentas.google_activo())


@router.post("/entrar")
def hacer_entrar(request: Request, email: str = Form(""), clave: str = Form("")):
    if _demasiados_intentos(request):
        return ir("/entrar", error="Demasiados intentos. Espera unos minutos.")
    try:
        usuario = cuentas.entrar(email, clave)
    except cuentas.ErrorCuenta as e:
        return ir("/entrar", error=str(e))
    return _con_sesion(request, usuario)


@router.post("/registro")
def hacer_registro(request: Request, email: str = Form(""), clave: str = Form(""), clave2: str = Form(""),
                   nombre: str = Form("")):
    if _demasiados_intentos(request):
        return ir("/entrar?modo=registro", error="Demasiados intentos. Espera unos minutos.")
    if clave != clave2:
        return ir("/entrar?modo=registro", error="Las contraseñas no coinciden.")
    try:
        usuario = cuentas.registrar(email, clave, nombre)
    except cuentas.ErrorCuenta as e:
        return ir("/entrar?modo=registro", error=str(e))
    bitacora.anotar("cuenta", "cuenta nueva (correo)", pid=usuario["pid"])
    return _con_sesion(request, usuario)


@router.post("/salir")
def salir(request: Request):
    cuentas.cerrar_sesion(request.cookies.get(cuentas.COOKIE))
    r = RedirectResponse("/entrar", status_code=303)
    r.delete_cookie(cuentas.COOKIE)
    return r


@router.get("/auth/google")
def auth_google(request: Request):
    if not cuentas.google_activo():
        return ir("/entrar", error="El inicio con Google todavía no está activado.")
    estado = secrets.token_urlsafe(16)
    r = RedirectResponse(cuentas.url_google(estado), status_code=303)
    r.set_cookie("fgm_oauth", estado, max_age=600, httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return r


@router.get("/auth/google/callback")
def auth_google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or not code:
        return ir("/entrar", error="Cancelaste el inicio con Google.")
    esperado = request.cookies.get("fgm_oauth", "")
    if not esperado or not secrets.compare_digest(esperado, state):
        return ir("/entrar", error="La sesión de Google venció. Inténtalo de nuevo.")
    try:
        g = cuentas.datos_google(code)
        usuario = cuentas.entrar_google(g["sub"], g["email"], g["nombre"])
    except Exception as e:   # red, Google o datos raros: se anota y se avisa
        bitacora.anotar("cuenta", f"falló Google: {type(e).__name__}: {e}", "aviso")
        return ir("/entrar", error="No se pudo entrar con Google. Inténtalo de nuevo.")
    r = _con_sesion(request, usuario)
    r.delete_cookie("fgm_oauth")
    return r


@router.get("/volver/{pid}")
def volver_a_mi_partida(pid: str):
    """Link personal para recuperar tu partida en otro navegador o si cambió la dirección del túnel."""
    if cuentas.login_obligatorio():
        return ir("/entrar")
    if not re.fullmatch(r"[0-9a-f]{32}", pid) or not ruta_de(pid).is_file():
        return HTMLResponse("<h1>No encontré esa partida 🤔</h1><p>Revisa el link. <a href='/'>Ir al inicio</a></p>", status_code=404)
    bitacora.anotar("juego", "volvió a su partida con el link personal", pid=pid)
    respuesta = RedirectResponse("/", status_code=303)
    respuesta.set_cookie(COOKIE_PARTIDA, pid, max_age=10 * 365 * 86400, samesite="lax", httponly=True)
    return respuesta
