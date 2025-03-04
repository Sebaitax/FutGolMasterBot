class Carta:
    def __init__(self,nombre,posicion,nacion,club,liga,OVR,PAC,DRI,DEF,PHY,precio):
        self.nombre = nombre
        self.posicion = posicion
        self.nacion = nacion
        self.club = club
        self.liga = liga
        self.estadisticas = {
            'OVR': OVR,
            'PAC': PAC,
            'DRI': DRI,
            'DEF': DEF,
            'PHY': PHY,
        }        
        self.precio = precio
        
   
    def to_dict(self):
        return {
            'nombre': self.nombre,
            'posicion': self.posicion,
            'nacion': self.nacion,
            'club': self.club,
            'liga': self.liga,
            'estadisticas': self.estadisticas,
            'precio': self.precio
        }