class Carta:
    def __init__(self,nombre,tipo,velocidad,disparo,pase,dribbling,defensa,fisico,equipo,nacionalidad,):
        self.nombre = nombre
        self.tipo = tipo
        self.estadisticas = {
            'velocidad':velocidad,
            'disparo': disparo,
            'pase': pase,
            'dribbling': dribbling,
            'defensa': defensa,
            'fisico': fisico
        }        
        self.equipo = equipo
        self.nacionalidad = nacionalidad
        self.precio = self.calcular_precio()
        
    def calcular_precio(self):
        return (self.estadisticas['velocidad'] + self.estadisticas['disparo'] + self.estadisticas['pase']) * 100