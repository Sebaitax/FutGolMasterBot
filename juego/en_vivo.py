"""Partidos en vivo entre amigos: sala de espera y un partido compartido por dos navegadores.

Los dos equipos son copias de los clubes de cada jugador al momento de empezar (su once,
banca y mejoras). El partido corre en el servidor (en memoria) y cada navegador lo va
pidiendo. En las jugadas clave los dos eligen a ciegas (uno ataca, el otro defiende) y se
define en un pulso de toques de precisión. Las tácticas las cambian los dos en vivo.

No toca las partidas guardadas (no hay lesiones, tarjetas ni premios): el resultado queda en
el registro de desafíos entre amigos. Si el servidor se reinicia, el partido se pierde.
"""
from __future__ import annotations

import random
import threading
import time
import uuid

from juego import antitrampas

from models.carta import Carta
from partidos.motor import FORMACIONES, LADOS_PENAL, RONDAS_PULSO, TACTICAS, Equipo, Jugador, Simulacion, armar_equipo
from partidos.narrador import Narrador

STATS = ("PAC", "SHO", "PAS", "DRI", "DEF", "PHY")
SUPLENTES_DEFECTO = 7
ESPERA_ELEGIR = 15      # segundos que se espera al rival para elegir antes de elegir por él
ESPERA_TOQUE = 8        # segundos por ronda del pulso
ABANDONO = 90           # sin noticias de un jugador: el partido sigue solo
ESPERANDO_VENCE = 120   # la sala de espera olvida a quien deja de preguntar
REACCIONES = ("😂", "🔥", "😱", "👏", "😤", "🫡")
APUESTAS = (0, 1000, 5000, 20000)
DEFENSA_SEGURA = {"jugada": "cerrar", "corner": "zona", "tiro_libre": "marcar"}


def equipo_de(datos: dict) -> Equipo:
    """Equipo del motor a partir de exportar_equipo() (con sus mejoras)."""
    jugadores, titulares, suplentes = [], [None] * 11, []
    for i, j in enumerate(datos["jugadores"]):
        c, nivel = j["carta"], j.get("nivel") or 1
        carta = Carta(nombre=c["nombre"], alias=c.get("alias") or "", posicion=c["posicion"], ovr=c["ovr"],
                      stats={s: c[s.lower()] for s in STATS}, nacion=c.get("nacion") or "", club=c.get("club") or "",
                      liga=c.get("liga") or "", precio=c.get("precio") or 0)
        if nivel > 1:
            carta.ovr_original = carta.ovr
            carta.ovr += nivel - 1
            carta.stats = {k: min(99, v + nivel - 1) for k, v in carta.stats.items()}
        jug = Jugador(carta, id=i + 1, nivel_mejora=nivel)
        jugadores.append(jug)
        puesto = j.get("puesto")
        if puesto is not None and 0 <= puesto < 11 and titulares[puesto] is None:
            titulares[puesto] = jug
        elif puesto is not None and 11 <= puesto < 11 + SUPLENTES_DEFECTO:
            suplentes.append(jug)
    formacion = datos.get("formacion") if datos.get("formacion") in FORMACIONES else "4-3-3"
    if None in titulares:   # once incompleto: se arma solo con lo que hay
        e = armar_equipo(datos["nombre"], jugadores, formacion, suplentes=SUPLENTES_DEFECTO)
    else:
        usados = {j.id for j in titulares} | {j.id for j in suplentes}
        resto = sorted((j for j in jugadores if j.id not in usados), key=lambda j: -j.carta.ovr)
        e = Equipo(datos["nombre"], formacion, titulares, (suplentes + resto)[:SUPLENTES_DEFECTO])
    e.mentalidad = datos.get("mentalidad") or "equilibrada"
    return e


