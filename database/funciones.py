from database.conexion import users_collection

# Crear un usuario
def crear_usuario(discord_id, nombre, saldo=1000, eslogan=""):
    usuario = {
        "discord_id": discord_id,
        "nombre": nombre,
        "saldo": saldo,
        "victorias": {"amistosos": 0, "liga": 0},
        "derrotas": {"amistosos": 0, "liga": 0},
        "imagenes": {"fondo": "", "perfil_discord": ""},
        "plantillas": [],
        "nivel_jugador": 1,
        "experiencia": 0,
        "eslogan": eslogan
    }
    resultado = users_collection.insert_one(usuario)
    return resultado.inserted_id

# Obtener un usuario
def obtener_usuario(discord_id):
    usuario = users_collection.find_one({"discord_id": discord_id})
    return usuario if usuario else "Usuario no encontrado."

# Actualizar saldo del usuario
def actualizar_saldo(discord_id, cantidad):
    resultado = users_collection.update_one(
        {"discord_id": discord_id},
        {"$inc": {"saldo": cantidad}}
    )
    return resultado.modified_count > 0

# Añadir una plantilla
def agregar_plantilla(discord_id, nombre_plantilla, cartas, estadio):
    nueva_plantilla = {
        "nombre": nombre_plantilla,
        "cartas": cartas,
        "estadio": estadio
    }
    resultado = users_collection.update_one(
        {"discord_id": discord_id},
        {"$push": {"plantillas": nueva_plantilla}}
    )
    return resultado.modified_count > 0

# Obtener las plantillas de un usuario
def obtener_plantillas(discord_id):
    usuario = users_collection.find_one({"discord_id": discord_id})
    return usuario.get("plantillas", []) if usuario else "Usuario no encontrado."

# Actualizar estadísticas después de un partido
def actualizar_estadisticas(discord_id, tipo_partido, resultado):
    campo = f"{'victorias' if resultado == 'victoria' else 'derrotas'}.{tipo_partido}"
    resultado = users_collection.update_one(
        {"discord_id": discord_id},
        {"$inc": {campo: 1}}
    )
    return resultado.modified_count > 0

# Eliminar un usuario
def eliminar_usuario(discord_id):
    resultado = users_collection.delete_one({"discord_id": discord_id})
    return resultado.deleted_count > 0


# --- Funciones para cartas ---

# Agregar una carta a la colección general
def agregar_carta(cards_collection, nombre, tipo, stats, precio_venta_rapida, equipo, liga, pais, imagen):
    carta = {
        "nombre": nombre,
        "tipo": tipo,
        "stats": stats,
        "precio_venta_rapida": precio_venta_rapida,
        "liga": liga,
        "equipo": equipo,
        "pais": pais,
        "imagen": imagen
    }
    resultado = cards_collection.insert_one(carta)
    return resultado.inserted_id

# Obtener una carta por nombre de la colección general
def obtener_carta(cards_collection, nombre):
    carta = cards_collection.find_one({"nombre": nombre})
    return carta if carta else "Carta no encontrada."

# Consultar cartas por tipo (bronze, plata, oro)
def consultar_cartas_por_tipo(cards_collection, tipo):
    cartas = cards_collection.find({"tipo": tipo})
    return list(cartas)

# Actualizar el precio de venta rápida
def actualizar_precio_venta(cards_collection, nombre, nuevo_precio):
    resultado = cards_collection.update_one(
        {"nombre": nombre},
        {"$set": {"precio_venta_rapida": nuevo_precio}}
    )
    return resultado.modified_count > 0


# --- Funciones para inventario ---

# Agregar una carta al inventario del usuario
def agregar_carta_inventario(inventory_collection, user_id, card_id):
    carta_en_inventario = {
        "card_id": card_id,
        "nivel_mejora": 1,
        "estado": "disponible",
        "duracion_lesion": 0,
        "tarjetas": {
            "amistosos": {"amarillas": 0, "rojas": 0},
            "liga": {"amarillas": 0, "rojas": 0}
        },
        "en_plantillas": []
    }
    resultado = inventory_collection.update_one(
        {"user_id": user_id},
        {"$push": {"cartas": carta_en_inventario}},
        upsert=True
    )
    return resultado.modified_count > 0

# Actualizar estado de una carta en el inventario
def actualizar_estado_carta(inventory_collection, user_id, card_id, nuevo_estado, tipo_partido, duracion_lesion=0):
    campo_estado = f"cartas.$.tarjetas.{tipo_partido}.estado"
    campo_lesion = "cartas.$.duracion_lesion"
    resultado = inventory_collection.update_one(
        {"user_id": user_id, "cartas.card_id": card_id},
        {"$set": {campo_estado: nuevo_estado, campo_lesion: duracion_lesion}}
    )
    return resultado.modified_count > 0

# Mejorar el nivel de una carta en el inventario
def mejorar_carta_inventario(inventory_collection, user_id, card_id, incremento=1, max_nivel=10):
    carta = inventory_collection.find_one(
        {"user_id": user_id, "cartas.card_id": card_id},
        {"cartas.$": 1}
    )
    if not carta or not carta.get("cartas"):
        return "Carta no encontrada en el inventario."

    nivel_actual = carta["cartas"][0]["nivel_mejora"]
    if nivel_actual + incremento > max_nivel:
        return "No se puede mejorar más allá del nivel máximo."

    resultado = inventory_collection.update_one(
        {"user_id": user_id, "cartas.card_id": card_id},
        {"$inc": {"cartas.$.nivel_mejora": incremento}}
    )
    return resultado.modified_count > 0
