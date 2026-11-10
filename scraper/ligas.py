"""Configuración de cada liga: de dónde salen los datos y cómo se juega.

Para sumar una liga nueva basta con agregar una entrada acá y correr:
    python -m scraper.plantillas --liga <clave>
    python -m scraper.estadisticas --liga <clave>
    python -m cartas.valoracion --liga <clave>
    python -m scraper.fotos --liga <clave> --recortar
"""

LIGAS = {
    "chile": {
        "nombre": "Liga de Primera",
        "pais": "Chile",
        # Clubes de la temporada por ID de Wikidata (la tabla de la página de temporada usa códigos)
        "clubes_wikidata": [
            "Q758689",    # Audax Italiano
            "Q721560",    # Universidad de Concepción
            "Q719719",    # Palestino
            "Q427446",    # Universidad Católica
            "Q737753",    # Universidad de Chile
            "Q207373",    # Colo-Colo
            "Q2407595",   # Coquimbo Unido
            "Q2317166",   # Deportes Concepción
            "Q642098",    # Deportes La Serena
            "Q105144613", # Deportes Limache
            "Q1103684",   # Everton
            "Q1023191",   # Huachipato
            "Q719722",    # O'Higgins
            "Q719383",    # Unión La Calera
            "Q2317539",   # Ñublense
            "Q642669",    # Cobresal
        ],
        "pagina_temporada": "Liga de Primera {anio}",
        "anexo": "Anexo:Estadísticas de la Liga de Primera {anio}",
        "tabla": "modulo",           # tabla de posiciones con |nombre_XXX= y |ganados_XXX=
        # escala de OVR de la liga (las ligas más fuertes tienen media y techo más altos)
        "ovr": {"media": 63.5, "desv": 6.0, "min": 48, "max": 84},
        "vueltas": 2,                # 16 equipos ida y vuelta = 30 fechas
    },
    "argentina": {
        "nombre": "Liga Profesional",
        "pais": "Argentina",
        "pagina_temporada": "Campeonato de Primera División {anio} (Argentina)",
        "seccion_equipos": "Equipos participantes",   # los clubes salen de esta tabla
        # nombre a usar para clubes cuyo título no permite desambiguarlos (título -> nombre)
        "renombrar": {"Asociación Atlética Estudiantes": "Estudiantes (RC)"},
        "anexo": None,                                # no hay anexo con goleadores por equipo
        "tabla": "plantilla",       # {{Tabla de posiciones equipo|g=|e=|p=|gf=|gc=|eq=}}
        "seccion_tabla": "Tabla general de la temporada",
        "ovr": {"media": 66.0, "desv": 6.0, "min": 50, "max": 87},
        "vueltas": 1,                # 30 equipos todos contra todos = 29 fechas
    },
    "brasil": {
        "nombre": "Brasileirão Serie A",
        "pais": "Brasil",
        "pagina_temporada": "Campeonato Brasileño de Fútbol Serie A {anio}",
        "seccion_equipos": "Información",
        "anexo": None,
        "tabla": "modulo",
        "ovr": {"media": 68.0, "desv": 6.0, "min": 52, "max": 89},
        "vueltas": 2,                # 20 equipos ida y vuelta = 38 fechas
    },
}


def liga(clave: str) -> dict:
    if clave not in LIGAS:
        raise SystemExit(f"Liga desconocida: {clave}. Opciones: {', '.join(LIGAS)}")
    return LIGAS[clave]


def archivo_planteles(clave: str, anio: int) -> str:
    return f"data/liga_{clave}_{anio}.json"


def archivo_stats(clave: str, anio: int) -> str:
    return f"data/liga_{clave}_{anio}_stats.json"


def archivo_cartas(clave: str, anio: int) -> str:
    return f"data/cartas_liga_{clave}_{anio}.csv"
