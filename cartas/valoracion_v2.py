"""Valoración v2 (propuesta): además de la nota, el rol y los goles, usa las estadísticas finas de 365Scores.

Cambios respecto de Valorador365:
- produccion: xG y xA cada 90' (delanteros y volantes), toques cada 90' (volantes y defensas),
  goles evitados = goles esperados recibidos - goles recibidos (arqueros) y atajadas cada 90'.
- precio: último traspaso con precio de los últimos 3 años (escala logarítmica, comparado dentro de la
  liga y con un descuento si era muy joven: los clubes pagan por la promesa).
- club: la mitad del peso (antes inflaba a todo el plantel del puntero).
- aporte (goles y asistencias reales): la mitad del peso, porque xG/xA miden lo mismo con menos suerte.

Las estadísticas extra se leen del caché de 365Scores (data/cache_365/atletas/<id>.json), sin red.
"""
from __future__ import annotations

import json
import math
import random
import re
from datetime import date
from pathlib import Path

from cartas.valoracion import Valorador365, _efecto_edad, _z, precio

CACHE = Path("data/cache_365/atletas")
# torneos de selección ADULTA (los juveniles y los de clubes no cuentan)
SELECCION = {5930: "Mundial", 7016: "Liga de las Naciones UEFA", 7165: "Liga de Naciones CONCACAF", 9034: "FIFA Series",
             588: "Clasificación Copa de África", 5472: "Clasificación Copa Asia", 5452: "Copa del Golfo"}
PARTIDOS_SELECCION_TOPE = 8   # con 8 partidos de selección en la temporada, el aporte es el máximo
EXTRA = {"goles esperados": "xg", "asistencias esperadas": "xa", "goles esperados recibidos": "xga",
         "grandes chances creadas": "chances_creadas", "toques": "toques", "minutos jugados": "minutos",
         "tiros al arco": "tiros_arco", "salvadas": "atajadas", "goles recibidos": "goles_recibidos"}