class PartidoVivo:
    def __init__(self, mid: str, local: dict, visita: dict, apuesta: int = 0):
        self.mid = mid
        self.apuesta = apuesta          # monedas que puso cada uno (el ganador se lleva las dos)
        self.reacciones: list[dict] = []
        self.sospechas = [0, 0]           # toques sospechosos de cada lado (control antitrampas)
        self.revancha = [False, False]
        self.revancha_mid: str | None = None
        self.lock = threading.RLock()
        self.pids = [local["pid"], visita["pid"]]
        self.datos = [local["equipo"], visita["equipo"]]
        self.nombres = [local["equipo"]["nombre"], visita["equipo"]["nombre"]]
        self.escudos = [local["equipo"].get("escudo") or "", visita["equipo"].get("escudo") or ""]
        self.semilla = random.randrange(10**9)
        self.decisiones: list[dict] = []
        self.intervenciones: list[dict] = []
        self.version = 0
        self.corte = 0                 # desde qué evento cambió todo en la última versión
        self.visto = [(1, 0), (1, 0)]  # último minuto que vio cada uno
        self.ultimo_contacto = [time.time(), time.time()]
        self.anotado = False
        self._nueva_pausa()
        self._reconstruir()

    # ---------------------------------------------------------------- simulación

    def _reconstruir(self):
        """Juega desde el inicio con la misma semilla, las tácticas pedidas y las decisiones tomadas."""
        sim = Simulacion(equipo_de(self.datos[0]), equipo_de(self.datos[1]), "amistoso", self.semilla)
        sim.duelos = True
        sim.programar(self.intervenciones)
        self.sim, self.gen, self.resultado = sim, sim.correr(interactivo=None), None
        try:
            self.pausa = next(self.gen)
            for d in self.decisiones:
                self.pausa = self.gen.send(d)
        except StopIteration as fin:
            self.pausa, self.resultado = None, fin.value

    def _nueva_pausa(self):
        self.eleccion = [None, None]
        self.toques = [[], []]
        self.prep = None
        self.desde_pausa = time.time()
        self.desde_ronda = time.time()

    def _continuar(self, decision: dict):
        self.decisiones.append(decision)
        self._nueva_pausa()
        try:
            self.pausa = self.gen.send(decision)
        except StopIteration as fin:
            self.pausa, self.resultado = None, fin.value

    # ---------------------------------------------------------------- jugadas clave

    def _roles(self) -> tuple[int, int]:
        """(lado que ataca, lado que defiende) en la pausa actual."""
        ataca = self.pausa["ataca"]
        return ataca, 1 - ataca

    def _preparar(self):
        ataca, defiende = self._roles()
        ea, ed = self.eleccion[ataca], self.eleccion[defiende]
        if self.pausa["tipo"] == "penal":
            self.prep = self.sim.preparar_penal(self.pausa, ea, ed)
        else:
            self.prep = self.sim.preparar_duelo(self.pausa, ea, ed)
        self.desde_ronda = time.time()
        if not self.prep.get("pulso", True):   # penal al otro lado: no hay pulso
            self._cerrar_pausa()

    def _cerrar_pausa(self):
        ataca, defiende = self._roles()
        pa = self.toques[ataca] + [0.1] * (RONDAS_PULSO - len(self.toques[ataca]))
        pd = self.toques[defiende] + [0.1] * (RONDAS_PULSO - len(self.toques[defiende]))
        if self.pausa["tipo"] == "penal":
            d = {"lado_pateador": self.prep["lado"], "lado_arquero": self.prep["adivina"], "prec_ataque": pa, "prec_defensa": pd}
        else:
            d = {"ataque": self.prep["ataque"], "defensa": self.prep["defensa"], "prec_ataque": pa, "prec_defensa": pd}
        self._continuar(d)

    def _vencimientos(self):
        """Si alguien no responde a tiempo, se decide por él (mal)."""
        if not self.pausa:
            return
        ahora = time.time()
        ataca, defiende = self._roles()
        if self.prep is None:
            if any(e is not None for e in self.eleccion) and ahora - self.desde_pausa > ESPERA_ELEGIR \
                    or ahora - self.desde_pausa > ESPERA_ELEGIR * 2:
                penal = self.pausa["tipo"] == "penal"
                for lado in (0, 1):
                    if self.eleccion[lado] is None:
                        self.eleccion[lado] = ("izq" if lado == ataca else "centro") if penal else \
                            (self._validas(lado)[0] if lado == ataca else DEFENSA_SEGURA.get(self.pausa.get("clase"), "cerrar"))
                self._preparar()
            return
        ronda = min(len(self.toques[0]), len(self.toques[1]))
        if ronda < RONDAS_PULSO and ahora - self.desde_ronda > ESPERA_TOQUE:
            for lado in (0, 1):
                if len(self.toques[lado]) <= ronda:
                    self.toques[lado].append(0.1)
            self.desde_ronda = ahora
            if min(len(self.toques[0]), len(self.toques[1])) >= RONDAS_PULSO:
                self._cerrar_pausa()

    def elegir(self, lado: int, eleccion: str):
        with self.lock:
            if not self.pausa or self.prep is not None or self.eleccion[lado] is not None:
                return
            validas = self._validas(lado)
            self.eleccion[lado] = eleccion if eleccion in validas else validas[0]
            if None not in self.eleccion:
                self._preparar()

    def _validas(self, lado: int) -> list[str]:
        if self.pausa["tipo"] == "penal":
            return list(LADOS_PENAL)
        rol = "ataque" if lado == self.pausa["ataca"] else "defensa"
        return [o["clave"] for o in self.sim.opciones_rol(self.pausa, rol)]

    def reaccionar(self, lado: int, emoji: str):
        with self.lock:
            if emoji in REACCIONES:
                self.reacciones = (self.reacciones + [{"n": len(self.reacciones) + 1, "lado": lado, "emoji": emoji}])[-30:]

    def tocar(self, lado: int, ronda: int, precision: float):
        with self.lock:
            if not self.pausa or self.prep is None or len(self.toques[lado]) != ronda or ronda >= RONDAS_PULSO:
                return
            precision = min(1.0, max(0.0, float(precision)))
            if time.time() - self.desde_ronda < antitrampas.SEGUNDOS_MIN_TOQUE_PVP:
                precision = antitrampas.FALLO   # nadie toca tan rápido
                self.sospechas[lado] += 1
            hist = getattr(self, "historial_pulso", [[], []])
            _, hist[lado], motivo = antitrampas.revisar([precision], None, hist[lado])
            self.historial_pulso = hist
            if motivo:
                precision = min(precision, antitrampas.TOPE_SOSPECHA)
                self.sospechas[lado] += 1
            self.toques[lado].append(precision)
            if len(self.toques[0]) == len(self.toques[1]):
                self.desde_ronda = time.time()
            if min(len(self.toques[0]), len(self.toques[1])) >= RONDAS_PULSO:
                self._cerrar_pausa()

    # ---------------------------------------------------------------- tácticas

    def tactica(self, lado: int, valor: str):
        with self.lock:
            if valor not in TACTICAS or self.resultado is not None or valor == self.sim.equipos[lado].tactica:
                return
            # desde el minuto siguiente al que ya vio el que va más adelantado (nadie ve cambiar el pasado)
            t, m = max(self.visto)
            clave = (t, m + 1)
            if self.intervenciones and clave <= max((i["t"], i["m"]) for i in self.intervenciones):
                clave = max((i["t"], i["m"]) for i in self.intervenciones)
                clave = (clave[0], clave[1] + 1)
            self.intervenciones.append({"t": clave[0], "m": clave[1], "tipo": "tactica", "valor": valor, "eq": lado})
            # las decisiones tomadas después de ese minuto ya no valen (el partido cambia desde ahí)
            self._reconstruir_desde(clave)

    def _reconstruir_desde(self, clave: tuple[int, int]):
        viejos = len(self.sim.eventos)
        decisiones = self.decisiones
        self.decisiones = []
        sim = Simulacion(equipo_de(self.datos[0]), equipo_de(self.datos[1]), "amistoso", self.semilla)
        sim.duelos = True
        sim.programar(self.intervenciones)
        self.sim, self.gen, self.resultado = sim, sim.correr(interactivo=None), None
        try:
            self.pausa = next(self.gen)
            for d in decisiones:
                if self.pausa and (self.pausa["tiempo"], self.pausa["minuto"]) >= clave:
                    break   # esta jugada ya no es la misma
                self.decisiones.append(d)
                self.pausa = self.gen.send(d)
        except StopIteration as fin:
            self.pausa, self.resultado = None, fin.value
        self._nueva_pausa()
        self.version += 1
        self.corte = min(viejos, self.sim.indice_intervencion.get(clave, len(self.sim.eventos)))

    # ---------------------------------------------------------------- lo que ve cada uno

    def estado(self, lado: int, desde: int, visto: tuple[int, int] | None) -> dict:
        with self.lock:
            self.ultimo_contacto[lado] = time.time()
            if visto:
                self.visto[lado] = max(self.visto[lado], tuple(visto))
            self._vencimientos()
            sim = self.sim
            parcial = self.resultado or sim.parcial()
            desde = max(0, min(desde, len(sim.eventos)))
            lineas = Narrador(parcial, self.semilla + desde).tramo(desde)
            pausa = None
            if self.pausa:
                ataca, defiende = self._roles()
                pausa = {k: v for k, v in self.pausa.items() if k != "ref"}
                pausa["rol"] = "ataque" if lado == ataca else "defensa"
                pausa["mi_eleccion"] = self.eleccion[lado]
                pausa["rival_eligio"] = self.eleccion[1 - lado] is not None
                if self.pausa["tipo"] == "duelo":
                    pausa.update(sim.opciones_pausa(self.pausa, pausa["rol"]))
                if self.prep is not None:
                    prep = dict(self.prep)
                    prep["rol"] = pausa["rol"]
                    pausa["prep"] = prep
                    hechas = min(len(self.toques[0]), len(self.toques[1]))
                    pausa["mis_toques"] = self.toques[lado]
                    pausa["toques_rival"] = self.toques[1 - lado][:hechas]   # solo las rondas que ya tocaron los dos
            return {
                "version": self.version, "corte": self.corte,
                "lineas": [l.a_dict() for l in lineas], "eventos": len(sim.eventos), "posesion": sim.posesion_min,
                "marcador": list(sim.goles), "pausa": pausa, "final": self.resultado is not None, "lado": lado,
                "tactica": sim.equipos[lado].tactica, "tactica_rival": sim.equipos[1 - lado].tactica,
                "tactica_rival_leida": sim.tactica_leida(1 - lado),
                "rival_conectado": time.time() - self.ultimo_contacto[1 - lado] < 15,
                "reacciones": [r for r in self.reacciones if r["lado"] != lado],
                "revancha": {"yo": self.revancha[lado], "rival": self.revancha[1 - lado], "partido": self.revancha_mid},
                "apuesta": self.apuesta,
            }

    def abandonado(self) -> bool:
        return all(time.time() - t > ABANDONO for t in self.ultimo_contacto)


