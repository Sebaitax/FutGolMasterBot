"""Prototipo: narración de un partido generada por IA a partir de las alineaciones.

Uso:
    python -m partidos.simulador_ia [ruta_datos.txt]

Requiere AIML_API_KEY en el .env. Todavía no está conectado al bot.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

AQUI = Path(__file__).resolve().parent
DATOS_EJEMPLO = AQUI / "datos_partido_ejemplo.txt"

PROMPT = """
Usa la siguiente información para generar una simulación de partido de fútbol tipo Fantasy para Discord:

{datos}

Requisitos:
- Incluir minuto a minuto con jugadas clave (goles, atajadas, faltas, tiros al palo, etc.).
- Formato de mensaje con emojis y estilo narrativo emocionante.
- Simular un partido con tiempos de juego, incluyendo el descanso y el final.
- Elegir un jugador destacado del partido.

Ejemplo de salida:

🔥 [Equipo 1] 🆚 [Equipo 2] - Simulación del Partido 🔥
📍 [Estadio]
⏳ Inicio del partido...

🕐 Minuto 5
💨 ¡Arranque explosivo! [Jugador] filtra un pase para [Jugador], pero [Arquero] reacciona con una gran atajada.

...
🔔 ¡Final del partido!
✅ [Equipo ganador] [Marcador] [Equipo perdedor]

🏆 Jugador del partido: [Mejor jugador] ⭐
"""


def simular_partido(datos_partido: str) -> str:
    client = OpenAI(base_url="https://api.aimlapi.com/v1", api_key=os.getenv("AIML_API_KEY"))
    respuesta = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Eres una IA deportiva especializada en narrar partidos de fútbol."},
            {"role": "user", "content": PROMPT.format(datos=datos_partido)},
        ],
    )
    return respuesta.choices[0].message.content


def main():
    load_dotenv()
    ruta = Path(sys.argv[1]) if len(sys.argv) > 1 else DATOS_EJEMPLO
    simulacion = simular_partido(ruta.read_text(encoding="utf-8"))
    print(simulacion)
    Path("simulacion_partido.txt").write_text(simulacion, encoding="utf-8")
    print("\nSimulación guardada en 'simulacion_partido.txt'")


if __name__ == "__main__":
    main()
