"""Modelo de carta de jugador."""
from dataclasses import dataclass, field

# Claves internas de estadísticas (las mismas columnas del CSV y de la BDD)
STATS = ("PAC", "SHO", "PAS", "DRI", "DEF", "PHY")

# Etiquetas propias que se muestran en las cartas
ETIQUETAS = {
    "PAC": "VEL",  # velocidad
    "SHO": "TIR",  # tiro
    "PAS": "PAS",  # pase
    "DRI": "REG",  # regate
    "DEF": "DEF",  # defensa
    "PHY": "FIS",  # físico
}


def nivel_por_ovr(ovr: int) -> str:
    """Devuelve el nivel de la carta según su valoración general."""
    if ovr >= 75:
        return "oro"
    if ovr >= 65:
        return "plata"
    return "bronce"


def _a_entero(valor, defecto=0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return defecto


@dataclass
class Carta:
    nombre: str
    posicion: str
    ovr: int
    stats: dict = field(default_factory=dict)
    alias: str = ""
    nacion: str = ""
    club: str = ""
    liga: str = ""
    precio: int = 0
    rara: bool = False

    @property
    def nivel(self) -> str:
        return nivel_por_ovr(self.ovr)

    @property
    def nombre_corto(self) -> str:
        """Nombre que se imprime en la carta (alias si existe)."""
        return (self.alias or self.nombre).strip()

    # ---------- Conversión ----------

    @classmethod
    def desde_csv(cls, fila: dict, rara: bool = False) -> "Carta":
        """Crea una carta desde una fila de los CSV de data/."""
        return cls(
            nombre=str(fila["Nombre"]).strip(),
            alias=str(fila.get("Alias") or "").strip(),
            posicion=str(fila.get("Posición", "")).replace("+", "").strip(),
            ovr=_a_entero(fila.get("OVR")),
            stats={s: _a_entero(fila.get(s)) for s in STATS},
            nacion=str(fila.get("Nación") or "").strip(),
            club=str(fila.get("Club") or "").strip(),
            liga=str(fila.get("Liga") or "").strip(),
            precio=_a_entero(fila.get("Precio")),
            rara=rara,
        )

    @classmethod
    def desde_dict(cls, doc: dict) -> "Carta":
        """Crea una carta desde un documento de MongoDB."""
        est = doc.get("estadisticas", {})
        return cls(
            nombre=doc.get("nombre", "Desconocido"),
            alias=doc.get("alias", ""),
            posicion=doc.get("posicion", ""),
            ovr=_a_entero(est.get("OVR")),
            stats={s: _a_entero(est.get(s)) for s in STATS},
            nacion=doc.get("nacion", ""),
            club=doc.get("club", ""),
            liga=doc.get("liga", ""),
            precio=_a_entero(doc.get("precio")),
            rara=bool(doc.get("rara", False)),
        )

    def to_dict(self) -> dict:
        return {
            "nombre": self.nombre,
            "alias": self.alias,
            "posicion": self.posicion,
            "nacion": self.nacion,
            "club": self.club,
            "liga": self.liga,
            "estadisticas": {"OVR": self.ovr, **self.stats},
            "nivel": self.nivel,
            "rara": self.rara,
            "precio": self.precio,
        }
