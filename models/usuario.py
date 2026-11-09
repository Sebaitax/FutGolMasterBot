"""Modelo de usuario y tarjeta de perfil."""
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FUENTES = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MAX_CARTAS = 100
MAX_PLANTILLAS = 5


def _fuente(peso: str, tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FUENTES / f"BarlowCondensed-{peso}.ttf"), tam)


@dataclass
class Usuario:
    user_id: int
    nombre: str
    avatar_url: str = ""
    saldo: int = 0
    cartas: int = 0
    plantillas: int = 0
    copas: int = 0
    last_claim: datetime | None = None

    @classmethod
    def desde_dict(cls, doc: dict) -> "Usuario":
        return cls(**{k: doc[k] for k in cls.__dataclass_fields__ if k in doc})

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}

    def imagen_perfil(self, avatar: bytes | None = None, nuevo: bool = False) -> BytesIO:
        """Dibuja la tarjeta de perfil y la devuelve como PNG en memoria."""
        ancho, alto = 700, 400
        img = Image.new("RGBA", (ancho, alto), (245, 246, 248, 255))
        d = ImageDraw.Draw(img)

        # Cabecera con degradado verde "cancha"
        for y in range(150):
            t = y / 149
            d.line([(0, y), (ancho, y)], fill=(int(20 + 20 * t), int(110 - 40 * t), int(60 - 20 * t)))
        d.text((30, 30), "FUTGOLMASTER", font=_fuente("Bold", 48), fill=(255, 255, 255))

        if avatar:
            try:
                foto = Image.open(BytesIO(avatar)).convert("RGBA").resize((110, 110))
                mascara = Image.new("L", foto.size, 0)
                ImageDraw.Draw(mascara).ellipse([0, 0, 110, 110], fill=255)
                d.ellipse([ancho - 152, 18, ancho - 28, 142], fill=(255, 255, 255))
                img.paste(foto, (ancho - 145, 25), mascara)
            except OSError:
                pass  # avatar inválido: se omite

        titulo = f"¡Bienvenido por primera vez, {self.nombre}!" if nuevo else self.nombre
        d.text((30, 165), titulo, font=_fuente("Bold", 36), fill=(20, 24, 32))

        f = _fuente("Medium", 26)
        filas = [
            f"Saldo: {self.saldo}$",
            f"Jugadores: {self.cartas}/{MAX_CARTAS}",
            f"Plantillas: {self.plantillas}/{MAX_PLANTILLAS}",
            f"Copas: {self.copas}",
        ]
        for i, texto in enumerate(filas):
            d.text((30, 220 + i * 40), texto, font=f, fill=(50, 56, 68))

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
