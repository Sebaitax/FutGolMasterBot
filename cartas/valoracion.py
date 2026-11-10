"""Cálculo de la valoración (OVR), los atributos y el precio de cada jugador.

Método (inspirado en FBref, TransferRoom y scoutingstats.ai):

1. Base: nivel del club (puntos por partido de la temporada), edad, rol en el
   plantel (dorsal), trayectoria (partidos en clubes ponderados por el nivel de
   la liga) y partidos con la selección adulta.
2. Rendimiento de la temporada: goles y asistencias por partido convertidos a
   percentil dentro de la misma línea (DEL, MED, DEF), "jugador de la fecha" y,
   para arqueros, goles recibidos por partido y vallas invictas.
3. Confianza: el rendimiento pesa según los partidos jugados; con pocos partidos
   el jugador queda cerca del promedio de su posición.
4. La suma se lleva a una escala fija (media y desviación) para que los OVR
   tengan un rango de liga sudamericana (≈50-84).
5. Atributos (PAC, SHO, PAS, DRI, DEF, PHY) según el arquetipo del puesto,
   ajustados por edad, estatura y aporte goleador. Precio propio según OVR y edad.

Uso:
    python -m cartas.valoracion --liga chile         # -> data/cartas_liga_chile_2026.csv
    python -m cartas.valoracion --liga argentina     # -> data/cartas_liga_argentina_2026.csv

Si la liga no tiene datos de rendimiento (goles, arqueros), ese componente queda neutro
y el OVR sale del club, la edad, el rol, la trayectoria y la selección.
"""
import argparse
import csv
import hashlib
import json
import math
import random
from datetime import date
from pathlib import Path

from scraper.ligas import archivo_cartas, archivo_planteles, archivo_stats, liga

# Escala final de OVR (por defecto; cada liga define la suya en scraper/ligas.py)
MEDIA_OVR, DESV_OVR, MIN_OVR, MAX_OVR = 63.5, 6.0, 48, 84

# Peso de cada componente (en puntos de OVR "crudos", antes de escalar)
PESOS = {
    "club": 7.0,          # de peor a mejor equipo de la tabla
    "trayectoria": 6.0,   # carrera en ligas de mayor nivel
    "seleccion": 4.0,     # partidos con la selección adulta
    "jugador_fecha": 1.5, # por cada premio (máximo 4)
    "rendimiento": {"DEL": 15.0, "MED": 9.0, "DEF": 3.5, "POR": 9.0},
}

# Arquetipos: diferencia de cada atributo respecto del OVR
ARQUETIPOS = {
    "ST": dict(PAC=2, SHO=5, PAS=-7, DRI=0, DEF=-38, PHY=3),
    "LW": dict(PAC=7, SHO=0, PAS=-3, DRI=5, DEF=-38, PHY=-8),
    "RW": dict(PAC=7, SHO=0, PAS=-3, DRI=5, DEF=-38, PHY=-8),
    "CAM": dict(PAC=0, SHO=0, PAS=4, DRI=5, DEF=-30, PHY=-10),
    "CM": dict(PAC=-4, SHO=-4, PAS=4, DRI=2, DEF=-8, PHY=0),
    "LM": dict(PAC=5, SHO=-4, PAS=2, DRI=3, DEF=-20, PHY=-4),
    "RM": dict(PAC=5, SHO=-4, PAS=2, DRI=3, DEF=-20, PHY=-4),
    "CDM": dict(PAC=-8, SHO=-12, PAS=0, DRI=-4, DEF=4, PHY=5),
    "CB": dict(PAC=-10, SHO=-35, PAS=-12, DRI=-18, DEF=5, PHY=5),
    "LB": dict(PAC=4, SHO=-28, PAS=-4, DRI=-4, DEF=0, PHY=-2),
    "RB": dict(PAC=4, SHO=-28, PAS=-4, DRI=-4, DEF=0, PHY=-2),
    # Arqueros: columnas = estirada, manos, saque, reflejos, velocidad, colocación
    "GK": dict(PAC=2, SHO=-2, PAS=-12, DRI=3, DEF=-30, PHY=1),
}

