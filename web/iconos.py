"""Íconos de línea (sprite /static/iconos.svg, Lucide + propios) en vez de emojis.

- `ico("trophy")` arma el <svg> para las plantillas (y FGM_ICO(...) en el navegador).
- `con_iconos(texto)` cambia los emojis que todavía traen los textos del motor (relato, resumen,
  opciones de las jugadas) por su ícono; los que son solo decoración se borran.
- `bandera(emoji)` cambia una bandera emoji (que Windows no dibuja: sale "CL") por una imagen.
"""
from __future__ import annotations

import html
import json
import re

from markupsafe import Markup

VERSION_SPRITE = "2"
SPRITE = f"/static/iconos.svg?v={VERSION_SPRITE}"

# emoji -> nombre del ícono ("" = se borra: era pura decoración)
EMOJI = {
    "🏆": "trophy", "⚽": "pelota", "🥅": "goal", "🧤": "hand", "🎯": "target", "🤝": "handshake",
    "🪄": "wand-sparkles", "🦵": "footprints", "🦶": "footprints", "🧱": "brick-wall", "🫂": "users",
    "🧍": "user-round", "🧠": "brain", "🚩": "flag", "🟥": "tarjeta-roja", "🟨": "tarjeta-amarilla",
    "🚑": "ambulance", "🔄": "refresh-cw", "🔁": "repeat-2", "⏳": "hourglass", "⏱": "timer", "⏸": "pause",
    "⏭": "skip-forward", "🔒": "lock", "🔑": "key-round", "🔎": "search", "👀": "eye", "⚠": "triangle-alert",
    "❗": "circle-alert", "🚨": "siren", "❌": "circle-x", "✅": "circle-check", "✔": "check", "✓": "check",
    "✕": "x", "⬆": "arrow-up", "⬇": "arrow-down", "♻": "recycle", "📋": "clipboard-list", "📜": "scroll-text",
    "📊": "chart-column", "📍": "map-pin", "🔋": "battery-low", "💨": "wind", "🎙": "mic", "🔔": "bell",
    "🏟": "estadio", "🛡": "shield", "🌎": "globe", "⚔": "swords", "🆚": "", "📦": "package", "🎁": "gift",
    "💎": "gem", "⭐": "star", "🌈": "sparkles", "✨": "sparkles", "🔥": "flame", "⚡": "zap", "⚖": "scale",
    "🧩": "puzzle", "😩": "", "💪": "", "😖": "", "🎉": "", "👌": "", "🤔": "", "😵": "", "🙋": "",
    "🟢": "punto-verde", "🔴": "punto-rojo", "🟡": "punto-amarillo", "💰": "coins", "🪙": "moneda",
    "🎟": "ticket", "🧾": "receipt", "🎲": "dices", "📧": "mail", "📅": "calendar", "🚪": "log-out",
    "🏠": "house", "🛣": "", "🗒": "clipboard-list", "👥": "users", "🎵": "music", "🔇": "volume-x",
    "🔈": "volume-1", "🔊": "volume-2", "❓": "circle-help", "➡": "arrow-right", "⬅": "arrow-left",
    "↖": "move-up-left", "↗": "move-up-right", "↩": "undo-2",
}
_PATRON = re.compile("(" + "|".join(sorted(map(re.escape, EMOJI), key=len, reverse=True)) + ")️?\\s?")


def ico_html(nombre: str, clase: str = "") -> str:
    if not nombre:
        return ""
    if nombre == "moneda":
        return f'<i class="moneda {clase}" aria-hidden="true"></i>'
    if nombre == "copa":
        return f'<img class="copa-img {clase}" src="/static/logo/copa.webp" alt="copas">'
    if nombre.startswith("punto-"):
        return f'<i class="punto {nombre[6:]} {clase}" aria-hidden="true"></i>'
    if nombre.startswith("tarjeta-"):
        return f'<i class="tarjeta-ico {nombre[8:]} {clase}" aria-hidden="true"></i>'
    return f'<svg class="ico {clase}" aria-hidden="true"><use href="{SPRITE}#i-{nombre}"/></svg>'


def ico(nombre: str, clase: str = "") -> Markup:
    return Markup(ico_html(nombre, clase))


def con_iconos(texto) -> Markup:
    """Escapa el texto y cambia los emojis conocidos por íconos (los decorativos se borran)."""
    def cambio(m):
        nombre = EMOJI[m.group(1)]
        return ico_html(nombre) + (" " if nombre and m.group(0).endswith(" ") else "")
    return Markup(_PATRON.sub(cambio, html.escape(str(texto or ""), quote=False)))


def bandera(emoji: str, clase: str = "") -> Markup:
    """Bandera emoji (🇨🇱, o la de Inglaterra) -> <img> de flagcdn, igual que en las cartas."""
    if not emoji:
        return Markup("")
    if emoji.startswith("🏴"):
        iso = "gb-eng"
    else:
        letras = [chr(ord(c) - 0x1F1E6 + 97) for c in emoji if 0x1F1E6 <= ord(c) <= 0x1F1FF]
        iso = "".join(letras)
    if not iso:
        return Markup(html.escape(emoji))
    return Markup(f'<img class="bandera {clase}" src="https://flagcdn.com/w40/{iso}.png" alt="" loading="lazy" onerror="this.remove()">')


def bandera_url(emoji: str) -> str:
    m = re.search(r'src="([^"]+)"', str(bandera(emoji)))
    return m.group(1) if m else ""


EMOJI_JSON = json.dumps({k: v for k, v in EMOJI.items()}, ensure_ascii=False)


# ------------------------------------------------------------------ insignias de cancha y sobres
from pathlib import Path as _Path  # noqa: E402

_ESTATICOS = _Path(__file__).parent / "static"


def _metal(indice: int) -> str:
    return "bronce" if indice < 3 else "plata" if indice < 7 else "oro"


def insignia(c: dict | None, clase: str = "") -> Markup:
    """Insignia de una cancha: la ilustración (/static/canchas/<tema>.webp) si existe; si no, un
    escudito con el número de la cancha (bronce las 3 primeras, plata hasta la Séptima, oro arriba)."""
    if not c:
        return Markup("")
    tema, i = c.get("tema", ""), int(c.get("indice", 0))
    img = _ESTATICOS / "canchas" / f"{tema}.webp"
    if tema and img.exists():
        return Markup(f'<img class="insignia-img {clase}" src="/static/canchas/{tema}.webp" alt="" title="{html.escape(c.get("nombre", ""))}">')
    return Markup(f'<span class="insignia {_metal(i)} {clase}" title="{html.escape(c.get("nombre", ""))}"><b>{i + 1}</b></span>')
