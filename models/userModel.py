from ..database.conexion import users_collection
class User:
    def __init__(self, user_id, nombre, avatar_url,saldo,cartas,plantillas,copas):
        self.user_id = user_id
        self.nombre = nombre
        self.avatar_url = avatar_url
        self.saldo = saldo
        self.cartas = cartas
        self.plantillas = plantillas
        self.copas = copas
   
    def mostrar_info(self):
        return (
            f"**{self.nombre}**\n"
            f"Avatar: {self.avatar_url}\n"
            f"Saldo: {self.saldo}$\n"
            f"Cartas: {self.cartas}/100\n"
            f"Plantillas: {self.plantillas}/5\n"
            f"Copas: {self.copas}"
        )
        
    def guardar_en_db(self):
        existing_user = users_collection.find_one({"user_id": self.user_id})
        if existing_user:
            print(f"Usuario {self.nombre} ya existe en la base de datos.")
        else:
           
            user_data = {
                "user_id": self.user_id,
                "nombre": self.nombre,
                "avatar_url": self.avatar_url,
                "saldo": self.saldo,
                "cartas": self.cartas,
                "plantillas": self.plantillas,
                "copas": self.copas,
            }
            # Insertar el documento en la colección "users"
            users_collection.insert_one(user_data)
            print(f"Usuario {self.nombre} guardado en la base de datos.")