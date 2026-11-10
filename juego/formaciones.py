"""Ubicación de los puestos en la cancha, enlaces entre compañeros y química.

Química (solo afecta a tu club; los bots quedan neutros):
- Cada puesto está enlazado con sus vecinos en la cancha.
- Enlace verde = mismo club (2 pts), amarillo = misma nación (1 pt), rojo = nada (0).
- La química de un jugador es el promedio de sus enlaces (0 a 1). Si juega fuera de
  su posición (rinde menos del 90%), vale la mitad.
- En el partido rinde entre 0,97 y 1,03 según su química.
"""
from __future__ import annotations

import math

from partidos.motor import FORMACIONES, afinidad

# (x, y) en % del ancho y alto de la cancha; tu arco abajo. Mismo orden que FORMACIONES.
# Separación pensada para cartas de ~14% del ancho: dos cartas que se cruzan en horizontal
# (a menos de 16 puntos) están al menos a 17 puntos en vertical.
COORDENADAS = {
    "4-3-3": [(50, 91), (12, 68), (37, 74), (63, 74), (88, 68), (27, 43), (50, 51), (73, 43), (16, 18), (50, 11), (84, 18)],
    "4-4-2": [(50, 91), (12, 68), (37, 74), (63, 74), (88, 68), (12, 42), (37, 47), (63, 47), (88, 42), (35, 14), (65, 14)],
    "4-2-3-1": [(50, 91), (12, 68), (37, 74), (63, 74), (88, 68), (35, 54), (65, 54), (15, 32), (50, 32), (85, 32), (50, 10)],
    "3-5-2": [(50, 92), (24, 72), (50, 75), (76, 72), (9, 45), (30, 43), (50, 55), (70, 43), (91, 45), (35, 14), (65, 14)],
    "5-3-2": [(50, 92), (9, 59), (29, 72), (50, 75), (71, 72), (91, 59), (25, 42), (50, 46), (75, 42), (35, 14), (65, 14)],
}
VECINOS = 2  # cada puesto se enlaza con sus 2 compañeros más cercanos


def _enlaces(formacion: str) -> list[tuple[int, int]]:
    pts = COORDENADAS[formacion]
    dist = lambda a, b: math.hypot((pts[a][0] - pts[b][0]) * 0.68, (pts[a][1] - pts[b][1]) * 0.88)
    pares = set()
    for i in range(len(pts)):
        cercanos = sorted((j for j in range(len(pts)) if j != i), key=lambda j: dist(i, j))[:VECINOS]
        pares.update(tuple(sorted((i, j))) for j in cercanos)
    return sorted(pares)


ENLACES = {f: _enlaces(f) for f in FORMACIONES}


def valor_enlace(a, b) -> int:
    """a y b son Cartas. 2 = mismo club, 1 = misma nación, 0 = sin relación."""
    if a.club and a.club == b.club:
        return 2
    if a.nacion and a.nacion == b.nacion:
        return 1
    return 0


def quimica(formacion: str, cartas: list) -> dict:
    """`cartas`: 11 Cartas (o None) en el orden de la formación.

    Devuelve {"enlaces": [(i, j, valor)], "jugadores": [0..1 por puesto], "equipo": 0..100}.
    """
    puestos = FORMACIONES[formacion]
    enlaces, suma, cuenta = [], [0.0] * 11, [0] * 11
    for i, j in ENLACES[formacion]:
        a, b = cartas[i], cartas[j]
        v = valor_enlace(a, b) if a and b else 0
        enlaces.append((i, j, v))
        for k in (i, j):
            suma[k] += v / 2
            cuenta[k] += 1
    jugadores = []
    for k in range(11):
        c = cartas[k]
        q = suma[k] / cuenta[k] if cuenta[k] and c else 0.0
        if c and afinidad(c.posicion, puestos[k]) < 0.9:
            q /= 2
        jugadores.append(round(q, 3))
    equipo = round(100 * sum(jugadores) / 11)
    return {"enlaces": enlaces, "jugadores": jugadores, "equipo": equipo}


def factor_quimica(q: float) -> float:
    return 0.97 + 0.06 * q
