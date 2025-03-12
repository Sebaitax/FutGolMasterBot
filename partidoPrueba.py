import os
from openai import OpenAI

# Configurar el cliente OpenAI con la API de AIML
client = OpenAI(
    base_url="https://api.aimlapi.com/v1",
    api_key="",  
)

# Función para leer el archivo de texto con los datos del partido
def leer_datos_partido(nombre_archivo):
    with open(nombre_archivo, "r", encoding="utf-8") as file:
        return file.read()

# Archivo de entrada con los datos del partido
archivo_datos = "datos_partido.txt"
datos_partido = leer_datos_partido(archivo_datos)

# Crear el prompt para la simulación del partido
prompt = f"""
Usa la siguiente información para generar una simulación de partido de fútbol tipo Fantasy para Discord:

{datos_partido}

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

# Llamar a la API para generar la simulación
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Eres una IA deportiva especializada en narrar partidos de fútbol."},
        {"role": "user", "content": prompt},
    ],
)

# Obtener el resultado generado
simulacion_partido = response.choices[0].message.content

# Mostrar la simulación
print(simulacion_partido)

# Guardar la simulación en un archivo de salida
with open("simulacion_partido.txt", "w", encoding="utf-8") as file:
    file.write(simulacion_partido)

print("\nSimulación guardada en 'simulacion_partido.txt'")
