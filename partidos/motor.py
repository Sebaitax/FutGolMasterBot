"""Motor de simulación de partidos basado en probabilidades.

Cada minuto se decide quién tiene la pelota, si hay ocasión, falta, lesión o
cambio. Las probabilidades salen de las cartas de cada equipo:

- Estadísticas y OVR de los jugadores.
- Afinidad con la posición en que juegan (un DFC de delantero rinde menos).
- Estado: lesionados y suspendidos no pueden jugar.
- Nivel de mejora de la carta (pequeño bonus).
- Energía: baja durante el partido, más rápido si el jugador tiene poco físico.

El resultado es reproducible si se pasa la misma `semilla`.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from models.carta import Carta

# ---------------------------------------------------------------- posiciones

LINEA = {
    "GK": "POR",
    "CB": "DEF", "LB": "DEF", "RB": "DEF", "LWB": "DEF", "RWB": "DEF",
    "CDM": "MED", "CM": "MED", "CAM": "MED", "LM": "MED", "RM": "MED",
    "LW": "DEL", "RW": "DEL", "ST": "DEL", "CF": "DEL",
}
ORDEN_LINEAS = ["POR", "DEF", "MED", "DEL"]

FORMACIONES = {
    "4-3-3": ["GK", "LB", "CB", "CB", "RB", "CM", "CDM", "CM", "LW", "ST", "RW"],
    "4-4-2": ["GK", "LB", "CB", "CB", "RB", "LM", "CM", "CM", "RM", "ST", "ST"],
    "4-2-3-1": ["GK", "LB", "CB", "CB", "RB", "CDM", "CDM", "LM", "CAM", "RM", "ST"],
    "3-5-2": ["GK", "CB", "CB", "CB", "LWB", "CM", "CDM", "CM", "RWB", "ST", "ST"],
    "5-3-2": ["GK", "LWB", "CB", "CB", "CB", "RWB", "CM", "CM", "CM", "ST", "ST"],
}

BANDAS = {"LB", "RB", "LWB", "RWB", "LM", "RM", "LW", "RW"}
ESTADOS_NO_DISPONIBLES = {"lesionado", "suspendido"}

# Mentalidad: multiplica el ataque propio y la defensa propia (más ataque = más espacios atrás)
MENTALIDADES = {
    "defensiva": (0.88, 1.10),
    "equilibrada": (1.0, 1.0),
    "ofensiva": (1.12, 0.91),
}
MAX_CAMBIOS = 5

# Táctica en vivo: multiplica el control (posesión), ataque, defensa, calidad de las ocasiones,
# gasto de energía y faltas del equipo que la usa.
TACTICAS = {
    "normal": dict(nombre="Normal", ico="⚖️", control=1.0, ataque=1.0, defensa=1.0, calidad=1.0, energia=1.0, faltas=1.0,
                   ayuda="Tu esquema de siempre."),
    "presion": dict(nombre="Presión alta", ico="🔥", control=1.07, ataque=1.04, defensa=0.97, calidad=1.0, energia=1.4,
                    faltas=1.35, ayuda="Más pelota y más llegadas, pero se cansan antes y hacen más faltas."),
    "contragolpe": dict(nombre="Contragolpe", ico="⚡", control=0.88, ataque=1.06, defensa=1.06, calidad=1.18, energia=1.05,
                        faltas=1.0, ayuda="Cedes la pelota; llegas menos, pero con ocasiones más claras."),
    "centros": dict(nombre="Centros al área", ico="🎯", control=1.0, ataque=1.12, defensa=1.0, calidad=0.86, energia=1.0,
                    faltas=1.0, ayuda="Muchas llegadas de menor calidad. Rinde con delanteros fuertes de cabeza."),
    "cuidar": dict(nombre="Cuidar el resultado", ico="🛡️", control=1.05, ataque=0.78, defensa=1.13, calidad=1.0,
                   energia=0.85, faltas=0.9, ayuda="Te cierras atrás y casi no atacas."),
}
PAUSAS_TACTICAS = 2      # pausas para hacer cambios cuando quieras (además del entretiempo)
ESPERA_TACTICA = 10      # minutos entre cambios de táctica
MAX_MOMENTOS = 4         # momentos clave por partido (tú decides la jugada)
PROB_MOMENTO = 0.35      # de cada ocasión tuya, cuántas se vuelven momento clave
SEPARACION_MOMENTOS = 8  # minutos mínimos entre momentos clave
# calidad extra de la ocasión según lo que elijas en un momento clave
CALIDAD_MOMENTO = {"tirar": 1.1, "pasar": 1.35, "gambetear": 1.65}
LADOS_PENAL = ("izq", "centro", "der")


def _poisson(lam: float, tope: int = 9) -> list[float]:
    p = [math.exp(-lam)]
    for k in range(1, tope):
        p.append(p[-1] * lam / k)
    return p


def linea(posicion: str) -> str:
    return LINEA.get(posicion.upper(), "MED")


def afinidad(natural: str, puesto: str) -> float:
    """Qué tan bien rinde un jugador de posición `natural` jugando en `puesto`."""
    natural, puesto = natural.upper(), puesto.upper()
    if natural == puesto:
        return 1.0
    ln, lp = linea(natural), linea(puesto)
    if "POR" in (ln, lp):
        return 0.25  # arquero de jugador de campo o al revés
    if ln == lp:
        return 0.92
    distancia = abs(ORDEN_LINEAS.index(ln) - ORDEN_LINEAS.index(lp))
    return 0.8 if distancia == 1 else 0.65


# ---------------------------------------------------------------- jugadores

@dataclass
class Jugador:
    """Una carta del inventario lista para jugar."""

    carta: Carta
    estado: str = "disponible"
    nivel_mejora: int = 1
    id: int | None = None  # identificador en la base de datos (para aplicar lesiones y tarjetas)
    quimica: float = 1.0   # multiplicador por química con los compañeros (0.97 a 1.03)

    @property
    def nombre(self) -> str:
        return self.carta.nombre_corto

    @property
    def disponible(self) -> bool:
        return self.estado.lower() not in ESTADOS_NO_DISPONIBLES


@dataclass
class EnCancha:
    """Estado de un jugador durante el partido."""

    jugador: Jugador
    puesto: str
    energia: float = 100.0
    amarillas: int = 0
    activo: bool = True
    slot: int = -1      # lugar de la formación que ocupa (0-10), para dibujarlo en la cancha
    salida: str = ""    # por qué dejó la cancha: cambio, tactico, lesion, roja, decision, tras_roja
    # estadísticas individuales
    goles: int = 0
    asistencias: int = 0
    tiros: int = 0
    a_puerta: int = 0
    atajadas: int = 0
    faltas: int = 0
    minutos: int = 0

    @property
    def nombre(self) -> str:
        return self.jugador.nombre

    @property
    def es_arquero(self) -> bool:
        return self.puesto == "GK"

    @property
    def linea(self) -> str:
        return linea(self.puesto)

    def factor(self) -> float:
        """Multiplicador por afinidad, energía y mejora."""
        energia = 0.75 + 0.25 * self.energia / 100
        mejora = 1 + 0.01 * (self.jugador.nivel_mejora - 1)
        return afinidad(self.jugador.carta.posicion, self.puesto) * energia * mejora * self.jugador.quimica

    def stat(self, clave: str) -> float:
        carta = self.jugador.carta
        valor = carta.ovr if clave == "OVR" else carta.stats.get(clave, carta.ovr)
        if linea(carta.posicion) == "POR" and clave != "OVR":
            valor = 30  # en los CSV, las stats de un arquero son de arquero
        return valor * self.factor()

    def gastar_energia(self, factor: float = 1.0):
        fisico = self.jugador.carta.stats.get("PHY", 60)
        if self.es_arquero:
            gasto = 0.12
        else:
            gasto = max(0.25, 0.58 - (fisico - 50) * 0.007) * factor
        self.energia = max(0.0, self.energia - gasto)


@dataclass
class Equipo:
    nombre: str
    formacion: str
    titulares: list[Jugador]
    suplentes: list[Jugador] = field(default_factory=list)
    mentalidad: str = "equilibrada"
    tactica: str = "normal"

    def validar(self):
        if self.mentalidad not in MENTALIDADES:
            raise ValueError(f"Mentalidad desconocida: {self.mentalidad}")
        if self.formacion not in FORMACIONES:
            raise ValueError(f"Formación desconocida: {self.formacion}")
        if len(self.titulares) != 11:
            raise ValueError(f"{self.nombre}: se necesitan 11 titulares ({len(self.titulares)})")
        no_disp = [j.nombre for j in self.titulares if not j.disponible]
        if no_disp:
            raise ValueError(f"{self.nombre}: jugadores no disponibles en el once: {', '.join(no_disp)}")


def armar_equipo(nombre: str, jugadores: list[Jugador], formacion: str = "4-3-3", suplentes: int = 7) -> Equipo:
    """Elige el mejor once disponible para la formación (y la banca)."""
    libres = sorted((j for j in jugadores if j.disponible), key=lambda j: -j.carta.ovr)
    puestos = FORMACIONES[formacion]
    once: list[Jugador | None] = [None] * len(puestos)
    # primero el arquero, después el resto
    for i in sorted(range(len(puestos)), key=lambda i: puestos[i] != "GK"):
        if not libres:
            raise ValueError(f"{nombre}: no hay suficientes jugadores disponibles")
        mejor = max(libres, key=lambda j: j.carta.ovr * afinidad(j.carta.posicion, puestos[i]))
        once[i] = mejor
        libres.remove(mejor)
    return Equipo(nombre, formacion, once, libres[:suplentes])


# ---------------------------------------------------------------- resultado

@dataclass
class Evento:
    minuto: int
    tipo: str          # inicio, gol, atajada, desviado, palo, falta, amarilla, roja, lesion, cambio, descanso, final, ocasion
    equipo: int = -1   # 0 local, 1 visita, -1 ninguno
    jugador: str = ""
    datos: dict = field(default_factory=dict)
    tiempo: int = 1    # 1 = primer tiempo, 2 = segundo tiempo

    @property
    def minuto_texto(self) -> str:
        """Minuto como en la tele: 26', 45+3', 90+2'."""
        limite = 45 if self.tiempo == 1 else 90
        if self.minuto > limite:
            return f"{limite}+{self.minuto - limite}'"
        return f"{self.minuto}'"