# Posición detallada desde las etiquetas de Wikidata
DETALLE = [
    ("extremo izquierdo", "LW"), ("extremo derecho", "RW"), ("extremo", "LW"),
    ("lateral izquierdo", "LB"), ("lateral derecho", "RB"), ("lateral", "RB"), ("carrilero", "LB"),
    ("defensor central", "CB"), ("defensa central", "CB"), ("líbero", "CB"),
    ("volante de dirección", "CDM"), ("pivote", "CDM"), ("mediocentro defensivo", "CDM"),
    ("mediapunta", "CAM"), ("centrocampista ofensivo", "CAM"), ("enganche", "CAM"),
    ("delantero centro", "ST"), ("segundo delantero", "ST"),
]
# Reparto cuando solo se conoce la línea (se asigna en orden de dorsal dentro del club)
CICLO = {"POR": ["GK"], "DEF": ["CB", "RB", "CB", "LB"], "MED": ["CM", "CDM", "CAM", "RM", "CM", "LM"],
         "DEL": ["ST", "LW", "RW", "ST"]}
LINEA = {"GK": "POR", "CB": "DEF", "LB": "DEF", "RB": "DEF", "CDM": "MED", "CM": "MED", "CAM": "MED",
         "LM": "MED", "RM": "MED", "LW": "DEL", "RW": "DEL", "ST": "DEL"}

PAISES = {"MAR": "Marruecos", "DNK": "Dinamarca", "RDC": "RD del Congo", "GNB": "Guinea-Bisáu", "GUI": "Guinea",
    "CHI": "Chile", "CHL": "Chile", "ARG": "Argentina", "URU": "Uruguay", "PAR": "Paraguay",
          "COL": "Colombia", "VEN": "Venezuela", "ECU": "Ecuador", "PER": "Perú", "BOL": "Bolivia",
          "BRA": "Brasil", "MEX": "México", "ESP": "España", "CPV": "Cabo Verde", "USA": "Estados Unidos",
          "PAN": "Panamá", "CRC": "Costa Rica", "HAI": "Haití", "ITA": "Italia", "FRA": "Francia",
          "ESA": "El Salvador", "HON": "Honduras", "GUA": "Guatemala", "ALE": "Alemania", "GER": "Alemania",
          "POR": "Portugal", "NED": "Países Bajos", "BEL": "Bélgica", "CRO": "Croacia", "SRB": "Serbia",
          "JPN": "Japón", "NGA": "Nigeria", "GHA": "Ghana", "SEN": "Senegal", "CIV": "Costa de Marfil",
          "CMR": "Camerún", "ANG": "Angola", "DOM": "República Dominicana", "CUB": "Cuba", "LIB": "Líbano",
          "SUI": "Suiza", "AUT": "Austria", "SWE": "Suecia", "DEN": "Dinamarca", "ENG": "Inglaterra",
          "IRL": "Irlanda", "ISR": "Israel", "GRE": "Grecia", "RUS": "Rusia", "UKR": "Ucrania",
          "AR": "Argentina", "PRY": "Paraguay", "SYR": "Siria", "ARM": "Armenia", "PUR": "Puerto Rico",
          "SVN": "Eslovenia", "URY": "Uruguay", "CL": "Chile", "UY": "Uruguay", "PY": "Paraguay"}


def _semilla(texto: str) -> int:
    return int(hashlib.md5(texto.encode("utf-8")).hexdigest()[:8], 16)


def _edad(nacimiento: str, hoy: date) -> float | None:
    try:
        n = date.fromisoformat(nacimiento)
    except ValueError:
        return None
    return (hoy - n).days / 365.25


def _clave(nombre: str) -> str:
    return nombre.split("(")[0].strip().lower()


def _percentil(valor: float, poblacion: list[float]) -> float:
    if not poblacion:
        return 0.5
    menores = sum(1 for v in poblacion if v < valor)
    iguales = sum(1 for v in poblacion if v == valor)
    return (menores + 0.5 * iguales) / len(poblacion)


