"""Lógica de una partida local: tu club juega la liga contra clubes bot.

No depende de la interfaz: la usan la web (web/app.py), los tests y el script
de calibración (scripts/simular_carrera.py).

Reglas de la versión de prueba:
- Pirámide de 3 divisiones (Liga Bronce, Plata y Oro) con los clubes reales de todas las
  ligas descargadas, ordenados por fuerza. Tu club empieza en la Liga Bronce.
- Cada división se juega ida y vuelta. Al final de la temporada suben los 2 primeros y
  bajan los 2 últimos de cada división. Las divisiones de arriba pagan más.
- Los bots usan su plantel real, eligen la formación que mejor les calza y ajustan
  la mentalidad según la fuerza del rival.
- Lesiones y suspensiones duran fechas: roja = 1 fecha, 5 amarillas = 1 fecha.
- Ganas monedas por partido y por posición final; con ellas compras sobres.
"""
from __future__ import annotations

import csv
import json
import random
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from juego import economia
from juego.bd import RUTA_POR_DEFECTO, conectar
from models.carta import STATS, Carta, nivel_por_ovr
from juego.formaciones import factor_quimica, quimica
from juego.identidad import escudo_por_defecto, generar_bots
DIVISIONES = ["Liga Bronce", "Liga Plata", "Liga Oro"]
CLAVES_DIVISION = ["bronce", "plata", "oro"]
TAMANO_MAXIMO_DIVISION = 16
MAX_ALINEACIONES = 5
from partidos.motor import (ESPERA_TACTICA, MAX_CAMBIOS, PAUSAS_TACTICAS, TACTICAS, FORMACIONES, MENTALIDADES, Equipo, Jugador, Simulacion, afinidad, armar_equipo, linea,
                            simular)
from partidos.narrador import Narrador

# Partidos en vivo en curso (memoria del proceso). Si se pierden (p. ej. al reiniciar el
# servidor), se reconstruyen repitiendo la simulación con la misma semilla y decisiones.
_SESIONES: dict[tuple, dict] = {}
MERCADO_ACTIVAS = 250      # publicaciones en venta a la vez
MERCADO_DURACION = 3       # fechas que dura una publicación (como máximo)

ESTADIOS_JSON = "data/estadios.json"         # estadios reales (scraper/estadios.py)
CATALOGOS = "data/cartas_liga_*_2026.csv"   # todas las ligas descargadas (sobres y mercado las mezclan)
PLANTEL_INICIAL = {"POR": 2, "DEF": 6, "MED": 6, "DEL": 4}
# El plantel inicial sale de la liga elegida, con OVR alrededor de la media del club más débil
RANGO_INICIAL = (-6, 3)         # respecto de esa media
SUPLENTES = 7
AMARILLAS_SUSPENSION = 5
PLANTEL_MINIMO = 16             # no se puede vender por debajo de esto
DIAS_POR_FECHA = 7              # para convertir días de lesión en fechas


class ErrorJuego(Exception):
    """Acción inválida del jugador (se muestra tal cual en la interfaz)."""


@dataclass
class FichaJugador:
    """Una carta de un plantel, con su estado en la temporada."""

    pid: int            # id en la tabla plantilla
    carta_id: int
    carta: Carta
    puesto: int | None
    lesion: int
    suspension: int
    amarillas: int
    partidos: int
    goles: int
    asistencias: int
    nivel: int = 1          # mejora con cartas repetidas (+1 OVR y atributos por nivel)
    ovr_base: int = 0

    @property
    def estado(self) -> str:
        if self.lesion:
            return "lesionado"
        if self.suspension:
            return "suspendido"
        return "disponible"

    @property
    def disponible(self) -> bool:
        return self.estado == "disponible"

    def jugador(self) -> Jugador:
        return Jugador(self.carta, estado=self.estado, id=self.pid)


