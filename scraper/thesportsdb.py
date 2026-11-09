"""Utilidades para la API pública de TheSportsDB (logos, banderas y fotos).

La key "3" es la key gratuita de pruebas; para uso real ver https://www.thesportsdb.com/api.php
"""
import os
from io import BytesIO

import requests
from PIL import Image

API = f"https://www.thesportsdb.com/api/v1/json/{os.getenv('THESPORTSDB_KEY', '3')}"


def _descargar_imagen(url: str) -> Image.Image | None:
    respuesta = requests.get(url, timeout=15)
    if respuesta.status_code == 200:
        return Image.open(BytesIO(respuesta.content))
    return None


def obtener_logo(equipo: str) -> Image.Image | None:
    datos = requests.get(f"{API}/searchteams.php", params={"t": equipo}, timeout=15).json()
    if datos.get("teams"):
        return _descargar_imagen(datos["teams"][0]["strBadge"])
    return None


def obtener_bandera(pais: str) -> Image.Image | None:
    datos = requests.get(f"{API}/all_countries.php", timeout=15).json()
    for country in datos.get("countries") or []:
        if country["name_en"].lower() == pais.lower():
            return _descargar_imagen(country["flag_url_32"])
    return None


def obtener_foto_jugador(jugador: str, equipo: str | None = None) -> Image.Image | None:
    datos = requests.get(f"{API}/searchplayers.php", params={"p": jugador}, timeout=15).json()
    for player in datos.get("player") or []:
        if player.get("strSport") != "Soccer":
            continue
        if equipo and player.get("strTeam") != equipo:
            continue
        if player.get("strCutout"):
            return _descargar_imagen(player["strCutout"])
    return None


if __name__ == "__main__":
    logo = obtener_logo("Arsenal")
    print("Logo Arsenal:", logo.size if logo else "no encontrado")
    bandera = obtener_bandera("Chile")
    print("Bandera Chile:", bandera.size if bandera else "no encontrada")
