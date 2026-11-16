"""Recorre la web como varios jugadores (páginas y acciones) buscando errores 500 y pantallas rotas.

Usa el cliente de pruebas de FastAPI (sin servidor). Crea partidas de prueba en data/partidas con ids
'ffff…' y las borra al final.

    python -m scripts.recorrer_web --jugadores 6
"""
from __future__ import annotations

import argparse
import random
import sys
import traceback
from pathlib import Path

from fastapi.testclient import TestClient

from juego import escalera as ESC
from juego import apuestas as AP

errores: list[str] = []
revisadas = 0


def pedir(c: TestClient, metodo: str, url: str, quien: str, **kw):
    global revisadas
    revisadas += 1
    try:
        r = c.request(metodo, url, follow_redirects=False, **kw)
    except Exception:
        errores.append(f"{quien} {metodo} {url}: EXCEPCIÓN\n{traceback.format_exc()[-800:]}")
        return None
    if r.status_code >= 500:
        errores.append(f"{quien} {metodo} {url}: {r.status_code} {r.text[:200]}")
    return r


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--jugadores", type=int, default=6)
    a = ap.parse_args()
    from web.app import app
    rng = random.Random(3)
    pids = []
    for n in range(a.jugadores):
        pid = f"{n:02d}".rjust(32, "f")
        pids.append(pid)
        c = TestClient(app, cookies={"fgm_partida": pid})
        q = f"web{n}"
        pedir(c, "POST", "/crear", q, data={"nombre_club": f"Web FC {n}", "pais": rng.choice(list(ESC.PAISES))})
        for url in ["/", "/plantel", "/inventario", "/tienda", "/amistosos", "/perfil", "/tabla", "/tabla-liga",
                    "/vivo", "/escalera/buscar", "/olvide", "/mercado", "/api/vivo/sala", "/api/escudo/vista",
                    "/album", "/album?liga=Liga%20de%20Primera", "/album?liga=Liga%20de%20Primera&club=Colo-Colo",
                    "/album?liga=No%20existe&club=Nadie"]:
            pedir(c, "GET", url, q)
        for liga in AP.LIGAS:
            pedir(c, "GET", f"/apuestas?liga={liga}", q)
        pedir(c, "POST", "/api/sobre/basico", q, json={})
        pedir(c, "POST", "/api/carta-gratis", q, json={})
        pedir(c, "POST", "/api/album/premio", q, json={"liga": "Liga de Primera", "club": "Colo-Colo", "nivel": 50})
        pedir(c, "POST", "/api/album/premio", q, json={"liga": 1, "club": None, "nivel": "x"})
        pedir(c, "POST", "/api/escalera/buscar", q, json={})
        pedir(c, "POST", "/api/escalera/cancelar", q, json={"motivo": "tiempo"})
        pedir(c, "POST", "/api/alineacion", q, json={"formacion": rng.choice(["4-4-2", "3-4-3", "5-4-1"]), "mentalidad": "equilibrada",
                                                     "once": [], "auto": True})
        pedir(c, "POST", "/api/perfil", q, json={"nombre": f"Web Renombrado {n}", "eslogan": "¡Vamos!", "estadio": "La Cancha"})
        # partido por copas en vivo de punta a punta, por la web
        r = pedir(c, "POST", "/escalera/jugar", q, data={"modo": "vivo"})
        destino = r.headers.get("location", "") if r is not None else ""
        if "/partido/" in destino:
            ruta = destino.split("testserver")[-1]
            pedir(c, "GET", ruta, q)
            pid_partido = ruta.split("/")[2]
            res = pedir(c, "POST", "/api/partido/avanzar", q, json={"desde": 0})
            for _ in range(60):
                if res is None or res.status_code != 200:
                    break
                d = res.json()
                pausa = d.get("pausa")
                if not pausa:
                    break
                decision = {}
                if pausa["tipo"] in ("ocasion", "defensa", "corner", "tiro_libre", "penal"):
                    elegir = "izq" if pausa["tipo"] == "penal" else (pausa.get("opciones") or [{"clave": "tirar"}])[0]["clave"]
                    prep = pedir(c, "POST", "/api/partido/elegir", q, json={"eleccion": elegir})
                    decision = {"lado": elegir, "precisiones": []} if pausa["tipo"] == "penal" else {"eleccion": elegir, "precisiones": [0.6, 0.7, 0.5]}
                res = pedir(c, "POST", "/api/partido/avanzar", q, json={"decision": decision, "desde": d.get("eventos", 0)})
            pedir(c, "POST", "/api/partido/avanzar", q, json={"terminar": True})
            for url in (f"/partido/{pid_partido}", f"/partido/{pid_partido}/resumen", f"/partido/{pid_partido}?pantalla=vieja", "/"):
                pedir(c, "GET", url, q)
        # sobres por tiempo ganados
        r = pedir(c, "GET", "/", q)
        if r is not None and '"sobres": [{' in r.text:
            import re
            for sid in re.findall(r'"id": (\d{10,})', r.text)[:2]:
                pedir(c, "POST", f"/api/sobres-tiempo/{sid}/abrir-ya", q, json={})
        pedir(c, "GET", "/inventario", q)
    # limpieza
    for pid in pids:
        for f in Path("data/partidas").glob(f"{pid}.sqlite*"):
            f.unlink()
    print(f"páginas y acciones revisadas: {revisadas} · errores: {len(errores)}")
    for e in errores:
        print("\n" + e)


if __name__ == "__main__":
    main()
