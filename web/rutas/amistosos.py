"""Amistosos y desafíos entre amigos (contra el club de otro jugador manejado por la máquina)."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from juego.formaciones import COORDENADAS
from juego.partida import Partida
from partidos.motor import FORMACIONES
from web.comun import P, PRINCIPAL, _carta_json, _ficha_json, _leer_partida, ir, jugadores_online, pagina, registro
from web.rutas.vivo import SALA

router = APIRouter()

# ------------------------------------------------------------------ amistosos

@router.get("/amistosos", response_class=HTMLResponse)
def amistosos(request: Request, p: Partida = P):
    if not p.existe:
        return ir("/")
    clubes = p.clubes()
    por_division = []
    for d in reversed(range(p.n_divisiones)):
        lista = sorted((c for c in clubes if c["division"] == d), key=lambda c: -c["fuerza"])
        por_division.append({"nombre": p.nombre_division(d), "clave": p.clave_division(d), "clubes": lista})
    yo = request.state.partida_id
    r = registro()
    try:
        historial, record = r.historial(yo), r.record(yo)
        r.marcar_vistos(yo)
    finally:
        r.cerrar()
    amigos = jugadores_online(yo)
    for a in amigos:
        a["record"] = record.get(a["pid"], {"g": 0, "e": 0, "p": 0})
    return pagina(request, "amistosos.html", p, divisiones=por_division, mi_fuerza=p.fuerza_equipo(p.usuario_id),
                  amigos=amigos, desafios=historial,
                  esperando_vivo=[o["nombre"] for o in SALA.ver(yo).get("otros", [])])


@router.get("/amigo/{amigo}", response_class=HTMLResponse)
def ver_amigo(request: Request, amigo: str, p: Partida = P):
    """La plantilla de un amigo: su once en la cancha, la banca y todo el plantel (solo mirar)."""
    if not p.existe:
        return ir("/")
    otro = _leer_partida(amigo)
    if not otro:
        return ir("/amistosos", error="Ese club ya no existe.")
    try:
        uid = otro.usuario_id
        e = otro.equipo(uid)
        once = otro._equipo_usuario(uid)
        titulares = {j.id for j in once.titulares}
        banca = {j.id for j in once.suplentes}
        fichas = sorted(otro.plantel(uid), key=lambda f: -f.carta.ovr)
        q = otro.quimica_usuario()
        stats = otro.estadisticas_club()["record"]["liga"]
        datos = {
            "pid": amigo, "nombre": e["nombre"], "estadio": e["estadio"], "eslogan": e["eslogan"] or "",
            "division": otro.nombre_division(otro.division_de(uid)), "fuerza": round(otro.fuerza_equipo(uid), 1),
            "quimica": q["equipo"], "formacion": once.formacion, "mentalidad": once.mentalidad, "record": stats,
            "once": json.dumps([_carta_json(j.carta, puesto=pu, mejora=j.nivel_mejora)
                                for j, pu in zip(once.titulares, FORMACIONES[once.formacion])], ensure_ascii=False),
            "coords": json.dumps(COORDENADAS[once.formacion]),
            "banca": json.dumps([_ficha_json(f) for f in fichas if f.pid in banca], ensure_ascii=False),
            "resto": json.dumps([_ficha_json(f) for f in fichas if f.pid not in titulares and f.pid not in banca],
                                ensure_ascii=False),
            "n_cartas": len(fichas),
        }
    finally:
        otro.con.close()
    yo = getattr(request.state, "partida_id", PRINCIPAL)
    r = registro()
    try:
        record = r.record(yo).get(amigo, {"g": 0, "e": 0, "p": 0})
    finally:
        r.cerrar()
    return pagina(request, "amigo.html", p, amigo=datos, mio=amigo == yo, entre_ustedes=record)
