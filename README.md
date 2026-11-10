# ⚽ FutGolMasterBot

Juego de fútbol: arma tu club con cartas de jugadores, juega una liga simulada contra clubes bot, gana monedas y abre sobres.

- **Versión jugable actual:** web local (FastAPI + SQLite), pensada también para celular.
- **Bot de Discord:** en pausa (nextcord + MongoDB).
- **Cartas:** diseño propio generado por código con Pillow.

---

## 🎮 Jugar en local (web)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
uvicorn web.app:app --reload    # abre http://127.0.0.1:8000
```

Para probar desde el celular en la misma red: `uvicorn web.app:app --host 0.0.0.0` y abre `http://<IP-de-tu-PC>:8000`.

Necesita los catálogos de cartas en `data/cartas_liga_*_2026.csv`. Para generarlos (Chile y Argentina; se pueden sumar ligas en `scraper/ligas.py`):

```bash
python -m scraper.plantillas --liga chile        # planteles (Wikipedia)
python -m scraper.estadisticas --liga chile      # tabla, goles, arqueros y perfiles (Wikipedia + Wikidata)
python -m cartas.valoracion --liga chile         # OVR, atributos y precio
# lo mismo con --liga argentina
```

La partida se guarda en `data/partida.sqlite`.

**Cómo se juega**
- Los clubes reales de todas las ligas descargadas se ordenan por fuerza en una pirámide: **Liga Oro, Plata y Bronce** (14 equipos cada una, ida y vuelta: 26 fechas).
- Tu club empieza en la Liga Bronce. Cada temporada suben los 2 primeros y bajan los 2 últimos de cada división; las divisiones de arriba pagan más.
- Empiezas con 18 jugadores modestos. Eliges formación, mentalidad y el once.
- Cada partido da monedas (victoria 1.000, empate 450, derrota 200, +50 por gol) y la posición final da un premio.
- Con las monedas abres sobres (bronce, plata, oro) con probabilidades visibles. Lo que sobra se vende.
- Lesiones y tarjetas duran fechas: roja = 1 fecha, 5 amarillas = 1 fecha.

Los valores de la economía están en `juego/economia.py`. Para calibrar la dificultad:

```bash
python -m scripts.simular_carrera --carreras 8 --temporadas 4 --estrategia plata
```

### Fotos y renders de jugadores (solo local)

Las cartas usan `assets/renders/<Nombre>.png` si existe (si no, una silueta). Esa carpeta no se sube a GitHub.

```bash
# Automático: fotos con licencia libre de Wikimedia Commons (autor y licencia en assets/renders/creditos.json)
python -m scraper.fotos --liga chile --recortar     # --recortar quita el fondo (pip install rembg)
python -m scraper.fotos --liga argentina --club "Boca Juniors" --forzar --recortar

# Manual: lista de faltantes con enlaces de búsqueda, y luego importar lo que bajes
python -m scraper.renders_manual pendientes --min-ovr 70   # abre data/renders_pendientes.html
#   guarda las imágenes en assets/renders/entrada/ (nombre parecido al del jugador)
python -m scraper.renders_manual importar
```

Los escudos van en `assets/escudos/<club>.png` (paquete PNG de footylogos.com, uso interno).

