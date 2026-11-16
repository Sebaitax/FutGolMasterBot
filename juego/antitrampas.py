"""Controles del servidor contra trampas en el pulso.

El pulso se juega en el navegador y este informa la precisión de cada toque (0 a 1). Un tramposo
puede mandar 1.0 siempre o responder al instante. El servidor no puede ver la pantalla, así que:

1. Tiempo mínimo: cada ronda necesita un mínimo de tiempo humano. Si las precisiones llegan antes
   de lo posible (medido con el reloj del servidor), cuentan como fallo (0.1).
2. Estadística: se guardan las últimas precisiones de cada jugador. Un promedio sostenido por
   sobre lo humano (muchos toques casi perfectos seguidos) se limita y queda anotado como sospecha.

No es infalible (nada lo es si el juego corre en el navegador), pero quita las trampas fáciles:
mandar "precision=1" a mano o con un script.
"""
from __future__ import annotations

SEGUNDOS_MIN_RONDA = 1.0      # cada ronda trae ~1,3 s de animaciones: nadie la completa en menos
SEGUNDOS_MIN_TOQUE_PVP = 0.35  # en vivo: desde que empieza la ronda hasta el toque
HISTORIAL = 30                # últimas precisiones que se miran
MUESTRA_MINIMA = 15
MEDIA_SOSPECHOSA = 0.92       # los mejores jugadores reales promedian bastante menos
TOPE_SOSPECHA = 0.75          # mientras haya sospecha, ningún toque vale más que esto
FALLO = 0.1


def limpiar(valores) -> list[float]:
    salida = []
    for v in valores if isinstance(valores, list) else []:
        try:
            salida.append(min(1.0, max(0.0, float(v))))
        except (TypeError, ValueError):
            salida.append(FALLO)
    return salida


def revisar(precisiones: list[float], segundos: float | None, historial: list[float]) -> tuple[list[float], list[float], str]:
    """Devuelve (precisiones aceptadas, historial nuevo, motivo de sospecha o "")."""
    precisiones = limpiar(precisiones)
    if not precisiones:
        return precisiones, historial, ""
    motivo = ""
    if segundos is not None and segundos < SEGUNDOS_MIN_RONDA * len(precisiones):
        motivo = f"pulso demasiado rápido ({segundos:.1f} s para {len(precisiones)} toques)"
        precisiones = [FALLO] * len(precisiones)
    historial = (historial + precisiones)[-HISTORIAL:]
    if len(historial) >= MUESTRA_MINIMA and sum(historial) / len(historial) >= MEDIA_SOSPECHOSA:
        motivo = motivo or f"precisión imposible: promedio {sum(historial) / len(historial):.2f} en {len(historial)} toques"
        precisiones = [min(p, TOPE_SOSPECHA) for p in precisiones]
    return precisiones, historial, motivo
