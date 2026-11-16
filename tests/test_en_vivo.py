"""Partidos en vivo entre amigos: sala, jugadas a pulso, reacciones y revancha."""
import tempfile
import unittest
from pathlib import Path

from juego.en_vivo import Sala
from juego.partida import Partida, conectar
from tests.test_juego import catalogo_ficticio


class TestEnVivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.catalogo = Path(cls.tmp.name) / "catalogo.csv"
        catalogo_ficticio(cls.catalogo)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def club(self, semilla):
        p = Partida(conectar(":memory:"))
        self.addCleanup(p.con.close)
        p.crear(f"Amigo {semilla}", semilla=semilla, catalogo=self.catalogo, divisiones=1)
        return p.exportar_equipo()

    def jugar_completo(self, vp):
        """Los dos lados eligen y tocan hasta el final."""
        clases = set()
        for _ in range(400):
            if vp.resultado is not None:
                break
            vp.estado(0, 0, None)
            if not vp.pausa:
                continue
            clases.add(vp.pausa.get("clase", "penal"))
            for lado in (0, 1):
                vp.elegir(lado, vp._validas(lado)[-1])
            for r in range(3):
                if not vp.pausa or vp.prep is None:
                    break
                vp.tocar(0, r, 0.9)
                vp.tocar(1, r, 0.3)
        self.assertIsNotNone(vp.resultado)
        return clases

    def test_partido_reacciones_y_revancha(self):
        sala = Sala()
        sala.esperar("A", {"nombre": "Club 1"}, apuesta=5000)
        self.assertEqual(sala.ver("B")["otros"][0]["apuesta"], 5000)
        mid = sala.aceptar("B", "A", self.club(2), self.club(1))
        self.assertEqual(sala.ver("A")["partido"], mid)
        vp = sala.partido(mid)
        self.assertEqual(vp.apuesta, 5000)
        vp.reaccionar(1, "🔥")
        vp.reaccionar(1, "no-vale")
        self.assertEqual([r["emoji"] for r in vp.estado(0, 0, None)["reacciones"]], ["🔥"])   # solo las del rival
        self.assertEqual(vp.estado(1, 0, None)["reacciones"], [])
        self.jugar_completo(vp)
        sala.terminar(mid)
        self.assertIsNone(sala.pedir_revancha(mid, 0))      # falta que el otro acepte
        nuevo = sala.pedir_revancha(mid, 1)
        self.assertTrue(nuevo)
        self.assertEqual(sala.partido(nuevo).pids, ["B", "A"])   # localía al revés
        self.assertEqual(sala.partido(nuevo).apuesta, 5000)

    def test_pelota_parada_entre_amigos(self):
        """Con muchos partidos aparecen córners y tiros libres como jugadas clave de los dos lados."""
        clases = set()
        for i in range(12):
            sala = Sala()
            sala.esperar("A", {"nombre": "x"})
            vp = sala.partido(sala.aceptar("B", "A", self.club(3 + i), self.club(30 + i)))
            clases |= self.jugar_completo(vp)
        self.assertTrue({"jugada", "corner", "tiro_libre"} <= clases)


if __name__ == "__main__":
    unittest.main()


class TestRelojesEnVivo(TestEnVivo):
    """Bugs de jugadas clave 'pegadas': relojes adelantados y tácticas que borraban la jugada en curso."""

    def nuevo(self):
        from juego.en_vivo import PartidoVivo
        vp = PartidoVivo("x", {"pid": "a", "equipo": self.club(11)}, {"pid": "b", "equipo": self.club(12)})
        vp._reconstruir()
        vp._nueva_pausa()
        self.assertIsNotNone(vp.pausa)
        return vp

    def test_el_reloj_parte_cuando_los_dos_llegan(self):
        import time
        vp = self.nuevo()
        clave = (vp.pausa["tiempo"], vp.pausa["minuto"])
        vp.visto = [(1, 0), (1, 0)]
        vp.pausa_creada = time.time() - 60          # la jugada existe hace un minuto en el servidor
        vp._vencimientos()
        self.assertIsNone(vp.prep, "no debe elegir por nadie si todavía no llegan a la jugada")
        vp.visto = [clave, (1, 0)]
        self.assertFalse(vp._pausa_activa())         # falta el otro
        vp.visto = [clave, clave]
        self.assertTrue(vp._pausa_activa())
        self.assertIsNone(vp.prep)                   # recién empieza a correr: nadie eligió por ellos

    def test_si_uno_se_desconecta_igual_corre(self):
        import time
        vp = self.nuevo()
        clave = (vp.pausa["tiempo"], vp.pausa["minuto"])
        vp.visto = [clave, (1, 0)]
        vp.ultimo_contacto = [time.time(), time.time() - 60]
        self.assertTrue(vp._pausa_activa())

    def test_no_se_cambia_la_tactica_en_plena_jugada(self):
        vp = self.nuevo()
        clave = (vp.pausa["tiempo"], vp.pausa["minuto"])
        vp.visto = [clave, clave]
        vp.elegir(0, vp._validas(0)[0])
        with self.assertRaises(ValueError):
            vp.tactica(1, "presion")
