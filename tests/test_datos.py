"""Tests de los datos de 365Scores: lectura de estadísticas, valoración y emparejamiento de fotos.
No usan internet."""
import unittest

from cartas.valoracion import Valorador365
from scraper.fotos_365 import emparejar, valida_global
from scraper.liga_365 import _numero, estadisticas


def _jugador(id_365, nombre, posicion="DEL", puesto="ST", puntaje=None, pj=0, goles=0, nacimiento="1998-01-01",
             seleccion=0):
    stats = {"pj": pj, "pj_equipo": 20, "goles": goles, "asistencias": 0}
    if puntaje is not None:
        stats["puntaje"] = puntaje
    return {"nombre": nombre, "id_365": id_365, "dorsal": "9", "nacionalidad": "Chile", "posicion": posicion,
            "puesto": puesto, "nacimiento": nacimiento, "altura_cm": 180, "partidos_seleccion": seleccion,
            "stats": stats, "tiene_foto": True}


class TestLectura365(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(_numero("25/27"), (25, 27))
        self.assertEqual(_numero("3(2Pen)"), 3)
        self.assertEqual(_numero("6.8"), 6.8)
        self.assertIsNone(_numero("-"))

    def test_estadisticas_de_la_liga(self):
        ficha = {"highlightStats": [
            {"competitionId": 593, "seasonNum": 50, "name": "Copa", "stats": [
                {"name": "Apariciones", "value": "9/10"}, {"name": "Puntaje", "value": "7.1"}]},
            {"competitionId": 135, "seasonNum": 130, "name": "Liga", "stats": [
                {"name": "Apariciones", "value": "25/27"}, {"name": "Goles", "value": "3"},
                {"name": "Puntaje", "value": "6.8"}, {"name": "Goles esperados", "value": "-"}]},
        ]}
        s = estadisticas(ficha, 135)
        self.assertEqual((s["pj"], s["pj_equipo"], s["goles"], s["puntaje"]), (25, 27, 3, 6.8))
        self.assertNotIn("otra_competicion", s)

    def test_recien_llegado_usa_otra_competicion(self):
        ficha = {"highlightStats": [
            {"competitionId": 999, "seasonNum": 3, "name": "Liga de Portugal", "stats": [
                {"name": "Apariciones", "value": "20"}, {"name": "Puntaje", "value": "7.3"}]}]}
        s = estadisticas(ficha, 135)
        self.assertEqual(s["otra_competicion"], "Liga de Portugal")
        self.assertEqual(s["puntaje"], 7.3)


class TestValoracion365(unittest.TestCase):
    def setUp(self):
        jugadores = [_jugador(i, f"Jugador {i}", puntaje=6.0 + (i % 10) / 10, pj=10 + i % 10) for i in range(40)]
        jugadores += [_jugador(100, "Crack", puntaje=7.9, pj=20, goles=15),
                      _jugador(101, "Suplente", puntaje=6.2, pj=3),
                      _jugador(102, "Arquero", posicion="POR", puesto="GK", puntaje=7.0, pj=20)]
        self.planteles = {"fuente": "365", "clubes": [{"club": "A", "jugadores": jugadores[::2]},
                                                       {"club": "B", "jugadores": jugadores[1::2]}]}
        self.stats = {"actualizado": "2026-11-10", "tabla": {
            "A": {"pj": 20, "puntos": 40}, "B": {"pj": 20, "puntos": 20}}}

    def ovr(self, planteles=None):
        filas = Valorador365(planteles or self.planteles, self.stats).calcular()
        return {f["jugador"]["nombre"]: f["ovr"] for f in filas}

    def test_buen_rendimiento_sube_el_ovr(self):
        o = self.ovr()
        self.assertGreater(o["Crack"], o["Suplente"] + 5)
        self.assertEqual(max(o.values()), o["Crack"])

    def test_corregir_el_nombre_no_cambia_el_ovr(self):
        antes = self.ovr()["Crack"]
        for club in self.planteles["clubes"]:
            for j in club["jugadores"]:
                if j["nombre"] == "Crack":
                    j["nombre"] = "Crack Corregido"
        self.assertEqual(self.ovr()["Crack Corregido"], antes)


class TestHomonimos(unittest.TestCase):
    """Errores reales de fotos: no deben volver a pasar."""

    def test_pulisic_no_es_christian_de_cruzeiro(self):
        carta = {"Nombre": "Christian", "Edad": "", "Posición": "CAM", "Nación": "Brasil"}
        pulisic = {"name": "Christian Pulisic", "age": 28, "nationalityName": "Estados Unidos",
                   "position": {"name": "Delantero"}}
        self.assertFalse(valida_global(carta, pulisic))

    def test_wanderson_no_es_janderson(self):
        carta = {"Nombre": "Janderson", "Edad": "", "Dorsal": "", "Posición": "RB"}
        self.assertIsNone(emparejar(carta, [{"name": "Wanderson", "age": 32, "jerseyNum": 10}]))

    def test_mismo_nombre_misma_edad_si(self):
        carta = {"Nombre": "Facundo Bernal", "Edad": "23", "Posición": "CM", "Nación": "Uruguay"}
        self.assertTrue(valida_global(carta, {"name": "Facundo Bernal", "age": 23, "nationalityName": "Uruguay",
                                              "position": {"name": "Mediocampista"}}))


if __name__ == "__main__":
    unittest.main()
