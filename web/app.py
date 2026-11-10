"""Web local para probar el juego.

    uvicorn web.app:app --reload            # http://127.0.0.1:8000
    uvicorn web.app:app --host 0.0.0.0      # para abrirla desde otro equipo de la red

La partida se guarda en data/partida.sqlite (o en la ruta de la variable FGM_BD).
"""
import html
import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlencode

import hashlib

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from cartas.generador import carta_a_bytes
from juego import economia
from juego.economia import SOBRES, valor_venta
from juego.identidad import COLORES, FORMAS, SIMBOLOS, escudo_svg
from juego.formaciones import COORDENADAS, ENLACES
from juego.partida import ErrorJuego, Partida
from models.carta import POSICIONES_ES, posicion_es
from partidos.motor import ESPERA_TACTICA, FORMACIONES, MENTALIDADES, PAUSAS_TACTICAS, TACTICAS

BD = Path(os.environ.get("FGM_BD", "data/partida.sqlite"))
AQUI = Path(__file__).parent

app = FastAPI(title="FutGolMaster")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
# fuente Barlow Condensed (licencia OFL, en el repositorio)
app.mount("/fuentes", StaticFiles(directory="assets/fonts"), name="fuentes")

# Escudos de los clubes (solo local). Si no están, se dibuja un escudo con iniciales.
ESCUDOS = Path("assets/escudos")
if ESCUDOS.is_dir():
    app.mount("/escudos", StaticFiles(directory=ESCUDOS), name="escudos")
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
app.mount("/estadios", StaticFiles(directory=ESTADIOS), name="estadios")

# Renders/fotos de jugadores (solo local): assets/renders/<Nombre>.png
RENDERS = Path("assets/renders")
RENDERS.mkdir(parents=True, exist_ok=True)
app.mount("/renders", StaticFiles(directory=RENDERS), name="renders")


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
# número de versión para los CSS/JS: el navegador los vuelve a bajar en cada arranque
import time as _time
plantillas.env.globals["version"] = int(_time.time())
plantillas.env.globals["posiciones_json"] = json.dumps(POSICIONES_ES)


def partida():
    """Dependencia: abre la partida para el pedido y cierra la conexión al terminar."""
    p = Partida.abrir(BD)
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
        datos.setdefault("monedas", p.monedas)
        datos.setdefault("temporada", p.temporada)
        datos.setdefault("club", p.nombre_equipo(p.usuario_id))
        datos.setdefault("nombre_div", p.nombre_division())
        datos.setdefault("clave_div", p.clave_division())
        datos.setdefault("hay_divisiones", p.n_divisiones > 1)
    datos["error"] = request.query_params.get("error")
    datos["aviso"] = request.query_params.get("aviso")
    return plantillas.TemplateResponse(request, nombre, datos)


def ir(url: str, error: str | None = None, aviso: str | None = None) -> RedirectResponse:
    if error or aviso:
        url += "?" + urlencode({"error": error} if error else {"aviso": aviso})
    return RedirectResponse(url, status_code=303)


def error_json(e: Exception) -> JSONResponse:
    return JSONResponse({"error": str(e) or "Datos inválidos."}, status_code=400)


def _ficha_json(f) -> dict:
    c = f.carta
    return {"pid": f.pid, "carta": f.carta_id, "nombre": c.nombre_corto, "completo": c.nombre, "pos": c.posicion,
            "ovr": c.ovr, "nivel": c.nivel, "club": c.club, "nacion": c.nacion, "stats": c.stats,
            "estado": f.estado, "lesion": f.lesion, "suspension": f.suspension, "amarillas": f.amarillas,
            "pj": f.partidos, "goles": f.goles, "asis": f.asistencias, "venta": valor_venta(c.precio),
            "render": render_url(c.nombre, c.club), "mejora": f.nivel, "ovr_base": f.ovr_base or c.ovr}


def _carta_json(carta, **extra) -> dict:
    return {"nombre": carta.nombre_corto, "completo": carta.nombre, "pos": carta.posicion, "ovr": carta.ovr,
            "nivel": carta.nivel, "club": carta.club, "nacion": carta.nacion, "stats": carta.stats,
            "render": render_url(carta.nombre, carta.club), **extra}


