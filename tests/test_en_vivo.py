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