def _efecto_edad(edad: float | None) -> float:
    if edad is None:
        return 0.0
    if edad < 24:
        return -(24 - edad) * 1.7
    if edad <= 31:
        return min(edad - 24, 3) * 0.4
    return max(-3.5, 1.2 - (edad - 31) * 0.6)  # el declive tiene tope: el rendimiento manda


def _efecto_dorsal(dorsal: str) -> float:
    try:
        n = int(dorsal)
    except ValueError:
        return -1.0
    if n <= 11:
        return 2.0
    if n <= 25:
        return 0.0
    return -2.5  # juveniles y tercer arquero suelen usar números altos


class Valorador:
    def __init__(self, planteles: dict, stats: dict, hoy: date | None = None, escala: dict | None = None):
        self.planteles = planteles
        self.stats = stats
        self.escala = escala or {"media": MEDIA_OVR, "desv": DESV_OVR, "min": MIN_OVR, "max": MAX_OVR}
        self.hoy = hoy or date.fromisoformat(stats.get("actualizado") or date.today().isoformat())
        self._preparar()

    # ------------------------------------------------------------ preparación

    def _preparar(self):
        tabla = self.stats["tabla"]
        ppg = {club: t["puntos"] / max(t["pj"], 1) for club, t in tabla.items()}
        lo, hi = min(ppg.values()), max(ppg.values())
        self.nivel_club = {club: (v - lo) / (hi - lo or 1) for club, v in ppg.items()}
        self.pj_equipo = max(t["pj"] for t in tabla.values())

        self.ga = {}
        for r in self.stats["goles_asistencias"]:
            for k in filter(None, (r["wiki_es"], _clave(r["nombre"]))):
                self.ga[k] = r
        self.pj = {_clave(k): v for k, v in self.stats["partidos_jugados"].items()} | self.stats["partidos_jugados"]
        self.arqueros = {}
        for a in self.stats["arqueros"]:
            for k in filter(None, (a["wiki_es"], _clave(a["nombre"]))):
                self.arqueros[k] = a
        self.premios = {_clave(k): v for k, v in self.stats["jugador_de_la_fecha"].items()}
        self.perfil = {t: self.stats["perfiles"].get(q, {}) for t, q in self.stats["wikidata"].items()}

    def _club_en_tabla(self, club: str) -> str:
        """Nombre del club tal como aparece en la tabla de posiciones."""
        nombre = club.lower()
        sin_paren = lambda c: c.lower().split(" (")[0]
        for criterio in (lambda c: c.lower() == nombre,                       # idéntico
                         lambda c: sin_paren(c) == nombre.split(" (")[0]):     # "Sarmiento" = "Sarmiento (J)"
            hallados = [c for c in self.nivel_club if criterio(c)]
            if len(hallados) == 1:
                return hallados[0]
        contenidos = [c for c in self.nivel_club if sin_paren(c) in nombre]   # el más largo gana
        if contenidos:
            return max(contenidos, key=len)
        return max(self.nivel_club, key=lambda c: len(set(c.lower().split()) & set(nombre.split())))

    def _buscar(self, dic: dict, j: dict):
        return dic.get(j["wiki_es"]) or dic.get(_clave(j["nombre"]))

    # ------------------------------------------------------------ posiciones

    def _puestos(self, jugadores: list[dict]) -> dict:
        puestos, contador = {}, {k: 0 for k in CICLO}
        orden = sorted(jugadores, key=lambda j: int(j["dorsal"]) if j["dorsal"].isdigit() else 99)
        for j in orden:
            linea = j["posicion"] if j["posicion"] in CICLO else "MED"
            detalle = " ".join(self.perfil.get(j["wiki_es"], {}).get("posiciones", [])).lower()
            puesto = next((p for txt, p in DETALLE if txt in detalle and LINEA[p] == linea), None)
            if not puesto:
                ciclo = CICLO[linea]
                puesto = ciclo[contador[linea] % len(ciclo)]
                contador[linea] += 1
            puestos[id(j)] = puesto
        return puestos

    # ------------------------------------------------------------ componentes

    def _rendimiento_campo(self, j: dict, linea: str) -> tuple[float, float, dict]:
        """(percentil 0-1, confianza 0-1, detalle) del aporte goleador por partido."""
        if not self.ga:
            return 0.0, 0.0, {"goles": 0, "asistencias": 0, "pj_estimado": 1}  # sin datos: neutro
        r = self._buscar(self.ga, j)
        goles, asis = (r["goles"], r["asistencias"]) if r else (0, 0)
        pj = self._buscar(self.pj, j) or 0
        if not pj:
            # Sin PJ publicado: si aportó, estimamos 2/3 de los partidos; si no, rol menor
            pj = round(self.pj_equipo * 0.66) if r else round(self.pj_equipo * 0.35)
        aporte = (goles * 1.0 + asis * 0.7) / max(pj, 1)
        confianza = min(1.0, pj / 15) * (1.0 if r else 0.6)
        return aporte, confianza, {"goles": goles, "asistencias": asis, "pj_estimado": pj}

    def _rendimiento_arquero(self, j: dict, promedio_gc: float) -> tuple[float, float, dict]:
        if not self.arqueros:
            return 0.5, 0.0, {}  # la liga no publica datos de arqueros: componente neutro
        a = self._buscar(self.arqueros, j)
        if not a or a["pj"] == 0:
            return 0.25, 0.6, {"pj": 0}  # arquero suplente sin minutos
        gc = a["goles_recibidos"] / a["pj"]
        invicta = a["vallas_invictas"] / a["pj"]
        puntaje = 0.5 + 0.35 * (promedio_gc - gc) / max(promedio_gc, 0.1) + 0.6 * (invicta - 0.25) + 0.03 * a["penales_atajados"]
        return max(0.0, min(1.0, puntaje)), min(1.0, a["pj"] / 15), {"pj": a["pj"], "gc_por_partido": round(gc, 2),
                                                                     "vallas_invictas": a["vallas_invictas"]}

    # ------------------------------------------------------------ cálculo

    def calcular(self) -> list[dict]:
        filas = []
        arq = [a for a in self.stats["arqueros"] if a["pj"] >= 5]
        promedio_gc = sum(a["goles_recibidos"] for a in arq) / max(sum(a["pj"] for a in arq), 1)

        for club in self.planteles["clubes"]:
            nombre_tabla = self._club_en_tabla(club["club"])
            puestos = self._puestos(club["jugadores"])
            for j in club["jugadores"]:
                puesto = puestos[id(j)]
                linea = LINEA[puesto]
                edad = _edad(j["nacimiento"], self.hoy)
                perfil = self.perfil.get(j["wiki_es"], {})
                if linea == "POR":
                    valor, conf, detalle = self._rendimiento_arquero(j, promedio_gc)
                else:
                    valor, conf, detalle = self._rendimiento_campo(j, linea)
                filas.append({"jugador": j, "club": club["club"], "club_tabla": nombre_tabla, "puesto": puesto,
                              "linea": linea, "edad": edad, "perfil": perfil, "valor": valor, "confianza": conf,
                              "detalle": detalle})

        # percentiles del aporte dentro de cada línea (solo jugadores con confianza razonable)
        for linea in ("DEL", "MED", "DEF"):
            pobl = [f["valor"] for f in filas if f["linea"] == linea and f["confianza"] >= 0.5]
            for f in filas:
                if f["linea"] == linea:
                    f["percentil"] = _percentil(f["valor"], pobl)
        for f in filas:
            if f["linea"] == "POR":
                f["percentil"] = f["valor"]

        # puntaje crudo
        for f in filas:
            j, perfil = f["jugador"], f["perfil"]
            comp = {
                "club": PESOS["club"] * (self.nivel_club[f["club_tabla"]] - 0.5),
                "edad": _efecto_edad(f["edad"]),
                "dorsal": _efecto_dorsal(j["dorsal"]),
                "trayectoria": PESOS["trayectoria"] * min(1.0, math.log1p(perfil.get("trayectoria", 0) / 40) / math.log1p(10)),
                "seleccion": PESOS["seleccion"] * min(1.0, perfil.get("partidos_seleccion", 0) / 60),
                "jugador_fecha": PESOS["jugador_fecha"] * min(4, self.premios.get(_clave(j["nombre"]), 0)),
                "rendimiento": PESOS["rendimiento"][f["linea"]] * (f["percentil"] - 0.5) * f["confianza"],
                "azar": random.Random(_semilla(j["nombre"] + club_seed(f))).gauss(0, 1.0),
            }
            f["componentes"] = {k: round(v, 2) for k, v in comp.items()}
            f["crudo"] = sum(comp.values())

        # escala final
        media = sum(f["crudo"] for f in filas) / len(filas)
        desv = math.sqrt(sum((f["crudo"] - media) ** 2 for f in filas) / len(filas)) or 1
        for f in filas:
            z = (f["crudo"] - media) / desv
            e = self.escala
            f["ovr"] = int(max(e["min"], min(e["max"], round(e["media"] + e["desv"] * z))))
            f["atributos"] = self._atributos(f)
            f["precio"] = precio(f["ovr"], f["edad"])
        return filas

    def _atributos(self, f: dict) -> dict:
        rng = random.Random(_semilla("attr" + f["jugador"]["nombre"]))
        ovr, edad = f["ovr"], f["edad"] or 27
        attrs = {k: ovr + d for k, d in ARQUETIPOS[f["puesto"]].items()}
        if f["linea"] != "POR":
            attrs["PAC"] += -max(0, edad - 28) * 0.9 + max(0, 23 - edad) * 0.8
            attrs["PHY"] += -max(0, edad - 31) * 0.8 - max(0, 22 - edad) * 1.0
            attrs["PAS"] += max(0, min(edad, 33) - 26) * 0.4
            alt = f["perfil"].get("estatura_cm")
            if alt:
                attrs["PHY"] += (alt - 178) * 0.25
                attrs["PAC"] -= max(0, alt - 186) * 0.3
            d = f["detalle"]
            pj = max(d.get("pj_estimado", 1), 1)
            attrs["SHO"] += min(6, d.get("goles", 0) / pj * 12)
            attrs["PAS"] += min(5, d.get("asistencias", 0) / pj * 14)
        for k in attrs:
            attrs[k] = int(max(15, min(95, round(attrs[k] + rng.gauss(0, 2.2)))))
        return attrs