# ------------------------------------------------------------------ inicio

@app.get("/", response_class=HTMLResponse)
def inicio(request: Request, p: Partida = P):
    if not p.existe:
        return pagina(request, "crear.html")
    if p.partido_en_vivo():
        return ir(f"/partido/{p.partido_en_vivo()['partido']}/vivo")
    tabla = p.tabla()
    posicion = next(i for i, f in enumerate(tabla, start=1) if f["usuario"])
    datos = dict(fecha=p.fecha, total=p.total_fechas, terminada=p.temporada_terminada, posicion=posicion,
                 fila=tabla[posicion - 1], movimientos=p.movimientos(5), historial=p.historial,
                 reemplaza=p._get("reemplaza"), objetivo=p.objetivo, evolucion=p.evolucion(),
                 fuerza=p.fuerza_equipo(p.usuario_id), quimica=p.quimica_usuario()["equipo"],
                 no_disponibles=[f for f in p.plantel() if not f.disponible], rival=None, tabla=tabla,
                 partida_antigua=p.n_divisiones == 1 or not p.con.execute(
                     "SELECT COUNT(*) FROM equipos WHERE es_usuario = 0 AND nombre_real != ''").fetchone()[0])
    proximo = p.proximo_partido()
    if proximo:
        rival_id = proximo["visita_id"] if proximo["local_id"] == p.usuario_id else proximo["local_id"]
        once = p.once_probable(rival_id)
        fila_rival = next(f for f in tabla if f["id"] == rival_id)
        datos["rival"] = {
            "nombre": p.nombre_equipo(rival_id), "fuerza": p.fuerza_equipo(rival_id),
            "local": proximo["local_id"] == p.usuario_id, "forma": fila_rival["forma"],
            "posicion": tabla.index(fila_rival) + 1, "formacion": once.formacion,
            "once": json.dumps([_carta_json(j.carta, puesto=pu) for j, pu in zip(once.titulares, FORMACIONES[once.formacion])],
                               ensure_ascii=False),
            "coords": json.dumps(COORDENADAS[once.formacion]),
        }
    ultimo = p.con.execute(
        "SELECT id FROM partidos WHERE jugado = 1 AND ? IN (local_id, visita_id) ORDER BY temporada DESC, fecha DESC LIMIT 1",
        (p.usuario_id,)).fetchone()
    datos["ultimo"] = p.partido(ultimo["id"]) if ultimo else None
    return pagina(request, "inicio.html", p, **datos)


@app.post("/crear")
def crear(nombre_club: str = Form(...), p: Partida = P):
    try:
        p.crear(nombre_club)
    except (ErrorJuego, FileNotFoundError) as e:
        return ir("/", error=str(e))
    return ir("/plantel", aviso="¡Club creado! Arma tu once antes de la primera fecha.")


@app.post("/reiniciar")
def reiniciar(p: Partida = P):
    p.borrar()
    _png.cache_clear()
    return ir("/")


@app.post("/jugar")
def jugar(p: Partida = P):
    try:
        pid = p.iniciar_partido()
    except ErrorJuego as e:
        return ir("/", error=str(e))
    return ir(f"/partido/{pid}/vivo")


@app.post("/jugar-rapido")
def jugar_rapido(p: Partida = P):
    try:
        pid = p.jugar_fecha()
    except ErrorJuego as e:
        return ir("/", error=str(e))
    return ir(f"/partido/{pid}")


@app.post("/nueva-temporada")
def nueva_temporada(p: Partida = P):
    try:
        p.nueva_temporada()
    except ErrorJuego as e:
        return ir("/", error=str(e))
    return ir("/", aviso="Nueva temporada. ¡Suerte!")


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
            "pausas_max": PAUSAS_TACTICAS, "espera_tactica": ESPERA_TACTICA}


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


