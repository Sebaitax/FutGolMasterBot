"""Núcleo compartido de la web: rutas de archivos, plantillas, escudos, la partida de cada jugador y ayudantes."""
import hashlib
import html
import json
import os
import re
import sqlite3
import unicodedata
from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from functools import lru_cache
from juego.amigos import Registro
from juego.economia import valor_venta
from juego.partida import Partida
from markupsafe import Markup
from models.carta import POSICIONES_ES, posicion_es
from pathlib import Path
from urllib.parse import quote, urlencode
from web import bitacora

BD = Path(os.environ.get("FGM_BD", "data/partida.sqlite"))
AQUI = Path(__file__).parent

# Escudos de los clubes (solo local). Si no están, se dibuja un escudo con iniciales.
ESCUDOS = Path("assets/escudos")
# nombre del club (como slug) -> archivo del escudo, cuando no coinciden
ALIAS_ESCUDO = {
    # Chile
    "deportes-la-serena": "la-serena", "everton": "everton-de-vina-del-mar", "o-higgins": "ohiggins",
    # Argentina
    "platense": "atletico-platense", "central-cordoba-sde": "central-cordoba-se", "talleres-c": "talleres",
    "estudiantes-lp": "estudiantes-de-la-plata", "estudiantes-rc": "estudiantes-de-rio-cuarto",
    "instituto": "instituto-cordoba", "gimnasia-y-esgrima-m": "gimnasia-y-esgrima",
    "newell-s-old-boys": "newells-old-boys", "sarmiento-j": "sarmiento",
}

# Fotos de estadios (solo local): assets/estadios/<club>.jpg (scraper/estadios.py)
ESTADIOS = Path("assets/estadios")
ESTADIOS.mkdir(parents=True, exist_ok=True)

# Renders/fotos de jugadores (solo local): assets/renders/<Nombre>.png
RENDERS = Path("assets/renders")
RENDERS.mkdir(parents=True, exist_ok=True)


def render_url(nombre: str, club: str = "") -> str | None:
    """Foto del jugador: "Nombre (Club).png" si hay homónimos, si no "Nombre.png"."""
    archivo = next((a for a in (RENDERS / f"{nombre} ({club}).png", RENDERS / f"{nombre}.png") if a.is_file()), None)
    if archivo is None:
        return None
    return f"/renders/{quote(archivo.name)}?v={int(archivo.stat().st_mtime)}"
plantillas = Jinja2Templates(directory=AQUI / "templates")


def _negrita(texto: str) -> Markup:
    """Convierte el **negrita** del narrador a HTML (escapando lo demás)."""
    seguro = html.escape(texto)
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", seguro).replace("\n", "<br>"))


def _miles(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _slug(nombre: str) -> str:
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plano).strip("-")


@lru_cache(maxsize=128)
def escudo_url(nombre: str) -> str | None:
    slug = ALIAS_ESCUDO.get(_slug(nombre), _slug(nombre))
    return f"/escudos/{slug}.png" if (ESCUDOS / f"{slug}.png").is_file() else None


# clubes del juego (bots y el tuyo): nombre -> (id, versión del escudo). Se refresca en cada página.
_EQUIPOS: dict[str, tuple[int, str]] = {}


def refrescar_escudos(p: Partida):
    _EQUIPOS.clear()
    if p.existe:
        for e in p.con.execute("SELECT id, nombre, escudo FROM equipos"):
            _EQUIPOS[e["nombre"]] = (e["id"], hashlib.md5((e["escudo"] or "").encode()).hexdigest()[:8])


def escudo(nombre: str, tam: str = "") -> Markup:
    """<img> del escudo o, si no hay, un escudo propio con las iniciales del club."""
    clase = f"escudo {tam}".strip()
    if nombre in _EQUIPOS:
        eid, v = _EQUIPOS[nombre]
        return Markup(f'<img class="{clase}" src="/escudo/equipo/{eid}?v={v}" alt="" loading="lazy">')
    url = escudo_url(nombre)
    if url:
        return Markup(f'<img class="{clase}" src="{url}" alt="" loading="lazy">')
    palabras = [w for w in re.findall(r"\w+", nombre) if len(w) > 2] or [nombre]
    iniciales = "".join(w[0] for w in palabras[:3]).upper()
    tono = sum(map(ord, nombre)) % 360
    return Markup(f'<span class="{clase} propio" style="--tono:{tono}">{html.escape(iniciales)}</span>')


def _escudos_disponibles() -> list[str]:
    return sorted(p.stem for p in ESCUDOS.glob("*.png")) if ESCUDOS.is_dir() else []


plantillas.env.globals.update(escudo=escudo, valor_venta=valor_venta, escudos_json=json.dumps(_escudos_disponibles()),
                               alias_escudo_json=json.dumps(ALIAS_ESCUDO))
