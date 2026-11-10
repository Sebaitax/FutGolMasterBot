"""Simula un partido desde la terminal con cartas de los CSV de data/.

Ejemplos:
    python -m partidos.simular --local "Real Madrid" --visita "Manchester City"
    python -m partidos.simular --aleatorio --semilla 7 --tipo liga
    python -m partidos.simular --local "Arsenal" --visita "Liverpool" --en-vivo
"""
import argparse
import csv
import glob
import random
import sys
import time

from models.carta import Carta
from partidos.motor import FORMACIONES, Jugador, armar_equipo, simular
from partidos.narrador import narrar

DURACION_EN_VIVO = 180  # segundos que dura un partido "en vivo" (3 minutos)


def cargar_cartas(rutas: list[str]) -> list[Carta]:
    cartas, vistos = [], set()
    for ruta in rutas:
        rara = "rara" in ruta.lower()
        with open(ruta, newline="", encoding="utf-8") as archivo:
            for fila in csv.DictReader(archivo):
                carta = Carta.desde_csv(fila, rara=rara)
                if carta.nombre not in vistos:
                    vistos.add(carta.nombre)
                    cartas.append(carta)
    return cartas


def plantel_de_club(cartas: list[Carta], club: str) -> list[Jugador]:
    jugadores = [Jugador(c) for c in cartas if c.club.lower() == club.lower()]
    if len(jugadores) < 11:
        sys.exit(f"'{club}' tiene solo {len(jugadores)} cartas en los CSV (se necesitan 11).")
    return jugadores


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Simula y narra un partido.")
    p.add_argument("--csv", nargs="*", default=sorted(glob.glob("data/cartas_*.csv")), help="CSV de cartas")
    p.add_argument("--local", help="Club local (según la columna Club)")
    p.add_argument("--visita", help="Club visitante")
    p.add_argument("--aleatorio", action="store_true", help="Arma dos equipos con cartas al azar")
    p.add_argument("--formacion", default="4-3-3", choices=FORMACIONES)
    p.add_argument("--formacion-visita", default=None, choices=FORMACIONES)
    p.add_argument("--tipo", default="amistoso", choices=["amistoso", "liga"])
    p.add_argument("--semilla", type=int, default=None)
    p.add_argument("--en-vivo", action="store_true", help="Narra con pausas, como en Discord")
    args = p.parse_args()

    cartas = cargar_cartas(args.csv)
    rng = random.Random(args.semilla)
    if args.aleatorio or not (args.local and args.visita):
        muestra = rng.sample(cartas, 36)
        a, b = [Jugador(c) for c in muestra[:18]], [Jugador(c) for c in muestra[18:]]
        nombres = (args.local or "Los Halcones", args.visita or "Deportivo Tormenta")
    else:
        a, b = plantel_de_club(cartas, args.local), plantel_de_club(cartas, args.visita)
        nombres = (args.local, args.visita)

    local = armar_equipo(nombres[0], a, args.formacion)
    visita = armar_equipo(nombres[1], b, args.formacion_visita or args.formacion)
    for eq in (local, visita):
        once = ", ".join(f"{j.nombre} ({j.carta.ovr})" for j in eq.titulares)
        print(f"📋 {eq.nombre} [{eq.formacion}]: {once}")
    print()

    resultado = simular(local, visita, tipo=args.tipo, semilla=args.semilla)
    lineas = narrar(resultado, semilla=args.semilla)
    pausa = DURACION_EN_VIVO / max(len(lineas), 1) if args.en_vivo else 0
    for linea in lineas:
        print(str(linea).replace("**", ""))
        if pausa:
            time.sleep(pausa)


if __name__ == "__main__":
    main()
