"""Compara la valoración actual (Valorador365) con la propuesta v2 sin tocar las cartas del juego.

    python -m scripts.comparar_valoracion                 # todas las ligas, resumen
    python -m scripts.comparar_valoracion --liga chile --top 30 --ver "Víctor Méndez" "Arturo Vidal"
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import date
from pathlib import Path

from cartas.valoracion import Valorador365
from cartas.valoracion_v2 import Valorador365v2, enriquecer
from scraper.fotos_365 import COMPETICION
from scraper.ligas import archivo_planteles, archivo_stats, liga


def valorar(clave: str, anio: int = 2026):
    cfg = liga(clave)
    planteles = json.loads(Path(archivo_planteles(clave, anio)).read_text(encoding="utf-8"))
    stats = json.loads(Path(archivo_stats(clave, anio)).read_text(encoding="utf-8"))
    manual = Path(f"data/ovr_manual_{clave}_{anio}.json")
    forzados = {k: v["ovr"] for k, v in json.loads(manual.read_text(encoding="utf-8")).items()} if manual.exists() else {}
    viejo = Valorador365(copy.deepcopy(planteles), stats, escala=cfg["ovr"])
    viejo.forzados = forzados
    nuevos_planteles = copy.deepcopy(planteles)
    hoy = date.today()
    for club in nuevos_planteles["clubes"]:
        for j in club["jugadores"]:
            enriquecer(j, COMPETICION[clave], hoy)
    nuevo = Valorador365v2(nuevos_planteles, stats, escala=cfg["ovr"])
    nuevo.forzados = forzados
    a = {f["jugador"]["nombre"]: f for f in viejo.calcular() if f["jugador"].get("tiene_foto", True)}
    b = {f["jugador"]["nombre"]: f for f in nuevo.calcular() if f["jugador"].get("tiene_foto", True)}
    return a, b, set(forzados)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--liga", default=None)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--ver", nargs="*", default=[])
    a = ap.parse_args()
    ligas = [a.liga] if a.liga else list(COMPETICION)
    for clave in ligas:
        viejo, nuevo, manuales = valorar(clave)
        comunes = [n for n in viejo if n in nuevo and str(viejo[n]["jugador"].get("id_365")) not in manuales]
        dif = {n: nuevo[n]["ovr"] - viejo[n]["ovr"] for n in comunes}
        media_abs = sum(abs(d) for d in dif.values()) / max(len(dif), 1)
        print(f"\n===== {liga(clave)['nombre']} ({clave}) · {len(comunes)} jugadores · cambio medio ±{media_abs:.1f} · "
              f"suben {sum(d > 0 for d in dif.values())}, bajan {sum(d < 0 for d in dif.values())}, igual {sum(d == 0 for d in dif.values())}")
        if a.liga:
            print(f"\nTop {a.top} con la fórmula NUEVA (entre paréntesis, la actual):")
            for i, n in enumerate(sorted(comunes, key=lambda n: -nuevo[n]["ovr"])[:a.top], 1):
                f = nuevo[n]
                c = f["componentes"]
                print(f"{i:>3}. {nuevo[n]['ovr']:>2} ({viejo[n]['ovr']:>2}, {dif[n]:+d})  {n:<26} {f['club_tabla'][:22]:<22} {f['puesto']:<4}"
                      f" prod {c.get('produccion', 0):+.1f} precio {c.get('precio', 0):+.1f} club {c.get('club', 0):+.1f}")
        print("\nLos que más suben:")
        for n in sorted(comunes, key=lambda n: -dif[n])[:6]:
            print(f"   {viejo[n]['ovr']} -> {nuevo[n]['ovr']} ({dif[n]:+d})  {n} · {nuevo[n]['club_tabla']} · {nuevo[n]['puesto']}")
        print("Los que más bajan:")
        for n in sorted(comunes, key=lambda n: dif[n])[:6]:
            print(f"   {viejo[n]['ovr']} -> {nuevo[n]['ovr']} ({dif[n]:+d})  {n} · {nuevo[n]['club_tabla']} · {nuevo[n]['puesto']}")
        for n in a.ver:
            if n in nuevo and n in viejo:
                print(f"\n>> {n}: {viejo[n]['ovr']} -> {nuevo[n]['ovr']}")
                print("   actual:", viejo[n]["componentes"])
                print("   nueva: ", nuevo[n]["componentes"])
                print("   stats: ", {k: v for k, v in (nuevo[n]["jugador"].get("stats") or {}).items()
                                   if k in ("pj", "minutos", "puntaje", "goles", "asistencias", "xg", "xa", "toques", "xga", "goles_recibidos", "atajadas")},
                      "traspaso:", nuevo[n]["jugador"].get("traspaso"))


if __name__ == "__main__":
    main()
