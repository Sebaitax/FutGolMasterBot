import pandas as pd
from pymongo import MongoClient
from database.conexion import cards_collection
from models.cartaModel  import Carta

df = pd.read_csv('cartas_ejemplo.csv')

for index, row in df.iterrows():
    carta = Carta(
        nombre=row['Nombre'],
        posicion=row['Posición'],
        club=row['Club'],
        liga=row['Liga'],
        OVR=row['OVR'],
        PAC=row['PAC'],
        DRI=row['DRI'],
        DEF=row['DEF'],
        PHY=row['PHY'],
        precio=row['Precio']
    )
    
    cards_collection.insert_one(carta.to_dict())

print("Datos guardados correctamente en MongoDB.")
