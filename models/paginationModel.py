from nextcord.ext import commands
from nextcord.ui import View, Button
import nextcord

class Pagination(View):
    def __init__(self, cartas, user_id):
        super().__init__(timeout=60)  # Los botones estarán activos durante 60 segundos
        self.cartas = cartas
        self.user_id = user_id
        self.current_page = 0  # Página inicial

    # Método para crear el embed con las cartas de la página actual
    def create_embed(self):
        start = self.current_page * 10  # Empezar en el índice adecuado
        end = start + 10  # Obtener un máximo de 10 cartas por página
        cartas_pagina = self.cartas[start:end]

        embed = nextcord.Embed(
            title="Tu inventario de cartas:",
            description=f"Tienes {len(self.cartas)} cartas en tu perfil.",
            color=nextcord.Color.green()
        )

        for i, carta in enumerate(cartas_pagina):
            carta_nombre = carta.get('nombre', f'Carta {start + i + 1}')
            embed.add_field(name=f'{carta_nombre}', value="Posición: "+carta.get('posicion', 'Desconocida') + "| Precio: " + str(carta.get("precio", "Desconocido")), inline=False)

        # Añadir los botones de paginación
        embed.set_footer(text=f"Página {self.current_page + 1} de {((len(self.cartas) - 1) // 10) + 1}")
        return embed

    # Botón para ir a la página anterior (colocado primero)
    @nextcord.ui.button(label="Anterior", style=nextcord.ButtonStyle.red)
    async def anterior(self, button: Button, interaction: nextcord.Interaction):
        if self.current_page > 0:  # Solo permite ir a la página anterior si no estamos en la primera página
            self.current_page -= 1
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    # Botón para ir a la página siguiente (colocado segundo)
    @nextcord.ui.button(label="Siguiente", style=nextcord.ButtonStyle.green)
    async def siguiente(self, button: Button, interaction: nextcord.Interaction):
        if self.current_page < (len(self.cartas) // 10):  # Solo permite ir a la siguiente página si hay más
            self.current_page += 1
            embed = self.create_embed()
            await interaction.response.edit_message(embed=embed, view=self)
