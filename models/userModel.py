class User:
    def __init__(self, user_id, nombre, avatar_url,saldo,cartas,plantillas,copas):
        self.user_id = user_id
        self.nombre = nombre
        self.avatar_url = avatar_url
        self.saldo = saldo
        self.cartas = cartas
        self.plantillas = plantillas
        self.copas = copas
   
    def mostrar_info(self,collection):
        existing_user = collection.find_one({"user_id":self.user_id})
        if existing_user:
            self.update(collection)
            info = (f"**{self.nombre}**\n"
            f"Avatar: {self.avatar_url}\n"
            f"Saldo: {self.saldo}$\n"
            f"Cartas: {self.cartas}/100\n"
            f"Plantillas: {self.plantillas}/5\n"
            f"Copas: {self.copas}")
        else:
            self.save(collection)
            info=(
            f"¡Bienvenido por primera vez!\n"
            f"**{self.nombre}**\n"
            f"Avatar: {self.avatar_url}\n"
            f"Saldo: {self.saldo}$\n"
            f"Cartas: {self.cartas}/100\n"
            f"Plantillas: {self.plantillas}/5\n"
            f"Copas: {self.copas}")
        return (info)
        
    def save(self,collection):
        collection.insert_one(self.to_dict())
    
    def update(self,collection):    
        collection.update_one({"user_id": self.user_id}, {"$set": self.to_dict()})
            
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "nombre": self.nombre,
            "avatar_url": self.avatar_url,
            "saldo": self.saldo,
            "cartas": self.cartas,
            "plantillas": self.plantillas,
            "copas": self.copas
        }