class User:
    def __init__(self, user_id, nombre, avatar_url,saldo,cartas,plantillas,copas):
        self.user_id = user_id
        self.nombre = nombre
        self.avatar_url = avatar_url
        self.saldo = saldo
        self.cartas = cartas
        self.plantillas = plantillas
        self.copas = copas

    def __str__(self):
        return f"Usuario: {self.nombre} (ID: {self.user_id})"

    def mostrar_info(self):
        info = f"{self.nombre}"
        return info