import sys
import os
# Agregar el directorio raíz al sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Importar config correctamente
from config import MONGO_URI, DATABASE_NAME
from pymongo import MongoClient
# Conexión a MongoDB
client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

# Ejemplo: colección de usuarios
users_collection = db["users"]

# Verificar la conexión
def probar_conexion():
    try:
        # Obtener una lista de colecciones como prueba
        colecciones = db.list_collection_names()
        print("Conexión exitosa a MongoDB. Colecciones disponibles:", colecciones)
    except Exception as e:
        print("Error al conectar a MongoDB:", e)

# Prueba de conexión
if __name__ == "__main__":
    probar_conexion()
