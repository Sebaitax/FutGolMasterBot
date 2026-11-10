"""Tests del motor y el narrador de partidos.  Ejecutar: python -m unittest"""
import statistics
import unittest

from models.carta import Carta
from partidos.motor import FORMACIONES, Evento, Jugador, afinidad, armar_equipo, simular
from partidos.narrador import narrar

POS_EXTRA = ["GK", "CB", "CM", "ST", "LB", "RW", "CDM"]


def equipo(nombre, ovr, formacion="4-3-3", estados=None):
    jugadores = []
    for i, pos in enumerate(FORMACIONES[formacion] + POS_EXTRA):
        o = ovr - (3 if i >= 11 else 0)
        ataque = pos in ("ST", "LW", "RW")
        defensa = pos in ("CB", "LB", "RB", "CDM")
        stats = dict(PAC=o, SHO=o + 5 if ataque else o - 20, PAS=o, DRI=o,
                     DEF=o + 5 if defensa else o - 30, PHY=o)
        carta = Carta(nombre=f"{nombre}{i}", posicion=pos, ovr=o, stats=stats)
        jugadores.append(Jugador(carta, estado=(estados or {}).get(i, "disponible")))
    return jugadores


class TestMotor(unittest.TestCase):
    def test_reproducible_con_semilla(self):
        a = simular(armar_equipo("A", equipo("A", 80)), armar_equipo("B", equipo("B", 78)), semilla=5)
        b = simular(armar_equipo("A", equipo("A", 80)), armar_equipo("B", equipo("B", 78)), semilla=5)
        self.assertEqual(a.goles, b.goles)
        self.assertEqual([(e.minuto, e.tipo, e.jugador) for e in a.eventos], [(e.minuto, e.tipo, e.jugador) for e in b.eventos])

    def test_lesionados_y_suspendidos_no_juegan(self):
        jugadores = equipo("A", 80, estados={0: "lesionado", 9: "suspendido"})
        eq = armar_equipo("A", jugadores)
        nombres = {j.nombre for j in eq.titulares}
        self.assertNotIn("A0", nombres)
        self.assertNotIn("A9", nombres)
        self.assertEqual(len(eq.titulares), 11)

    def test_afinidad(self):
        self.assertEqual(afinidad("ST", "ST"), 1.0)
        self.assertGreater(afinidad("CB", "LB"), afinidad("CB", "CM"))
        self.assertGreater(afinidad("CB", "CM"), afinidad("CB", "ST"))
        self.assertLess(afinidad("ST", "GK"), 0.3)

    def test_minuto_de_adicion(self):
        self.assertEqual(Evento(48, "gol", tiempo=1).minuto_texto, "45+3'")
        self.assertEqual(Evento(92, "gol", tiempo=2).minuto_texto, "90+2'")
        self.assertEqual(Evento(26, "gol", tiempo=1).minuto_texto, "26'")

    def test_estadisticas_realistas_y_favorito_gana_mas(self):
        goles, gana_fuerte, gana_debil = [], 0, 0
        n = 400
        for s in range(n):
            r = simular(armar_equipo("A", equipo("A", 85)), armar_equipo("B", equipo("B", 76)), semilla=s)
            goles.append(sum(r.goles))
            gana_fuerte += r.ganador == 0
            gana_debil += r.ganador == 1
        self.assertTrue(2.0 < statistics.mean(goles) < 4.0, statistics.mean(goles))
        self.assertGreater(gana_fuerte / n, 0.55)
        self.assertGreater(gana_debil, 0)  # las sorpresas existen

    def test_amistoso_no_acumula_amarillas(self):
        for s in range(30):
            r = simular(armar_equipo("A", equipo("A", 80)), armar_equipo("B", equipo("B", 80)), tipo="amistoso", semilla=s)
            self.assertTrue(all(t["tipo"] == "roja" for t in r.tarjetas))


class TestNarrador(unittest.TestCase):
    def test_narra_goles_y_final(self):
        for s in range(20):
            r = simular(armar_equipo("A", equipo("A", 82)), armar_equipo("B", equipo("B", 79)), semilla=s)
            texto = "\n".join(str(l) for l in narrar(r, semilla=s))
            self.assertIn("Final del partido", texto)
            self.assertEqual(texto.count("⚽ ") - texto.count("⚽ A:") - texto.count("⚽ B:"), sum(r.goles))
            self.assertNotIn("{", texto)  # sin plantillas sin reemplazar


if __name__ == "__main__":
    unittest.main()


