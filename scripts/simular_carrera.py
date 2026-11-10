"""Simula carreras completas con un jugador automático para calibrar la dificultad.

Uso:
    python -m scripts.simular_carrera --carreras 10 --temporadas 4 --estrategia oro

Estrategias de compra:
    oro       ahorra y compra solo sobres oro
    plata     compra un sobre plata cada vez que le alcanza
Después de cada compra vende lo que sobra (se queda con los mejores PLANTEL_MAX).
"""
import argparse
import statistics
import sys
import time

from juego.bd import conectar
from juego.economia import SOBRES, valor_venta
from juego.partida import Partida

PLANTEL_MAX = 26


def depurar(partida: Partida):
    fichas = partida.plantel()
    arqueros = [f for f in fichas if f.carta.posicion == "GK"]
    sobran = sorted((f for f in fichas if f not in arqueros[:2]), key=lambda f: f.carta.ovr)
    while len(partida.plantel()) > PLANTEL_MAX and sobran:
        partida.vender(sobran.pop(0).pid)


def comprar(partida: Partida, estrategia: str):
    sobre = SOBRES[estrategia]
    while partida.monedas >= sobre["precio"]:
        partida.abrir_sobre(estrategia)
        depurar(partida)


def carrera(semilla: int, temporadas: int, estrategia: str) -> list[dict]:
    p = Partida(conectar(":memory:"))
    p.crear("Bot FC", semilla=semilla)
    for t in range(temporadas):
        while not p.temporada_terminada:
            comprar(p, estrategia)
            p.alinear_auto()
            p.jugar_fecha()
        if t < temporadas - 1:
            p.nueva_temporada()
    once = sorted((f.carta.ovr for f in p.plantel()), reverse=True)[:11]
    hist = p.historial
    hist[-1]["once_final"] = round(sum(once) / 11, 1)
    return hist


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser()
    a.add_argument("--carreras", type=int, default=10)
    a.add_argument("--temporadas", type=int, default=4)
    a.add_argument("--estrategia", default="oro", choices=["oro", "plata"])
    args = a.parse_args()

    inicio = time.time()
    por_temporada: dict[int, list[int]] = {}
    once_final, titulos = [], 0
    for c in range(args.carreras):
        hist = carrera(1000 + c, args.temporadas, args.estrategia)
        for h in hist:
            por_temporada.setdefault(h["temporada"], []).append(h["posicion"])
        titulos += any(h["posicion"] == 1 for h in hist)
        once_final.append(hist[-1]["once_final"])
        ruta = " → ".join(f"{h['nombre_division'].split()[-1]} {h['posicion']}°" for h in hist)
        print(f"carrera {c + 1}: {ruta} · once final {hist[-1]['once_final']}", flush=True)

    print(f"\nEstrategia {args.estrategia} · {args.carreras} carreras · {time.time() - inicio:.0f}s")
    for t, pos in sorted(por_temporada.items()):
        print(f"Temporada {t}: posición media {statistics.mean(pos):.1f} · mejor {min(pos)} · peor {max(pos)}"
              f" · top 4: {sum(p <= 4 for p in pos)}/{len(pos)} · campeón: {sum(p == 1 for p in pos)}/{len(pos)}")
    print(f"Carreras con al menos un título: {titulos}/{args.carreras} · once final medio {statistics.mean(once_final):.1f}")


if __name__ == "__main__":
    main()
