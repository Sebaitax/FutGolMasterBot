class User:
    def __init__(self, user_id, nombre,global_name, avatar_url, fecha_union=None):
        self.user_id = user_id
        self.nombre = nombre
        self.global_name = global_name
        self.avatar_url = avatar_url
        self.fecha_union = fecha_union  # Opcional: la fecha en la que se unió al servidor

    def __str__(self):
        return f"Usuario: {self.nombre} Global:{self.global_name} (ID: {self.user_id})"

    def mostrar_info(self):
        info = f"ID: {self.user_id}\n"
        info += f"Nombre: {self.nombre}\n"
        info += f"Nombre Global: {self.global_name}\n"
        info += f"Avatar: {self.avatar_url}\n"
        if self.fecha_union:
            info += f"Fecha de unión: {self.fecha_union}\n"
        return info
