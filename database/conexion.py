import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pymongo import MongoClient

from dotenv import load_dotenv


load_dotenv()

client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv('DATABASE_NAME')]

# Ejemplo: colección de usuarios
users_collection = db["users"]

# Verificar la conexión
def probar_conexion():
    try:
        colecciones = db.list_collection_names()
        print("Conexión exitosa a MongoDB. Colecciones disponibles:", colecciones)
    except Exception as e:
        print("Error al conectar a MongoDB:", e)

if __name__ == "__main__":
    probar_conexion()