class TestEnVivo(unittest.TestCase):
    """Momentos clave, penales, táctica en vivo, probabilidad de ganar y el porqué del resultado."""

    @staticmethod
    def _sim(semilla, intervenciones=()):
        from partidos.motor import Simulacion
        sim = Simulacion(armar_equipo("A", equipo("A", 78)), armar_equipo("B", equipo("B", 76)), "liga", semilla)
        sim.programar(list(intervenciones))
        return sim

    @staticmethod
    def _jugar(sim, decidir=lambda pausa: {}):
        gen = sim.correr(interactivo=0)
        pausas = []
        try:
            pausa = next(gen)
            while True:
                pausas.append(dict(pausa))
                pausa = gen.send(decidir(pausa))
        except StopIteration as fin:
            return fin.value, pausas

    def test_intervencion_no_cambia_lo_ya_jugado(self):
        base, _ = self._jugar(self._sim(3))
        sim = self._sim(3, [{"t": 1, "m": 30, "tipo": "tactica", "valor": "presion"}])
        res, _ = self._jugar(sim)
        corte = sim.indice_intervencion[(1, 30)]
        firma = lambda evs: [(e.tiempo, e.minuto, e.tipo, e.jugador) for e in evs]
        self.assertEqual(firma(base.eventos[:corte]), firma(res.eventos[:corte]))
        self.assertEqual(res.eventos[corte].tipo, "tactica")

    def test_pausa_tactica_permite_cambios(self):
        sim = self._sim(4, [{"t": 2, "m": 60, "tipo": "pausa"}])

        def decidir(p):
            if p["tipo"] == "pausa":
                est = sim.estado(0)
                return {"cambios": [{"sale": est["cancha"][5]["id"], "entra": est["banca"][0]["id"]}], "tactica": "cuidar"}
            return {}
        # los jugadores del test no tienen id de base de datos: se los damos
        for eq in (0, 1):
            for i, j in enumerate(sim.equipos[eq].titulares + sim.equipos[eq].suplentes):
                j.id = eq * 100 + i
        res, pausas = self._jugar(sim, decidir)
        self.assertIn("pausa", [p["tipo"] for p in pausas])
        cambios = [e for e in res.eventos if e.tipo == "cambio" and e.datos.get("motivo") == "decision"]
        self.assertTrue(cambios)
        self.assertEqual(sim.equipos[0].tactica, "cuidar")

    def test_momentos_clave_y_penales(self):
        from partidos.motor import MAX_MOMENTOS
        vistos = {"ocasion": 0, "penal": 0}
        for semilla in range(60):
            sim = self._sim(semilla)

            def decidir(p):
                if p["tipo"] == "ocasion":
                    ops = sim.opciones_ocasion(p)["opciones"]
                    self.assertEqual([o["clave"] for o in ops], ["tirar", "pasar", "gambetear"])
                    self.assertTrue(all(0 <= o["prob"] <= 100 for o in ops))
                    return {"eleccion": ["tirar", "pasar", "gambetear"][semilla % 3]}
                if p["tipo"] == "penal":
                    return {"lado": "izq"}
                return {}
            res, pausas = self._jugar(sim, decidir)
            tipos = [p["tipo"] for p in pausas]
            self.assertLessEqual(tipos.count("ocasion"), MAX_MOMENTOS)
            for k in vistos:
                vistos[k] += tipos.count(k)
            for e in res.eventos:
                if e.datos.get("penal") and e.tipo in ("gol", "atajada", "desviado") and e.equipo == 0 and e.tipo != "atajada":
                    self.assertEqual(e.datos["lado"], "izq")  # el lado que elegiste
            self.assertFalse(sim._pendientes)  # no quedan jugadas sin resolver
        self.assertGreater(vistos["ocasion"], 30)
        self.assertGreater(vistos["penal"], 0)

    def test_probabilidad_de_ganar_y_razones(self):
        for semilla in range(20):
            sim = self._sim(semilla)
            res, _ = self._jugar(sim)
            for _, _, _, pg, pe in sim.posesion_min:
                self.assertTrue(0 <= pg <= 100 and 0 <= pe <= 100 and pg + pe <= 100)
            pg, pe = sim.posesion_min[-1][3:]
            if res.goles[0] > res.goles[1]:
                self.assertGreaterEqual(pg, 85)
            elif res.goles[0] < res.goles[1]:
                self.assertLessEqual(pg, 15)
            self.assertEqual(len(res.razones), 2)
            self.assertTrue(all(len(r) <= 5 for r in res.razones))
            self.assertTrue(all(len(x) == 2 for r in res.razones for x in r))
