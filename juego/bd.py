"""Base de datos SQLite de una partida local (un solo jugador)."""
import sqlite3
from pathlib import Path

RUTA_POR_DEFECTO = Path("data/partida.sqlite")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS cartas (
    id INTEGER PRIMARY KEY,
    nombre TEXT, alias TEXT, posicion TEXT, club TEXT, nacion TEXT, liga TEXT,
    ovr INTEGER, pac INTEGER, sho INTEGER, pas INTEGER, dri INTEGER, def INTEGER, phy INTEGER,
    precio INTEGER, edad INTEGER
);
CREATE TABLE IF NOT EXISTS equipos (
    id INTEGER PRIMARY KEY,
    nombre TEXT UNIQUE,
    es_usuario INTEGER DEFAULT 0,
    division INTEGER DEFAULT 0,      -- 0 bronce, 1 plata, 2 oro
    formacion TEXT DEFAULT '4-3-3',
    mentalidad TEXT DEFAULT 'equilibrada'
);
-- Cada fila es una copia de una carta en un equipo (la misma carta puede estar en varios)
CREATE TABLE IF NOT EXISTS plantilla (
    id INTEGER PRIMARY KEY,
    equipo_id INTEGER REFERENCES equipos(id),
    carta_id INTEGER REFERENCES cartas(id),
    puesto INTEGER,              -- índice en la formación (0-10) si es titular elegido
    lesion INTEGER DEFAULT 0,    -- fechas que le quedan lesionado
    suspension INTEGER DEFAULT 0,
    amarillas INTEGER DEFAULT 0, -- acumuladas para la suspensión
    partidos INTEGER DEFAULT 0, goles INTEGER DEFAULT 0, asistencias INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS partidos (
    id INTEGER PRIMARY KEY,
    temporada INTEGER, fecha INTEGER, division INTEGER DEFAULT 0,
    local_id INTEGER, visita_id INTEGER,
    goles_local INTEGER, goles_visita INTEGER,
    jugado INTEGER DEFAULT 0,
    detalle TEXT                 -- JSON con la narración (solo partidos del usuario)
);
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY, temporada INTEGER, fecha INTEGER, concepto TEXT, monto INTEGER
);
CREATE TABLE IF NOT EXISTS estado (clave TEXT PRIMARY KEY, valor TEXT);
-- objetos de colección: escudos y estadios de los clubes reales
CREATE TABLE IF NOT EXISTS coleccionables (
    id INTEGER PRIMARY KEY, tipo TEXT, club TEXT, nombre TEXT, rareza TEXT, archivo TEXT, capacidad INTEGER
);
CREATE TABLE IF NOT EXISTS objetos (
    id INTEGER PRIMARY KEY, coleccionable_id INTEGER REFERENCES coleccionables(id), nuevo INTEGER DEFAULT 1
);
-- alineaciones guardadas (hasta 5): puestos = JSON con 18 pids (11 titulares + 7 suplentes)
CREATE TABLE IF NOT EXISTS alineaciones (
    id INTEGER PRIMARY KEY, nombre TEXT, formacion TEXT, mentalidad TEXT, puestos TEXT
);
-- mercado de transferencias: jugadores que los clubes bot ponen en venta (vencen tras unas fechas)
CREATE TABLE IF NOT EXISTS mercado (
    id INTEGER PRIMARY KEY, carta_id INTEGER REFERENCES cartas(id), vendedor_id INTEGER REFERENCES equipos(id),
    precio INTEGER, publicada INTEGER, expira INTEGER  -- publicada/expira: temporada * 100 + fecha
);
CREATE INDEX IF NOT EXISTS ix_plantilla_equipo ON plantilla(equipo_id);
CREATE INDEX IF NOT EXISTS ix_partidos_fecha ON partidos(temporada, fecha);
"""


def conectar(ruta: str | Path = RUTA_POR_DEFECTO) -> sqlite3.Connection:
    if str(ruta) != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta, check_same_thread=False)  # la web abre una conexión por pedido
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    # columnas agregadas después (partidas creadas con versiones anteriores)
    nuevas = {
        "equipos": {"division": "INTEGER DEFAULT 0", "estadio": "TEXT DEFAULT ''", "escudo": "TEXT DEFAULT ''",
                    "eslogan": "TEXT DEFAULT ''", "nombre_real": "TEXT DEFAULT ''", "estadio_img": "TEXT DEFAULT ''"},
        "partidos": {"division": "INTEGER DEFAULT 0", "tipo": "TEXT DEFAULT 'liga'"},
        "plantilla": {"nivel": "INTEGER DEFAULT 1"},
    }
    for tabla, columnas in nuevas.items():
        existentes = {c["name"] for c in con.execute(f"PRAGMA table_info({tabla})")}
        for nombre, tipo in columnas.items():
            if nombre not in existentes:
                con.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
    return con
