import nextcord
from nextcord.ui import Button, View

class Paginacion(View):
    def __init__(self, cartas, user_id):
        super().__init__()
        self.cartas = cartas
        self.user_id = user_id
        self.current_page = 0  #

    async def mostrar_cartas(self, interaction):
        start = self.current_page * 5
        end = start + 5
        cartas_pag = self.cartas[start:end]

        mensaje = "Estas son tus cartas:\n"
        view = View()

        for carta in cartas_pag:
            nombre_carta = carta.get('nombre', 'Carta desconocida')
            button = Button(label=f"{nombre_carta}", style=nextcord.ButtonStyle.gray, emoji="📜")
            
            async def button_callback(interaction: nextcord.Interaction, carta=carta):
                await interaction.response.send_message(f"📜 Información de la carta:\n\n{carta.mostrar_info()}")

            button.callback = button_callback
            view.add_item(button)

        if self.current_page > 0:
            volver_button = Button(label="Volver", style=nextcord.ButtonStyle.red, emoji="⬅️")
            
            async def volver_callback(interaction: nextcord.Interaction):
                self.current_page -= 1
                await self.mostrar_cartas(interaction)  

            volver_button.callback = volver_callback
            view.add_item(volver_button)

        if end < len(self.cartas):
            siguiente_button = Button(label="Siguiente", style=nextcord.ButtonStyle.green, emoji="➡️")
            
            async def siguiente_callback(interaction: nextcord.Interaction):
                self.current_page += 1
                await self.mostrar_cartas(interaction)  

            siguiente_button.callback = siguiente_callback
            view.add_item(siguiente_button)

        await interaction.response.send_message(mensaje, view=view)