def _sin_tildes(texto: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def _carta(fila: sqlite3.Row) -> Carta:
    return Carta(
        nombre=fila["nombre"], alias=fila["alias"], posicion=fila["posicion"], ovr=fila["ovr"],
        stats={s: fila[s.lower()] for s in STATS}, nacion=fila["nacion"], club=fila["club"],
        liga=fila["liga"], precio=fila["precio"],
    )


def fuerza(jugadores: list[Jugador], formacion: str | None = None) -> float:
    """Media de OVR del mejor once (ajustada por afinidad con el puesto)."""
    formacion = formacion or "4-3-3"
    try:
        e = armar_equipo("x", jugadores, formacion)
    except ValueError:
        return 0.0
    puestos = FORMACIONES[formacion]
    return sum(j.carta.ovr * afinidad(j.carta.posicion, p) for j, p in zip(e.titulares, puestos)) / 11


def mejor_formacion(jugadores: list[Jugador]) -> str:
    return max(FORMACIONES, key=lambda f: fuerza(jugadores, f))


class Partida:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    @classmethod
    def abrir(cls, ruta: str | Path = RUTA_POR_DEFECTO) -> "Partida":
        return cls(conectar(ruta))

    # ------------------------------------------------------------ estado

    def _get(self, clave: str, defecto=None):
        fila = self.con.execute("SELECT valor FROM estado WHERE clave = ?", (clave,)).fetchone()
        return json.loads(fila["valor"]) if fila else defecto

    def _set(self, clave: str, valor):
        self.con.execute("INSERT OR REPLACE INTO estado VALUES (?, ?)", (clave, json.dumps(valor, ensure_ascii=False)))

    def borrar(self):
        """Elimina la partida completa (para empezar de cero)."""
        for tabla in ("objetos", "coleccionables", "alineaciones", "movimientos", "partidos", "plantilla", "equipos",
                      "cartas", "estado"):
            self.con.execute(f"DELETE FROM {tabla}")
        self.con.commit()

    @property
    def existe(self) -> bool:
        return self._get("usuario_id") is not None

    @property
    def usuario_id(self) -> int:
        return self._get("usuario_id")

    @property
    def monedas(self) -> int:
        return self._get("monedas", 0)

    @property
    def temporada(self) -> int:
        return self._get("temporada", 1)

    @property
    def fecha(self) -> int:
        return self._get("fecha", 1)

    @property
    def semilla(self) -> int:
        return self._get("semilla", 0)

    @property
    def total_fechas(self) -> int:
        n = self.con.execute("SELECT COUNT(*) FROM equipos WHERE division = ?", (self.division,)).fetchone()[0]
        return self.vueltas * (n - 1)

    @property
    def vueltas(self) -> int:
        return self._get("vueltas", 2)

    @property
    def n_divisiones(self) -> int:
        return self._get("divisiones", 1)

    def division_de(self, equipo_id: int) -> int:
        fila = self.con.execute("SELECT division FROM equipos WHERE id = ?", (equipo_id,)).fetchone()
        return fila["division"] if fila else 0

    @property
    def division(self) -> int:
        """División en la que juega tu club esta temporada."""
        return self.division_de(self.usuario_id)

    def nombre_division(self, division: int | None = None) -> str:
        d = self.division if division is None else division
        return DIVISIONES[d] if self.n_divisiones > 1 else "Liga"

    def clave_division(self, division: int | None = None) -> str:
        d = self.division if division is None else division
        return CLAVES_DIVISION[d] if self.n_divisiones > 1 else "bronce"

    def cupos(self, division: int | None = None) -> tuple[int, int]:
        """(cuántos suben, cuántos bajan) en la división."""
        if self.n_divisiones == 1:
            return 0, 0
        d = self.division if division is None else division
        n = self.con.execute("SELECT COUNT(*) FROM equipos WHERE division = ?", (d,)).fetchone()[0]
        mov = 2 if n >= 8 else 1
        return (mov if d < self.n_divisiones - 1 else 0), (mov if d > 0 else 0)

    @property
    def temporada_terminada(self) -> bool:
        return self.fecha > self.total_fechas

    @property
    def historial(self) -> list[dict]:
        return self._get("historial", [])

    def nombre_equipo(self, equipo_id: int) -> str:
        return self.con.execute("SELECT nombre FROM equipos WHERE id = ?", (equipo_id,)).fetchone()["nombre"]

    def equipo(self, equipo_id: int) -> sqlite3.Row:
        return self.con.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,)).fetchone()

    def _mover_monedas(self, monto: int, concepto: str):
        self._set("monedas", self.monedas + monto)
        self.con.execute("INSERT INTO movimientos (temporada, fecha, concepto, monto) VALUES (?, ?, ?, ?)",
                         (self.temporada, self.fecha, concepto, monto))

    def _rng(self, *partes) -> random.Random:
        return random.Random("-".join(str(p) for p in (self.semilla, *partes)))

    # ------------------------------------------------------------ crear

    def crear(self, nombre_club: str, semilla: int | None = None, catalogo: str | Path | None = None,
              divisiones: int = 3):
        """Crea la partida con los clubes de todos los catálogos (`catalogo`: CSV o patrón glob).

        Con 3 divisiones, los clubes se ordenan por fuerza y se reparten en Oro, Plata y
        Bronce (mismo tamaño, par); tu club ocupa el último cupo de la Bronce. Con 1
        división juegan todos y tu club toma el cupo del más débil.
        """
        import glob
        if self.existe:
            raise ErrorJuego("Ya hay una partida creada.")
        nombre_club = nombre_club.strip()[:40]
        if not nombre_club:
            raise ErrorJuego("Ponle un nombre a tu club.")
        semilla = semilla if semilla is not None else random.randrange(10**9)
        self._set("semilla", semilla)
        rng = random.Random(semilla)

        rutas = sorted(glob.glob(str(catalogo or CATALOGOS)))
        if not rutas:
            raise ErrorJuego("No hay catálogo de cartas en data/. Corre los scripts de scraper/ primero.")
        filas = []
        for ruta in rutas:
            with open(ruta, newline="", encoding="utf-8") as f:
                filas += list(csv.DictReader(f))
        if nombre_club.lower() in {f["Club"].lower() for f in filas}:
            raise ErrorJuego("Ese nombre ya lo usa un club real.")
        for f in filas:
            self.con.execute(
                "INSERT INTO cartas (nombre, alias, posicion, club, nacion, liga, ovr, pac, sho, pas, dri, def, phy, precio, edad)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f["Nombre"], f.get("Alias", ""), f["Posición"], f["Club"], f.get("Nación", ""), f.get("Liga", ""),
                 int(f["OVR"]), *(int(f[s]) for s in STATS), int(f.get("Precio") or 0), int(f.get("Edad") or 0)),
            )

        # todos los clubes reales, con su plantel
        clubes = [r["club"] for r in self.con.execute("SELECT DISTINCT club FROM cartas ORDER BY club")]
        for club in clubes:
            cur = self.con.execute("INSERT INTO equipos (nombre) VALUES (?)", (club,))
            self.con.execute("INSERT INTO plantilla (equipo_id, carta_id) SELECT ?, id FROM cartas WHERE club = ?",
                             (cur.lastrowid, club))
        fuerzas = {e["id"]: fuerza([f.jugador() for f in self.plantel(e["id"])]) for e in self._bots()}
        orden = sorted(fuerzas, key=lambda e: -fuerzas[e])

        tamano = min(TAMANO_MAXIMO_DIVISION, (len(clubes) + 1) // divisiones // 2 * 2)
        if divisiones > 1 and tamano >= 4:
            quedan = orden[: divisiones * tamano - 1]
            for d in range(divisiones):  # los más fuertes arriba (Oro)
                for eid in quedan[d * tamano:(d + 1) * tamano]:
                    self.con.execute("UPDATE equipos SET division = ? WHERE id = ?", (divisiones - 1 - d, eid))
            sobran = orden[divisiones * tamano - 1:]
        else:
            divisiones = 1
            sobran = orden[-1:] if len(clubes) % 2 == 0 else []
            if sobran:
                self._set("reemplaza", self.nombre_equipo(sobran[0]))
        for eid in sobran:  # quedan fuera de la competencia (sus cartas siguen en sobres y mercado)
            self.con.execute("DELETE FROM plantilla WHERE equipo_id = ?", (eid,))
            self.con.execute("DELETE FROM equipos WHERE id = ?", (eid,))
        self._set("divisiones", divisiones)

        # los rivales son clubes bot: nombre, escudo y estadio inventados (el plantel es el de un club real)
        bots = self._bots()
        identidades = generar_bots(len(bots), semilla, set(clubes) | {nombre_club})
        for e, ide in zip(bots, identidades):
            self.con.execute("UPDATE equipos SET nombre_real = nombre, nombre = ?, estadio = ?, escudo = ? WHERE id = ?",
                             (ide["nombre"], ide["estadio"], json.dumps(ide["escudo"]), e["id"]))
        if nombre_club.lower() in {i["nombre"].lower() for i in identidades}:
            raise ErrorJuego("Ese nombre ya lo usa otro club.")

        uid = self.con.execute(
            "INSERT INTO equipos (nombre, es_usuario, division, estadio, escudo) VALUES (?, 1, 0, ?, ?)",
            (nombre_club, f"Estadio {nombre_club}", json.dumps(escudo_por_defecto(nombre_club)))).lastrowid
        self._set("usuario_id", uid)

        # plantel inicial: alrededor de la fuerza del club más débil de tu división
        rivales = [fuerzas[r["id"]] for r in self.con.execute(
            "SELECT id FROM equipos WHERE division = 0 AND es_usuario = 0")]
        media = round(min(rivales)) if rivales else 63
        bajo, alto = media + RANGO_INICIAL[0], media + RANGO_INICIAL[1]
        for ln, cantidad in PLANTEL_INICIAL.items():
            for margen in range(0, 20, 2):  # si no alcanzan, se amplía el rango
                candidatos = [r["id"] for r in self.con.execute(
                    "SELECT id, posicion FROM cartas WHERE ovr BETWEEN ? AND ? ORDER BY id", (bajo - margen, alto + margen))
                    if linea(r["posicion"]) == ln]
                if len(candidatos) >= cantidad:
                    break
            for carta_id in rng.sample(candidatos, min(cantidad, len(candidatos))):
                self.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)", (uid, carta_id))

        self._set("vueltas", 2)
        self._set("monedas", 0)
        self._set("temporada", 1)
        self._set("fecha", 1)
        self._mover_monedas(economia.MONEDAS_INICIALES, "Monedas iniciales")
        self._asegurar_coleccionables()
        self._crear_fixture()
        self.alinear_auto()
        self.con.execute("INSERT INTO alineaciones (nombre, formacion, mentalidad, puestos) VALUES ('Titular', ?, ?, ?)",
                         (self.equipo(uid)["formacion"], "equilibrada", json.dumps(self._puestos_actuales())))
        self._set("alineacion_activa", self.con.execute("SELECT MAX(id) FROM alineaciones").fetchone()[0])
        self._set("ultima_carta_gratis", 0)
        self._fijar_objetivo()
        self.con.commit()

    def _bots(self) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM equipos WHERE es_usuario = 0").fetchall()

    def _crear_fixture(self):
        """Todos contra todos dentro de cada división (método del círculo); con 2 vueltas, ida y vuelta."""
        for d in range(self.n_divisiones):
            ids = [r["id"] for r in self.con.execute("SELECT id FROM equipos WHERE division = ? ORDER BY id", (d,))]
            if len(ids) >= 2:
                self._fixture_division(d, ids)

    def _fixture_division(self, division: int, ids: list[int]):
        self._rng("fixture", self.temporada, division).shuffle(ids)
        n = len(ids)
        rondas = []
        for r in range(n - 1):
            rondas.append([(ids[i], ids[n - 1 - i]) if (r + i) % 2 == 0 else (ids[n - 1 - i], ids[i]) for i in range(n // 2)])
            ids = [ids[0], ids[-1], *ids[1:-1]]
        if self.vueltas == 2:
            rondas += [[(b, a) for a, b in ronda] for ronda in rondas]
        for fecha, ronda in enumerate(rondas, start=1):
            for local, visita in ronda:
                self.con.execute("INSERT INTO partidos (temporada, fecha, division, local_id, visita_id) VALUES (?, ?, ?, ?, ?)",
                                 (self.temporada, fecha, division, local, visita))

    # ------------------------------------------------------------ planteles

    def plantel(self, equipo_id: int | None = None) -> list[FichaJugador]:
        equipo_id = equipo_id or self.usuario_id
        filas = self.con.execute(
            "SELECT p.id AS pid, p.carta_id, p.puesto, p.lesion, p.suspension, p.amarillas, p.partidos, p.goles,"
            " p.asistencias, p.nivel, c.* FROM plantilla p JOIN cartas c ON c.id = p.carta_id WHERE p.equipo_id = ?"
            " ORDER BY c.ovr + p.nivel DESC, p.id", (equipo_id,))
        salida = []
        for f in filas:
            carta, nivel = _carta(f), f["nivel"] or 1
            base = carta.ovr
            if nivel > 1:  # cada nivel de mejora: +1 a la media y a cada atributo
                carta.ovr += nivel - 1
                carta.stats = {k: min(99, v + nivel - 1) for k, v in carta.stats.items()}
            salida.append(FichaJugador(f["pid"], f["carta_id"], carta, f["puesto"], f["lesion"], f["suspension"],
                                       f["amarillas"], f["partidos"], f["goles"], f["asistencias"], nivel, base))
        return salida

    def alinear_auto(self, formacion: str | None = None):
        """Elige el mejor once disponible y los 7 suplentes, y los guarda."""
        uid = self.usuario_id
        formacion = formacion or self.equipo(uid)["formacion"]
        fichas = self.plantel(uid)
        e = armar_equipo("x", [f.jugador() for f in fichas if f.disponible], formacion)
        usados = {j.id for j in e.titulares}
        banca = self._banca([f.jugador() for f in fichas if f.disponible and f.pid not in usados])
        self.con.execute("UPDATE plantilla SET puesto = NULL WHERE equipo_id = ?", (uid,))
        for i, j in enumerate(e.titulares + banca):
            self.con.execute("UPDATE plantilla SET puesto = ? WHERE id = ?", (i, j.id))
        self.con.execute("UPDATE equipos SET formacion = ? WHERE id = ?", (formacion, uid))
        self._guardar_en_activa()
        self.con.commit()

    def guardar_alineacion(self, formacion: str, mentalidad: str, puestos: dict[int, int]):
        """`puestos` = {índice: pid}; 0-10 titulares, 11-17 suplentes. Los vacíos se completan al jugar."""
        if formacion not in FORMACIONES:
            raise ErrorJuego("Formación desconocida.")
        if mentalidad not in MENTALIDADES:
            raise ErrorJuego("Mentalidad desconocida.")
        uid = self.usuario_id
        propios = {f.pid for f in self.plantel(uid)}
        elegidos = [pid for pid in puestos.values() if pid]
        if len(elegidos) != len(set(elegidos)):
            raise ErrorJuego("Un jugador no puede ocupar dos puestos.")
        if not set(elegidos) <= propios:
            raise ErrorJuego("Ese jugador no es de tu plantel.")
        self.con.execute("UPDATE plantilla SET puesto = NULL WHERE equipo_id = ?", (uid,))
        for i, pid in puestos.items():
            if pid and 0 <= i < 11 + SUPLENTES:
                self.con.execute("UPDATE plantilla SET puesto = ? WHERE id = ?", (i, pid))
        self.con.execute("UPDATE equipos SET formacion = ?, mentalidad = ? WHERE id = ?", (formacion, mentalidad, uid))
        self._guardar_en_activa()
        self.con.commit()

    def _equipo_usuario(self) -> Equipo:
        uid = self.usuario_id
        datos = self.equipo(uid)
        puestos = FORMACIONES[datos["formacion"]]
        fichas = self.plantel(uid)
        titulares: list[Jugador | None] = [None] * 11
        for f in fichas:
            if f.puesto is not None and f.puesto < 11 and f.disponible and titulares[f.puesto] is None:
                titulares[f.puesto] = f.jugador()
        usados = {j.id for j in titulares if j}
        # suplentes elegidos (en su orden); si alguno no está disponible, se salta
        elegidos = [f.jugador() for f in sorted((f for f in fichas if f.puesto is not None and 11 <= f.puesto < 11 + SUPLENTES),
                                                key=lambda f: f.puesto)
                    if f.disponible and f.pid not in usados]
        ids_elegidos = {j.id for j in elegidos}
        otros = [f.jugador() for f in fichas if f.disponible and f.pid not in usados and f.pid not in ids_elegidos]
        libres = elegidos + otros
        # puestos vacíos del once (lesionados, suspendidos o sin elegir): entra el mejor disponible,
        # primero entre los suplentes elegidos
        for i in sorted(range(11), key=lambda i: puestos[i] != "GK"):
            if titulares[i] is None:
                if not libres:
                    libres = [f.jugador() for f in fichas if f.pid not in {j.id for j in titulares if j}]
                    for j in libres:
                        j.estado = "disponible"  # emergencia: juega aunque esté tocado
                candidatos = [j for j in libres if j.id in ids_elegidos] or libres
                mejor = max(candidatos, key=lambda j: j.carta.ovr * afinidad(j.carta.posicion, puestos[i]))
                titulares[i] = mejor
                libres.remove(mejor)
        q = quimica(datos["formacion"], [j.carta for j in titulares])
        for j, valor in zip(titulares, q["jugadores"]):
            j.quimica = factor_quimica(valor)
        # banca: los elegidos que quedan y, si faltan, se completa con los mejores
        banca = [j for j in libres if j.id in ids_elegidos][:SUPLENTES]
        if len(banca) < SUPLENTES:
            resto = [j for j in libres if j.id not in ids_elegidos]
            banca += self._banca(resto)[: SUPLENTES - len(banca)] if not any(j.carta.posicion == "GK" for j in banca) \
                else sorted(resto, key=lambda j: -j.carta.ovr)[: SUPLENTES - len(banca)]
        return Equipo(datos["nombre"], datos["formacion"], titulares, banca, datos["mentalidad"])

    @staticmethod
    def _banca(libres: list[Jugador]) -> list[Jugador]:
        libres = sorted(libres, key=lambda j: -j.carta.ovr)
        arquero = next((j for j in libres if j.carta.posicion == "GK"), None)
        banca = [arquero] if arquero else []
        banca += [j for j in libres if j is not arquero][: SUPLENTES - len(banca)]
        return banca

    def _equipo_bot(self, equipo_id: int, fuerza_rival: float) -> Equipo:
        datos = self.equipo(equipo_id)
        fichas = self.plantel(equipo_id)
        jugadores = [f.jugador() for f in fichas if f.disponible]
        if len(jugadores) < 11:  # emergencia
            jugadores = [Jugador(f.carta, id=f.pid) for f in fichas]
        formacion = mejor_formacion(jugadores)
        propia = fuerza(jugadores, formacion)
        mentalidad = "ofensiva" if propia > fuerza_rival + 3 else "defensiva" if propia < fuerza_rival - 3 else "equilibrada"
        e = armar_equipo(datos["nombre"], jugadores, formacion, suplentes=SUPLENTES)
        e.mentalidad = mentalidad
        return e

    def armar(self, equipo_id: int, fuerza_rival: float = 0) -> Equipo:
        if equipo_id == self.usuario_id:
            return self._equipo_usuario()
        return self._equipo_bot(equipo_id, fuerza_rival)

    def fuerza_equipo(self, equipo_id: int) -> float:
        if equipo_id == self.usuario_id:
            e = self._equipo_usuario()
            return sum(j.carta.ovr * afinidad(j.carta.posicion, p)
                       for j, p in zip(e.titulares, FORMACIONES[e.formacion])) / 11
        jugadores = [f.jugador() for f in self.plantel(equipo_id) if f.disponible]
        return fuerza(jugadores, mejor_formacion(jugadores)) if len(jugadores) >= 11 else 0.0

    # ------------------------------------------------------------ jugar

    def partidos_fecha(self, fecha: int | None = None, temporada: int | None = None,
                       division: int | None = None) -> list[sqlite3.Row]:
        """Partidos de la fecha (de todas las divisiones, o de una si se indica)."""
        extra, params = ("AND p.division = ?", (division,)) if division is not None else ("", ())
        return self.con.execute(
            "SELECT p.*, l.nombre AS local, v.nombre AS visita FROM partidos p"
            " JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visita_id"
            f" WHERE p.temporada = ? AND p.fecha = ? {extra} ORDER BY p.id",
            (temporada or self.temporada, fecha or self.fecha, *params)).fetchall()

    def proximo_partido(self) -> sqlite3.Row | None:
        if self.temporada_terminada:
            return None
        uid = self.usuario_id
        return next((p for p in self.partidos_fecha() if uid in (p["local_id"], p["visita_id"])), None)

    def partido(self, partido_id: int) -> sqlite3.Row | None:
        return self.con.execute(
            "SELECT p.*, l.nombre AS local, v.nombre AS visita FROM partidos p"
            " JOIN equipos l ON l.id = p.local_id JOIN equipos v ON v.id = p.visita_id WHERE p.id = ?",
            (partido_id,)).fetchone()

    def _preparar(self, p) -> tuple[Equipo, Equipo, int]:
        f_local, f_visita = self.fuerza_equipo(p["local_id"]), self.fuerza_equipo(p["visita_id"])
        local, visita = self.armar(p["local_id"], f_visita), self.armar(p["visita_id"], f_local)
        return local, visita, self._rng("partido", p["id"]).randrange(10**9)

    def _registrar(self, partido_id: int, res):
        self.con.execute("UPDATE partidos SET goles_local = ?, goles_visita = ?, jugado = 1 WHERE id = ?",
                         (res.goles[0], res.goles[1], partido_id))
        for lista in res.jugadores:
            for en in lista:
                if en.minutos and en.jugador.id:
                    self.con.execute(
                        "UPDATE plantilla SET partidos = partidos + 1, goles = goles + ?, asistencias = asistencias + ? WHERE id = ?",
                        (en.goles, en.asistencias, en.jugador.id))

    def _cerrar_fecha(self, resultados: list):
        # las sanciones vigentes se cumplieron en esta fecha; después se aplican las nuevas
        self.con.execute("UPDATE plantilla SET lesion = MAX(lesion - 1, 0), suspension = MAX(suspension - 1, 0)")
        for res in resultados:
            self._aplicar_sanciones(res)
        self._set("fecha", self.fecha + 1)
        if self.temporada_terminada:
            self._cerrar_temporada()
        self.con.commit()

    def jugar_fecha(self) -> int:
        """Juega toda la fecha sin pausas (simulación rápida). Devuelve el id del partido del usuario."""
        if self.temporada_terminada:
            raise ErrorJuego("La temporada terminó. Empieza una nueva.")
        if self.partido_en_vivo():
            raise ErrorJuego("Tienes un partido en curso.")
        uid = self.usuario_id
        resultados, partido_usuario = [], None
        for p in self.partidos_fecha():
            if p["jugado"]:
                continue
            local, visita, semilla = self._preparar(p)
            sim = Simulacion(local, visita, "liga", semilla)
            res = sim.jugar()
            self._registrar(p["id"], res)
            resultados.append(res)
            if uid in (p["local_id"], p["visita_id"]):
                partido_usuario = p["id"]
                self._guardar_detalle(p["id"], res, semilla, local, visita, sim.posesion_min)
                self._premiar(res, 0 if p["local_id"] == uid else 1)
        self._cerrar_fecha(resultados)
        return partido_usuario

    # ------------------------------------------------------------ partido en vivo

    def partido_en_vivo(self) -> dict | None:
        return self._get("vivo")

    def iniciar_partido(self) -> int:
        """Empieza tu partido de la fecha en modo en vivo (con pausas para decidir)."""
        vivo = self.partido_en_vivo()
        if vivo:
            return vivo["partido"]
        if self.temporada_terminada:
            raise ErrorJuego("La temporada terminó. Empieza una nueva.")
        p = self.proximo_partido()
        self._set("vivo", {"partido": p["id"], "decisiones": [], "intervenciones": []})
        self.con.commit()
        return p["id"]

    def _sesion(self) -> dict:
        vivo = self.partido_en_vivo()
        if not vivo:
            raise ErrorJuego("No hay un partido en curso.")
        clave = (self.semilla, vivo["partido"])
        ses = _SESIONES.get(clave)
        intervenciones = vivo.get("intervenciones", [])
        if ses and ses["n"] == len(vivo["decisiones"]) and ses["ni"] == len(intervenciones):
            return ses
        # reconstruir: misma semilla y mismas decisiones => mismo partido
        p = self.partido(vivo["partido"])
        local, visita, semilla = self._preparar(p)
        lado = 0 if p["local_id"] == self.usuario_id else 1
        sim = Simulacion(local, visita, p["tipo"] or "liga", semilla)
        sim.programar(intervenciones)
        ses = {"sim": sim, "gen": sim.correr(interactivo=lado), "lado": lado, "partido": p, "local": local,
               "visita": visita, "semilla": semilla, "pausa": None, "resultado": None, "n": 0,
               "ni": len(intervenciones)}
        self._continuar(ses, None, primero=True)
        for d in vivo["decisiones"]:
            self._continuar(ses, d)
        _SESIONES.clear()
        _SESIONES[clave] = ses
        return ses

    @staticmethod
    def _continuar(ses: dict, decision, primero: bool = False):
        try:
            ses["pausa"] = next(ses["gen"]) if primero else ses["gen"].send(decision)
        except StopIteration as fin:
            ses["pausa"], ses["resultado"] = None, fin.value
        if not primero:
            ses["n"] += 1

    def avanzar_partido(self, decision: dict | None = None, desde: int = 0, terminar: bool = False) -> dict:
        """Aplica la decisión de la pausa actual (si hay) y juega hasta la siguiente pausa o el final.

        Devuelve las líneas narradas desde el evento `desde`, la posesión minuto a minuto,
        la pausa pendiente (con opciones) y si el partido terminó. El partido se registra
        (tabla, premios, sanciones) recién cuando llega `terminar`: cuando terminas de verlo.
        """
        ses = self._sesion()
        if decision is not None and ses["pausa"] is not None:
            vivo = self.partido_en_vivo()
            vivo["decisiones"].append(decision)
            vivo["ultima"] = list(ses["sim"].posesion_min[-1][:2]) if ses["sim"].posesion_min else [1, 0]
            self._set("vivo", vivo)
            self._continuar(ses, decision)
            self.con.commit()
        if terminar:
            if ses["resultado"] is None:
                raise ErrorJuego("El partido todavía no termina.")
            pid = ses["partido"]["id"]
            self._finalizar_en_vivo(ses)
            return {"terminado": True, "partido": pid}
        return self._respuesta(ses, desde)

    def intervenir_partido(self, tiempo: int, minuto: int, tipo: str, valor: str | None = None) -> dict:
        """Táctica o pausa para cambios pedida en vivo, al final del minuto que estás viendo.

        El partido se vuelve a jugar desde el inicio con la misma semilla: hasta ese minuto
        todo queda igual y desde ahí cambia según lo que pediste.
        """
        ses = self._sesion()
        sim, lado = ses["sim"], ses["lado"]
        vivo = self.partido_en_vivo()
        inter = vivo.setdefault("intervenciones", [])
        clave = (int(tiempo), int(minuto))
        if clave not in {(x[0], x[1]) for x in sim.posesion_min}:
            raise ErrorJuego("Ese minuto todavía no se juega.")
        previas = [tuple(vivo.get("ultima") or (1, 0))] + [(i["t"], i["m"]) for i in inter]
        if clave <= max(previas):
            raise ErrorJuego("Espera al minuto siguiente.")
        if tipo == "pausa":
            usadas = sum(1 for i in inter if i["tipo"] == "pausa")
            if usadas >= PAUSAS_TACTICAS:
                raise ErrorJuego("Ya usaste tus pausas.")
            if sim.cambios[lado] >= MAX_CAMBIOS or not sim.banca[lado]:
                raise ErrorJuego("No te quedan cambios.")
        elif tipo == "tactica":
            if valor not in TACTICAS:
                raise ErrorJuego("Táctica desconocida.")
            if valor == sim.equipos[lado].tactica:
                raise ErrorJuego("Ya estás jugando así.")
            espera = self._espera_tactica(inter, clave)
            if espera:
                raise ErrorJuego(f"Puedes volver a cambiar la táctica en {espera}'.")
        else:
            raise ErrorJuego("Acción desconocida.")
        inter.append({"t": clave[0], "m": clave[1], "tipo": tipo, "valor": valor})
        self._set("vivo", vivo)
        self.con.commit()
        ses = self._sesion()  # se rehace con la intervención
        desde = ses["sim"].indice_intervencion.get(clave, len(ses["sim"].eventos))
        return self._respuesta(ses, desde)

    @staticmethod
    def _espera_tactica(inter: list[dict], clave: tuple[int, int]) -> int:
        """Minutos que faltan para poder cambiar otra vez la táctica (0 = ya se puede)."""
        absoluto = lambda t, m: min(m, 45) if t == 1 else max(m, 46)
        tacticas = [i for i in inter if i["tipo"] == "tactica"]
        if not tacticas:
            return 0
        ultima = tacticas[-1]
        return max(0, absoluto(ultima["t"], ultima["m"]) + ESPERA_TACTICA - absoluto(*clave))

    def _respuesta(self, ses: dict, desde: int) -> dict:
        sim, lado = ses["sim"], ses["lado"]
        parcial = ses["resultado"] or sim.parcial()
        lineas = Narrador(parcial, ses["semilla"] + desde).tramo(desde)
        pausa = None
        if ses["pausa"]:
            pausa = {k: v for k, v in ses["pausa"].items() if k != "ref"}
            if pausa["tipo"] in ("descanso", "roja", "pausa"):
                pausa["estado"] = self._estado_pausa(sim, lado, ses)
                pausa.setdefault("segundos", 60)
            if pausa["tipo"] == "roja":
                pausa["opciones"] = sim.opciones_roja(lado, ses["pausa"])
            if pausa["tipo"] == "ocasion":
                pausa.update(sim.opciones_ocasion(ses["pausa"]))
        vivo = self.partido_en_vivo() or {}
        inter = vivo.get("intervenciones", [])
        marcas = [tuple(vivo["ultima"])] if vivo.get("ultima") else []
        marcas += [(i["t"], i["m"]) for i in inter]
        tacticas = [i for i in inter if i["tipo"] == "tactica"]
        return {
            "partido": ses["partido"]["id"],
            "lineas": [l.a_dict() for l in lineas],
            "eventos": len(sim.eventos),
            "posesion": sim.posesion_min,
            "marcador": list(sim.goles),
            "pausa": pausa,
            "final": ses["resultado"] is not None,
            "lado": lado,
            "tactica": sim.equipos[lado].tactica,
            "tactica_rival": sim.equipos[1 - lado].tactica,
            "pausas_restantes": PAUSAS_TACTICAS - sum(1 for i in inter if i["tipo"] == "pausa"),
            "cambios_restantes": MAX_CAMBIOS - sim.cambios[lado] if sim.banca[lado] else 0,
            "ultima_tactica": [tacticas[-1]["t"], tacticas[-1]["m"]] if tacticas else None,
            "reanudar": list(max(marcas)) if marcas else None,  # al recargar: hasta dónde ya se vio
        }

    def alineaciones_vivo(self) -> list[dict]:
        """Once inicial de ambos equipos (en orden de la formación) para dibujarlos en la cancha."""
        ses = self._sesion()
        return [{"formacion": e.formacion, "jugadores": [j.nombre for j in e.titulares]} for e in (ses["local"], ses["visita"])]

    def _estado_pausa(self, sim, lado: int, ses: dict) -> dict:
        """Estado de los jugadores para la pausa, con las amarillas acumuladas en la temporada
        (en liga, una amarilla más puede dejar al jugador suspendido)."""
        est = sim.estado(lado)
        liga = sim.tipo != "amistoso"
        ids = [j["id"] for j in est["cancha"] + est["banca"] if j.get("id")]
        acum = {}
        if ids and liga:
            marcas = ",".join("?" * len(ids))
            acum = dict(self.con.execute(f"SELECT id, amarillas FROM plantilla WHERE id IN ({marcas})", ids).fetchall())
        for j in est["cancha"] + est["banca"]:
            total = acum.get(j.get("id"), 0) + j.get("amarillas", 0)
            j["acumuladas"] = total
            j["riesgo"] = liga and total == AMARILLAS_SUSPENSION - 1
        est["limite_amarillas"] = AMARILLAS_SUSPENSION
        return est

    def _finalizar_en_vivo(self, ses: dict):
        res, p = ses["resultado"], ses["partido"]
        if p["tipo"] == "amistoso":  # no cuenta para nada: ni tabla, ni sanciones, ni fecha
            self.con.execute("UPDATE partidos SET goles_local = ?, goles_visita = ?, jugado = 1 WHERE id = ?",
                             (res.goles[0], res.goles[1], p["id"]))
            self._guardar_detalle(p["id"], res, ses["semilla"], ses["local"], ses["visita"], ses["sim"].posesion_min)
            self.con.execute("DELETE FROM estado WHERE clave = 'vivo'")
            _SESIONES.pop((self.semilla, p["id"]), None)
            self.con.commit()
            return
        self._registrar(p["id"], res)
        self._guardar_detalle(p["id"], res, ses["semilla"], ses["local"], ses["visita"], ses["sim"].posesion_min)
        self._premiar(res, ses["lado"])
        resultados = [res]
        for otro in self.partidos_fecha():
            if otro["jugado"] or otro["id"] == p["id"]:
                continue
            local, visita, semilla = self._preparar(otro)
            r = simular(local, visita, tipo="liga", semilla=semilla)
            self._registrar(otro["id"], r)
            resultados.append(r)
        self.con.execute("DELETE FROM estado WHERE clave = 'vivo'")
        _SESIONES.pop((self.semilla, p["id"]), None)
        self._cerrar_fecha(resultados)

    def _guardar_detalle(self, partido_id: int, res, semilla: int, local: Equipo, visita: Equipo, posesion=()):
        lineas = Narrador(res, semilla).narrar()
        fila = self.partido(partido_id)
        lado = 0 if fila and fila["local_id"] == self.usuario_id else 1
        detalle = {
            "lado": lado,
            "razones": res.razones[lado],
            "lineas": [l.a_dict() for l in lineas],
            "posesion": list(posesion),
            "estadisticas": res.estadisticas,
            "mvp": list(res.mvp),
            "alineaciones": [
                {"formacion": e.formacion, "mentalidad": e.mentalidad,
                 "titulares": [{"nombre": j.nombre, "ovr": j.carta.ovr, "puesto": p}
                               for j, p in zip(e.titulares, FORMACIONES[e.formacion])]}
                for e in (local, visita)
            ],
        }
        self.con.execute("UPDATE partidos SET detalle = ? WHERE id = ?", (json.dumps(detalle, ensure_ascii=False), partido_id))

    def _premiar(self, res, lado: int):
        g = res.ganador
        clave = "empate" if g < 0 else "victoria" if g == lado else "derrota"
        monto = economia.PREMIO_PARTIDO[clave] + economia.PREMIO_GOL * res.goles[lado]
        monto = int(monto * economia.MULTIPLICADOR_DIVISION.get(self.division, 1))
        self._mover_monedas(monto, f"Fecha {self.fecha}: {clave}")

    def _aplicar_sanciones(self, res):
        expulsados = {t["id"] for t in res.tarjetas if t["tipo"] == "roja"}
        for les in res.lesiones:
            fechas = round(les["dias"] / DIAS_POR_FECHA)
            if fechas and les.get("id"):
                self.con.execute("UPDATE plantilla SET lesion = MAX(lesion, ?) WHERE id = ?", (fechas, les["id"]))
        for pid in expulsados:
            if pid:
                self.con.execute("UPDATE plantilla SET suspension = suspension + 1 WHERE id = ?", (pid,))
        for t in res.tarjetas:
            if t["tipo"] == "amarilla" and t.get("id") and t["id"] not in expulsados:
                self.con.execute(
                    "UPDATE plantilla SET amarillas = amarillas + 1 WHERE id = ?", (t["id"],))
        self.con.execute(
            "UPDATE plantilla SET suspension = suspension + 1, amarillas = 0 WHERE amarillas >= ?", (AMARILLAS_SUSPENSION,))

    def _fijar_objetivo(self):
        """La directiva pide terminar un puesto mejor que lo que indica la fuerza del plantel."""
        fuerzas = sorted(((self.fuerza_equipo(e["id"]), e["id"]) for e in
                          self.con.execute("SELECT id FROM equipos WHERE division = ?", (self.division,))), reverse=True)
        esperado = next(i for i, (_, eid) in enumerate(fuerzas, start=1) if eid == self.usuario_id)
        objetivo = max(1, min(esperado - 1, len(fuerzas) - 2))
        self._set("objetivo", {"temporada": self.temporada, "posicion": objetivo, "esperado": esperado,
                               "premio": economia.PREMIO_OBJETIVO})

    @property
    def objetivo(self) -> dict | None:
        o = self._get("objetivo")
        if not o or o["temporada"] != self.temporada:
            self._fijar_objetivo()
            self.con.commit()
            o = self._get("objetivo")
        return o

    def _cerrar_temporada(self):
        # ascensos y descensos de todas las divisiones (se aplican al empezar la temporada siguiente)
        cambios = {}
        for d in range(self.n_divisiones):
            t = self.tabla(division=d)
            suben, bajan = self.cupos(d)
            for f in t[:suben]:
                cambios[f["id"]] = d + 1
            for f in t[len(t) - bajan:] if bajan else []:
                cambios[f["id"]] = d - 1
        self._set("cambios_division", {str(k): v for k, v in cambios.items()})

        tabla = self.tabla()
        posicion = next(i for i, f in enumerate(tabla, start=1) if f["id"] == self.usuario_id)
        mult = economia.MULTIPLICADOR_DIVISION.get(self.division, 1)
        premio = int(economia.premio_temporada(posicion) * mult)
        self._mover_monedas(premio, f"Premio temporada {self.temporada}: {posicion}° lugar")
        objetivo = self.objetivo
        cumplido = posicion <= objetivo["posicion"]
        if cumplido:
            self._mover_monedas(objetivo["premio"], f"Objetivo cumplido: top {objetivo['posicion']}")
        self._set("historial", self.historial + [
            {"temporada": self.temporada, "posicion": posicion, "puntos": tabla[posicion - 1]["pts"],
             "division": self.division, "nombre_division": self.nombre_division(),
             "movimiento": ("asciende" if cambios.get(self.usuario_id, self.division) > self.division else
                            "desciende" if cambios.get(self.usuario_id, self.division) < self.division else ""),
             "campeon": tabla[0]["nombre"], "podio": [f["nombre"] for f in tabla[:3]], "premio": premio,
             "objetivo": objetivo["posicion"], "cumplido": cumplido,
             "premio_objetivo": objetivo["premio"] if cumplido else 0}])

    def nueva_temporada(self):
        if not self.temporada_terminada:
            raise ErrorJuego("La temporada todavía no termina.")
        for eid, d in self._get("cambios_division", {}).items():
            self.con.execute("UPDATE equipos SET division = ? WHERE id = ?", (d, int(eid)))
        self.con.execute("DELETE FROM estado WHERE clave = 'cambios_division'")
        self._set("temporada", self.temporada + 1)
        self._set("fecha", 1)
        self.con.execute("UPDATE plantilla SET lesion = 0, suspension = 0, amarillas = 0, partidos = 0, goles = 0, asistencias = 0")
        self._crear_fixture()
        self._fijar_objetivo()
        self.con.commit()

    # ------------------------------------------------------------ consultas

    def tabla(self, temporada: int | None = None, division: int | None = None) -> list[dict]:
        """Tabla de una división (por defecto, la tuya) en una temporada."""
        temporada = temporada or self.temporada
        division = self.division if division is None else division
        ids = {r[0] for r in self.con.execute(
            "SELECT local_id FROM partidos WHERE temporada = ? AND division = ? UNION "
            "SELECT visita_id FROM partidos WHERE temporada = ? AND division = ?", (temporada, division, temporada, division))}
        filas = {r["id"]: dict(id=r["id"], nombre=r["nombre"], usuario=bool(r["es_usuario"]),
                               pj=0, g=0, e=0, p=0, gf=0, gc=0, pts=0, forma=[])
                 for r in self.con.execute("SELECT * FROM equipos") if r["id"] in ids}
        for p in self.con.execute("SELECT * FROM partidos WHERE temporada = ? AND division = ? AND jugado = 1 ORDER BY fecha",
                                  (temporada, division)):
            for eq, gf, gc in ((p["local_id"], p["goles_local"], p["goles_visita"]),
                               (p["visita_id"], p["goles_visita"], p["goles_local"])):
                f = filas[eq]
                f["pj"] += 1
                f["gf"] += gf
                f["gc"] += gc
                r = "g" if gf > gc else "e" if gf == gc else "p"
                f[r] += 1
                f["pts"] += {"g": 3, "e": 1, "p": 0}[r]
                f["forma"] = (f["forma"] + [r.upper()])[-5:]
        for f in filas.values():
            f["dg"] = f["gf"] - f["gc"]
        return sorted(filas.values(), key=lambda f: (-f["pts"], -f["dg"], -f["gf"], f["nombre"]))

    def goleadores(self, limite: int = 10, division: int | None = None) -> list[sqlite3.Row]:
        division = self.division if division is None else division
        return self.con.execute(
            "SELECT c.nombre, c.alias, COALESCE(NULLIF(e.nombre_real, ''), e.nombre) AS equipo, e.es_usuario, p.goles, p.asistencias, p.partidos"
            " FROM plantilla p JOIN cartas c ON c.id = p.carta_id JOIN equipos e ON e.id = p.equipo_id"
            " WHERE p.goles > 0 AND e.division = ? ORDER BY p.goles DESC, p.asistencias DESC, p.partidos LIMIT ?",
            (division, limite)).fetchall()

    def movimientos(self, limite: int = 10) -> list[sqlite3.Row]:
        return self.con.execute("SELECT * FROM movimientos ORDER BY id DESC LIMIT ?", (limite,)).fetchall()

    def carta(self, carta_id: int) -> Carta | None:
        fila = self.con.execute("SELECT * FROM cartas WHERE id = ?", (carta_id,)).fetchone()
        return _carta(fila) if fila else None

    # ------------------------------------------------------------ tienda

    def abrir_sobre(self, clave: str) -> list[FichaJugador]:
        """Abre un sobre y devuelve las cartas (los objetos quedan en `ultimos_objetos`)."""
        return self.abrir_sobre_completo(clave)["cartas"]

    def abrir_sobre_completo(self, clave: str) -> dict:
        """{"cartas": [FichaJugador], "objetos": [dict]}. Cada lugar del sobre puede ser un objeto de colección."""
        sobre = economia.SOBRES.get(clave)
        if not sobre:
            raise ErrorJuego("Ese sobre no existe.")
        if self.monedas < sobre["precio"]:
            raise ErrorJuego("No te alcanzan las monedas.")
        self._asegurar_coleccionables()
        n_mov = self.con.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
        rng = self._rng("sobre", n_mov)
        self._mover_monedas(-sobre["precio"], sobre["nombre"])
        niveles, pesos = zip(*sobre["probabilidades"].items())
        # pueden salir cartas que ya tienes (sirven para mejorarlas), pero no dos iguales en el mismo sobre
        excluir, nuevos, objetos = set(), [], []
        for nivel in rng.choices(niveles, weights=pesos, k=sobre["cartas"]):
            if rng.random() < sobre.get("objeto", 0):
                obj = self._sortear_objeto(rng, nivel)
                if obj:
                    objetos.append(obj)
                    continue
            todas = [r["id"] for r in self.con.execute("SELECT id, ovr FROM cartas ORDER BY id") if nivel_por_ovr(r["ovr"]) == nivel]
            ids = [i for i in todas if i not in excluir] or todas
            elegida = rng.choice(ids)
            excluir.add(elegida)
            cur = self.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)", (self.usuario_id, elegida))
            nuevos.append(cur.lastrowid)
        self.con.commit()
        self.ultimos_objetos = objetos
        return {"cartas": [f for f in self.plantel() if f.pid in nuevos], "objetos": objetos}

    # ------------------------------------------------------------ objetos de colección

    def _asegurar_coleccionables(self):
        """Crea el catálogo de escudos y estadios (una vez por partida)."""
        if self.con.execute("SELECT COUNT(*) FROM coleccionables").fetchone()[0]:
            return
        # escudos: uno por club real; la rareza sale de la fuerza de su plantel
        por_club: dict[str, list] = {}
        for f in self.con.execute("SELECT * FROM cartas"):
            por_club.setdefault(f["club"], []).append(Jugador(_carta(f)))
        fuerzas = sorted(((fuerza(js), club) for club, js in por_club.items() if len(js) >= 11), reverse=True)
        tercio = max(1, len(fuerzas) // 3)
        for i, (_, club) in enumerate(fuerzas):
            rareza = "oro" if i < tercio else "plata" if i < 2 * tercio else "bronce"
            self.con.execute("INSERT INTO coleccionables (tipo, club, nombre, rareza, archivo, capacidad)"
                             " VALUES ('escudo', ?, ?, ?, '', 0)", (club, club, rareza))
        # estadios: los que haya en data/estadios.json
        ruta = Path(ESTADIOS_JSON)
        if ruta.exists():
            vistos = set()
            for e in json.loads(ruta.read_text(encoding="utf-8")):
                e["estadio"] = re.sub(r"\s*\((Chile|Argentina|Brasil)\)$", "", e.get("estadio") or "").strip()
                if e["estadio"] and e["estadio"] not in vistos:  # un estadio compartido es un solo objeto
                    vistos.add(e["estadio"])
                    self.con.execute(
                        "INSERT INTO coleccionables (tipo, club, nombre, rareza, archivo, capacidad) VALUES ('estadio', ?, ?, ?, ?, ?)",
                        (e["club"], e["estadio"], economia.rareza_estadio(e.get("capacidad") or 0), e.get("archivo", ""),
                         e.get("capacidad") or 0))

    def _sortear_objeto(self, rng: random.Random, rareza: str) -> dict | None:
        """Un objeto que no tengas (primero de la rareza sorteada). None si ya tienes todos."""
        propios = {r[0] for r in self.con.execute("SELECT coleccionable_id FROM objetos")}
        todos = [dict(r) for r in self.con.execute("SELECT * FROM coleccionables ORDER BY id") if r["id"] not in propios]
        if not todos:
            return None
        tipos = sorted({o["tipo"] for o in todos})
        tipo = rng.choice(tipos)
        candidatos = ([o for o in todos if o["tipo"] == tipo and o["rareza"] == rareza]
                      or [o for o in todos if o["tipo"] == tipo] or todos)
        obj = rng.choice(candidatos)
        self.con.execute("INSERT INTO objetos (coleccionable_id) VALUES (?)", (obj["id"],))
        return obj

    def coleccion(self) -> list[dict]:
        """Todos los objetos de colección, marcando los que tienes."""
        self._asegurar_coleccionables()
        propios = {r["coleccionable_id"]: r["nuevo"] for r in self.con.execute("SELECT * FROM objetos")}
        e = self.equipo(self.usuario_id)
        salida = []
        for r in self.con.execute("SELECT * FROM coleccionables ORDER BY tipo, rareza DESC, nombre"):
            o = dict(r, tengo=r["id"] in propios, nuevo=bool(propios.get(r["id"])))
            o["en_uso"] = ((o["tipo"] == "escudo" and e["escudo"] == f"real:{o['club']}") or
                           (o["tipo"] == "estadio" and e["estadio"] == o["nombre"] and (e["estadio_img"] or "") == (o["archivo"] or "")))
            salida.append(o)
        return salida

    def marcar_objetos_vistos(self):
        self.con.execute("UPDATE objetos SET nuevo = 0")
        self.con.commit()

    def usar_objeto(self, coleccionable_id: int):
        """Equipa un escudo (pasa a ser tu logo) o un estadio (nombre y foto) de tu colección."""
        tengo = self.con.execute("SELECT 1 FROM objetos WHERE coleccionable_id = ?", (coleccionable_id,)).fetchone()
        obj = self.con.execute("SELECT * FROM coleccionables WHERE id = ?", (coleccionable_id,)).fetchone()
        if not tengo or not obj:
            raise ErrorJuego("Ese objeto no está en tu colección.")
        if obj["tipo"] == "escudo":
            self.con.execute("UPDATE equipos SET escudo = ? WHERE id = ?", (f"real:{obj['club']}", self.usuario_id))
        else:
            self.con.execute("UPDATE equipos SET estadio = ?, estadio_img = ? WHERE id = ?",
                             (obj["nombre"], obj["archivo"] or "", self.usuario_id))
        self.con.commit()

    def vender(self, pid: int) -> int:
        return self.vender_varios([pid])

    def vender_varios(self, pids: list[int]) -> int:
        """Venta rápida de varias cartas. Se puede deshacer la última venta con deshacer_venta()."""
        fichas = self.plantel()
        por_pid = {f.pid: f for f in fichas}
        pids = list(dict.fromkeys(pids))
        if not pids or any(pid not in por_pid for pid in pids):
            raise ErrorJuego("Esa carta no está en tu plantel.")
        if len(fichas) - len(pids) < PLANTEL_MINIMO:
            raise ErrorJuego(f"Necesitas al menos {PLANTEL_MINIMO} jugadores en el plantel.")
        arqueros = sum(f.carta.posicion == "GK" for f in fichas) - sum(por_pid[p].carta.posicion == "GK" for p in pids)
        if arqueros < 2:
            raise ErrorJuego("Necesitas al menos 2 arqueros.")
        total = 0
        for pid in pids:
            total += economia.valor_venta(por_pid[pid].carta.precio)
            self.con.execute("DELETE FROM plantilla WHERE id = ?", (pid,))
        nombres = ", ".join(por_pid[p].carta.nombre_corto for p in pids[:3]) + ("…" if len(pids) > 3 else "")
        self._mover_monedas(total, f"Venta de {nombres}")
        self._set("ultima_venta", {"cartas": [por_pid[p].carta_id for p in pids], "monto": total})
        self.con.commit()
        return total

    @property
    def ultima_venta(self) -> dict | None:
        return self._get("ultima_venta")

    def deshacer_venta(self) -> int:
        venta = self.ultima_venta
        if not venta:
            raise ErrorJuego("No hay una venta para deshacer.")
        if self.monedas < venta["monto"]:
            raise ErrorJuego("Ya gastaste esas monedas.")
        for carta_id in venta["cartas"]:
            self.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)", (self.usuario_id, carta_id))
        self._mover_monedas(-venta["monto"], "Venta deshecha")
        self.con.execute("DELETE FROM estado WHERE clave = 'ultima_venta'")
        self.con.commit()
        return len(venta["cartas"])

    # ------------------------------------------------------------ mercado de transferencias

    def _momento(self) -> int:
        return self.temporada * 100 + self.fecha

    def _reponer_mercado(self):
        """Los clubes bot ponen jugadores en venta: en cada fecha vencen publicaciones y entran
        nuevas hasta tener MERCADO_ACTIVAS. Se hace al mirar el mercado (una vez por fecha)."""
        ahora = self._momento()
        if self._get("mercado_momento") == ahora:
            return
        self.con.execute("DELETE FROM mercado WHERE expira < ?", (ahora,))
        activas = {r[0] for r in self.con.execute("SELECT carta_id FROM mercado")}
        propios = {f.carta_id for f in self.plantel()}
        clubes = {e["nombre_real"] or e["nombre"]: e["id"] for e in self._bots()}  # los bots pueden tener otro nombre
        rng = self._rng("mercado", ahora)
        candidatas = [f for f in self.con.execute("SELECT id, club, precio FROM cartas ORDER BY id")
                      if f["id"] not in activas and f["id"] not in propios and f["club"] in clubes]
        rng.shuffle(candidatas)
        for f in candidatas[: max(0, MERCADO_ACTIVAS - len(activas))]:
            factor = rng.uniform(0.7, 0.85) if rng.random() < 0.08 else rng.uniform(0.9, 1.35)  # a veces, una ganga
            precio = int(round(max(50, f["precio"] * factor), -1 if f["precio"] < 10000 else -2))
            duracion = rng.randint(1, MERCADO_DURACION)
            self.con.execute("INSERT INTO mercado (carta_id, vendedor_id, precio, publicada, expira) VALUES (?, ?, ?, ?, ?)",
                             (f["id"], clubes[f["club"]], precio, ahora, ahora + duracion - 1))
        self._set("mercado_momento", ahora)
        self.con.commit()

    def _publicacion(self, fila: sqlite3.Row, propios: set) -> dict:
        return {"publicacion_id": fila["mid"], "carta_id": fila["id"], "carta": _carta(fila), "precio": fila["mprecio"],
                "edad": fila["edad"],
                "vendedor": fila["vendedor"], "quedan": fila["expira"] - self._momento() + 1,
                "en_mercado": True, "vendida": False, "tuya": fila["id"] in propios}

    def ofertas(self) -> list[dict]:
        """Jugadores en venta en el mercado de transferencias (los publican los clubes bot)."""
        self._reponer_mercado()
        propios = {f.carta_id for f in self.plantel()}
        filas = self.con.execute(
            "SELECT c.*, m.id AS mid, m.precio AS mprecio, m.expira, e.nombre AS vendedor FROM mercado m"
            " JOIN cartas c ON c.id = m.carta_id JOIN equipos e ON e.id = m.vendedor_id ORDER BY c.ovr DESC, m.precio")
        return [self._publicacion(f, propios) for f in filas]

    def buscar(self, texto: str = "", club: str = "", nacion: str = "", posicion: str = "", solo_venta: bool = True,
               ovr_min: int = 0, ovr_max: int = 99, precio_max: int = 0, orden: str = "ovr",
               limite: int = 60) -> list[dict]:
        """Buscador del mercado: por nombre (sin importar tildes), club, país, posición (línea
        POR/DEF/MED/DEL o puesto exacto), OVR y precio. Con solo_venta=False busca en todos los
        jugadores del juego (para ver sus stats) y dice si están en venta."""
        palabras = _sin_tildes(texto).split()
        posicion = posicion.upper()
        en_venta = {o["carta_id"]: o for o in self.ofertas()}
        if solo_venta:
            filas = [o for o in en_venta.values()]
        else:
            if not (palabras or club or nacion or posicion):
                return []
            propios = {f.carta_id for f in self.plantel()}
            filas = [en_venta.get(f["id"]) or {"carta_id": f["id"], "carta": _carta(f), "precio": None, "vendedor": "",
                                               "edad": f["edad"],
                                               "quedan": 0, "en_mercado": False, "vendida": False,
                                               "tuya": f["id"] in propios}
                     for f in self.con.execute("SELECT * FROM cartas")]
        encontrados = []
        for o in filas:
            c = o["carta"]
            if club and c.club != club or nacion and _sin_tildes(c.nacion) != _sin_tildes(nacion):
                continue
            if posicion and posicion not in (c.posicion, linea(c.posicion)):
                continue
            if not ovr_min <= c.ovr <= ovr_max or precio_max and (o["precio"] or 0) > precio_max:
                continue
            if palabras and not all(p in _sin_tildes(f"{c.nombre} {c.alias}") for p in palabras):
                continue
            encontrados.append(o)
        clave = {"precio": lambda o: (o["precio"] is None, o["precio"] or 0, -o["carta"].ovr),
                 "precio_desc": lambda o: (o["precio"] is None, -(o["precio"] or 0)),
                 "vence": lambda o: (not o["en_mercado"], o["quedan"], -o["carta"].ovr)}.get(
            orden, lambda o: (-o["carta"].ovr, o["precio"] or 0))
        return sorted(encontrados, key=clave)[:limite]

    def opciones_busqueda(self) -> dict:
        """Clubes y países del catálogo, para los filtros del buscador."""
        clubes = [r[0] for r in self.con.execute("SELECT DISTINCT club FROM cartas ORDER BY club")]
        naciones = {}  # los datos traen "Chile" y "CHILE": uno por país
        for (n,) in self.con.execute("SELECT DISTINCT nacion FROM cartas WHERE nacion != ''"):
            clave = _sin_tildes(n)
            if clave not in naciones or not n.isupper():
                naciones[clave] = n if not n.isupper() else n.title()
        return {"clubes": clubes, "naciones": sorted(naciones.values(), key=_sin_tildes)}

    def en_venta(self, carta_id: int) -> list[dict]:
        """Publicaciones de un jugador en el mercado (vacío si nadie lo está vendiendo)."""
        return sorted((o for o in self.ofertas() if o["carta_id"] == carta_id), key=lambda o: o["precio"])

    def comprar(self, carta_id: int) -> FichaJugador:
        """Compra al jugador en el mercado (la publicación más barata, si hubiera varias)."""
        oferta = min((o for o in self.ofertas() if o["carta_id"] == carta_id), key=lambda o: o["precio"], default=None)
        if not oferta:
            raise ErrorJuego("Ese jugador ya no está en venta.")
        if oferta["tuya"]:
            raise ErrorJuego("Ya tienes a ese jugador.")
        if self.monedas < oferta["precio"]:
            raise ErrorJuego("No te alcanzan las monedas.")
        pid = self.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)",
                               (self.usuario_id, carta_id)).lastrowid
        self.con.execute("DELETE FROM mercado WHERE id = ?", (oferta["publicacion_id"],))
        self._mover_monedas(-oferta["precio"], f"Fichaje de {oferta['carta'].nombre_corto} ({oferta['vendedor']})")
        self.con.commit()
        return next(f for f in self.plantel() if f.pid == pid)

    def evolucion(self) -> list[int]:
        """Tu posición en la tabla después de cada fecha jugada."""
        partidos = self.con.execute("SELECT * FROM partidos WHERE temporada = ? AND division = ? AND jugado = 1 ORDER BY fecha",
                                    (self.temporada, self.division)).fetchall()
        pts = {e: [0, 0, 0] for p in partidos for e in (p["local_id"], p["visita_id"])}  # pts, dg, gf
        posiciones = []
        for fecha in sorted({p["fecha"] for p in partidos}):
            for p in (x for x in partidos if x["fecha"] == fecha):
                for eq, gf, gc in ((p["local_id"], p["goles_local"], p["goles_visita"]),
                                   (p["visita_id"], p["goles_visita"], p["goles_local"])):
                    pts[eq][0] += 3 if gf > gc else 1 if gf == gc else 0
                    pts[eq][1] += gf - gc
                    pts[eq][2] += gf
            orden = sorted(pts, key=lambda e: (-pts[e][0], -pts[e][1], -pts[e][2]))
            posiciones.append(orden.index(self.usuario_id) + 1)
        return posiciones

    def once_probable(self, equipo_id: int) -> Equipo:
        return self.armar(equipo_id, self.fuerza_equipo(self.usuario_id))

    def quimica_usuario(self) -> dict:
        e = self._equipo_usuario()
        return quimica(e.formacion, [j.carta for j in e.titulares])

    # ------------------------------------------------------------ carta gratis

    def segundos_para_carta_gratis(self) -> int:
        ultima = self._get("ultima_carta_gratis", 0)
        return max(0, int(ultima + economia.CARTA_GRATIS_SEGUNDOS - time.time()))

    def reclamar_carta_gratis(self) -> FichaJugador:
        espera = self.segundos_para_carta_gratis()
        if espera:
            raise ErrorJuego(f"La próxima carta gratis estará en {espera // 60} min.")
        rng = random.Random()
        niveles, pesos = zip(*economia.CARTA_GRATIS_PROBABILIDADES.items())
        nivel = rng.choices(niveles, weights=pesos)[0]
        ids = [r["id"] for r in self.con.execute("SELECT id, ovr FROM cartas") if nivel_por_ovr(r["ovr"]) == nivel]
        pid = self.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)",
                               (self.usuario_id, rng.choice(ids))).lastrowid
        self._set("ultima_carta_gratis", time.time())
        self.con.commit()
        return next(f for f in self.plantel() if f.pid == pid)

    # ------------------------------------------------------------ mejora con repetidas

    def copias(self) -> dict[int, list[FichaJugador]]:
        """carta_id -> tus copias de esa carta."""
        salida: dict[int, list[FichaJugador]] = {}
        for f in self.plantel():
            salida.setdefault(f.carta_id, []).append(f)
        return salida

    def puede_mejorar(self, ficha: FichaJugador, copias: dict | None = None) -> bool:
        copias = copias or self.copias()
        return ficha.nivel < economia.NIVEL_MAXIMO and len(copias.get(ficha.carta_id, [])) > 1

    def mejorar(self, pid: int) -> FichaJugador:
        """Sube un nivel la carta gastando una copia repetida (la de menor nivel que no esté jugando) y monedas."""
        copias = self.copias()
        ficha = next((f for c in copias.values() for f in c if f.pid == pid), None)
        if not ficha:
            raise ErrorJuego("Esa carta no está en tu plantel.")
        if ficha.nivel >= economia.NIVEL_MAXIMO:
            raise ErrorJuego("Esa carta ya está al máximo.")
        otras = [f for f in copias[ficha.carta_id] if f.pid != pid]
        if not otras:
            raise ErrorJuego("Necesitas una carta repetida de ese jugador para mejorarla.")
        costo = economia.costo_mejora(ficha.nivel)
        if self.monedas < costo:
            raise ErrorJuego(f"Necesitas {costo} monedas.")
        gastada = min(otras, key=lambda f: (f.puesto is not None and f.puesto < 11, f.puesto is not None, f.nivel))
        self.con.execute("DELETE FROM plantilla WHERE id = ?", (gastada.pid,))
        self.con.execute("UPDATE plantilla SET nivel = nivel + 1 WHERE id = ?", (pid,))
        self._mover_monedas(-costo, f"Mejora de {ficha.carta.nombre_corto} a nivel {ficha.nivel + 1}")
        self.con.commit()
        return next(f for f in self.plantel() if f.pid == pid)

    # ------------------------------------------------------------ alineaciones guardadas (hasta 5)

    def _puestos_actuales(self) -> list:
        puestos = [None] * (11 + SUPLENTES)
        for f in self.plantel():
            if f.puesto is not None and f.puesto < len(puestos):
                puestos[f.puesto] = f.pid
        return puestos

    def _guardar_en_activa(self):
        activa = self._get("alineacion_activa")
        if activa:
            e = self.equipo(self.usuario_id)
            self.con.execute("UPDATE alineaciones SET formacion = ?, mentalidad = ?, puestos = ? WHERE id = ?",
                             (e["formacion"], e["mentalidad"], json.dumps(self._puestos_actuales()), activa))

    def alineaciones(self) -> list[dict]:
        activa = self._get("alineacion_activa")
        return [dict(r, activa=r["id"] == activa) for r in self.con.execute("SELECT * FROM alineaciones ORDER BY id")]

    def nueva_alineacion(self, nombre: str) -> int:
        nombre = (nombre or "").strip()[:20]
        if not nombre:
            raise ErrorJuego("Ponle un nombre a la alineación.")
        if self.con.execute("SELECT COUNT(*) FROM alineaciones").fetchone()[0] >= MAX_ALINEACIONES:
            raise ErrorJuego(f"Puedes tener hasta {MAX_ALINEACIONES} alineaciones.")
        self._guardar_en_activa()
        e = self.equipo(self.usuario_id)
        nueva = self.con.execute("INSERT INTO alineaciones (nombre, formacion, mentalidad, puestos) VALUES (?, ?, ?, ?)",
                                 (nombre, e["formacion"], e["mentalidad"], json.dumps(self._puestos_actuales()))).lastrowid
        self._set("alineacion_activa", nueva)
        self.con.commit()
        return nueva

    def usar_alineacion(self, alineacion_id: int):
        fila = self.con.execute("SELECT * FROM alineaciones WHERE id = ?", (alineacion_id,)).fetchone()
        if not fila:
            raise ErrorJuego("Esa alineación no existe.")
        self._guardar_en_activa()
        propios = {f.pid for f in self.plantel()}
        puestos = {i: pid for i, pid in enumerate(json.loads(fila["puestos"] or "[]")) if pid in propios}
        self._set("alineacion_activa", alineacion_id)
        self.guardar_alineacion(fila["formacion"], fila["mentalidad"], puestos)

    def renombrar_alineacion(self, alineacion_id: int, nombre: str):
        nombre = (nombre or "").strip()[:20]
        if not nombre:
            raise ErrorJuego("Ponle un nombre a la alineación.")
        self.con.execute("UPDATE alineaciones SET nombre = ? WHERE id = ?", (nombre, alineacion_id))
        self.con.commit()

    def borrar_alineacion(self, alineacion_id: int):
        if alineacion_id == self._get("alineacion_activa"):
            raise ErrorJuego("No puedes borrar la alineación que estás usando.")
        self.con.execute("DELETE FROM alineaciones WHERE id = ?", (alineacion_id,))
        self.con.commit()

    # ------------------------------------------------------------ amistosos

    def iniciar_amistoso(self, rival_id: int, de_local: bool = True) -> int:
        if self.partido_en_vivo():
            raise ErrorJuego("Ya tienes un partido en curso.")
        rival = self.equipo(rival_id)
        if not rival or rival["es_usuario"]:
            raise ErrorJuego("Elige un club rival.")
        local, visita = (self.usuario_id, rival_id) if de_local else (rival_id, self.usuario_id)
        pid = self.con.execute(
            "INSERT INTO partidos (temporada, fecha, division, tipo, local_id, visita_id) VALUES (?, 0, -1, 'amistoso', ?, ?)",
            (self.temporada, local, visita)).lastrowid
        self._set("vivo", {"partido": pid, "decisiones": [], "intervenciones": []})
        self.con.commit()
        return pid

    def clubes(self) -> list[dict]:
        """Todos los clubes de la pirámide con su fuerza (para elegir rival de amistoso)."""
        return [dict(e, fuerza=round(self.fuerza_equipo(e["id"]), 1)) for e in self._bots()]

    # ------------------------------------------------------------ perfil

    def actualizar_perfil(self, eslogan: str | None = None, estadio: str | None = None, escudo: dict | str | None = None):
        uid = self.usuario_id
        if eslogan is not None:
            self.con.execute("UPDATE equipos SET eslogan = ? WHERE id = ?", (eslogan.strip()[:80], uid))
        if estadio is not None:
            estadio = estadio.strip()[:40]
            if not estadio:
                raise ErrorJuego("Ponle un nombre al estadio.")
            self.con.execute("UPDATE equipos SET estadio = ? WHERE id = ?", (estadio, uid))
        if escudo is not None:
            self.con.execute("UPDATE equipos SET escudo = ? WHERE id = ?",
                             (escudo if isinstance(escudo, str) else json.dumps(escudo), uid))
        self.con.commit()

    def estadisticas_club(self) -> dict:
        """Récord histórico de tu club en liga y amistosos, y títulos."""
        uid = self.usuario_id
        rec = {"liga": dict(pj=0, g=0, e=0, p=0, gf=0, gc=0), "amistoso": dict(pj=0, g=0, e=0, p=0, gf=0, gc=0)}
        for p in self.con.execute("SELECT * FROM partidos WHERE jugado = 1 AND ? IN (local_id, visita_id)", (uid,)):
            r = rec["amistoso" if p["tipo"] == "amistoso" else "liga"]
            gf, gc = (p["goles_local"], p["goles_visita"]) if p["local_id"] == uid else (p["goles_visita"], p["goles_local"])
            r["pj"] += 1
            r["gf"] += gf
            r["gc"] += gc
            r["g" if gf > gc else "e" if gf == gc else "p"] += 1
        hist = self.historial
        return {
            "record": rec,
            "titulos": [h for h in hist if h["posicion"] == 1],
            "ascensos": [h for h in hist if h.get("movimiento") == "asciende"],
            "temporadas": len(hist),
        }

