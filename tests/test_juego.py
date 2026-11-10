"""Tests del núcleo del juego con un catálogo ficticio (no depende de data/)."""
import csv
import json
import random
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from juego.bd import conectar
from juego.economia import SOBRES
from juego.partida import PLANTEL_MINIMO, ErrorJuego, Partida

PUESTOS = ["GK", "GK", "CB", "CB", "CB", "LB", "RB", "CDM", "CM", "CM", "CAM", "LM", "RM", "LW", "RW", "ST", "ST", "ST", "CB", "CM"]


def catalogo_ficticio(ruta: Path, clubes: int = 16):
    rng = random.Random(1)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Nombre", "Alias", "Posición", "Club", "Nación", "Liga", "OVR", "PAC", "SHO", "PAS", "DRI", "DEF", "PHY", "Precio", "Edad", "Dorsal"])
        for c in range(clubes):
            base = 60 + c  # clubes de distinta fuerza
            for i, pos in enumerate(PUESTOS):
                ovr = max(50, min(85, base + rng.randint(-5, 5)))
                stats = [max(30, min(95, ovr + rng.randint(-10, 10))) for _ in range(6)]
                w.writerow([f"Jugador {c}-{i}", f"J{c}-{i}", pos, f"Club {c}", "Ficticia", "Liga Test", ovr, *stats,
                            int(400 * 1.17 ** (ovr - 50)), 25, i + 1])


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.catalogo = Path(cls.tmp.name) / "catalogo.csv"
        catalogo_ficticio(cls.catalogo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def nueva(self, semilla=1) -> Partida:
        p = Partida(conectar(":memory:"))
        self.addCleanup(p.con.close)
        p.crear("Mi Club", semilla=semilla, catalogo=self.catalogo, divisiones=1)
        return p


class TestJuego(_Base):
    def test_crear(self):
        p = self.nueva()
        equipos = p.con.execute("SELECT COUNT(*) FROM equipos").fetchone()[0]
        self.assertEqual(equipos, 16)  # el usuario reemplaza al club más débil
        self.assertEqual(p._get("reemplaza"), "Club 0")
        self.assertEqual(len(p.plantel()), 18)
        self.assertEqual(sum(f.puesto is not None and f.puesto < 11 for f in p.plantel()), 11)
        self.assertEqual(sum(f.puesto is not None and f.puesto >= 11 for f in p.plantel()), 7)  # suplentes
        with self.assertRaises(ErrorJuego):
            p.crear("Otro")

    def test_fixture(self):
        p = self.nueva()
        self.assertEqual(p.total_fechas, 30)
        cruces = Counter()
        for fecha in range(1, 31):
            partidos = p.partidos_fecha(fecha)
            equipos = [e for x in partidos for e in (x["local_id"], x["visita_id"])]
            self.assertEqual(len(equipos), len(set(equipos)), "un equipo juega dos veces en la fecha")
            for x in partidos:
                cruces[(x["local_id"], x["visita_id"])] += 1
        self.assertEqual(len(cruces), 16 * 15)  # cada par, una vez de local y otra de visita
        self.assertTrue(all(v == 1 for v in cruces.values()))

    def test_temporada_completa(self):
        p = self.nueva()
        monedas = p.monedas
        while not p.temporada_terminada:
            pid = p.jugar_fecha()
            self.assertIsNotNone(p.partido(pid)["detalle"])
        tabla = p.tabla()
        self.assertTrue(all(f["pj"] == 30 for f in tabla))
        self.assertEqual(sum(f["g"] for f in tabla), sum(f["p"] for f in tabla))
        self.assertGreater(p.monedas, monedas)
        self.assertEqual(len(p.historial), 1)
        with self.assertRaises(ErrorJuego):
            p.jugar_fecha()
        p.nueva_temporada()
        self.assertEqual((p.temporada, p.fecha), (2, 1))
        self.assertTrue(all(f["pj"] == 0 for f in p.tabla()))

    def test_reproducible(self):
        a, b = self.nueva(7), self.nueva(7)
        for _ in range(3):
            a.jugar_fecha()
            b.jugar_fecha()
        self.assertEqual([(f["nombre"], f["pts"]) for f in a.tabla()], [(f["nombre"], f["pts"]) for f in b.tabla()])

    def test_sanciones(self):
        p = self.nueva()
        fichas = p.plantel()
        titular = next(f for f in fichas if f.puesto == 5)
        p.con.execute("UPDATE plantilla SET suspension = 1 WHERE id = ?", (titular.pid,))
        equipo = p._equipo_usuario()
        self.assertNotIn(titular.pid, [j.id for j in equipo.titulares + equipo.suplentes])
        self.assertEqual(len(equipo.titulares), 11)
        p.jugar_fecha()
        cumplida = next(f for f in p.plantel() if f.pid == titular.pid)
        self.assertEqual(cumplida.suspension, 0)

        # 5 amarillas = una fecha de suspensión
        p.con.execute("UPDATE plantilla SET amarillas = 4 WHERE id = ?", (titular.pid,))
        res = type("R", (), {"lesiones": [], "tarjetas": [{"id": titular.pid, "tipo": "amarilla"}]})()
        p._aplicar_sanciones(res)
        f = next(f for f in p.plantel() if f.pid == titular.pid)
        self.assertEqual((f.suspension, f.amarillas), (1, 0))

    def test_sobres_y_venta(self):
        p = self.nueva()
        with self.assertRaises(ErrorJuego):
            p.abrir_sobre("oro")  # no alcanza
        antes = p.monedas
        nuevos = p.abrir_sobre("bronce")
        self.assertEqual(len(nuevos), SOBRES["bronce"]["cartas"])
        self.assertEqual(p.monedas, antes - SOBRES["bronce"]["precio"])
        vendida = max(p.plantel(), key=lambda f: f.carta.precio if f.carta.posicion != "GK" else 0)
        p.vender(vendida.pid)
        self.assertNotIn(vendida.pid, [f.pid for f in p.plantel()])
        while len(p.plantel()) > PLANTEL_MINIMO:
            p.vender(next(f.pid for f in p.plantel() if f.carta.posicion != "GK"))
        with self.assertRaises(ErrorJuego):
            p.vender(p.plantel()[0].pid)

    def test_alineacion_manual(self):
        p = self.nueva()
        fichas = p.plantel()
        with self.assertRaises(ErrorJuego):
            p.guardar_alineacion("4-3-3", "ofensiva", {0: fichas[0].pid, 1: fichas[0].pid})
        p.guardar_alineacion("4-4-2", "defensiva", {0: fichas[0].pid})
        e = p._equipo_usuario()
        self.assertEqual((e.formacion, e.mentalidad), ("4-4-2", "defensiva"))
        self.assertEqual(e.titulares[0].id, fichas[0].pid)
        self.assertEqual(len(e.titulares), 11)  # los vacíos se completan solos


class TestNuevo(_Base):
    """Partido en vivo, química, mercado, venta con deshacer y objetivo."""

    def test_partido_en_vivo_y_reconstruccion(self):
        from juego import partida as modulo
        p = self.nueva(5)
        pid = p.iniciar_partido()
        self.assertEqual(p.iniciar_partido(), pid)  # no crea otro
        with self.assertRaises(ErrorJuego):
            p.jugar_fecha()  # hay un partido en curso
        r = p.avanzar_partido(desde=0)
        self.assertIn(r["pausa"]["tipo"], ("descanso", "roja"))
        lineas = [l["texto"] for l in r["lineas"]]
        modulo._SESIONES.clear()  # simula que el servidor se reinició
        r2 = p.avanzar_partido(desde=0)
        self.assertEqual([l["texto"] for l in r2["lineas"]], lineas)  # misma semilla => mismo partido
        pausas = []
        while not r2["final"]:
            pausa = r2["pausa"]
            pausas.append(pausa["tipo"])
            if pausa["tipo"] == "roja":
                o = pausa["opciones"][0]
                decision = {"entra": o["entra"], "sale": o["sale"]}
            else:
                decision = {"mentalidad": "ofensiva", "cambios": []}
            r2 = p.avanzar_partido(decision, desde=r2["eventos"])
        self.assertIn("descanso", pausas)
        self.assertFalse(p.partido(pid)["jugado"])  # se registra cuando terminas de verlo
        p.avanzar_partido(desde=r2["eventos"], terminar=True)
        self.assertTrue(p.partido(pid)["jugado"])
        self.assertEqual(p.fecha, 2)
        self.assertIsNone(p.partido_en_vivo())
        self.assertTrue(all(x["jugado"] for x in p.partidos_fecha(1)))

    def test_tactica_y_pausa_en_vivo(self):
        p = self.nueva(7)
        pid = p.iniciar_partido()

        def jugados_despues(r, visto):
            """Avanza las pausas (sin decidir nada) hasta que haya minutos jugados después de `visto`."""
            while True:
                ms = [tuple(x[:2]) for x in r["posesion"] if tuple(x[:2]) > visto]
                if ms:
                    return r, ms, visto
                visto = tuple(r["posesion"][-1][:2])
                r = p.avanzar_partido({}, desde=r["eventos"])

        r, ms, visto = jugados_despues(p.avanzar_partido(desde=0), (1, 0))
        t, m = ms[0]
        r = p.intervenir_partido(t, m, "tactica", "presion")
        self.assertEqual(r["tactica"], "presion")
        self.assertTrue(any(l["tipo"] == "tactica" for l in r["lineas"]))
        with self.assertRaisesRegex(ErrorJuego, "siguiente"):  # no se puede volver atrás en el tiempo
            p.intervenir_partido(t, m, "pausa")
        r, ms, visto = jugados_despues(r, (t, m))
        t2, m2 = ms[0]
        if t2 == t and m2 - m < 10:  # hay que esperar 10 minutos para volver a cambiarla
            with self.assertRaisesRegex(ErrorJuego, "táctica"):
                p.intervenir_partido(t2, m2, "tactica", "normal")
        r = p.intervenir_partido(t2, m2, "pausa")
        self.assertEqual(r["pausa"]["tipo"], "pausa")
        self.assertIn("estado", r["pausa"])
        self.assertEqual(r["pausas_restantes"], 1)
        from juego import partida as modulo
        modulo._SESIONES.clear()  # al reconstruir sale lo mismo
        self.assertEqual(p.avanzar_partido(desde=0)["pausa"]["tipo"], "pausa")
        while not r["final"]:
            r = p.avanzar_partido({}, desde=r["eventos"])
        self.assertFalse(p.partido(pid)["jugado"])
        p.avanzar_partido(desde=r["eventos"], terminar=True)
        self.assertTrue(p.partido(pid)["jugado"])
        detalle = json.loads(p.partido(pid)["detalle"])
        self.assertIn("razones", detalle)
        self.assertEqual(len(detalle["posesion"][0]), 5)  # con la probabilidad de ganar

    def test_quimica(self):
        from juego.formaciones import ENLACES, quimica
        from models.carta import Carta
        mismos = [Carta(f"J{i}", pos, 70, club="A", nacion="X") for i, pos in
                  enumerate(["GK", "LB", "CB", "CB", "RB", "CM", "CDM", "CM", "LW", "ST", "RW"])]
        self.assertEqual(quimica("4-3-3", mismos)["equipo"], 100)
        distintos = [Carta(c.nombre, c.posicion, 70, club=str(i), nacion=str(i)) for i, c in enumerate(mismos)]
        self.assertEqual(quimica("4-3-3", distintos)["equipo"], 0)
        self.assertTrue(all(len(ENLACES[f]) >= 10 for f in ENLACES))
        p = self.nueva()
        e = p._equipo_usuario()
        self.assertTrue(all(0.97 <= j.quimica <= 1.03 for j in e.titulares))

    def test_mercado(self):
        p = self.nueva()
        ofertas = p.ofertas()
        self.assertGreater(len(ofertas), 100)  # los clubes bot publican jugadores en venta
        self.assertEqual([o["carta_id"] for o in ofertas], [o["carta_id"] for o in p.ofertas()])  # estable en la fecha
        self.assertTrue(all(o["vendedor"] and o["quedan"] >= 1 and not o["tuya"] for o in ofertas))
        barata = min(ofertas, key=lambda o: o["precio"])
        self.assertEqual([o["carta_id"] for o in p.en_venta(barata["carta_id"])], [barata["carta_id"]])
        antes = len(p.plantel())
        p.comprar(barata["carta_id"])
        self.assertEqual(len(p.plantel()), antes + 1)
        self.assertEqual(p.en_venta(barata["carta_id"]), [])  # la publicación desaparece
        with self.assertRaises(ErrorJuego):
            p.comprar(barata["carta_id"])  # ya no está en venta
        # buscador: todos los jugadores (para ver stats) o solo lo que está en venta
        nombre = barata["carta"].nombre.split()[-1]
        todos = p.buscar(nombre, solo_venta=False)
        self.assertTrue(any(o["carta_id"] == barata["carta_id"] for o in todos))
        self.assertTrue(all(o["en_mercado"] for o in p.buscar(posicion="DEF")))
        baratos = p.buscar(orden="precio", precio_max=5000)
        self.assertTrue(all(o["precio"] <= 5000 for o in baratos))
        self.assertEqual([o["precio"] for o in baratos], sorted(o["precio"] for o in baratos))

    def test_venta_y_deshacer(self):
        p = self.nueva()
        p.abrir_sobre("bronce")
        monedas, n = p.monedas, len(p.plantel())
        pids = [f.pid for f in p.plantel() if f.carta.posicion != "GK"][:2]
        p.vender_varios(pids)
        self.assertEqual(len(p.plantel()), n - 2)
        p.deshacer_venta()
        self.assertEqual((len(p.plantel()), p.monedas), (n, monedas))
        with self.assertRaises(ErrorJuego):
            p.deshacer_venta()

    def test_suplentes_elegidos(self):
        p = self.nueva()
        fichas = p.plantel()
        banca = sorted((f for f in fichas if f.puesto is not None and f.puesto >= 11), key=lambda f: f.puesto)
        titulares = {f.puesto: f.pid for f in fichas if f.puesto is not None and f.puesto < 11}
        # solo 2 suplentes elegidos a mano y en otro orden; los demás se completan al jugar
        elegidos = {11: banca[-1].pid, 12: banca[0].pid}
        p.guardar_alineacion("4-3-3", "equilibrada", {**titulares, **elegidos})
        e = p._equipo_usuario()
        self.assertEqual([j.id for j in e.suplentes[:2]], list(elegidos.values()))
        self.assertEqual(len(e.suplentes), 7)

    def test_sobre_sin_repetidas_dentro(self):
        p = self.nueva()
        p._mover_monedas(200000, "test")
        for _ in range(10):
            nuevas = [f.carta_id for f in p.abrir_sobre("plata")]
            self.assertEqual(len(nuevas), len(set(nuevas)))

    def test_mejora_con_repetida(self):
        from juego import economia
        p = self.nueva()
        p._mover_monedas(50000, "test")
        ficha = p.plantel()[0]
        with self.assertRaises(ErrorJuego):
            p.mejorar(ficha.pid)  # sin repetida no se puede
        p.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)", (p.usuario_id, ficha.carta_id))
        antes = len(p.plantel())
        mejorada = p.mejorar(ficha.pid)
        self.assertEqual(mejorada.nivel, 2)
        self.assertEqual(mejorada.carta.ovr, ficha.carta.ovr + 1)
        self.assertEqual(len(p.plantel()), antes - 1)  # se gastó la copia
        # hasta el máximo
        for _ in range(economia.NIVEL_MAXIMO):
            p.con.execute("INSERT INTO plantilla (equipo_id, carta_id) VALUES (?, ?)", (p.usuario_id, ficha.carta_id))
        while True:
            try:
                mejorada = p.mejorar(ficha.pid)
            except ErrorJuego:
                break
        self.assertEqual(mejorada.nivel, economia.NIVEL_MAXIMO)

    def test_carta_gratis_cada_8_horas(self):
        p = self.nueva()
        self.assertEqual(p.segundos_para_carta_gratis(), 0)
        antes = len(p.plantel())
        p.reclamar_carta_gratis()
        self.assertEqual(len(p.plantel()), antes + 1)
        self.assertGreater(p.segundos_para_carta_gratis(), 8 * 3600 - 100)
        with self.assertRaises(ErrorJuego):
            p.reclamar_carta_gratis()

    def test_alineaciones_guardadas(self):
        p = self.nueva()
        self.assertEqual(len(p.alineaciones()), 1)
        titular = p.alineaciones()[0]["id"]
        rotacion = p.nueva_alineacion("Rotación")
        p.guardar_alineacion("5-3-2", "defensiva", {0: p.plantel()[-1].pid})
        p.usar_alineacion(titular)
        self.assertEqual(p.equipo(p.usuario_id)["formacion"], "4-3-3")
        p.usar_alineacion(rotacion)
        e = p.equipo(p.usuario_id)
        self.assertEqual((e["formacion"], e["mentalidad"]), ("5-3-2", "defensiva"))
        for i in range(3):
            p.nueva_alineacion(f"Extra {i}")
        with self.assertRaises(ErrorJuego):
            p.nueva_alineacion("Sexta")
        with self.assertRaises(ErrorJuego):
            p.borrar_alineacion(p._get("alineacion_activa"))

    def test_amistoso_no_cuenta(self):
        p = self.nueva()
        rival = p.clubes()[0]["id"]
        pid = p.iniciar_amistoso(rival)
        r = p.avanzar_partido(desde=0)
        while not r["final"]:
            pausa = r["pausa"]
            d = {"entra": pausa["opciones"][0]["entra"], "sale": pausa["opciones"][0]["sale"]} if pausa["tipo"] == "roja" else {}
            r = p.avanzar_partido(d, desde=r["eventos"])
        p.avanzar_partido(desde=r["eventos"], terminar=True)
        self.assertTrue(p.partido(pid)["jugado"])
        self.assertEqual(p.fecha, 1)  # no avanza la liga
        self.assertTrue(all(f["pj"] == 0 for f in p.tabla()))
        self.assertEqual(p.estadisticas_club()["record"]["amistoso"]["pj"], 1)

    def test_objetos_de_coleccion(self):
        p = self.nueva()
        escudos = [o for o in p.coleccion() if o["tipo"] == "escudo"]
        self.assertEqual(len(escudos), 16)  # uno por club del catálogo
        p._mover_monedas(10**6, "test")
        obtenidos = []
        for _ in range(40):
            obtenidos += p.abrir_sobre_completo("oro")["objetos"]
        self.assertTrue(obtenidos)
        ids = [o["id"] for o in obtenidos]
        self.assertEqual(len(ids), len(set(ids)))  # nunca uno que ya tienes
        escudo = next(o for o in obtenidos if o["tipo"] == "escudo")
        p.usar_objeto(escudo["id"])
        self.assertEqual(p.equipo(p.usuario_id)["escudo"], f"real:{escudo['club']}")
        no_tengo = next(o for o in p.coleccion() if not o["tengo"])
        with self.assertRaises(ErrorJuego):
            p.usar_objeto(no_tengo["id"])

    def test_clubes_bot_inventados(self):
        p = Partida(conectar(":memory:"))
        self.addCleanup(p.con.close)
        p.crear("Mi Club", semilla=3, catalogo=self.catalogo, divisiones=3)
        reales = {f"Club {i}" for i in range(16)}
        bots = p._bots()
        self.assertTrue(bots)
        self.assertFalse({b["nombre"] for b in bots} & reales)
        self.assertTrue(all(b["estadio"] and b["escudo"] and b["nombre_real"] in reales for b in bots))

    def test_objetivo(self):
        p = self.nueva()
        o = p.objetivo
        self.assertTrue(1 <= o["posicion"] <= 14)
        while not p.temporada_terminada:
            p.jugar_fecha()
        h = p.historial[-1]
        self.assertEqual(h["cumplido"], h["posicion"] <= o["posicion"])
        self.assertEqual(len(p.evolucion()), 30)


if __name__ == "__main__":
    unittest.main()