def _plano(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn").strip()


def _num(v):
    m = re.match(r"^-?\d+(\.\d+)?", str(v).strip())
    return float(m.group(0)) if m else None


def _millones(texto: str) -> float | None:
    """'€30M' -> 30.0; '€750K' -> 0.75; 'Libre' -> None."""
    m = re.search(r"([\d.,]+)\s*([MK])", str(texto).upper())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v if m.group(2) == "M" else v / 1000


def enriquecer(j: dict, competicion: int, hoy: date) -> None:
    """Agrega a j["stats"] xG, xA, etc. y a j el último precio de traspaso (si es reciente)."""
    ruta = CACHE / f"{j.get('id_365')}.json"
    if not ruta.exists():
        return
    try:
        f = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return
    bloques = f.get("highlightStats") or []
    otra = (j.get("stats") or {}).get("otra_competicion")
    elegidos = [b for b in bloques if b.get("competitionId") == competicion] if not otra else \
        [b for b in bloques if _plano(b.get("name", "")) == _plano(otra)] or bloques
    if elegidos:
        b = max(elegidos, key=lambda b: b.get("seasonNum") or 0)
        s = j.setdefault("stats", {})
        for st in b.get("stats") or []:
            clave = EXTRA.get(_plano(st.get("name", "")))
            v = _num(st.get("value"))
            if clave and v is not None:
                s[clave] = v
    # partidos con la selección adulta en ESTA temporada (no la carrera): la última edición de cada torneo
    ultimos = {}
    for b in bloques:
        if b.get("competitionId") in SELECCION:
            if b["competitionId"] not in ultimos or (b.get("seasonNum") or 0) > (ultimos[b["competitionId"]].get("seasonNum") or 0):
                ultimos[b["competitionId"]] = b
    j["seleccion_temporada"] = int(sum(next((_num(s.get("value")) or 0 for s in b.get("stats") or []
                                             if _plano(s.get("name", "")) == "apariciones"), 0) for b in ultimos.values()))
    precios = []
    for t in f.get("transfers") or []:
        m = _millones(t.get("price") or "")
        anio = int((t.get("date") or "0")[:4] or 0)
        if m and anio >= hoy.year - 3:
            precios.append((anio, m))
    if precios:
        anio, m = max(precios)
        j["traspaso"] = {"anio": anio, "millones": m}


class Valorador365v2(Valorador365):
    PESOS = {"puntaje": 13.0, "rol": 5.0, "club": 3.5, "seleccion": 4.0, "precio": 2.5,
             "aporte": {"DEL": 3.0, "MED": 1.5, "DEF": 0.5, "POR": 2.0},
             "produccion": {"DEL": 4.5, "MED": 3.0, "DEF": 1.0, "POR": 4.0}}

    def calcular(self) -> list[dict]:
        filas = super().calcular()            # nota, rol, aporte, club, edad... (lo de siempre)
        P = self.PESOS

        # no todas las ligas publican lo mismo en 365Scores (Chile: sin xG ni minutos; Argentina: sin minutos
        # ni toques): sin minutos se estiman con los partidos jugados, y se usa lo que cada liga sí tenga
        def minutos(s):
            return s.get("minutos") or (s.get("pj") or 0) * 80

        def por90(s, clave):
            m = minutos(s)
            return s[clave] * 90 / m if m >= 270 and s.get(clave) is not None else None

        # producción por línea (comparada dentro de la línea, solo con quien jugó lo suficiente)
        for f in filas:
            s = f["jugador"].get("stats") or {}
            ln = f["linea"]
            xg, xa, toq = por90(s, "xg"), por90(s, "xa"), por90(s, "toques")
            arco, chances, ataj = por90(s, "tiros_arco"), por90(s, "chances_creadas"), por90(s, "atajadas")
            if ln == "POR":
                m = minutos(s)
                if s.get("xga") is not None and s.get("goles_recibidos") is not None and m >= 270:
                    f["_prod"] = (s["xga"] - s["goles_recibidos"]) * 90 / m + 0.05 * (ataj or 0)   # goles evitados
                else:
                    # solo atajadas no sirve: el arquero del equipo que más ataca ataja menos (no es peor)
                    f["_prod"] = None
            elif ln == "DEL":
                if xg is not None:
                    f["_prod"] = xg + 0.7 * (xa or 0) + 0.04 * (arco or 0)
                elif arco is not None:
                    f["_prod"] = 0.12 * arco + 0.08 * (chances or 0)
                else:
                    f["_prod"] = None
            elif ln == "MED":
                partes = [v for v in ((xa or 0) + 0.5 * (xg or 0) if xg is not None or xa is not None else None,
                                      0.0015 * toq if toq is not None else None,
                                      0.08 * chances if chances is not None and xa is None else None) if v is not None]
                f["_prod"] = sum(partes) if partes else None
            else:
                f["_prod"] = 0.004 * toq if toq is not None else None
            t = f["jugador"].get("traspaso")
            if t:
                # los clubes pagan la promesa: a un sub-23 se le descuenta parte del precio
                joven = max(0, 23 - (f["edad"] or 25)) * 0.12
                f["_precio"] = math.log10(max(t["millones"], 0.05)) - joven
            else:
                f["_precio"] = None
        for ln in ("POR", "DEF", "MED", "DEL"):
            grupo = [f for f in filas if f["linea"] == ln]
            pobl = [f["_prod"] for f in grupo if f["_prod"] is not None and f["confianza"] >= 0.4]
            for f in grupo:
                z = _z(f["_prod"], pobl) if f["_prod"] is not None else 0.0
                f["componentes"]["produccion"] = round(P["produccion"][ln] * z / 6 * f["confianza"] * 2, 2)
        pobl_precio = [f["_precio"] for f in filas if f["_precio"] is not None]
        for f in filas:
            c = f["componentes"]
            c["precio"] = round(P["precio"] * (_z(f["_precio"], pobl_precio) / 3) if f["_precio"] is not None else 0.0, 2)
            c["club"] = round(c["club"] * P["club"] / self.PESOS_365["club"], 2)
            c["aporte"] = round(c["aporte"] * P["aporte"][f["linea"]] / self.PESOS_365["aporte"][f["linea"]], 2)
            c.pop("manual", None)
            # selección: los partidos de esta temporada (Mundial, Nations League...), no los de toda la carrera
            c["seleccion"] = round(P["seleccion"] * min(1.0, f["jugador"].get("seleccion_temporada", 0) / PARTIDOS_SELECCION_TOPE), 2)
            edad = f["edad"] or 0
            if 0 < edad < 24:
                # jóvenes: el castigo por edad es para los que todavía no están probados; si son titulares y
                # rinden (mucha confianza y buena nota), casi no se aplica (Yamal, Güler, Cubarsí...)
                rinde = f["rol"] * f["confianza"] * (1.0 if c["puntaje"] > 0 else 0.5)
                c["edad"] = round(_efecto_edad(edad) * (1 - 0.8 * min(1.0, rinde)), 2)
            if edad > 32:
                # veteranos: la edad pesa aunque rindan (antes casi no se notaba si jugaban mucho)
                c["edad"] = round(_efecto_edad(edad) * (1 - 0.3 * f["confianza"]), 2)
            f["crudo"] = sum(c.values())

        # misma escala de la liga (media y desviación), sin contar a los agregados a mano
        base = [f for f in filas if not f["jugador"].get("manual")] or filas
        media = sum(f["crudo"] for f in base) / len(base)
        desv = math.sqrt(sum((f["crudo"] - media) ** 2 for f in base) / len(base)) or 1
        forzados = getattr(self, "forzados", {})
        e = self.escala
        for f in filas:
            f["ovr"] = int(max(e["min"], min(e["max"], round(e["media"] + e["desv"] * (f["crudo"] - media) / desv))))
            manual = forzados.get(str(f["jugador"].get("id_365")))
            if manual:
                f["componentes"]["manual"] = int(manual) - f["ovr"]
                f["ovr"] = int(manual)
            # atributos y precio salen de la media nueva
            f["atributos"] = self._atributos(f)
            fijos = getattr(self, "atributos_fijos", {}).get(str(f["jugador"].get("id_365")))
            if fijos:
                f["atributos"].update(fijos)
            f["precio"] = precio(f["ovr"], f["edad"])
        return filas
