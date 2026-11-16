"""Simulación masiva de carreras con bots que usan TODO el juego, para encontrar bugs y medir el balance.

Cada bot crea un club (país al azar) y en cada paso hace algo al azar: partido por copas en vivo
(jugadas clave, penales, cambios, tácticas, pausas), sobres de la tienda, sobres por tiempo, carta
gratis, mejoras, ventas, alineaciones (automática, formación al azar, guardadas), cambio de nombre,
amistosos y partidos en vivo contra otro bot (PvP, con cambios de táctica y revancha).

Después de cada acción revisa invariantes (cosas que nunca deberían pasar). Distingue:
  - rechazos esperados (ErrorJuego: "no te alcanzan las monedas", etc.)
  - BUGS (cualquier otra excepción o un invariante roto), con su traza.

Uso:
    python -m scripts.simular_escalera --bots 40 --pasos 120 --pvp 30
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import statistics
import sys
import time
import traceback

from juego import antitrampas
from juego import economia
from juego import escalera as ESC
from juego.bd import conectar
from juego.en_vivo import Sala
from juego.partida import EXCLUSIVAS, ErrorJuego, Partida
from partidos.motor import FORMACIONES, MENTALIDADES, RONDAS_PULSO, TACTICAS

# los bots responden al instante: sin esto el control antitrampas los castigaría a todos
antitrampas.SEGUNDOS_MIN_RONDA = 0
antitrampas.SEGUNDOS_MIN_TOQUE_PVP = 0

bugs: list[dict] = []
rechazos = collections.Counter()
acciones = collections.Counter()
partidos_por_cancha = collections.defaultdict(lambda: collections.Counter())   # cancha -> resultado
duraciones = []


def bug(donde: str, detalle: str, bot: str):
    bugs.append({"donde": donde, "detalle": detalle[-1500:], "bot": bot})


# ------------------------------------------------------------------ invariantes

def revisar(p: Partida, bot: str, donde: str):
    try:
        if p.monedas < 0:
            bug(donde, f"monedas negativas: {p.monedas}", bot)
        if p.copas < ESC.piso(p.max_copas):
            bug(donde, f"copas {p.copas} bajo el piso {ESC.piso(p.max_copas)} (máx {p.max_copas})", bot)
        if p.copas < 0:
            bug(donde, f"copas negativas {p.copas}", bot)
        pl = p.plantel()
        if len(pl) < 11:
            bug(donde, f"plantel con {len(pl)} cartas", bot)
        for f in pl:
            if not 1 <= (f.nivel or 1) <= economia.NIVEL_MAXIMO:
                bug(donde, f"nivel fuera de rango: {f.carta.nombre} nivel {f.nivel}", bot)
            if f.lesion < 0 or f.suspension < 0:
                bug(donde, f"lesión/suspensión negativa: {f.carta.nombre}", bot)
            if f.carta.nombre in EXCLUSIVAS:
                bug(donde, f"carta exclusiva obtenida: {f.carta.nombre}", bot)
        puestos = [f.puesto for f in pl if f.puesto is not None]
        if len(puestos) != len(set(puestos)):
            bug(donde, f"puestos repetidos en la alineación: {sorted(puestos)}", bot)
        datos = p.exportar_equipo()
        if len(datos["jugadores"]) < 11:
            bug(donde, "exportar_equipo con menos de 11", bot)
        p.fuerza_equipo(p.usuario_id)
        ids = [s["id"] for s in p.sobres_tiempo()]
        if len(ids) != len(set(ids)):
            bug(donde, "sobres por tiempo con id repetido", bot)
        for s in p.sobres_tiempo():
            if s["estado"] not in ("listo", "abriendo", "bloqueado") or s["restante"] < 0:
                bug(donde, f"sobre por tiempo raro: {s}", bot)
    except Exception:
        bug(f"{donde} (al revisar)", traceback.format_exc(), bot)


# ------------------------------------------------------------------ partido contra la máquina (en vivo)

SENSATO = False   # --sensato: juega como una persona razonable (once automático, sin cambios locos, pulso decente)


def decidir_pausa(p: Partida, pausa: dict, rng: random.Random) -> dict:
    tipo = pausa["tipo"]
    if SENSATO and tipo not in ("ocasion", "defensa", "corner", "tiro_libre", "penal", "roja"):
        return {}
    if tipo in ("ocasion", "defensa", "corner", "tiro_libre", "penal"):
        if tipo == "penal":
            eleccion = rng.choice(["izq", "centro", "der"])
        else:
            eleccion = rng.choice([o["clave"] for o in pausa.get("opciones") or [{"clave": "tirar"}]])
        prep = p.elegir_jugada(eleccion)
        if tipo == "penal":
            return {"lado": prep["lado"] if prep["rol"] == "ataque" else prep["adivina"], "precisiones": []}
        precision = (lambda: rng.uniform(0.45, 0.95)) if SENSATO else rng.random
        return {"eleccion": eleccion, "precisiones": [round(precision(), 2) for _ in range(RONDAS_PULSO)]}
    if tipo == "roja":
        ops = pausa.get("opciones") or []
        if ops and rng.random() < 0.7:
            o = rng.choice(ops)
            return {"entra": o["entra"], "sale": o["sale"]}
        return {}
    # entretiempo / pausa táctica: cambios al azar (válidos o no), táctica y mentalidad
    est = pausa.get("estado") or {}
    cambios = []
    if est.get("cancha") and est.get("banca") and rng.random() < 0.6:
        for _ in range(rng.randint(1, 3)):
            cambios.append({"sale": rng.choice(est["cancha"])["id"], "entra": rng.choice(est["banca"])["id"]})
    return {"cambios": cambios, "tactica": rng.choice(list(TACTICAS)), "mentalidad": rng.choice(list(MENTALIDADES))}


def jugar_en_vivo(p: Partida, rng: random.Random, bot: str, etiqueta: str):
    t0 = time.time()
    r = p.avanzar_partido(None, 0)
    for _ in range(80):
        if r.get("final") and not r.get("pausa"):
            break
        # a veces, cambiar la táctica o pedir pausa en el minuto que "se está viendo"
        if r.get("posesion") and not SENSATO and rng.random() < 0.25:
            t, m = r["posesion"][len(r["posesion"]) // 2][:2]
            try:
                r2 = p.intervenir_partido(t, m, rng.choice(["tactica", "tactica", "pausa"]), rng.choice(list(TACTICAS)))
                r = r2
                continue
            except ErrorJuego as e:
                rechazos[f"intervenir: {e}"] += 1
        pausa = r.get("pausa")
        if not pausa:
            break
        try:
            decision = decidir_pausa(p, pausa, rng)
        except ErrorJuego as e:
            rechazos[f"elegir: {e}"] += 1
            decision = {}
        r = p.avanzar_partido(decision, r.get("eventos", 0))
    else:
        bug(etiqueta, "el partido no terminó en 80 pausas (¿pegado?)", bot)
    p.avanzar_partido(None, 0, terminar=True)
    if p.partido_en_vivo():
        bug(etiqueta, "quedó un partido en vivo después de terminar", bot)
    duraciones.append(time.time() - t0)


def partido_copas(p: Partida, rng: random.Random, bot: str):
    cancha = p.cancha
    p.iniciar_escalera(None, en_vivo=True)
    jugar_en_vivo(p, rng, bot, "partido por copas")
    h = p.historial_escalera[0]
    partidos_por_cancha[cancha][h["resultado"]] += 1


# ------------------------------------------------------------------ el resto de las opciones

def accion_al_azar(p: Partida, rng: random.Random, bot: str):
    opciones = [("copas", 40), ("tienda", 8), ("tiempo", 10), ("gratis", 4), ("mejorar", 8), ("vender", 5),
                ("alinear", 6), ("guardadas", 3), ("nombre", 2), ("amistoso", 4)]
    accion = rng.choices([o for o, _ in opciones], weights=[w for _, w in opciones])[0]
    acciones[accion] += 1
    if accion == "copas":
        partido_copas(p, rng, bot)
    elif accion == "tienda":
        p.abrir_sobre_completo(rng.choice(list(economia.SOBRES)))
    elif accion == "tiempo":
        sobres = p.sobres_tiempo()
        if sobres:
            s = rng.choice(sobres)
            if rng.random() < 0.5:   # que pase el tiempo
                guardados = p._get("sobres_tiempo")
                for g in guardados:
                    if g["id"] == s["id"]:
                        g["desbloqueo"] = time.time() - 13 * 3600
                p._set("sobres_tiempo", guardados)
                p.abrir_sobre_tiempo(s["id"])
            else:
                p.abrir_sobre_tiempo(s["id"], pagar=True)
    elif accion == "gratis":
        p._set("ultima_carta_gratis", 0)
        p.reclamar_carta_gratis()
    elif accion == "mejorar":
        copias = p.copias()
        candidatas = [fs for fs in copias.values() if len(fs) > 1]
        if candidatas:
            p.mejorar(rng.choice(rng.choice(candidatas)).pid)
    elif accion == "vender":
        libres = [f for f in p.plantel() if f.puesto is None]
        if libres:
            p.vender_varios([f.pid for f in rng.sample(libres, min(len(libres), rng.randint(1, 4)))])
    elif accion == "alinear":
        if SENSATO or rng.random() < 0.5:
            p.alinear_auto(rng.choice(list(FORMACIONES)))
        else:   # alineación a mano, a veces inválida a propósito
            f = rng.choice(list(FORMACIONES))
            pl = p.plantel()
            elegidos = rng.sample(pl, min(len(pl), 18))
            puestos = {i: x.pid for i, x in enumerate(elegidos)}
            if rng.random() < 0.15 and len(elegidos) > 2:
                puestos[1] = puestos[0]   # repetido: debería rechazarse o corregirse
            p.guardar_alineacion(f, rng.choice(list(MENTALIDADES)), puestos)
    elif accion == "guardadas" and not SENSATO:
        if rng.random() < 0.5:
            p.nueva_alineacion(f"Plan {rng.randint(1, 99)}")
        else:
            al = p.alineaciones()
            if al:
                a = rng.choice(al)
                (p.usar_alineacion if rng.random() < 0.7 else p.borrar_alineacion)(a["id"])
    elif accion == "nombre":
        p.actualizar_perfil(nombre=rng.choice(["Bot " + str(rng.randint(1, 10**6)), "ab", "Colo-Colo", "  Espacios   Raros  "]))
    elif accion == "amistoso":
        bots = [e["id"] for e in p.con.execute("SELECT id FROM equipos WHERE es_usuario = 0 LIMIT 40")]
        p.iniciar_amistoso(rng.choice(bots), rng.random() < 0.5)
        jugar_en_vivo(p, rng, bot, "amistoso")


# ------------------------------------------------------------------ PvP en vivo entre dos bots

def pvp(a: tuple, b: tuple, rng: random.Random, sala: Sala):
    (na, pa), (nb, pb) = a, b
    try:
        sala.buscar_copas(na, pa.copas, pa.exportar_equipo())
        mid = sala.buscar_copas(nb, pb.copas, pb.exportar_equipo())
        if not mid:
            bug("pvp", f"no se emparejaron ({pa.copas} vs {pb.copas} copas)", na)
            return
        vp = sala.partido(mid)
        lados = {na: vp.pids.index(na), nb: vp.pids.index(nb)}
        for vuelta in range(3000):
            if vp.resultado is not None:
                break
            for lado in (0, 1):
                r = vp.estado(lado, 0, (2, 120))   # "ya vi todo": la jugada clave empieza a correr
            if vp.pausa:
                if rng.random() < 0.05:
                    try:
                        vp.tactica(rng.choice([0, 1]), rng.choice(list(TACTICAS)))
                    except ValueError:
                        rechazos["pvp: táctica en plena jugada"] += 1
                for lado in (0, 1):
                    if vp.pausa and vp.prep is None and vp.eleccion[lado] is None:
                        vp.elegir(lado, rng.choice(vp._validas(lado)))
                for ronda in range(RONDAS_PULSO):
                    for lado in (0, 1):
                        if vp.pausa and vp.prep is not None:
                            vp.tocar(lado, len(vp.toques[lado]), rng.random())
        else:
            bug("pvp", "el partido en vivo no terminó (¿pegado?)", na)
            return
        res = vp.resultado
        for nombre, p in ((na, pa), (nb, pb)):
            i = lados[nombre]
            p.resultado_online(res.goles[i], res.goles[1 - i], vp.nombres[1 - i], vp.escalera.get(vp.pids[1 - i], 0))
        sala.terminar(mid)
        if rng.random() < 0.2:   # revancha
            sala.pedir_revancha(mid, 0)
            nuevo = sala.pedir_revancha(mid, 1)
            if nuevo:
                sala.terminar(nuevo)
        acciones["pvp"] += 1
    except Exception:
        bug("pvp", traceback.format_exc(), na)


# ------------------------------------------------------------------ informe

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--bots", type=int, default=30)
    ap.add_argument("--pasos", type=int, default=100)
    ap.add_argument("--pvp", type=int, default=20)
    ap.add_argument("--semilla", type=int, default=1)
    ap.add_argument("--salida", default="simulacion_bugs.json")
    ap.add_argument("--sensato", action="store_true", help="jugar como una persona razonable (para medir el balance)")
    a = ap.parse_args()
    global SENSATO
    SENSATO = a.sensato
    rng = random.Random(a.semilla)
    t0 = time.time()
    carreras = []
    for n in range(a.bots):
        nombre = f"bot{n:03d}"
        p = Partida(conectar(":memory:"))
        p.crear(f"Bot FC {n}", semilla=rng.randrange(10**6), pais=rng.choice(list(ESC.PAISES)))
        carreras.append((nombre, p))
    sala = Sala()
    # se intercalan las carreras y, de vez en cuando, un PvP entre dos bots con copas parecidas
    for paso in range(a.pasos):
        for nombre, p in carreras:
            try:
                accion_al_azar(p, rng, nombre)
            except ErrorJuego as e:
                rechazos[str(e)[:60]] += 1
            except Exception:
                bug(f"paso {paso}", traceback.format_exc(), nombre)
                p.con.rollback()
            revisar(p, nombre, f"paso {paso}")
        if a.pvp and paso % max(1, a.pasos // a.pvp) == 0:
            orden = sorted(carreras, key=lambda c: c[1].copas)
            i = rng.randrange(len(orden) - 1)
            pvp(orden[i], orden[i + 1], rng, sala)
        if paso % 10 == 0:
            print(f"paso {paso}/{a.pasos} · bugs {len(bugs)} · {time.time() - t0:.0f} s", flush=True)

    # ---- informe
    print("\n================ INFORME ================")
    print(f"{a.bots} bots · {a.pasos} pasos · {time.time() - t0:.0f} s · acciones: {dict(acciones)}")
    copas = sorted(p.copas for _, p in carreras)
    canchas = collections.Counter(ESC.CANCHAS[p.cancha][0] for _, p in carreras)
    print(f"copas finales: mín {copas[0]} · mediana {statistics.median(copas)} · máx {copas[-1]}")
    print("canchas finales:", dict(canchas))
    print("monedas finales: mediana", statistics.median(p.monedas for _, p in carreras),
          "· máx", max(p.monedas for _, p in carreras))
    print("partidos contra bots por cancha (G/E/P y % de victorias):")
    for c in sorted(partidos_por_cancha):
        r = partidos_por_cancha[c]
        tot = sum(r.values())
        print(f"  {ESC.CANCHAS[c][0]:<20} {r['victoria']:>4}/{r['empate']:>3}/{r['derrota']:>3}  {100 * r['victoria'] / tot:.0f}%")
    if duraciones:
        print(f"tiempo de servidor por partido: {statistics.mean(duraciones):.2f} s promedio, máx {max(duraciones):.2f} s")
    print("rechazos esperados (top):", rechazos.most_common(12))
    print(f"\nBUGS: {len(bugs)}")
    agrupados = collections.defaultdict(list)
    for b in bugs:
        clave = b["detalle"].strip().splitlines()[-1][:160]
        agrupados[clave].append(b)
    for clave, lista in sorted(agrupados.items(), key=lambda x: -len(x[1])):
        print(f"\n--- x{len(lista)} · {lista[0]['donde']} · {clave}")
        print(lista[0]["detalle"][-900:])
    with open(a.salida, "w", encoding="utf-8") as f:
        json.dump(bugs, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