class Sala:
    """Quién está esperando rival y los partidos en curso (en memoria del servidor)."""

    def __init__(self):
        self.lock = threading.RLock()
        self.esperando: dict[str, dict] = {}
        self.partidos: dict[str, PartidoVivo] = {}
        self.de_jugador: dict[str, str] = {}

    def _limpiar(self):
        ahora = time.time()
        for pid in [p for p, e in self.esperando.items() if ahora - e["visto"] > ESPERANDO_VENCE]:
            del self.esperando[pid]
        for mid in [m for m, p in self.partidos.items() if p.abandonado()]:
            for pid in self.partidos[mid].pids:
                self.de_jugador.pop(pid, None)
            del self.partidos[mid]

    def esperar(self, pid: str, info: dict, apuesta: int = 0):
        with self.lock:
            self._limpiar()
            if pid in self.de_jugador:
                return
            self.esperando[pid] = {**info, "pid": pid, "apuesta": apuesta if apuesta in APUESTAS else 0,
                                   "desde": self.esperando.get(pid, {}).get("desde", time.time()), "visto": time.time()}

    def cancelar(self, pid: str):
        with self.lock:
            self.esperando.pop(pid, None)

    def ver(self, pid: str) -> dict:
        """Lo que ve un jugador en la sala: si ya tiene partido, y quiénes esperan."""
        with self.lock:
            self._limpiar()
            if pid in self.esperando:
                self.esperando[pid]["visto"] = time.time()
            mid = self.de_jugador.get(pid)
            if mid and mid in self.partidos and self.partidos[mid].resultado is None:
                return {"partido": mid}
            return {"partido": None, "esperando": pid in self.esperando,
                    "otros": [{k: v for k, v in e.items() if k != "visto"} for p, e in self.esperando.items() if p != pid]}

    def apuesta_de(self, rival: str) -> int:
        with self.lock:
            return self.esperando.get(rival, {}).get("apuesta", 0)

    def aceptar(self, pid: str, rival: str, mio: dict, suyo: dict) -> str:
        """`pid` acepta jugar contra `rival` (que está esperando). El que esperaba juega de local."""
        with self.lock:
            if rival not in self.esperando:
                raise ValueError("Ese rival ya no está esperando.")
            if pid in self.de_jugador or rival in self.de_jugador:
                raise ValueError("Ya hay un partido en curso.")
            mid = uuid.uuid4().hex[:12]
            self.partidos[mid] = PartidoVivo(mid, {"pid": rival, "equipo": suyo}, {"pid": pid, "equipo": mio},
                                             apuesta=self.esperando[rival].get("apuesta", 0))
            self.de_jugador[pid] = self.de_jugador[rival] = mid
            self.esperando.pop(rival, None)
            self.esperando.pop(pid, None)
            return mid

    def pedir_revancha(self, mid: str, lado: int) -> str | None:
        """Revancha: cuando la piden los dos, otro partido con los mismos clubes (y la misma apuesta), con la localía al revés."""
        with self.lock:
            p = self.partidos.get(mid)
            if not p or p.resultado is None:
                return None
            p.revancha[lado] = True
            if all(p.revancha) and not p.revancha_mid and not any(pid in self.de_jugador for pid in p.pids):
                nuevo = uuid.uuid4().hex[:12]
                self.partidos[nuevo] = PartidoVivo(nuevo, {"pid": p.pids[1], "equipo": p.datos[1]},
                                                   {"pid": p.pids[0], "equipo": p.datos[0]}, apuesta=p.apuesta)
                for pid in p.pids:
                    self.de_jugador[pid] = nuevo
                p.revancha_mid = nuevo
            return p.revancha_mid

    def partido(self, mid: str) -> PartidoVivo | None:
        return self.partidos.get(mid)

    def terminar(self, mid: str):
        with self.lock:
            p = self.partidos.get(mid)
            if p:
                for pid in p.pids:
                    if self.de_jugador.get(pid) == mid:
                        del self.de_jugador[pid]