@app.get("/partido/{partido_id}/vivo", response_class=HTMLResponse)
def partido_vivo(request: Request, partido_id: int, p: Partida = P):
    vivo = p.partido_en_vivo()
    if not vivo or vivo["partido"] != partido_id:
        return ir(f"/partido/{partido_id}")
    datos = _datos_partido(p, p.partido(partido_id))
    datos["modo"] = "vivo"
    datos["equipos"] = p.alineaciones_vivo()
    return pagina(request, "partido.html", p, partido=datos, datos=json.dumps(datos, ensure_ascii=False))


@app.post("/api/partido/avanzar")
async def api_avanzar(request: Request, p: Partida = P):
    cuerpo = await request.json()
    try:
        return p.avanzar_partido(cuerpo.get("decision"), int(cuerpo.get("desde", 0)), bool(cuerpo.get("terminar")))
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)


@app.post("/api/partido/intervenir")
async def api_intervenir(request: Request, p: Partida = P):
    """Cambiar la táctica o pedir una pausa para hacer cambios, en el minuto que estás viendo."""
    cuerpo = await request.json()
    try:
        return p.intervenir_partido(int(cuerpo["tiempo"]), int(cuerpo["minuto"]), str(cuerpo["tipo"]), cuerpo.get("valor"))
    except (ErrorJuego, KeyError, TypeError, ValueError) as e:
        return error_json(e)


@app.get("/partido/{partido_id}", response_class=HTMLResponse)
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


@app.get("/partido/{partido_id}/resumen", response_class=HTMLResponse)
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


# ------------------------------------------------------------------ plantel

@app.get("/plantel", response_class=HTMLResponse)
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


@app.post("/api/alineacion")
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


@app.post("/api/vender")
async def api_vender(request: Request, p: Partida = P):
    cuerpo = await request.json()
    try:
        monto = p.vender_varios([int(x) for x in cuerpo.get("pids", [])])
    except (ErrorJuego, TypeError, ValueError) as e:
        return error_json(e)
    return {"monto": monto, "monedas": p.monedas}


@app.post("/api/deshacer-venta")
def api_deshacer(p: Partida = P):
    try:
        n = p.deshacer_venta()
    except ErrorJuego as e:
        return error_json(e)
    return {"cartas": n, "monedas": p.monedas}


# ------------------------------------------------------------------ tienda y mercado

