"""Cuentas de jugadores: correo + contraseña o Google. Base de datos SQLite en data/cuentas.sqlite.

- Cada cuenta tiene su partida (data/partidas/<pid>.sqlite): entras desde cualquier dispositivo.
- Contraseñas con scrypt (salt propio por cuenta). Sesiones con un token aleatorio en una cookie
  httponly; en la base se guarda solo su hash (si alguien lee la base, no puede usar las sesiones).
- Google: flujo "authorization code" de OpenID Connect, sin librerías extra. Se activa con las
  variables de entorno FGM_GOOGLE_ID, FGM_GOOGLE_SECRET y FGM_URL_BASE.
- Administradores: correos en FGM_ADMINS (separados por coma).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

RUTA = Path("data/cuentas.sqlite")
COOKIE = "fgm_sesion"
DIAS_SESION = 90
MIN_CLAVE = 6

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    nombre TEXT DEFAULT '',
    clave TEXT,                 -- scrypt: "sal$hash" en hex (NULL si solo entra con Google)
    google_sub TEXT UNIQUE,     -- id de la cuenta de Google
    pid TEXT UNIQUE NOT NULL,   -- su partida: data/partidas/<pid>.sqlite
    creado REAL NOT NULL,
    ultimo_ingreso REAL
);
CREATE TABLE IF NOT EXISTS sesiones (
    token_hash TEXT PRIMARY KEY,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    creada REAL NOT NULL,
    expira REAL NOT NULL,
    dispositivo TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS sesiones_usuario ON sesiones (usuario_id);
"""


class ErrorCuenta(Exception):
    pass