plantillas.env.filters.update(negrita=_negrita, miles=_miles, pos=posicion_es)
class _VersionEstaticos:
    """Versión de los CSS/JS para el ?v=: cambia cada vez que se modifica uno (así el navegador
    no usa una copia vieja aunque el servidor no se haya reiniciado)."""
    def __str__(self) -> str:
        return str(int(max(f.stat().st_mtime for f in (AQUI / "static").iterdir() if f.is_file())))


plantillas.env.globals["version"] = _VersionEstaticos()
plantillas.env.globals["posiciones_json"] = json.dumps(POSICIONES_ES)
from web import iconos as _iconos  # noqa: E402
plantillas.env.globals.update(ico=_iconos.ico, bandera=_iconos.bandera, insignia=_iconos.insignia, emoji_iconos_json=_iconos.EMOJI_JSON,
                              sprite_iconos=_iconos.SPRITE)
plantillas.env.filters.update(iconos=_iconos.con_iconos, bandera=_iconos.bandera)


COOKIE_PARTIDA = "fgm_partida"
PRINCIPAL = "principal"   # la partida de la PC donde corre el servidor (data/partida.sqlite)


def ruta_partida(request: Request) -> Path:
    pid = getattr(request.state, "partida_id", PRINCIPAL)
    return BD if pid == PRINCIPAL else BD.parent / "partidas" / f"{pid}.sqlite"


def _leer_partida(pid: str):
    """Abre la partida de otro jugador solo para leer (None si no existe o no tiene club)."""
    ruta = BD if pid == PRINCIPAL else BD.parent / "partidas" / f"{pid}.sqlite"
    if not re.fullmatch(r"[0-9a-f]{32}|" + PRINCIPAL, pid) or not ruta.is_file():
        return None
    con = sqlite3.connect(f"file:{ruta.resolve().as_posix()}?mode=ro", uri=True, check_same_thread=False)
    con.row_factory = sqlite3.Row
    try:
        p = Partida(con)
        if p.existe:
            return p
    except sqlite3.Error:
        pass
    con.close()
    return None


def jugadores_online(yo: str) -> list[dict]:
    """Los demás jugadores con club creado (para desafiarlos), el más activo primero."""
    rutas = [(PRINCIPAL, BD)] + [(r.stem, r) for r in (BD.parent / "partidas").glob("*.sqlite")]
    salida = []
    for pid, ruta in rutas:
        if pid == yo or not ruta.is_file():
            continue
        p = _leer_partida(pid)
        if not p:
            continue
        try:
            uid = p.usuario_id
            e = p.equipo(uid)
            salida.append({"pid": pid, "nombre": e["nombre"], "estadio": e["estadio"], "escudo": e["escudo"] or "",
                           "fuerza": round(p.fuerza_equipo(uid), 1), "division": p.info_cancha()["nombre"],
                           "activo": ruta.stat().st_mtime})
        except Exception:
            continue
        finally:
            p.con.close()
    return sorted(salida, key=lambda j: -j["activo"])


# los clubes de los amigos en tu liga desbalancean (tienen planteles mucho más fuertes que los bots):
# apagado. Con la lista vacía, cada lugar que ocupaba un amigo vuelve a su bot (con sus puntos y fixture).
LIGA_CON_AMIGOS = False


def sincronizar_liga(p: Partida, yo: str) -> dict[str, int]:
    """Mete en tu liga a los amigos que están en tu misma división (en sus partidas)."""
    if not p.existe or p.n_divisiones == 1:
        return {}
    if not LIGA_CON_AMIGOS:
        try:
            return p.sincronizar_liga_amigos({})
        except sqlite3.Error:
            return {}
    amigos = {}
    for pid in [PRINCIPAL] + [r.stem for r in (BD.parent / "partidas").glob("*.sqlite")]:
        if pid == yo:
            continue
        otra = _leer_partida(pid)
        if not otra:
            continue
        try:
            if otra.n_divisiones > 1:
                amigos[pid] = {**otra.exportar_equipo(), "division": otra.clave_division(otra.division_de(otra.usuario_id))}
        except Exception:
            continue
        finally:
            otra.con.close()
    try:
        return p.sincronizar_liga_amigos(amigos)
    except sqlite3.Error:
        return {}


# rutas que se piden muchísimo (imágenes, consultas cada segundo): solo se anotan si fallan o tardan
SILENCIOSAS = ("/static", "/fuentes", "/escudos", "/escudo/", "/estadios", "/renders", "/carta/", "/logos", "/api/escudo/vista",
               "/api/vivo/sala", "/api/log", "/favicon")


def ruta_de(pid: str) -> Path:
    return BD if pid == PRINCIPAL else BD.parent / "partidas" / f"{pid}.sqlite"


def registro() -> Registro:
    return Registro(BD.parent / "amigos.sqlite")


