"""Ranking de copas (y la tabla de la liga antigua)."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego import escalera as ESC
from juego.partida import Partida
from web.comun import P, PRINCIPAL, _yo, ir, pagina, sincronizar_liga
from web.rutas.inicio import _jugadores_escalera

router = APIRouter()

# ------------------------------------------------------------------ tabla

@router.get("/tabla", response_class=HTMLResponse)
def tabla(request: Request, p: Partida = P):
    """Ranking global de copas (todos los jugadores)."""
    if not p.existe:
        return ir("/")
    yo = _yo(request)
    filas = _jugadores_escalera(yo) + [{"pid": yo, "nombre": p.nombre_equipo(p.usuario_id), "copas": p.copas,
                                       "pais": p.pais, "cancha": p.cancha}]
    filas.sort(key=lambda j: -j["copas"])
    ranking = [{"nombre": j["nombre"], "copas": j["copas"], "yo": j["pid"] == yo,
                "bandera": ESC.PAISES.get(j["pais"], ESC.PAISES[ESC.PAIS_DEFECTO])[1],
                "cancha": ESC.info_cancha(j["cancha"], j["pais"])} for j in filas]
    return pagina(request, "tabla.html", p, ranking=ranking)


@router.get("/tabla-liga", response_class=HTMLResponse)
def tabla_liga(request: Request, fecha: int | None = None, division: int | None = None, p: Partida = P):
    if not p.existe:
        return ir("/")
    sincronizar_liga(p, getattr(request.state, "partida_id", PRINCIPAL))
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
    return pagina(request, "tabla_liga.html", p, tabla=p.tabla(division=division), goleadores=p.goleadores(10, division),
                  fecha=fecha, total=total, partidos=p.partidos_fecha(fecha, division=division), fixture=fixture,
                  fecha_actual=p.fecha, uid=uid, division=division, mia=mia, divisiones=divisiones,
                  suben=suben, bajan=bajan, nombre_div_tabla=p.nombre_division(division),
                  clave_div_tabla=p.clave_division(division))