@app.get("/tienda", response_class=HTMLResponse)
def tienda(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    return pagina(request, "tienda.html", p, sobres=SOBRES, espera_gratis=p.segundos_para_carta_gratis(),
                  objetos_tengo=sum(1 for o in p.coleccion() if o["tengo"]), objetos_total=len(p.coleccion()),
                  prob_gratis=economia.CARTA_GRATIS_PROBABILIDADES)


def objeto_json(o: dict) -> dict:
    if o["tipo"] == "escudo":
        imagen = escudo_url(o["club"])
    else:
        imagen = f"/estadios/{quote(o['archivo'])}" if o.get("archivo") else None
    return {"id": o["id"], "tipo": o["tipo"], "club": o["club"], "nombre": o["nombre"], "nivel": o["rareza"],
            "capacidad": o.get("capacidad") or 0, "imagen": imagen, "tengo": o.get("tengo", True),
            "nuevo": o.get("nuevo", False), "en_uso": o.get("en_uso", False)}


@app.post("/api/sobre/{clave}")
def api_sobre(clave: str, p: Partida = P):
    try:
        r = p.abrir_sobre_completo(clave)
    except ErrorJuego as e:
        return error_json(e)
    return {"cartas": [_ficha_json(f) for f in r["cartas"]], "objetos": [objeto_json(o) for o in r["objetos"]],
            "monedas": p.monedas}


@app.post("/api/objeto/{coleccionable_id}/usar")
def api_usar_objeto(coleccionable_id: int, p: Partida = P):
    try:
        p.usar_objeto(coleccionable_id)
    except ErrorJuego as e:
        return error_json(e)
    return {"ok": True}


@app.get("/mercado", response_class=HTMLResponse)
def mercado(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    return pagina(request, "mercado.html", p, fecha=p.fecha, en_venta=len(p.ofertas()), **p.opciones_busqueda())


def _oferta_json(o: dict) -> dict:
    return _carta_json(o["carta"], carta_id=o["carta_id"], en_mercado=o["en_mercado"], precio=o["precio"],
                       vendedor=o["vendedor"], quedan=o["quedan"], vendida=o["vendida"], tuya=o["tuya"],
                       edad=o.get("edad") or None, liga=o["carta"].liga, valor=o["carta"].precio)


@app.get("/api/buscar")
def api_buscar(q: str = "", club: str = "", nacion: str = "", pos: str = "", venta: int = 1, ovr_min: int = 0,
               ovr_max: int = 99, precio_max: int = 0, orden: str = "ovr", p: Partida = P):
    """venta=1: lo que está en venta en el mercado; venta=0: todos los jugadores del juego."""
    if not p.existe:
        return error_json(ErrorJuego("Primero crea una partida."))
    resultados = p.buscar(q[:60], club=club, nacion=nacion, posicion=pos[:4], solo_venta=bool(venta),
                          ovr_min=ovr_min, ovr_max=ovr_max, precio_max=precio_max, orden=orden[:12])
    return {"resultados": [_oferta_json(o) for o in resultados]}


@app.get("/api/mercado/jugador/{carta_id}")
def api_en_venta(carta_id: int, p: Partida = P):
    """¿Alguien vende a este jugador? (para el botón "Buscar en el mercado")."""
    if not p.existe:
        return error_json(ErrorJuego("Primero crea una partida."))
    return {"publicaciones": [_oferta_json(o) for o in p.en_venta(carta_id)], "monedas": p.monedas}


@app.post("/api/comprar/{carta_id}")
def api_comprar(carta_id: int, p: Partida = P):
    try:
        f = p.comprar(carta_id)
    except ErrorJuego as e:
        return error_json(e)
    return {"carta": _ficha_json(f), "monedas": p.monedas}


# ------------------------------------------------------------------ tabla

@app.get("/tabla", response_class=HTMLResponse)
def tabla(request: Request, fecha: int | None = None, division: int | None = None, p: Partida = P):
    if not p.existe:
        return ir("/")
    mia = p.division
    division = mia if division is None or not 0 <= division < p.n_divisiones else division
    total = p.total_fechas
    actual = min(p.fecha, total)
    fecha = max(1, min(fecha or (actual - 1 if actual > 1 and not p.temporada_terminada else actual), total))
    uid = p.usuario_id
    fixture = p.con.execute(
        "SELECT p.*, l.nombre AS local, v.nombre AS visita FROM partidos p JOIN equipos l ON l.id = p.local_id"
        " JOIN equipos v ON v.id = p.visita_id WHERE p.temporada = ? AND ? IN (p.local_id, p.visita_id) ORDER BY p.fecha",
        (p.temporada, uid)).fetchall()
    suben, bajan = p.cupos(division)
    divisiones = [{"n": d, "nombre": p.nombre_division(d), "clave": p.clave_division(d)}
                  for d in reversed(range(p.n_divisiones))]
    return pagina(request, "tabla.html", p, tabla=p.tabla(division=division), goleadores=p.goleadores(10, division),
                  fecha=fecha, total=total, partidos=p.partidos_fecha(fecha, division=division), fixture=fixture,
                  fecha_actual=p.fecha, uid=uid, division=division, mia=mia, divisiones=divisiones,
                  suben=suben, bajan=bajan, nombre_div_tabla=p.nombre_division(division),
                  clave_div_tabla=p.clave_division(division))


@lru_cache(maxsize=256)
def _png(carta_id: int) -> bytes:
    p = Partida.abrir(BD)
    try:
        carta = p.carta(carta_id)
    finally:
        p.con.close()
    return carta_a_bytes(carta).getvalue() if carta else b""


@app.get("/carta/{carta_id}.png")
def imagen_carta(carta_id: int):
    datos = _png(carta_id)
    if not datos:
        return Response(status_code=404)
    return Response(datos, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


# ------------------------------------------------------------------ escudos de los clubes del juego

@app.get("/escudo/equipo/{equipo_id}")
def escudo_equipo(equipo_id: int, p: Partida = P):
    e = p.equipo(equipo_id)
    if not e:
        return Response(status_code=404)
    valor = e["escudo"] or ""
    if valor.startswith("real:"):  # escudo de colección (club real)
        url = escudo_url(valor[5:])
        if url:
            return FileResponse(ESCUDOS / Path(url).name, media_type="image/png", headers={"Cache-Control": "max-age=31536000"})
    if valor.startswith("archivo:"):
        ruta = LOGOS_USUARIO / valor.split(":", 1)[1].split("#")[0]
        if ruta.is_file():
            return FileResponse(ruta, media_type="image/png", headers={"Cache-Control": "max-age=31536000"})
    return Response(escudo_svg(valor), media_type="image/svg+xml", headers={"Cache-Control": "max-age=31536000"})


@app.get("/api/escudo/vista")
def escudo_vista(forma: str = "clasico", c1: str = "#1f8a52", c2: str = "#ffffff", simbolo: str = "ninguno",
                 texto: str = ""):
    """Vista previa del diseñador de escudos del perfil."""
    return Response(escudo_svg({"forma": forma, "c1": c1, "c2": c2, "simbolo": simbolo, "texto": texto}),
                    media_type="image/svg+xml")


# ------------------------------------------------------------------ perfil

LOGOS_USUARIO = Path("data/logos")


@app.get("/perfil", response_class=HTMLResponse)
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


@app.post("/api/perfil")
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
        p.actualizar_perfil(eslogan=cuerpo.get("eslogan"), estadio=cuerpo.get("estadio"), escudo=escudo_nuevo)
    except (ErrorJuego, TypeError, AttributeError) as e:
        return error_json(e)
    return {"ok": True}


@app.post("/api/perfil/logo")
async def api_logo(archivo: UploadFile = File(...), p: Partida = P):
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
    nombre = f"club_{p.usuario_id}.png"
    img.save(LOGOS_USUARIO / nombre)
    # "#<hora>" cambia el valor guardado, así el navegador no reutiliza el escudo anterior
    p.actualizar_perfil(escudo=f"archivo:{nombre}#{int(_time.time())}")
    return {"ok": True}


# ------------------------------------------------------------------ inventario y mejoras

@app.get("/inventario", response_class=HTMLResponse)
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


@app.post("/api/mejorar/{pid}")
def api_mejorar(pid: int, p: Partida = P):
    try:
        f = p.mejorar(pid)
    except ErrorJuego as e:
        return error_json(e)
    return {"carta": _ficha_json(f), "monedas": p.monedas}


@app.post("/api/carta-gratis")
def api_carta_gratis(p: Partida = P):
    try:
        f = p.reclamar_carta_gratis()
    except ErrorJuego as e:
        return error_json(e)
    return {"cartas": [_ficha_json(f)], "monedas": p.monedas, "espera": p.segundos_para_carta_gratis()}


# ------------------------------------------------------------------ alineaciones guardadas

@app.post("/api/alineaciones/{accion}")
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


# ------------------------------------------------------------------ amistosos

@app.get("/amistosos", response_class=HTMLResponse)
def amistosos(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    clubes = p.clubes()
    por_division = []
    for d in reversed(range(p.n_divisiones)):
        lista = sorted((c for c in clubes if c["division"] == d), key=lambda c: -c["fuerza"])
        por_division.append({"nombre": p.nombre_division(d), "clave": p.clave_division(d), "clubes": lista})
    return pagina(request, "amistosos.html", p, divisiones=por_division, mi_fuerza=p.fuerza_equipo(p.usuario_id))


@app.post("/amistoso/{rival_id}")
def jugar_amistoso(rival_id: int, de_local: str = Form("1"), p: Partida = P):
    try:
        pid = p.iniciar_amistoso(rival_id, de_local == "1")
    except ErrorJuego as e:
        return ir("/amistosos", error=str(e))
    return ir(f"/partido/{pid}/vivo")

