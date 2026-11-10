"""Descarga fotos de jugadores desde 365Scores.

Usa la API JSON que consume la web de 365scores.com (planteles por club) y su CDN de
imágenes. Las fotos son de 365Scores: quedan SOLO en local (assets/renders/ está en
.gitignore) y en assets/renders/creditos.json se marca su origen.

Uso:
    # un jugador, con el enlace de su ficha (o solo el id)
    python -m scraper.fotos_365 --url https://www.365scores.com/es/football/player/mateo-mendoza-125772
    python -m scraper.fotos_365 --id 125772 --nombre "Mateo Mendoza"

    # todo el plantel de un club, con el enlace de su página
    python -m scraper.fotos_365 --equipo https://www.365scores.com/es/football/team/colo-colo-1239/squad

    # toda una liga (empareja cada carta con el plantel del club en 365Scores)
    python -m scraper.fotos_365 --liga argentina
    python -m scraper.fotos_365 --liga chile --club "Colo-Colo" --forzar

    # apellidos para quienes en Wikipedia tienen un solo nombre ("Danilo" -> "Danilo Santos");
    # después correr cartas.valoracion para regenerar las cartas
    python -m scraper.fotos_365 --liga brasil --nombres

    # buscar en todo 365Scores a quien no está en su club, y luego dejar los planteles como hoy
    # (excluye juveniles sin foto y a quien ya no está en el primer equipo; después correr cartas.valoracion)
    python -m scraper.fotos_365 --liga chile --buscar
    python -m scraper.fotos_365 --liga chile --depurar

    # escudos de los clubes de una liga (assets/escudos/<club>.png)
    python -m scraper.fotos_365 --liga brasil --escudos

Las fotos vienen con fondo blanco: se quita con rembg (--sin-recortar para dejarlo).
Por defecto no pisa renders que ya existen; con --forzar los reemplaza.
"""
import argparse
import csv
import difflib
import io
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image

from scraper.ligas import archivo_cartas, liga

UA = {"User-Agent": "Mozilla/5.0 (FutGolMasterBot)"}
API = "https://webws.365scores.com/web"
IMAGEN = "https://imagecache.365scores.com/image/upload/f_png,w_600,c_limit/{version}Athletes/{id}"
FICHA = "https://www.365scores.com/es/football/player/{slug}-{id}"
RENDERS = Path("assets/renders")
CREDITOS = RENDERS / "creditos.json"
PARAMS = {"appTypeId": 5, "langId": 29, "timezoneName": "America/Santiago"}

# competición de cada liga en 365Scores y nombres de club que no coinciden con los nuestros
COMPETICION = {"chile": 135, "argentina": 72, "brasil": 113}
ALIAS_CLUB = {
    "Cobresal": "Deportes Cobresal",
    "Universidad de Concepción": "U. de Concepción",
    "Unión La Calera": "U. La Calera",
    "Estudiantes (LP)": "Estudiantes de La Plata",
    "Estudiantes (RC)": "Estudiantes RC",
    "Gimnasia y Esgrima (LP)": "Gimnasia La Plata",
    "Gimnasia y Esgrima (M)": "Gimnasia de Mendoza",
    "Unión": "Unión de Santa Fe",
    "Talleres (C)": "Talleres de Córdoba",
    "Central Córdoba (SdE)": "Central Córdoba SdE",
    "Sarmiento (J)": "Sarmiento Junín",
}