def conectar() -> sqlite3.Connection:
    RUTA.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(RUTA, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def login_obligatorio() -> bool:
    return os.environ.get("FGM_LOGIN", "") == "1"


def admins() -> set[str]:
    return {e.strip().lower() for e in os.environ.get("FGM_ADMINS", "").split(",") if e.strip()}


# ------------------------------------------------------------------ contraseñas

def _hash(clave: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    h = hashlib.scrypt(clave.encode(), salt=sal, n=2 ** 14, r=8, p=1, dklen=32)
    return f"{sal.hex()}${h.hex()}"


def _verificar(clave: str, guardado: str | None) -> bool:
    if not guardado or "$" not in guardado:
        return False
    sal, _ = guardado.split("$", 1)
    return hmac.compare_digest(_hash(clave, bytes.fromhex(sal)), guardado)


def _email_valido(email: str) -> str:
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) or len(email) > 120:
        raise ErrorCuenta("Ese correo no es válido.")
    return email


# ------------------------------------------------------------------ cuentas

def _publico(fila: sqlite3.Row | None) -> dict | None:
    if not fila:
        return None
    u = dict(fila)
    u.pop("clave", None)
    u["admin"] = u["email"] in admins()
    return u


def registrar(email: str, clave: str, nombre: str = "") -> dict:
    email = _email_valido(email)
    if len(clave or "") < MIN_CLAVE:
        raise ErrorCuenta(f"La contraseña debe tener al menos {MIN_CLAVE} caracteres.")
    con = conectar()
    try:
        fila = con.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        if fila and fila["clave"]:
            raise ErrorCuenta("Ya existe una cuenta con ese correo. Entra con tu contraseña.")
        if fila:   # existía solo con Google: se le agrega contraseña
            con.execute("UPDATE usuarios SET clave = ? WHERE id = ?", (_hash(clave), fila["id"]))
            uid = fila["id"]
        else:
            uid = con.execute("INSERT INTO usuarios (email, nombre, clave, pid, creado) VALUES (?, ?, ?, ?, ?)",
                              (email, (nombre or "").strip()[:40], _hash(clave), uuid.uuid4().hex, time.time())).lastrowid
        con.commit()
        return _publico(con.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone())
    finally:
        con.close()


def entrar(email: str, clave: str) -> dict:
    email = (email or "").strip().lower()
    con = conectar()
    try:
        fila = con.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        if fila and not fila["clave"] and fila["google_sub"]:
            raise ErrorCuenta("Esa cuenta entra con Google. Usa el botón «Entrar con Google».")
        if not fila or not _verificar(clave or "", fila["clave"]):
            raise ErrorCuenta("Correo o contraseña incorrectos.")
        return _publico(fila)
    finally:
        con.close()


def entrar_google(sub: str, email: str, nombre: str) -> dict:
    """Busca la cuenta por su id de Google (o por correo, y la vincula); si no existe, la crea."""
    email = _email_valido(email)
    con = conectar()
    try:
        fila = con.execute("SELECT * FROM usuarios WHERE google_sub = ?", (sub,)).fetchone() \
            or con.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
        if fila:
            con.execute("UPDATE usuarios SET google_sub = ?, nombre = COALESCE(NULLIF(nombre, ''), ?) WHERE id = ?",
                        (sub, nombre[:40], fila["id"]))
            uid = fila["id"]
        else:
            uid = con.execute("INSERT INTO usuarios (email, nombre, google_sub, pid, creado) VALUES (?, ?, ?, ?, ?)",
                              (email, nombre[:40], sub, uuid.uuid4().hex, time.time())).lastrowid
        con.commit()
        return _publico(con.execute("SELECT * FROM usuarios WHERE id = ?", (uid,)).fetchone())
    finally:
        con.close()


# ------------------------------------------------------------------ sesiones

def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def crear_sesion(usuario_id: int, dispositivo: str = "") -> str:
    token = secrets.token_urlsafe(32)
    ahora = time.time()
    con = conectar()
    try:
        con.execute("INSERT INTO sesiones VALUES (?, ?, ?, ?, ?)",
                    (_h(token), usuario_id, ahora, ahora + DIAS_SESION * 86400, dispositivo[:60]))
        con.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE id = ?", (ahora, usuario_id))
        con.execute("DELETE FROM sesiones WHERE expira < ?", (ahora,))
        con.commit()
    finally:
        con.close()
    return token


def usuario_de(token: str | None) -> dict | None:
    if not token:
        return None
    con = conectar()
    try:
        return _publico(con.execute(
            "SELECT u.* FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id WHERE s.token_hash = ? AND s.expira > ?",
            (_h(token), time.time())).fetchone())
    finally:
        con.close()


def cerrar_sesion(token: str | None):
    if not token:
        return
    con = conectar()
    try:
        con.execute("DELETE FROM sesiones WHERE token_hash = ?", (_h(token),))
        con.commit()
    finally:
        con.close()


def lista() -> list[dict]:
    """Para el admin: cuentas con su último ingreso."""
    con = conectar()
    try:
        return [_publico(f) for f in con.execute("SELECT * FROM usuarios ORDER BY ultimo_ingreso DESC")]
    finally:
        con.close()


# ------------------------------------------------------------------ Google (OpenID Connect)

def google_activo() -> bool:
    return bool(os.environ.get("FGM_GOOGLE_ID") and os.environ.get("FGM_GOOGLE_SECRET") and os.environ.get("FGM_URL_BASE"))


def _redirect_uri() -> str:
    return os.environ["FGM_URL_BASE"].rstrip("/") + "/auth/google/callback"


def url_google(estado: str) -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": os.environ["FGM_GOOGLE_ID"], "redirect_uri": _redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": estado, "prompt": "select_account"})


def datos_google(codigo: str) -> dict:
    """Cambia el código por los datos de la cuenta (sub, email, nombre). El id_token viene directo
    de Google por HTTPS, así que basta con leerlo (y revisar emisor, audiencia y vencimiento)."""
    cuerpo = urllib.parse.urlencode({
        "code": codigo, "client_id": os.environ["FGM_GOOGLE_ID"], "client_secret": os.environ["FGM_GOOGLE_SECRET"],
        "redirect_uri": _redirect_uri(), "grant_type": "authorization_code"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=cuerpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        token = json.load(r)["id_token"]
    carga = token.split(".")[1]
    datos = json.loads(base64.urlsafe_b64decode(carga + "=" * (-len(carga) % 4)))
    if datos.get("iss") not in ("https://accounts.google.com", "accounts.google.com") \
            or datos.get("aud") != os.environ["FGM_GOOGLE_ID"] or datos.get("exp", 0) < time.time():
        raise ErrorCuenta("No se pudo verificar la cuenta de Google.")
    if not datos.get("email_verified"):
        raise ErrorCuenta("Tu correo de Google no está verificado.")
    return {"sub": datos["sub"], "email": datos["email"], "nombre": datos.get("name", "")}
