"""Carga cartas desde un CSV de data/ a la colección `cards` de MongoDB.

Uso (desde la raíz del proyecto):
    python -m scripts.cargar_cartas data/cartas_ejemplo.csv
    python -m scripts.cargar_cartas data/cartas_oro_raras.csv --rara
"""
import argparse
import csv

from database.conexion import cards_collection
from models.carta import Carta


def main():
    parser = argparse.ArgumentParser(description="Carga cartas desde un CSV a MongoDB.")
    parser.add_argument("csv", help="Ruta del CSV")
    parser.add_argument("--rara", action="store_true", help="Marca las cartas como raras")
    args = parser.parse_args()

    with open(args.csv, newline="", encoding="utf-8") as archivo:
        cartas = [Carta.desde_csv(fila, rara=args.rara).to_dict() for fila in csv.DictReader(archivo)]

    if cartas:
        cards_collection.insert_many(cartas)
    print(f"OK: {len(cartas)} cartas guardadas en MongoDB.")


if __name__ == "__main__":
    main()