def _anotador(yo: str, p: Partida):
    """Al terminar un desafío, deja el resultado en el registro compartido (lo ve también el amigo)."""
    def anotar(amigo: str, resultado: dict):
        eid = p._get("amigos", {}).get(amigo)
        rival = p.nombre_equipo(eid).removesuffix(" (amigo)") if eid else "?"
        r = registro()
        try:
            r.anotar(yo, p.nombre_equipo(p.usuario_id), amigo, rival, resultado)
        finally:
            r.cerrar()
    return anotar


def partida(request: Request):
    """Dependencia: abre la partida del navegador y cierra la conexión al terminar."""
    ruta = ruta_partida(request)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # quien todavía no crea su club no deja archivo (visitas sueltas, vistas previas de links)
    p = Partida.abrir(ruta if ruta.exists() or request.url.path == "/crear" else ":memory:")
    p.al_terminar_desafio = _anotador(getattr(request.state, "partida_id", PRINCIPAL), p)
    p.al_sospechar = lambda motivo: bitacora.anotar("trampa", motivo, "aviso")
    p.sincronizar_catalogo()   # cartas de ligas agregadas después de crear la partida
    try:
        yield p
    finally:
        p.con.close()


P = Depends(partida)


def pagina(request: Request, nombre: str, p: Partida | None = None, **datos) -> HTMLResponse:
    if p is not None:
        refrescar_escudos(p)
    if p is not None and p.existe:
        datos.setdefault("carta_gratis_lista", p.segundos_para_carta_gratis() == 0)
        r = registro()
        try:
            datos.setdefault("desafios_nuevos", r.sin_ver(getattr(request.state, "partida_id", PRINCIPAL)))
        finally:
            r.cerrar()
        datos.setdefault("monedas", p.monedas)
        datos.setdefault("temporada", p.temporada)
        datos.setdefault("club", p.nombre_equipo(p.usuario_id))
        datos.setdefault("nombre_div", p.nombre_division())
        datos.setdefault("clave_div", p.clave_division())
        datos.setdefault("hay_divisiones", False)
        datos.setdefault("copas_cab", p.copas)
        datos.setdefault("cancha_cab", p.info_cancha())
    datos.setdefault("usuario", getattr(request.state, "usuario", None))
    datos["error"] = request.query_params.get("error")
    datos["aviso"] = request.query_params.get("aviso")
    return plantillas.TemplateResponse(request, nombre, datos)


def ir(url: str, error: str | None = None, aviso: str | None = None) -> RedirectResponse:
    if error:
        bitacora.anotar("error_juego", error, "aviso", detalle={"destino": url})
    if error or aviso:
        url += ("&" if "?" in url else "?") + urlencode({"error": error} if error else {"aviso": aviso})
    return RedirectResponse(url, status_code=303)


def error_json(e: Exception) -> JSONResponse:
    bitacora.anotar("error_juego", str(e) or type(e).__name__, "aviso", detalle={"clase": type(e).__name__})
    return JSONResponse({"error": str(e) or "Datos inválidos."}, status_code=400)


def _ficha_json(f) -> dict:
    c = f.carta
    return {"pid": f.pid, "carta": f.carta_id, "nombre": c.nombre_corto, "completo": c.nombre, "pos": c.posicion,
            "ovr": c.ovr, "nivel": c.nivel, "club": c.club, "nacion": c.nacion, "liga": c.liga, "stats": c.stats,
            "estado": f.estado, "lesion": f.lesion, "suspension": f.suspension, "amarillas": f.amarillas,
            "pj": f.partidos, "goles": f.goles, "asis": f.asistencias, "venta": valor_venta(c.precio),
            "render": render_url(c.nombre, c.club), "mejora": f.nivel, "ovr_base": f.ovr_base or c.ovr}


def _carta_json(carta, **extra) -> dict:
    return {"nombre": carta.nombre_corto, "completo": carta.nombre, "pos": carta.posicion, "ovr": carta.ovr,
            "nivel": carta.nivel, "club": carta.club, "nacion": carta.nacion, "liga": carta.liga, "stats": carta.stats,
            "render": render_url(carta.nombre, carta.club), **extra}


def _yo(request: Request) -> str:
    return getattr(request.state, "partida_id", PRINCIPAL)


def _info_club(p: Partida) -> dict:
    e = p.equipo(p.usuario_id)
    return {"nombre": e["nombre"], "escudo": e["escudo"] or "", "fuerza": round(p.fuerza_equipo(p.usuario_id), 1),
            "division": p.nombre_division()}


def _es_la_pc(request: Request) -> bool:
    """Solo desde la PC del servidor (nunca por el túnel público)."""
    if any(h in request.headers for h in ("cf-connecting-ip", "x-forwarded-for", "cf-ray")):
        return False
    servidor = (request.scope.get("server") or ("",))[0]
    return request.client is not None and request.client.host in ("127.0.0.1", "::1", servidor)


@lru_cache(maxsize=256)
def _nombre_club(pid: str, _minuto: int) -> str:
    p = _leer_partida(pid)
    if not p:
        return ""
    try:
        return p.nombre_equipo(p.usuario_id)
    except Exception:
        return ""
    finally:
        p.con.close()