@dataclass
class Resultado:
    equipos: tuple[str, str]
    goles: list[int]
    eventos: list[Evento]
    estadisticas: list[dict]
    jugadores: list[list[EnCancha]]
    mvp: tuple[int, str, float]
    lesiones: list[dict]         # para actualizar el inventario
    tarjetas: list[dict]
    tipo: str
    razones: list = field(default_factory=lambda: [[], []])  # por qué se ganó o perdió, por equipo

    @property
    def ganador(self) -> int:
        if self.goles[0] == self.goles[1]:
            return -1
        return 0 if self.goles[0] > self.goles[1] else 1


# ---------------------------------------------------------------- simulación

class Simulacion:
    def __init__(self, local: Equipo, visita: Equipo, tipo: str = "amistoso", semilla: int | None = None):
        local.validar()
        visita.validar()
        self.rng = random.Random(semilla)
        self.tipo = tipo
        self.equipos = (local, visita)
        self.cancha = [
            [EnCancha(j, p, slot=i) for i, (j, p) in enumerate(zip(e.titulares, FORMACIONES[e.formacion]))]
            for e in self.equipos
        ]
        self.banca = [list(e.suplentes) for e in self.equipos]
        self.usados: list[list[EnCancha]] = [list(c) for c in self.cancha]
        self.cambios = [0, 0]
        self.goles = [0, 0]
        self.eventos: list[Evento] = []
        self.est = [dict(posesion=0, tiros=0, a_puerta=0, faltas=0, amarillas=0, rojas=0, corners=0) for _ in range(2)]
        self.lesiones: list[dict] = []
        self.tarjetas: list[dict] = []
        self.minuto = 0
        self.tiempo = 1
        self.posesion_min: list[tuple[int, int, int]] = []  # (tiempo, minuto, equipo con la pelota)
        self.interactivo: int | None = None                 # equipo que toma decisiones (pausas)
        self._pausas: list[dict] = []
        self._pendientes: dict[int, tuple] = {}             # jugadas esperando tu decisión
        self._n_pend = 0
        self.intervenciones: dict[tuple[int, int], list[dict]] = {}  # táctica o pausa pedidas en vivo
        self.indice_intervencion: dict[tuple[int, int], int] = {}
        self.momentos: list[dict] = []                      # momentos clave ya resueltos
        self._n_momentos = 0
        self._ultimo_momento = -99
        self.cambios_tactica: list[dict] = []
        self.fuerza_inicial = [1.0, 1.0]

    def programar(self, intervenciones: list[dict]):
        """Intervenciones en vivo del equipo interactivo: {"t", "m", "tipo": tactica|pausa, "valor"}."""
        self.intervenciones = {}
        for i in intervenciones:
            self.intervenciones.setdefault((int(i["t"]), int(i["m"])), []).append(i)

    # --- fuerza de cada equipo -------------------------------------------

    def _activos(self, eq: int) -> list[EnCancha]:
        return [j for j in self.cancha[eq] if j.activo]

    def _suma(self, eq: int, pesos_linea: dict, formula) -> float:
        return sum(formula(j) * pesos_linea.get(j.linea, 0) for j in self._activos(eq))

    def control(self, eq: int) -> float:
        f = lambda j: 0.45 * j.stat("PAS") + 0.35 * j.stat("DRI") + 0.2 * j.stat("PHY")
        return (self._suma(eq, {"MED": 1.0, "DEF": 0.35, "DEL": 0.45}, f) * (1.03 if eq == 0 else 1.0)
                * self._t(eq, "control"))

    def ataque(self, eq: int) -> float:
        f = lambda j: 0.45 * j.stat("SHO") + 0.3 * j.stat("DRI") + 0.25 * j.stat("PAC")
        return (self._suma(eq, {"DEL": 1.0, "MED": 0.55, "DEF": 0.15}, f) * MENTALIDADES[self.equipos[eq].mentalidad][0]
                * self._t(eq, "ataque"))

    def defensa(self, eq: int) -> float:
        f = lambda j: 0.65 * j.stat("DEF") + 0.2 * j.stat("PHY") + 0.15 * j.stat("PAC")
        return (self._suma(eq, {"DEF": 1.0, "MED": 0.45, "DEL": 0.1}, f) * MENTALIDADES[self.equipos[eq].mentalidad][1]
                * self._t(eq, "defensa"))

    def _t(self, eq: int, clave: str) -> float:
        return TACTICAS.get(self.equipos[eq].tactica, TACTICAS["normal"])[clave]

    def arquero(self, eq: int) -> EnCancha | None:
        return next((j for j in self._activos(eq) if j.es_arquero), None)

    # --- utilidades -------------------------------------------------------

    def _elegir(self, candidatos: list[EnCancha], peso) -> EnCancha:
        pesos = [max(peso(j), 0.01) for j in candidatos]
        return self.rng.choices(candidatos, weights=pesos)[0]

    def _evento(self, tipo: str, eq: int = -1, jugador: str = "", **datos):
        datos.setdefault("marcador", tuple(self.goles))
        self.eventos.append(Evento(self.minuto, tipo, eq, jugador, datos, self.tiempo))

    def _sacar(self, eq: int, j: EnCancha, motivo: str) -> EnCancha | None:
        """Saca a un jugador; si se puede, entra un suplente en su puesto."""
        j.activo = False
        j.salida = motivo
        if motivo != "roja" and self.banca[eq] and self.cambios[eq] < MAX_CAMBIOS:
            puesto = j.puesto
            entra = max(self.banca[eq], key=lambda s: s.carta.ovr * afinidad(s.carta.posicion, puesto))
            self.banca[eq].remove(entra)
            nuevo = EnCancha(entra, puesto, slot=j.slot)
            self.cancha[eq].append(nuevo)
            self.usados[eq].append(nuevo)
            self.cambios[eq] += 1
            self._evento("cambio", eq, entra.nombre, sale=j.nombre, motivo=motivo)
            return nuevo
        if j.es_arquero:
            # sin cambios: un jugador de campo va al arco
            reemplazo = max(self._activos(eq), key=lambda x: x.jugador.carta.stats.get("PHY", 50), default=None)
            if reemplazo:
                reemplazo.puesto = "GK"
                reemplazo.slot = j.slot
                self._evento("al_arco", eq, reemplazo.nombre)
        return None

    # --- jugadas ----------------------------------------------------------

    def _ocasion(self, eq: int) -> bool:
        """Una ocasión de gol. Devuelve True si quedó esperando tu decisión (momento clave)."""
        activos = [j for j in self._activos(eq) if not j.es_arquero]
        if not activos:
            return False
        # reparte los tiros: los delanteros patean más, pero no siempre el mismo
        peso_tiro = {"DEL": 2.0, "MED": 1.5, "DEF": 0.4}
        cabeza = self.equipos[eq].tactica == "centros"
        tirador = self._elegir(activos, lambda j: peso_tiro.get(j.linea, 0.1) * j.stat("SHO")
                               * (j.jugador.carta.stats.get("PHY", 60) / 60 if cabeza else 1))
        otros = [j for j in activos if j is not tirador]
        asistente = self._elegir(otros, lambda j: j.stat("PAS") ** 2) if otros and self.rng.random() < 0.72 else None
        jugada = self._tipo_jugada(tirador, asistente)
        if cabeza and asistente and jugada not in ("centro", "centro_cabeza"):
            jugada = "centro_cabeza" if tirador.jugador.carta.stats.get("PHY", 60) >= 70 else "centro"
        ahora = (self.tiempo - 1) * 50 + self.minuto
        if (eq == self.interactivo and self._n_momentos < MAX_MOMENTOS
                and ahora - self._ultimo_momento >= SEPARACION_MOMENTOS and self.rng.random() < PROB_MOMENTO):
            self._n_momentos += 1
            self._ultimo_momento = ahora
            ref = self._pendiente(("ocasion", eq, tirador, asistente, jugada))
            self._evento("momento", eq, tirador.nombre, asistente=asistente.nombre if asistente else "")
            self._pausas.append({"tipo": "ocasion", "ref": ref, "jugador": tirador.nombre, "minuto": self.minuto,
                                 "tiempo": self.tiempo, "segundos": 8})
            return True
        self._tiro(eq, tirador, asistente, jugada=jugada)
        return False

    def _pendiente(self, datos: tuple) -> int:
        self._n_pend += 1
        self._pendientes[self._n_pend] = datos
        return self._n_pend

    def _tipo_jugada(self, tirador: EnCancha, asistente: EnCancha | None) -> str:
        """Cómo se armó la ocasión, según las características de quienes participan."""
        stats = tirador.jugador.carta.stats
        r = self.rng.random()
        if asistente:
            if asistente.puesto in BANDAS and r < 0.7:
                return "centro_cabeza" if stats.get("PHY", 60) >= 75 and self.rng.random() < 0.55 else "centro"
            if stats.get("PAC", 60) >= 85 and r < 0.45:
                return "contragolpe"
            return "pared" if r < 0.5 else "pase_filtrado"
        if stats.get("DRI", 60) >= 82 and r < 0.5:
            return "individual"
        if stats.get("SHO", 60) >= 80 and r < 0.75:
            return "lejano"
        return "rebote" if r < 0.5 else "lejano"

    def _probs_tiro(self, eq: int, tirador: EnCancha, calidad: float = 1.0, penal: bool = False):
        """(probabilidad de ir al arco, probabilidad de gol si va al arco, arquero rival)."""
        arquero = self.arquero(1 - eq)
        sho = tirador.stat("SHO")
        gk = arquero.stat("OVR") if arquero else 20
        if penal:
            return 0.82, min(0.95, max(0.08, 0.9 * (sho / max(gk, 1)) ** 1.6)), arquero
        calidad *= self._t(eq, "calidad")
        raiz = calidad ** 0.5
        p_puerta = min(max(0.7 * raiz, 0.15), max(0.15, (0.36 + (sho - 70) * 0.008) * raiz))
        p_gol = min(0.95, max(0.08, 0.26 * calidad * (sho / max(gk, 1)) ** 1.6))
        return p_puerta, p_gol, arquero

    def _tiro(self, eq: int, tirador: EnCancha, asistente: EnCancha | None, penal: bool = False, jugada: str = "penal",
              calidad: float = 1.0):
        p_puerta, p_gol, _ = self._probs_tiro(eq, tirador, calidad, penal)
        if self.rng.random() > p_puerta:
            if not penal and self.rng.random() < 0.07:
                resultado = "palo"
            elif not penal and self.rng.random() < 0.3:
                resultado = "corner"
            else:
                resultado = "desviado"
        else:
            resultado = "gol" if self.rng.random() < p_gol else "atajada"
        self._registrar_tiro(eq, tirador, asistente, resultado, penal, jugada)

    def _registrar_tiro(self, eq: int, tirador: EnCancha, asistente: EnCancha | None, resultado: str,
                        penal: bool = False, jugada: str = "penal", extra: dict | None = None):
        rival = 1 - eq
        asis = asistente.nombre if asistente and not penal else ""
        extra = extra or {}
        self.est[eq]["tiros"] += 1
        tirador.tiros += 1
        arquero = self.arquero(rival)
        if resultado == "palo":
            self._evento("palo", eq, tirador.nombre, jugada=jugada, asistente=asis, penal=penal, **extra)
            return
        if resultado in ("corner", "desviado"):
            if resultado == "corner":
                self.est[eq]["corners"] += 1
            self._evento("desviado", eq, tirador.nombre, corner=resultado == "corner", jugada=jugada, penal=penal,
                         asistente=asis, **extra)
            return
        self.est[eq]["a_puerta"] += 1
        tirador.a_puerta += 1
        if resultado == "gol":
            self.goles[eq] += 1
            tirador.goles += 1
            if asistente and not penal:
                asistente.asistencias += 1
            self._evento(
                "gol", eq, tirador.nombre,
                asistente=asis,
                penal=penal,
                jugada=jugada,
                golazo=not penal and tirador.stat("SHO") > 80 and self.rng.random() < 0.25,
                goles_jugador=tirador.goles,
                portero=arquero.nombre if arquero else "",
                **extra,
            )
        else:
            if arquero:
                arquero.atajadas += 1
            self._evento("atajada", rival, arquero.nombre if arquero else "", tirador=tirador.nombre, penal=penal,
                         jugada=jugada, asistente=asis, **extra)

    def _falta(self, eq_posesion: int):
        infractor_eq = 1 - eq_posesion if self.rng.random() < 0.72 else eq_posesion
        victima_eq = 1 - infractor_eq
        activos = [j for j in self._activos(infractor_eq) if not j.es_arquero]
        if not activos:
            return
        peso = {"DEF": 1.0, "MED": 0.85, "DEL": 0.4}
        infractor = self._elegir(
            activos,
            lambda j: peso.get(j.linea, 0.3) * (140 - j.jugador.carta.stats.get("DEF", 50)) * (0.5 if j.amarillas else 1),
        )
        infractor.faltas += 1
        self.est[infractor_eq]["faltas"] += 1

        # quien ya tiene amarilla se cuida más
        p_amarilla = 0.06 if infractor.amarillas else 0.15
        r = self.rng.random()
        if r < 0.003:
            self._expulsar(infractor_eq, infractor, directa=True)
        elif r < p_amarilla:
            infractor.amarillas += 1
            self.est[infractor_eq]["amarillas"] += 1
            self.tarjetas.append({"equipo": infractor_eq, "jugador": infractor.nombre, "id": infractor.jugador.id, "tipo": "amarilla"})
            if infractor.amarillas >= 2:
                self._expulsar(infractor_eq, infractor, directa=False)
            else:
                self._evento("amarilla", infractor_eq, infractor.nombre)
        else:
            self._evento("falta", infractor_eq, infractor.nombre)

        # penal: falta del equipo que defiende, a veces dentro del área
        if infractor_eq != eq_posesion and self.rng.random() < 0.016:
            atacantes = [j for j in self._activos(victima_eq) if not j.es_arquero]
            if atacantes:
                pateador = max(atacantes, key=lambda j: j.stat("SHO"))
                self._evento("penal", victima_eq, pateador.nombre)
                if self.interactivo is not None:
                    arquero = self.arquero(infractor_eq)
                    ref = self._pendiente(("penal", victima_eq, pateador))
                    self._pausas.append({"tipo": "penal", "ref": ref, "patea": victima_eq == self.interactivo,
                                         "pateador": pateador.nombre, "arquero": arquero.nombre if arquero else "",
                                         "minuto": self.minuto, "tiempo": self.tiempo, "segundos": 7})
                else:
                    self._tiro(victima_eq, pateador, None, penal=True)

    def _expulsar(self, eq: int, j: EnCancha, directa: bool):
        self.est[eq]["rojas"] += 1
        self.tarjetas.append({"equipo": eq, "jugador": j.nombre, "id": j.jugador.id, "tipo": "roja"})
        self._evento("roja", eq, j.nombre, directa=directa)
        self._sacar(eq, j, "roja")
        if eq == self.interactivo:
            self._pausas.append({"tipo": "roja", "jugador": j.nombre, "id": j.jugador.id, "puesto": j.puesto, "slot": j.slot,
                                 "minuto": self.minuto, "tiempo": self.tiempo})

    def _lesion(self, eq: int):
        activos = self._activos(eq)
        lesionado = self._elegir(
            activos, lambda j: (110 - j.jugador.carta.stats.get("PHY", 60)) * (1.5 - j.energia / 100)
        )
        dias = self.rng.choices([1, 3, 7, 14, 30], weights=[35, 30, 20, 10, 5])[0]
        self.lesiones.append({"equipo": eq, "jugador": lesionado.nombre, "id": lesionado.jugador.id, "dias": dias})
        self._evento("lesion", eq, lesionado.nombre, dias=dias)
        self._sacar(eq, lesionado, "lesion")

    def _cambios_tacticos(self, eq: int):
        if eq == self.interactivo:
            return  # tus cambios los haces tú (entretiempo y pausas); solo las lesiones cambian solas
        if not (60 <= self.minuto <= 85) or not self.banca[eq] or self.cambios[eq] >= MAX_CAMBIOS:
            return
        cansados = [j for j in self._activos(eq) if not j.es_arquero and j.energia < 68]
        if cansados and self.rng.random() < 0.12:
            self._sacar(eq, min(cansados, key=lambda j: j.energia), "tactico")

    # --- partido ----------------------------------------------------------

    def _minuto(self):
        self.minuto += 1
        for eq in (0, 1):
            factor = self._t(eq, "energia")
            for j in self._activos(eq):
                j.gastar_energia(factor)
                j.minutos += 1

        c0, c1 = self.control(0) ** 3, self.control(1) ** 3
        eq = 0 if self.rng.random() < c0 / (c0 + c1) else 1
        self.est[eq]["posesion"] += 1

        rel = self.ataque(eq) / max(self.defensa(1 - eq), 1)
        p_ocasion = min(0.6, max(0.06, 0.27 * rel ** 1.25))
        esperando = False
        if self.rng.random() < p_ocasion:
            esperando = self._ocasion(eq)
        p_falta = 0.26 * (0.72 * self._t(1 - eq, "faltas") + 0.28 * self._t(eq, "faltas"))
        if self.rng.random() < p_falta and not esperando:
            self._falta(eq)
        for e in (0, 1):
            if self.rng.random() < 0.0018:
                self._lesion(e)
            self._cambios_tacticos(e)
            self._tactica_bot(e)
        pg, pe = self.prob_victoria()
        self.posesion_min.append((self.tiempo, self.minuto, eq, pg, pe))

    def _tactica_bot(self, eq: int):
        """Los bots también ajustan: si ganan se cierran, si pierden van a buscarlo."""
        if eq == self.interactivo or self.tiempo != 2 or self.minuto not in (60, 75):
            return
        dif = self.goles[eq] - self.goles[1 - eq]
        self._poner_tactica(eq, "cuidar" if dif >= 1 else "presion" if dif < 0 else "normal")

    def _poner_tactica(self, eq: int, tactica: str):
        if tactica not in TACTICAS or self.equipos[eq].tactica == tactica:
            return
        self.equipos[eq].tactica = tactica
        self.cambios_tactica.append({"equipo": eq, "tactica": tactica, "tiempo": self.tiempo, "minuto": self.minuto,
                                     "marcador": list(self.goles)})
        self._evento("tactica", eq, "", tactica=tactica)

    def _ritmo(self, eq: int) -> float:
        """Goles esperados por minuto del equipo, con lo que hay ahora en cancha."""
        c0, c1 = self.control(eq) ** 3, self.control(1 - eq) ** 3
        pos = c0 / max(c0 + c1, 1e-9)
        rel = self.ataque(eq) / max(self.defensa(1 - eq), 1)
        p_oc = min(0.6, max(0.06, 0.27 * rel ** 1.25))
        tiradores = sorted((j for j in self._activos(eq) if not j.es_arquero), key=lambda j: -j.stat("SHO"))[:4]
        if not tiradores:
            return 0.0
        probs = [self._probs_tiro(eq, j) for j in tiradores]
        p_gol = sum(a * b for a, b, _ in probs) / len(probs)
        return pos * p_oc * p_gol

    def prob_victoria(self) -> tuple[int, int]:
        """(% de que gane el local, % de empate) según el marcador y lo que queda."""
        resto = (max(0, 45 - self.minuto) + 48) if self.tiempo == 1 else max(0.3, 93 - self.minuto)
        p0, p1 = _poisson(self._ritmo(0) * resto), _poisson(self._ritmo(1) * resto)
        g0, g1 = self.goles
        gana = sum(a * b for i, a in enumerate(p0) for k, b in enumerate(p1) if g0 + i > g1 + k)
        empate = sum(a * b for i, a in enumerate(p0) for k, b in enumerate(p1) if g0 + i == g1 + k)
        return round(100 * gana), round(100 * empate)

    def correr(self, interactivo: int | None = None):
        """Generador que juega el partido.

        Si `interactivo` es 0 o 1, se detiene (yield) en el descanso y cuando expulsan a un
        jugador de ese equipo. Se continúa con `gen.send(decision)`; al terminar, el
        Resultado viene en StopIteration.value. Sin interactivo no hay pausas.
        """
        self.interactivo = interactivo
        self.fuerza_inicial = [self.control(e) + self.ataque(e) + self.defensa(e) for e in (0, 1)]
        self._evento("inicio")
        for tiempo, fin in ((1, 45), (2, 90)):
            self.tiempo = tiempo
            adicion = self.rng.randint(1, 4) if tiempo == 1 else self.rng.randint(2, 6)
            while self.minuto < fin:
                self._minuto()
                self._intervenir()
                yield from self._atender_pausas()
            self._evento("adicion", minutos=adicion)
            while self.minuto < fin + adicion:
                self._minuto()
                self._intervenir()
                yield from self._atender_pausas()
            if tiempo == 1:
                self._evento("descanso")
                self.minuto = 45
                if interactivo is not None:
                    decision = yield {"tipo": "descanso", "minuto": 45, "tiempo": 1}
                    self.tiempo = 2
                    self._aplicar_descanso(interactivo, decision or {})
            else:
                self._evento("final")
        return self._resultado()

    def _intervenir(self):
        """Aplica lo que pediste en vivo al terminar este minuto (táctica o pausa para cambios)."""
        clave = (self.tiempo, self.minuto)
        acciones = self.intervenciones.get(clave)
        if not acciones or self.interactivo is None:
            return
        self.indice_intervencion[clave] = len(self.eventos)
        for a in acciones:
            if a.get("tipo") == "tactica":
                self._poner_tactica(self.interactivo, a.get("valor"))
            elif a.get("tipo") == "pausa":
                self._pausas.append({"tipo": "pausa", "minuto": self.minuto, "tiempo": self.tiempo, "segundos": 30})

    def _atender_pausas(self):
        while self._pausas:
            pausa = self._pausas.pop(0)
            if pausa["tipo"] == "roja" and not self.opciones_roja(self.interactivo, pausa):
                continue  # sin cambios ni banca: no hay nada que decidir
            decision = (yield pausa) or {}
            if pausa["tipo"] == "roja":
                self._aplicar_roja(self.interactivo, pausa, decision)
            elif pausa["tipo"] == "ocasion":
                self._resolver_ocasion(pausa, decision)
            elif pausa["tipo"] == "penal":
                self._resolver_penal(pausa, decision)
            else:
                self._aplicar_descanso(self.interactivo, decision)

    def jugar(self) -> Resultado:
        gen = self.correr()
        try:
            while True:
                next(gen)
        except StopIteration as fin:
            return fin.value

    # --- decisiones del equipo interactivo ------------------------------

    def estado(self, eq: int) -> dict:
        """Jugadores en cancha y en la banca (para la interfaz de cambios)."""
        def ficha(j: Jugador) -> dict:
            c = j.carta
            return {"id": j.id, "nombre": j.nombre, "pos": c.posicion, "ovr": c.ovr, "nivel": c.nivel,
                    "club": c.club, "nacion": c.nacion}
        return {
            "cancha": [{**ficha(e.jugador), "puesto": e.puesto, "slot": e.slot, "energia": round(e.energia),
                        "amarillas": e.amarillas, "goles": e.goles, "asistencias": e.asistencias}
                       for e in self._activos(eq)],
            # quienes ya salieron (expulsados, lesionados, cambiados) y el lugar que dejaron
            "fuera": [{"id": e.jugador.id, "nombre": e.nombre, "slot": e.slot, "motivo": e.salida,
                       "amarillas": e.amarillas} for e in self.usados[eq] if not e.activo],
            "banca": [ficha(j) for j in self.banca[eq]],
            "cambios": MAX_CAMBIOS - self.cambios[eq],
            "formacion": self.equipos[eq].formacion,
            "mentalidad": self.equipos[eq].mentalidad,
            "tactica": self.equipos[eq].tactica,
        }

    # --- momentos clave ---------------------------------------------------

    def _receptor(self, eq: int, tirador: EnCancha) -> EnCancha | None:
        otros = [j for j in self._activos(eq) if j is not tirador and j.linea in ("DEL", "MED")]
        return max(otros, key=lambda j: j.stat("SHO"), default=None)

    def _defensor(self, eq: int) -> EnCancha | None:
        rivales = [j for j in self._activos(1 - eq) if not j.es_arquero]
        defensas = [j for j in rivales if j.linea == "DEF"] or rivales
        return max(defensas, key=lambda j: j.stat("DEF"), default=None)

    @staticmethod
    def _p_pase(tirador: EnCancha) -> float:
        return min(0.9, max(0.35, 0.5 + (tirador.stat("PAS") - 65) * 0.012))

    @staticmethod
    def _p_regate(tirador: EnCancha, defensor: EnCancha) -> float:
        return min(0.8, max(0.2, 0.45 + (tirador.stat("DRI") - defensor.stat("DEF")) * 0.015))

    def opciones_ocasion(self, pausa: dict) -> dict:
        """Las 3 jugadas posibles con su probabilidad real de terminar en gol."""
        _, eq, tirador, asistente, _ = self._pendientes[pausa["ref"]]
        receptor, defensor = self._receptor(eq, tirador), self._defensor(eq)
        a, b, arquero = self._probs_tiro(eq, tirador, CALIDAD_MOMENTO["tirar"])
        ops = [{"clave": "tirar", "titulo": "Rematar", "detalle": f"{tirador.nombre} le pega al arco",
                "prob": round(100 * a * b)}]
        if receptor:
            pase = self._p_pase(tirador)
            a2, b2, _ = self._probs_tiro(eq, receptor, CALIDAD_MOMENTO["pasar"])
            ops.append({"clave": "pasar", "titulo": "Pasarla", "detalle": f"Pase a {receptor.nombre}, que entra más solo",
                        "exito": round(100 * pase), "prob": round(100 * pase * a2 * b2)})
        if defensor:
            regate = self._p_regate(tirador, defensor)
            a3, b3, _ = self._probs_tiro(eq, tirador, CALIDAD_MOMENTO["gambetear"])
            ops.append({"clave": "gambetear", "titulo": "Encarar", "detalle": f"{tirador.nombre} encara a {defensor.nombre}",
                        "exito": round(100 * regate), "prob": round(100 * regate * a3 * b3)})
        c = tirador.jugador.carta
        return {"tirador": {"id": tirador.jugador.id, "nombre": tirador.nombre, "pos": c.posicion, "ovr": c.ovr,
                            "nivel": c.nivel, "club": c.club},
                "arquero": arquero.nombre if arquero else "", "opciones": ops}

    def _resolver_ocasion(self, pausa: dict, decision: dict):
        _, eq, tirador, asistente, jugada = self._pendientes.pop(pausa["ref"])
        eleccion = decision.get("eleccion") if decision.get("eleccion") in CALIDAD_MOMENTO else "tirar"
        if not tirador.activo:
            return
        antes, exito = self.goles[eq], True
        receptor, defensor = self._receptor(eq, tirador), self._defensor(eq)
        if eleccion == "pasar" and receptor:
            exito = self.rng.random() < self._p_pase(tirador)
            if exito:
                self._tiro(eq, receptor, tirador, jugada="pase_filtrado", calidad=CALIDAD_MOMENTO["pasar"])
            else:
                self._evento("perdida", eq, tirador.nombre, otro=receptor.nombre, como="pase")
        elif eleccion == "gambetear" and defensor:
            exito = self.rng.random() < self._p_regate(tirador, defensor)
            if exito:
                self._tiro(eq, tirador, None, jugada="individual", calidad=CALIDAD_MOMENTO["gambetear"])
            else:
                self._evento("perdida", eq, tirador.nombre, otro=defensor.nombre, como="gambeta")
        else:
            eleccion = "tirar"
            self._tiro(eq, tirador, asistente, jugada=jugada, calidad=CALIDAD_MOMENTO["tirar"])
        self.momentos.append({"eleccion": eleccion, "exito": exito, "gol": self.goles[eq] > antes,
                              "minuto": self.minuto, "tiempo": self.tiempo})

    def _resolver_penal(self, pausa: dict, decision: dict):
        _, eq, pateador = self._pendientes.pop(pausa["ref"])
        pesos = [42, 16, 42]
        ia = self.rng.choices(LADOS_PENAL, weights=pesos)[0]
        tuyo = decision.get("lado") if decision.get("lado") in LADOS_PENAL else self.rng.choices(LADOS_PENAL, weights=pesos)[0]
        lado, adivina = (tuyo, ia) if eq == self.interactivo else (ia, tuyo)
        arquero = self.arquero(1 - eq)
        sho = pateador.stat("SHO")
        gk = arquero.stat("OVR") if arquero else 20
        afuera = 0.0 if lado == "centro" else min(0.2, max(0.03, 0.12 - (sho - 70) * 0.004))
        if self.rng.random() < afuera:
            resultado = "desviado"
        elif lado == adivina:
            p_atajar = 0.85 if lado == "centro" else min(0.75, max(0.3, 0.55 + (gk - sho) * 0.01))
            resultado = "atajada" if self.rng.random() < p_atajar else "gol"
        else:
            resultado = "gol"
        self._registrar_tiro(eq, pateador, None, resultado, penal=True, jugada="penal",
                             extra={"lado": lado, "adivina": adivina})
        if eq == self.interactivo:
            self.momentos.append({"eleccion": "penal", "exito": resultado == "gol", "gol": resultado == "gol",
                                  "minuto": self.minuto, "tiempo": self.tiempo})
        else:
            self.momentos.append({"eleccion": "atajar_penal", "exito": resultado != "gol", "gol": False,
                                  "minuto": self.minuto, "tiempo": self.tiempo})

    def opciones_roja(self, eq: int, pausa: dict) -> list[dict]:
        """Hasta 2 suplentes para cubrir el puesto del expulsado (sale el más prescindible)."""
        if self.cambios[eq] >= MAX_CAMBIOS or not self.banca[eq]:
            return []
        puesto = pausa["puesto"]
        activos = self._activos(eq)
        if puesto == "GK":
            sale = self.arquero(eq)  # el jugador de campo que se puso los guantes
        else:
            sale = None
            for ln in ("DEL", "MED", "DEF"):
                candidatos = [j for j in activos if j.linea == ln and ln != linea(puesto)]
                if candidatos:
                    sale = min(candidatos, key=lambda j: j.stat("OVR"))
                    break
        if sale is None:
            return []
        entran = sorted(self.banca[eq], key=lambda j: -j.carta.ovr * afinidad(j.carta.posicion, puesto))[:2]
        return [{"entra": j.id, "entra_nombre": j.nombre, "entra_pos": j.carta.posicion, "entra_ovr": j.carta.ovr,
                 "entra_nivel": j.carta.nivel, "entra_club": j.carta.club,
                 "afinidad": round(100 * afinidad(j.carta.posicion, puesto)),
                 "sale": sale.jugador.id, "sale_nombre": sale.nombre, "sale_puesto": sale.puesto, "puesto": puesto}
                for j in entran]

    def _cambio(self, eq: int, sale_id, entra_id, puesto: str | None = None, motivo: str = "decision",
                slot: int | None = None) -> bool:
        if self.cambios[eq] >= MAX_CAMBIOS:
            return False
        sale = next((j for j in self._activos(eq) if j.jugador.id == sale_id), None)
        entra = next((j for j in self.banca[eq] if j.id == entra_id), None)
        if not sale or not entra:
            return False
        sale.activo = False
        sale.salida = motivo
        self.banca[eq].remove(entra)
        nuevo = EnCancha(entra, puesto or sale.puesto, slot=sale.slot if slot is None else slot)
        self.cancha[eq].append(nuevo)
        self.usados[eq].append(nuevo)
        self.cambios[eq] += 1
        self._evento("cambio", eq, entra.nombre, sale=sale.nombre, motivo=motivo)
        return True

    def _aplicar_roja(self, eq: int, pausa: dict, decision: dict):
        if decision.get("entra") and decision.get("sale"):
            self._cambio(eq, decision["sale"], decision["entra"], pausa["puesto"], motivo="tras_roja",
                         slot=pausa.get("slot"))

    def _aplicar_descanso(self, eq: int, decision: dict):
        if decision.get("mentalidad") in MENTALIDADES:
            self.equipos[eq].mentalidad = decision["mentalidad"]
        if decision.get("tactica") in TACTICAS:
            self._poner_tactica(eq, decision["tactica"])
        for c in decision.get("cambios", [])[:MAX_CAMBIOS]:
            self._cambio(eq, c.get("sale"), c.get("entra"))

    def parcial(self) -> "Resultado":
        """Resultado con lo jugado hasta ahora (no modifica la simulación)."""
        return self._resultado()

    def _resultado(self) -> Resultado:
        total = sum(e["posesion"] for e in self.est) or 1
        est = [dict(e, posesion=round(100 * e["posesion"] / total)) for e in self.est]

        mejor = (-1, "", 0.0)
        for eq in (0, 1):
            ganador = self.goles[eq] > self.goles[1 - eq]
            valla = self.goles[1 - eq] == 0
            for j in self.usados[eq]:
                if j.minutos == 0:
                    continue
                nota = 6.0 + 1.2 * j.goles + 0.8 * j.asistencias + 0.15 * j.a_puerta + 0.35 * j.atajadas
                nota += 0.3 if ganador else 0
                nota += 0.5 if valla and j.linea in ("POR", "DEF") else 0
                nota -= 0.3 * min(j.amarillas, 1) + (1.5 if not j.activo and j.amarillas >= 2 else 0)
                nota = round(min(10.0, nota), 1)
                if nota > mejor[2]:
                    mejor = (eq, j.nombre, nota)

        razones = [self._razones(e, est) for e in (0, 1)]
        return Resultado(
            razones=razones,
            equipos=(self.equipos[0].nombre, self.equipos[1].nombre),
            goles=list(self.goles),
            eventos=list(self.eventos),
            estadisticas=est,
            jugadores=self.usados,
            mvp=mejor,
            lesiones=self.lesiones,
            # en amistosos las amarillas no se acumulan (rojas y lesiones sí)
            tarjetas=[t for t in self.tarjetas if self.tipo != "amistoso" or t["tipo"] == "roja"],
            tipo=self.tipo,
        )


