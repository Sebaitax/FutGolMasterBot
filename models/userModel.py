from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import os
import requests
class User:
    def __init__(self, user_id, nombre, avatar_url,saldo,cartas,plantillas,copas,last_claim):
        self.user_id = user_id
        self.nombre = nombre
        self.avatar_url = avatar_url
        self.saldo = saldo
        self.cartas = cartas
        self.plantillas = plantillas
        self.copas = copas
        self.last_claim = last_claim
   
    def mostrar_info(self,collection):
        
        
        existing_user = collection.find_one({"user_id":self.user_id})
        
        FONDO_ESTADIO_PATH = "estadio.png"  
        if not os.path.exists(FONDO_ESTADIO_PATH):
            print("❌ No se encontró la imagen de fondo `estadio.png`.")
            return     
        
                
        try:
            fondo = Image.open(FONDO_ESTADIO_PATH).convert("RGBA")
        except Exception as e:
            print(f"❌ Error al abrir la imagen de fondo: {e}")
            return
        
        
        width, height = 700, 400
        img = Image.new("RGBA", (width, height), "white")
        draw = ImageDraw.Draw(img)
        
        
        fondo = fondo.resize((width, 150))
        img.paste(fondo, (0, 0))
        
        response = requests.get(self.avatar_url)
         
        try:
            avatar = Image.open(BytesIO(response.content)).convert("RGBA")
            avatar = avatar.resize((100, 100))
            img.paste(avatar, (width - 125, 25), avatar)
        except Exception as e:
            print(f"❌ Error al cargar el avatar: {e}")
            return
        
        try:
            font_title = ImageFont.truetype("arial.ttf", 28)
            font_text = ImageFont.truetype("arial.ttf", 22)
        except IOError:
            print("❌ No se encontró la fuente 'arial.ttf'.")
            return
            
  
        # Guardar la imagen generada en memoria
       
        
        if existing_user:
            self.update(collection)
            draw.text((30, 160), f"Nombre: {self.nombre}", fill="black", font=font_title)

            # Dibujar la caja de información abajo
            info_x, info_y = 30, 200
            draw.text((info_x, info_y), f"Saldo: {self.saldo}$", fill="black", font=font_text)
            draw.text((info_x, info_y + 30), f"Jugadores: {self.cartas}/100", fill="black", font=font_text)
            draw.text((info_x, info_y + 60), f"Estadio: Monumental Colo Colo", fill="black", font=font_text)
            draw.text((info_x, info_y + 90), f"Plantillas: {self.plantillas}/5", fill="black", font=font_text)
            draw.text((info_x, info_y + 120), f"Copas: {self.copas}", fill="black", font=font_text)

            image_stream = BytesIO()
            img.save(image_stream, format="PNG")
            image_stream.seek(0)
        else:
            self.save(collection)
            draw.text((30, 160), f"¡Bienvenido por primera vez {self.nombre}!", fill="black", font=font_title)

            # Dibujar la caja de información abajo
            info_x, info_y = 30, 200
            draw.text((info_x, info_y), f"Saldo: {self.saldo}$", fill="black", font=font_text)
            draw.text((info_x, info_y + 30), f"Jugadores: {self.cartas}/100", fill="black", font=font_text)
            draw.text((info_x, info_y + 60), f"Estadio: Monumental Colo Colo", fill="black", font=font_text)
            draw.text((info_x, info_y + 90), f"Plantillas: {self.plantillas}/5", fill="black", font=font_text)
            draw.text((info_x, info_y + 120), f"Copas: {self.copas}", fill="black", font=font_text)
            image_stream = BytesIO()
            img.save(image_stream, format="PNG")
            image_stream.seek(0)
            
        return (image_stream)
        
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
            "copas": self.copas,
            "last_claim": self.last_claim
        }
        
        
        
        