def _plano(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(re.split(r"[^a-z0-9]+", t)).strip()


def _api(ruta: str, **params) -> dict:
    url = f"{API}/{ruta}/?" + urllib.parse.urlencode({**PARAMS, **params})
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.load(r)


_recortador = None


def quitar_fondo(imagen: Image.Image) -> Image.Image:
    """Las fotos vienen con fondo blanco: se quita con rembg (la 1.ª vez baja un modelo)."""
    global _recortador
    if _recortador is None:
        from scraper.fotos import cargar_recortador
        _recortador = cargar_recortador()
    return _recortador(imagen)


def bajar_foto(atleta: dict, recortar: bool = True) -> Image.Image | None:
    """Foto del jugador (RGBA, recortada al contorno) o None si 365Scores no tiene."""
    version = atleta.get("imageVersion") or 0
    url = IMAGEN.format(version=f"v{version}/" if version else "", id=atleta["id"])
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            imagen = Image.open(io.BytesIO(r.read())).convert("RGBA")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    if recortar:
        imagen = quitar_fondo(imagen)
    caja = imagen.getchannel("A").getbbox()
    return imagen.crop(caja) if caja else imagen


def clubes(competicion: int) -> dict[str, int]:
    """Nombre del club en 365Scores -> id, según la tabla de posiciones."""
    datos = _api("standings", competitions=competicion)
    return {r["competitor"]["name"]: r["competitor"]["id"]
            for s in datos.get("standings", []) for r in s.get("rows", [])}


def plantel(club_id: int) -> list[dict]:
    datos = _api("squads", competitors=club_id)
    return [a for s in datos.get("squads", []) for a in s.get("athletes", [])]


def puntaje(carta: dict, atleta: dict) -> float:
    """Qué tan probable es que la carta y el jugador de 365Scores sean la misma persona."""
    a, b = _plano(carta["Nombre"]), _plano(atleta["name"])
    if a == b:
        base = 1.0
    elif set(a.split()) <= set(b.split()) or set(b.split()) <= set(a.split()):
        base = 0.9  # "Mateo Mendoza" vs "Mateo Nicolás Mendoza"
    else:
        base = difflib.SequenceMatcher(None, a, b).ratio()
        if not (carta.get("Edad") and atleta.get("age")):
            base -= 0.2  # nombres solo parecidos y sin edad para confirmar ("Janderson" vs "Wanderson")
    if carta.get("Dorsal") and str(atleta.get("jerseyNum", "")) == carta["Dorsal"]:
        base += 0.05
    if carta.get("Edad") and atleta.get("age"):
        diferencia = abs(int(atleta["age"]) - int(carta["Edad"]))
        if diferencia == 0:
            base += 0.05
        elif diferencia > 1:  # homónimo (p. ej. "Lautaro Bianco" 19 años vs "Lautaro Blanco" 27)
            base -= 0.5
    return base


def emparejar(carta: dict, atletas: list[dict], minimo: float = 0.85) -> dict | None:
    puntos = sorted(((puntaje(carta, a), a) for a in atletas), key=lambda x: -x[0])
    if not puntos or puntos[0][0] < minimo:
        return None
    if len(puntos) > 1 and puntos[1][0] >= puntos[0][0]:  # empate: no adivinar
        return None
    return puntos[0][1]


_repetidos: set[str] | None = None


def archivo_render(nombre: str, club: str = "") -> Path:
    """assets/renders/<Nombre>.png, o <Nombre> (<Club>).png si hay varias cartas con ese nombre
    (p. ej. tres "Danilo" en Brasil). El generador y la web buscan primero la versión con club."""
    global _repetidos
    if _repetidos is None:
        from collections import Counter
        cuenta = Counter(c["Nombre"] for c in todas_las_cartas())
        _repetidos = {n for n, k in cuenta.items() if k > 1}
    if club and nombre in _repetidos:
        return RENDERS / f"{nombre} ({club}).png"
    return RENDERS / f"{nombre}.png"


def guardar(destino: Path, atleta: dict, imagen: Image.Image, creditos: dict, recortada: bool):
    RENDERS.mkdir(parents=True, exist_ok=True)
    imagen.save(destino, optimize=True)
    nombre = destino.stem
    creditos[nombre] = {"origen": "365scores", "autor": "365Scores", "licencia": "© 365Scores (solo uso local)",
                        "fuente": FICHA.format(slug=atleta.get("nameForURL", ""), id=atleta["id"]),
                        "id_365": atleta["id"], "recortada": recortada}


def emparejar_atleta(atleta: dict, cartas: list[dict], minimo: float = 0.85) -> dict | None:
    """La carta que corresponde a un jugador de 365Scores (o None si no hay una clara)."""
    puntos = sorted(((puntaje(c, atleta), c) for c in cartas), key=lambda x: -x[0])
    if not puntos or puntos[0][0] < minimo:
        return None
    if len(puntos) > 1 and puntos[1][0] >= puntos[0][0]:
        return None
    return puntos[0][1]


def todas_las_cartas() -> list[dict]:
    from scraper.renders_manual import cargar_cartas
    return cargar_cartas()


def un_equipo(args):
    """Todo el plantel de un club, con el enlace de su página en 365Scores."""
    m = re.search(r"/team/([^/]+)-(\d+)", args.equipo)
    if not m:
        sys.exit(f"No encontré el id del club en {args.equipo}")
    atletas = plantel(int(m.group(2)))
    print(f"{len(atletas)} jugadores en el plantel de {m.group(1)}")
    cartas = todas_las_cartas()
    slug = _plano(m.group(1))
    del_club = [c for c in cartas if _plano(ALIAS_CLUB.get(c["Club"], c["Club"])) == slug]
    creditos = cargar_creditos()
    bajadas, sin_foto = 0, []
    for atleta in atletas:
        # se guarda con el nombre de su carta si la tiene (para que el generador la encuentre):
        # se busca en las cartas del club; en otro club solo vale el nombre idéntico (+ edad)
        carta = emparejar_atleta(atleta, del_club) or emparejar_atleta(atleta, cartas, minimo=1.05)
        nombre = carta["Nombre"] if carta else atleta["name"]
        destino = archivo_render(nombre, carta["Club"] if carta else "")
        if not args.forzar and destino.exists():
            continue
        try:
            imagen = bajar_foto(atleta, not args.sin_recortar)
        except Exception as e:
            print(f"  ✗ {atleta['name']}: {e}")
            continue
        if imagen is None:
            sin_foto.append(atleta["name"])
            continue
        guardar(destino, atleta, imagen, creditos, not args.sin_recortar)
        bajadas += 1
        print(f"  ✓ {nombre}" + ("" if nombre == atleta["name"] else f" <- {atleta['name']}"), flush=True)
        time.sleep(0.2)
    escribir_creditos(creditos)
    print(f"OK: {bajadas} fotos nuevas en {RENDERS}/")
    if sin_foto:
        print(f"{len(sin_foto)} sin foto en 365Scores: {', '.join(sin_foto)}")


def cargar_creditos() -> dict:
    return json.loads(CREDITOS.read_text(encoding="utf-8")) if CREDITOS.exists() else {}


def escribir_creditos(creditos: dict):
    CREDITOS.write_text(json.dumps(creditos, ensure_ascii=False, indent=1), encoding="utf-8")


def archivo_nombres(clave: str, anio: int) -> Path:
    return Path(f"data/nombres_365_{clave}_{anio}.json")


def nombres(args):
    """Nombre con apellido para los jugadores que en Wikipedia figuran con una sola palabra
    ("Danilo" -> "Danilo Santos"). Lo usa cartas.valoracion al armar el CSV de cartas."""
    from datetime import date
    from scraper.ligas import archivo_planteles
    planteles = json.loads(Path(archivo_planteles(args.liga, args.anio)).read_text(encoding="utf-8"))
    por_plano = {_plano(n): i for n, i in clubes(COMPETICION[args.liga]).items()}
    salida, cambios = {}, 0
    for club in planteles["clubes"]:
        club_id = por_plano.get(_plano(ALIAS_CLUB.get(club["club"], club["club"])))
        if club_id is None:
            print(f"  ! club sin pareja en 365Scores: {club['club']}")
            continue
        atletas = plantel(club_id)
        time.sleep(0.3)
        for j in club["jugadores"]:
            nombre = j["nombre"].split("(")[0].strip()
            if len(nombre.split()) != 1:
                continue
            edad = ""
            if j.get("nacimiento"):
                n = date.fromisoformat(j["nacimiento"])
                hoy = date.today()
                edad = str(hoy.year - n.year - ((hoy.month, hoy.day) < (n.month, n.day)))
            atleta = emparejar({"Nombre": nombre, "Edad": edad, "Dorsal": j.get("dorsal", "")}, atletas)
            if atleta and len(atleta["name"].split()) > 1 and _plano(atleta["name"]) != _plano(nombre):
                completo = " ".join(atleta["name"].split())  # 365Scores a veces trae dobles espacios
                salida.setdefault(club["club"], {})[f"{nombre}|{j.get('dorsal', '')}"] = completo
                cambios += 1
                print(f"  {nombre:18} -> {completo}  ({club['club']})")
    destino = archivo_nombres(args.liga, args.anio)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK: {cambios} nombres con apellido -> {destino}  (ahora corre: python -m cartas.valoracion --liga {args.liga})")


ESCUDO = "https://imagecache.365scores.com/image/upload/f_png,w_256,c_limit/Competitors/{id}"


def escudos(args):
    """Escudos de los clubes de una liga en assets/escudos/<slug>.png (los que falten)."""
    destino = Path("assets/escudos")
    destino.mkdir(parents=True, exist_ok=True)
    with open(archivo_cartas(args.liga, args.anio), newline="", encoding="utf-8") as f:
        nuestros = sorted({c["Club"] for c in csv.DictReader(f)})
    por_plano = {_plano(n): i for n, i in clubes(COMPETICION[args.liga]).items()}
    for club in nuestros:
        archivo = destino / f"{_plano(club).replace(' ', '-')}.png"
        club_id = por_plano.get(_plano(ALIAS_CLUB.get(club, club)))
        if club_id is None:
            print(f"  ! sin pareja en 365Scores: {club}")
            continue
        if archivo.exists() and not args.forzar:
            continue
        with urllib.request.urlopen(urllib.request.Request(ESCUDO.format(id=club_id), headers=UA), timeout=30) as r:
            imagen = Image.open(io.BytesIO(r.read())).convert("RGBA")
        caja = imagen.getchannel("A").getbbox()
        (imagen.crop(caja) if caja else imagen).save(archivo, optimize=True)
        print(f"  ✓ {club} -> {archivo}")
        time.sleep(0.2)


def un_jugador(args):
    if args.url:
        m = re.search(r"-(\d+)/?(?:[?#].*)?$", args.url)
        if not m:
            sys.exit(f"No encontré el id del jugador en {args.url}")
        args.id = int(m.group(1))
    atletas = _api("athletes", athletes=args.id).get("athletes", [])
    if not atletas:
        sys.exit(f"365Scores no tiene un jugador con id {args.id}")
    atleta = atletas[0]
    nombre = args.nombre or atleta["name"]
    destino = RENDERS / f"{nombre}.png"
    if destino.exists() and not args.forzar:
        sys.exit(f"Ya existe {destino} (usa --forzar para reemplazarlo)")
    imagen = bajar_foto(atleta, not args.sin_recortar)
    if imagen is None:
        sys.exit(f"{atleta['name']} no tiene foto en 365Scores")
    creditos = cargar_creditos()
    guardar(destino, atleta, imagen, creditos, not args.sin_recortar)
    escribir_creditos(creditos)
    print(f"✓ {atleta['name']} -> {destino} ({imagen.width}x{imagen.height})")


def _texto(s: str) -> str:
    """El buscador a veces devuelve UTF-8 mal decodificado ("BenjamÃ­n" -> "Benjamín")."""
    if "Ã" in s or "Â" in s:
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s


GRUPO = {"GK": "Portero", "CB": "Defensor", "LB": "Defensor", "RB": "Defensor", "LWB": "Defensor", "RWB": "Defensor",
         "CDM": "Mediocampista", "CM": "Mediocampista", "CAM": "Mediocampista", "LM": "Mediocampista",
         "RM": "Mediocampista", "LW": "Delantero", "RW": "Delantero", "ST": "Delantero", "CF": "Delantero"}
INCOMPATIBLES = [{"Portero", "Defensor"}, {"Portero", "Mediocampista"}, {"Portero", "Delantero"},
                 {"Defensor", "Delantero"}]


def valida_global(carta: dict, ficha: dict) -> bool:
    """Fuera del plantel del club hay muchos homónimos ("Christian" de Cruzeiro -> Christian Pulisic):
    - nombre idéntico y misma edad (±1): vale (las posiciones de juveniles en Wikipedia no son fiables);
    - nombre idéntico sin edad en la carta: misma nacionalidad y posición compatible;
    - nombre solo parecido: edad, nacionalidad y posición."""
    mismo_nombre = _plano(carta["Nombre"]) == _plano(_texto(ficha["name"]))
    edad_ok = None
    if carta.get("Edad") and ficha.get("age"):
        edad_ok = abs(int(ficha["age"]) - int(carta["Edad"])) <= 1
    if edad_ok is False:
        return False
    if mismo_nombre and edad_ok:
        return True
    nac = _plano(carta.get("Nación", ""))
    nac_ok = len(nac) > 3 and _plano(_texto(ficha.get("nationalityName") or "")) == nac  # "GNB" y similares: sin dato
    grupos = {GRUPO.get(carta.get("Posición", "")), (ficha.get("position") or {}).get("name")}
    pos_ok = not any(grupos == par for par in map(set, INCOMPATIBLES))
    if mismo_nombre:
        return nac_ok and pos_ok
    return bool(edad_ok) and nac_ok and pos_ok


def buscar_global(carta: dict) -> tuple[dict, str] | None:
    """Busca al jugador en todo 365Scores (para quien ya no está en el plantel de su club).
    Devuelve (atleta, club actual) solo si nombre y edad cuadran."""
    try:
        r = _api("search", query=carta["Nombre"], filter="all")
    except Exception:
        return None
    candidatos = [a for a in r.get("athletes", []) if a.get("sportId") == 1][:5]
    mejor = None
    for i, a in enumerate(candidatos):
        try:  # el buscador no trae la edad: se pide la ficha
            d = _api("athletes", athletes=a["id"])
        except Exception:
            continue
        if not d.get("athletes"):
            continue
        ficha = d["athletes"][0]
        ficha["name"] = _texto(ficha["name"])
        club = next((_texto(c["name"]) for c in d.get("competitors", []) if c["id"] == ficha.get("clubId")), "")
        if not valida_global(carta, ficha):
            continue
        puntos = puntaje(carta, ficha)
        # apodos ("Gabigol" -> "Gabriel Barbosa"): primer resultado y misma edad exacta
        if (puntos < 0.85 and i == 0 and len(carta["Nombre"].split()) == 1 and carta.get("Edad")
                and str(ficha.get("age")) == carta["Edad"]):
            puntos = 0.86
        if puntos >= 0.85 and (mejor is None or puntos > mejor[0]):
            mejor = (puntos, ficha, club)
        time.sleep(0.15)
    return (mejor[1], mejor[2]) if mejor else None


def archivo_ajustes(clave: str, anio: int) -> Path:
    return Path(f"data/ajustes_365_{clave}_{anio}.json")


def depurar(args):
    """Deja los planteles como están hoy en 365Scores (Wikipedia va atrasada). Escribe
    data/ajustes_365_<liga>_<año>.json, que aplica cartas.valoracion:
      - excluir: cartas sin foto (juveniles) o de jugadores que ya no están en el primer equipo;
      - traspasos: quien se fue a otro club de la misma liga y no tiene carta allí.
    Requiere haber corrido antes: --liga <x> --buscar."""
    from scraper.renders_manual import cargar_cartas, tiene_render
    todas = {f'{c["Nombre"]}|{c["Club"]}': c for c in cargar_cartas()}
    with open(archivo_cartas(args.liga, args.anio), newline="", encoding="utf-8") as f:
        de_la_liga = {f'{c["Nombre"]}|{c["Club"]}': c for c in csv.DictReader(f)}
    clubes_liga = {_plano(ALIAS_CLUB.get(c["Club"], c["Club"])): c["Club"] for c in de_la_liga.values()}
    ruta_cambios = Path(f"data/cambios_club_365_{args.liga}_{args.anio}.json")
    cambios = json.loads(ruta_cambios.read_text(encoding="utf-8")) if ruta_cambios.exists() else {}

    excluir, traspasos = set(), {}
    for clave, c in de_la_liga.items():
        if not tiene_render(c["Nombre"], c["Club"]):
            excluir.add(clave)
    for clave, actual in cambios.items():
        c = de_la_liga.get(clave)
        if c is None or _plano(actual) == _plano(ALIAS_CLUB.get(c["Club"], c["Club"])):
            continue
        nuevo = clubes_liga.get(_plano(actual))
        if nuevo and f'{c["Nombre"]}|{nuevo}' not in todas:
            traspasos[clave] = nuevo  # se cambia de club dentro de la liga
        else:
            excluir.add(clave)  # reserva, juveniles, otro país, o ya tiene carta en su club nuevo
    excluir -= set(traspasos)
    destino = archivo_ajustes(args.liga, args.anio)
    destino.write_text(json.dumps({"excluir": sorted(excluir), "traspasos": traspasos}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    print(f"{len(excluir)} cartas a excluir y {len(traspasos)} traspasos -> {destino}")
    for clave, nuevo in traspasos.items():
        print(f"  {clave.replace('|', ' (')}) -> {nuevo}")
    print(f"Ahora corre: python -m cartas.valoracion --liga {args.liga}")


def una_liga(args):
    liga(args.liga)
    if args.liga not in COMPETICION:
        sys.exit(f"Falta el id de 365Scores de la liga {args.liga} en COMPETICION")
    with open(archivo_cartas(args.liga, args.anio), newline="", encoding="utf-8") as f:
        cartas = [c for c in csv.DictReader(f) if not args.club or c["Club"].lower() == args.club.lower()]
    cartas = [c for c in cartas if args.forzar or not archivo_render(c["Nombre"], c["Club"]).exists()]
    print(f"{len(cartas)} cartas sin foto")
    if not cartas:
        return

    ids = clubes(COMPETICION[args.liga])
    por_plano = {_plano(n): i for n, i in ids.items()}
    planteles: dict[str, list[dict]] = {}
    for club in sorted({c["Club"] for c in cartas}):
        club_id = por_plano.get(_plano(ALIAS_CLUB.get(club, club)))
        if club_id is None:
            print(f"  ! club sin pareja en 365Scores: {club} (agrégalo a ALIAS_CLUB)")
            continue
        planteles[club] = plantel(club_id)
        time.sleep(0.3)
    todos = [a for p in planteles.values() for a in p]

    creditos = cargar_creditos()
    bajadas, sin_pareja, sin_foto = 0, [], []
    cambios_club: dict[str, str] = {}
    for carta in sorted(cartas, key=lambda c: -int(c["OVR"])):
        atleta = emparejar(carta, planteles.get(carta["Club"], []))
        if atleta is None:  # puede haberse cambiado de club: se exige nombre idéntico y misma edad o dorsal
            atleta = emparejar(carta, todos, minimo=1.05)
        club_actual = ""
        if atleta is None and args.buscar:  # 365Scores está al día: puede estar en otro club o liga
            encontrado = buscar_global(carta)
            if encontrado:
                atleta, club_actual = encontrado
                cambios_club[f"{carta['Nombre']}|{carta['Club']}"] = club_actual
        if atleta is None:
            sin_pareja.append(f"{carta['Nombre']} ({carta['Club']})")
            continue
        try:
            imagen = bajar_foto(atleta, not args.sin_recortar)
        except Exception as e:  # una foto rota no corta el resto
            print(f"  ✗ {carta['Nombre']}: {e}")
            continue
        if imagen is None:
            sin_foto.append(carta["Nombre"])
            continue
        guardar(archivo_render(carta["Nombre"], carta["Club"]), atleta, imagen, creditos, not args.sin_recortar)
        bajadas += 1
        donde = f"{carta['Club']} -> ahora en {club_actual}" if club_actual else carta["Club"]
        print(f"  ✓ {carta['Nombre']} <- {atleta['name']} ({donde})", flush=True)
        if bajadas % 20 == 0:
            escribir_creditos(creditos)
        time.sleep(0.2)

    escribir_creditos(creditos)
    print(f"OK: {bajadas} fotos nuevas en {RENDERS}/")
    if cambios_club:  # quiénes cambiaron de club según 365Scores (Wikipedia va atrasada)
        ruta = Path(f"data/cambios_club_365_{args.liga}_{args.anio}.json")
        previos = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
        ruta.write_text(json.dumps({**previos, **cambios_club}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(cambios_club)} jugadores en otro club según 365Scores -> {ruta}")
    if sin_foto:
        print(f"{len(sin_foto)} sin foto en 365Scores: {', '.join(sin_foto)}")
    if sin_pareja:
        print(f"{len(sin_pareja)} sin pareja en 365Scores:")
        for n in sin_pareja:
            print("  ·", n)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Fotos de jugadores desde 365Scores (solo uso local).")
    p.add_argument("--url", help="Enlace a la ficha del jugador en 365scores.com")
    p.add_argument("--id", type=int, help="Id del jugador en 365Scores")
    p.add_argument("--nombre", help="Nombre del archivo (como en el CSV de cartas); por defecto el de 365Scores")
    p.add_argument("--equipo", help="Enlace a la página de un club (bajar todo su plantel)")
    p.add_argument("--liga", help="Bajar las fotos de todas las cartas de una liga")
    p.add_argument("--anio", type=int, default=2026)
    p.add_argument("--club", help="Solo un club (nombre como en el CSV de cartas)")
    p.add_argument("--sin-recortar", action="store_true", help="Dejar el fondo blanco original")
    p.add_argument("--escudos", action="store_true", help="Con --liga: bajar los escudos de los clubes")
    p.add_argument("--nombres", action="store_true", help="Con --liga: apellidos para los jugadores de un solo nombre")
    p.add_argument("--buscar", action="store_true", help="Con --liga: buscar en todo 365Scores a quien no esté en su club")
    p.add_argument("--depurar", action="store_true", help="Con --liga: excluir juveniles/ex jugadores según 365Scores")
    p.add_argument("--forzar", action="store_true", help="Reemplazar fotos que ya existen")
    args = p.parse_args()
    if args.url or args.id:
        un_jugador(args)
    elif args.equipo:
        un_equipo(args)
    elif args.liga and args.depurar:
        depurar(args)
    elif args.liga and args.nombres:
        nombres(args)
    elif args.liga and args.escudos:
        escudos(args)
    elif args.liga:
        una_liga(args)
    else:
        p.error("indica --url/--id, --equipo o --liga")


if __name__ == "__main__":
    main()