def _plural(n: int, uno: str, varios: str) -> str:
    return f"{n} {uno if n == 1 else varios}"


def _razones_de(sim: "Simulacion", eq: int, est: list[dict]) -> list[list[str]]:
    """Las claves del partido desde el punto de vista del equipo `eq` (icono, texto), máximo 5."""
    r: list[list[str]] = []
    rival = 1 - eq
    for e, quien in ((eq, "Jugaste"), (rival, "El rival jugó")):
        roja = next((ev for ev in sim.eventos if ev.tipo == "roja" and ev.equipo == e), None)
        if roja:
            r.append(["🟥", f"{quien} con 10 desde el {roja.minuto_texto}"])
    if eq == sim.interactivo and sim.momentos:
        jugadas = [m for m in sim.momentos if m["eleccion"] not in ("penal", "atajar_penal")]
        if jugadas:
            goles = sum(m["gol"] for m in jugadas)
            r.append(["🎯", f"Momentos clave: {_plural(goles, 'gol', 'goles')} en {_plural(len(jugadas), 'decisión', 'decisiones')}"])
        for m in sim.momentos:
            if m["eleccion"] == "penal":
                r.append(["🥅", "Convertiste tu penal" if m["gol"] else "Fallaste el penal"])
            elif m["eleccion"] == "atajar_penal":
                r.append(["🧤", "¡Adivinaste y atajaste el penal!" if m["exito"] else "Te convirtieron el penal"])
    cambios = [c for c in sim.cambios_tactica if c["equipo"] == eq]
    if cambios:
        c = cambios[-1]
        gf = sim.goles[eq] - c["marcador"][eq]
        gc = sim.goles[rival] - c["marcador"][rival]
        r.append(["🧠", f"Con «{TACTICAS[c['tactica']]['nombre']}» desde el {c['minuto']}' el parcial fue {gf}-{gc}"])
    pos = est[eq]["posesion"]
    if pos >= 57:
        r.append(["📊", f"Dominaste la pelota ({pos}%): tu mediocampo controló el partido"])
    elif pos <= 43:
        r.append(["📊", f"El rival tuvo la pelota ({100 - pos}%): su mediocampo fue superior"])
    ap, g = est[eq]["a_puerta"], sim.goles[eq]
    if ap >= 5 and g <= 1:
        r.append(["😩", f"Perdonaste: {_plural(ap, 'tiro', 'tiros')} al arco y solo {_plural(g, 'gol', 'goles')}"])
    elif g >= 2 and g * 2 >= ap:
        r.append(["🔥", f"Fuiste letal: {_plural(g, 'gol', 'goles')} con {_plural(ap, 'tiro', 'tiros')} al arco"])
    for e, texto in ((rival, "El arquero rival, {n}, atajó {a}"), (eq, "Tu arquero {n} te salvó con {a} atajadas")):
        arq = max((j for j in sim.usados[e] if j.puesto == "GK"), key=lambda j: j.atajadas, default=None)
        if arq and arq.atajadas >= 4:
            r.append(["🧤", texto.format(n=arq.nombre, a=arq.atajadas)])
    cansados = [j.nombre for j in sim._activos(eq) if not j.es_arquero and j.energia < 40]
    if cansados:
        r.append(["🔋", f"{', '.join(cansados[:2])} {'terminó' if len(cansados) == 1 else 'terminaron'} sin piernas: haz cambios antes"])
    for j in sim._activos(eq):
        af = afinidad(j.jugador.carta.posicion, j.puesto)
        if af < 0.85 and j.minutos >= 30:
            r.append(["📍", f"{j.nombre} jugó fuera de posición (rinde {round(100 * af)}%)"])
            break
    f = sim.fuerza_inicial[eq] / max(sim.fuerza_inicial[rival], 1e-9)
    if f < 0.93:
        r.append(["⚖️", "En el papel el rival era superior"])
    elif f > 1.07:
        r.append(["⚖️", "En el papel eras superior"])
    return r[:5]


Simulacion._razones = lambda self, eq, est: _razones_de(self, eq, est)


def simular(local: Equipo, visita: Equipo, tipo: str = "amistoso", semilla: int | None = None) -> Resultado:
    return Simulacion(local, visita, tipo, semilla).jugar()
