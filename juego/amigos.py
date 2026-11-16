"""Registro compartido de desafíos entre amigos (data/amigos.sqlite).

Cada jugador tiene su propia partida; cuando uno desafía a otro, el partido se juega en la
partida del que desafía (contra una copia del club del amigo) y el resultado se anota acá
para que los dos lo vean.
"""
import json
import sqlite3
import time
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS desafios (
    id INTEGER PRIMARY KEY,
    creado REAL,
    retador TEXT, retador_club TEXT,      -- id de partida (cookie) y nombre del club
    rival TEXT, rival_club TEXT,
    retador_local INTEGER,
    goles_retador INTEGER, goles_rival INTEGER,
    goleadores TEXT,                      -- JSON [retador, rival]
    visto INTEGER DEFAULT 0               -- el rival ya lo vio
);
CREATE INDEX IF NOT EXISTS ix_desafios_rival ON desafios(rival);
CREATE INDEX IF NOT EXISTS ix_desafios_retador ON desafios(retador);
"""


class Registro:
    def __init__(self, ruta: str | Path):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(ruta, check_same_thread=False, timeout=10)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)

    def cerrar(self):
        self.con.close()

    def anotar(self, retador: str, retador_club: str, rival: str, rival_club: str, r: dict) -> int:
        cur = self.con.execute(
            "INSERT INTO desafios (creado, retador, retador_club, rival, rival_club, retador_local, goles_retador, goles_rival,"
            " goleadores) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), retador, retador_club, rival, rival_club, int(r["de_local"]), r["goles"], r["goles_rival"],
             json.dumps([r.get("goleadores", []), r.get("goleadores_rival", [])], ensure_ascii=False)))
        self.con.commit()
        return cur.lastrowid

    def historial(self, yo: str, limite: int = 30) -> list[dict]:
        """Desafíos donde participé, vistos desde mi lado (mis goles primero)."""
        salida = []
        for d in self.con.execute("SELECT * FROM desafios WHERE ? IN (retador, rival) ORDER BY id DESC LIMIT ?", (yo, limite)):
            soy_retador = d["retador"] == yo
            gol = json.loads(d["goleadores"] or "[[], []]")
            mios, suyos = (d["goles_retador"], d["goles_rival"]) if soy_retador else (d["goles_rival"], d["goles_retador"])
            salida.append({
                "id": d["id"], "creado": d["creado"], "yo_desafie": soy_retador,
                "otro": d["rival"] if soy_retador else d["retador"],
                "otro_club": d["rival_club"] if soy_retador else d["retador_club"],
                "mios": mios, "suyos": suyos,
                "resultado": "g" if mios > suyos else "e" if mios == suyos else "p",
                "mis_goleadores": gol[0] if soy_retador else gol[1],
                "sus_goleadores": gol[1] if soy_retador else gol[0],
                "nuevo": not soy_retador and not d["visto"],
            })
        return salida

    def record(self, yo: str) -> dict[str, dict]:
        """Ganados/empatados/perdidos contra cada amigo."""
        rec: dict[str, dict] = {}
        for h in self.historial(yo, limite=10_000):
            r = rec.setdefault(h["otro"], {"g": 0, "e": 0, "p": 0})
            r[h["resultado"]] += 1
        return rec

    def sin_ver(self, yo: str) -> int:
        return self.con.execute("SELECT COUNT(*) FROM desafios WHERE rival = ? AND visto = 0", (yo,)).fetchone()[0]

    def marcar_vistos(self, yo: str):
        self.con.execute("UPDATE desafios SET visto = 1 WHERE rival = ?", (yo,))
        self.con.commit()