def club_seed(f: dict) -> str:
    return f["club"]


def precio(ovr: int, edad: float | None) -> int:
    """Precio propio en monedas del juego (no es un valor de mercado real)."""
    base = 400 * 1.17 ** (ovr - 50)
    e = edad or 27
    factor = 1.35 if e <= 21 else 1.2 if e <= 24 else 1.0 if e <= 29 else 0.8 if e <= 32 else 0.6
    bruto = base * factor
    paso = 50 if bruto < 5000 else 250 if bruto < 50000 else 1000
    return int(round(bruto / paso) * paso)


def _alias(nombre: str) -> str:
    limpio = nombre.split("(")[0].strip()
    partes = limpio.split()
    return partes[-1] if len(partes) == 2 else limpio


def main():
    p = argparse.ArgumentParser(description="Calcula OVR, atributos y precio de los jugadores.")
    p.add_argument("--liga", default="chile")
    p.add_argument("--anio", type=int, default=2026)
    p.add_argument("--salida", default=None)
    args = p.parse_args()
    cfg = liga(args.liga)

    planteles = json.loads(Path(archivo_planteles(args.liga, args.anio)).read_text(encoding="utf-8"))
    stats = json.loads(Path(archivo_stats(args.liga, args.anio)).read_text(encoding="utf-8"))
    filas = Valorador(planteles, stats, escala=cfg["ovr"]).calcular()
    # apellidos de 365Scores para quienes en Wikipedia tienen un solo nombre ("Danilo" -> "Danilo Santos");
    # se aplican después de calcular para no cambiar las valoraciones (el nombre es semilla del azar)
    ruta_nombres = Path(f"data/nombres_365_{args.liga}_{args.anio}.json")
    if ruta_nombres.exists():
        completos = json.loads(ruta_nombres.read_text(encoding="utf-8"))
        for club in planteles["clubes"]:
            for j in club["jugadores"]:
                nuevo = completos.get(club["club"], {}).get(f"{j['nombre'].split('(')[0].strip()}|{j.get('dorsal', '')}")
                if nuevo:
                    j["nombre"] = nuevo

    # planteles como están hoy en 365Scores (scraper.fotos_365 --depurar): fuera juveniles y ex jugadores,
    # y traspasos dentro de la liga. Se aplica después de calcular para no mover el OVR de los demás.
    ruta_ajustes = Path(f"data/ajustes_365_{args.liga}_{args.anio}.json")
    if ruta_ajustes.exists():
        ajustes = json.loads(ruta_ajustes.read_text(encoding="utf-8"))
        excluir = set(ajustes.get("excluir", []))
        clave = lambda f: f'{f["jugador"]["nombre"].split("(")[0].strip()}|{f["club_tabla"]}'
        for f in filas:
            if clave(f) in ajustes.get("traspasos", {}):
                f["club_tabla"] = ajustes["traspasos"][clave(f)]
        antes = len(filas)
        filas = [f for f in filas if clave(f) not in excluir]
        print(f"Ajustes 365Scores: {antes - len(filas)} excluidos, {len(ajustes.get('traspasos', {}))} traspasos")

    salida = Path(args.salida or archivo_cartas(args.liga, args.anio))
    columnas = ["Nombre", "Alias", "Posición", "Club", "Nación", "Liga", "OVR", "PAC", "SHO", "PAS", "DRI", "DEF",
                "PHY", "Precio", "Edad", "Dorsal"]
    # alias únicos dentro de cada club ("V. Méndez" si hay dos Méndez)
    alias = {}
    por_club = {}
    for f in filas:
        por_club.setdefault(f["club_tabla"], []).append(f)
    for grupo in por_club.values():
        cuenta = {}
        for f in grupo:
            a = _alias(f["jugador"]["nombre"])
            cuenta[a] = cuenta.get(a, 0) + 1
        for f in grupo:
            a = _alias(f["jugador"]["nombre"])
            nombre = f["jugador"]["nombre"].split("(")[0].strip().split()
            alias[id(f)] = f"{nombre[0][0]}. {a}" if cuenta[a] > 1 and len(nombre) > 1 and a != " ".join(nombre) else a

    with salida.open("w", newline="", encoding="utf-8") as archivo:
        w = csv.DictWriter(archivo, fieldnames=columnas)
        w.writeheader()
        for f in sorted(filas, key=lambda f: -f["ovr"]):
            j = f["jugador"]
            w.writerow({"Nombre": j["nombre"].split("(")[0].strip(), "Alias": alias[id(f)],
                        "Posición": f["puesto"], "Club": f["club_tabla"],
                        "Nación": PAISES.get(j["nacionalidad"]) or j["nacionalidad"].title(), "Liga": cfg["nombre"],
                        "OVR": f["ovr"], **f["atributos"], "Precio": f["precio"],
                        "Edad": int(f["edad"]) if f["edad"] else "", "Dorsal": j["dorsal"]})

    # desglose para revisar por qué cada jugador tiene su OVR
    desglose = {f["jugador"]["nombre"]: {"club": f["club_tabla"], "puesto": f["puesto"], "ovr": f["ovr"],
                                         "componentes": f["componentes"], "detalle": f["detalle"],
                                         "confianza": round(f["confianza"], 2)} for f in filas}
    salida.with_suffix(".desglose.json").write_text(json.dumps(desglose, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {len(filas)} jugadores -> {salida}")


if __name__ == "__main__":
    main()
