# ⚽ FutGolMasterBot

Bot de Discord para coleccionar cartas de jugadores de fútbol, armar plantillas y disputar partidos simulados.

- **Backend:** Python 3.11+ con [nextcord](https://github.com/nextcord/nextcord)
- **Base de datos:** MongoDB
- **Cartas:** diseño propio generado por código con Pillow

---

## 🚀 Puesta en marcha

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
partidos/              Prototipo de narración de partidos con IA
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

## 🗺️ Diseño del juego (pendiente)

### Inventario
Cada carta del inventario tiene nivel de mejora, estado (disponible, lesionado o suspendido), duración de la lesión, tarjetas acumuladas y las plantillas en las que está.

### Partidos
- **Amistosos:** no acumulan amarillas, pero las rojas y las lesiones sí cuentan.
- **Liga rankeada:** se aplican amarillas, rojas y lesiones. El partido se narra en tiempo real en Discord y dura unos 3 minutos.
- Prototipo de narración con IA: `python -m partidos.simulador_ia` (requiere `AIML_API_KEY`).

### Plantillas
Hasta 5 por usuario, cada una con nombre, jugadores, formación (4-4-2, 3-5-2, …) y estadio.

### Otros módulos
Mercado, estadísticas y plataforma web.