## 🤖 Bot de Discord (en pausa)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # y completa TOKEN, MONGO_URI y DATABASE_NAME
python bot.py
```

### Comandos del bot

| Comando | Qué hace |
|---|---|
| `/p` | Muestra tu perfil (lo crea la primera vez) |
| `/claim` | Reclama una carta aleatoria (espera configurable con `CLAIM_COOLDOWN_SEGUNDOS`) |
| `/cartas` | Muestra tu inventario paginado |

---

## 📁 Estructura

```
bot.py                 Punto de entrada: carga los cogs y arranca el bot
cogs/                  Comandos de Discord (perfil, cartas)
models/                Carta, Usuario y la vista paginada del inventario
database/              Conexión a MongoDB y funciones de acceso
cartas/generador.py    Generador de imágenes de cartas (diseño propio)
scripts/               Tareas sueltas, como cargar cartas a la BDD
scraper/               Obtención de datos y renders (ejecución manual)
partidos/              Motor de partidos por probabilidades y narrador
juego/                 Lógica del juego: liga, alineación, sanciones, economía (SQLite)
web/                   Web local (FastAPI + plantillas Jinja)
assets/fonts/          Fuente Barlow Condensed (licencia OFL)
data/                  CSV de cartas — solo local, ignorado por git
assets/renders/        Renders de jugadores — solo local, ignorado por git
```

---

## 🃏 Cartas

Las cartas se dibujan por código en `cartas/generador.py`: forma, colores por nivel, barras de estadísticas y tipografía son propios. No se usan plantillas, logos ni fuentes de terceros.

- **Niveles:** bronce (< 65), plata (65–74), oro (≥ 75). Las cartas **raras** llevan franjas y un borde más grueso.
- **Estadísticas:** VEL, TIR, PAS, REG, DEF, FIS y la valoración general.
- **Render:** si existe `assets/renders/<Nombre>_<OVR>.png` se usa. Si no, se dibuja una silueta genérica.

```bash
# Generar imágenes de muestra en assets/cartas/
python -m cartas.generador data/cartas_ejemplo.csv --limite 5

# Cargar cartas a MongoDB
python -m scripts.cargar_cartas data/cartas_ejemplo.csv
python -m scripts.cargar_cartas data/cartas_oro_raras.csv --rara
```

### Datos y scraping

Los scripts de `scraper/` se ejecutan a mano y guardan su resultado **solo en local** (`data/` y `assets/renders/` están en `.gitignore`):

```bash
python -m scraper.futbin --version gold_rare --paginas 10 --salida data/cartas_oro_raras.csv
python -m scraper.renders data/cartas_ejemplo.csv
```

> ⚠️ Los datos y las imágenes que se obtienen de sitios de terceros pertenecen a sus dueños. **No los subas al repositorio** ni los uses con fines comerciales.

---

## ⚽ Partidos simulados

El motor (`partidos/motor.py`) simula el partido minuto a minuto con probabilidades. Usa:
- las estadísticas y el OVR de cada carta;
- la afinidad con el puesto en que juega cada jugador;
- el estado (los lesionados y suspendidos no juegan);
- el nivel de mejora;
- la energía, que baja más rápido si el jugador tiene poco físico.

Genera goles, atajadas, tiros al palo, faltas, tarjetas, penales, lesiones, cambios y tiempo de adición (`45+3'`). Con la misma semilla, el resultado se repite.

El narrador (`partidos/narrador.py`) arma cada jugada según quién participa (centro desde la banda, contragolpe, pared, jugada individual, remate de lejos…) y comenta el contexto: empate, remontada, doblete o gol sobre la hora.

```bash
python -m partidos.simular --local "Liverpool" --visita "Chelsea" --tipo liga
python -m partidos.simular --aleatorio --semilla 7 --en-vivo
python -m unittest            # tests, incluida la calibración estadística
```

---

## 🗺️ Diseño del juego (pendiente)

### Inventario
Cada carta del inventario tiene nivel de mejora, estado (disponible, lesionado o suspendido), duración de la lesión, tarjetas acumuladas y las plantillas en las que está.

### Partidos
- **Amistosos:** no acumulan amarillas, pero las rojas y las lesiones sí cuentan.
- **Liga rankeada:** se aplican amarillas, rojas y lesiones. El partido se narra en tiempo real en Discord y dura unos 3 minutos.

### Plantillas
Hasta 5 por usuario, cada una con nombre, jugadores, formación (4-4-2, 3-5-2, …) y estadio.

### Otros módulos
Mercado, estadísticas y plataforma web.
