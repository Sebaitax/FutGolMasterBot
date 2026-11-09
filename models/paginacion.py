"""Vista paginada del inventario de cartas."""
import nextcord
from nextcord.ui import Button, View

POR_PAGINA = 10


class Paginacion(View):
    def __init__(self, cartas: list, user_id: int):
        super().__init__(timeout=60)  # Los botones quedan activos 60 segundos
        self.cartas = cartas
        self.user_id = user_id
        self.pagina = 0

    @property
    def total_paginas(self) -> int:
        return max(1, (len(self.cartas) - 1) // POR_PAGINA + 1)

    def crear_embed(self) -> nextcord.Embed:
        inicio = self.pagina * POR_PAGINA
        embed = nextcord.Embed(
            title="Tu inventario de cartas",
            description=f"Tienes {len(self.cartas)} cartas en tu perfil.",
            color=nextcord.Color.green(),
        )
        for i, carta in enumerate(self.cartas[inicio : inicio + POR_PAGINA], start=inicio + 1):
            ovr = carta.get("estadisticas", {}).get("OVR", "?")
            nivel = carta.get("nivel", "").capitalize()
            rara = " ✨" if carta.get("rara") else ""
            embed.add_field(
                name=f"{i}. {carta.get('nombre', 'Carta')} ({ovr}){rara}",
                value=f"{carta.get('posicion', '?')} | {nivel} | Precio: {carta.get('precio', '?')}",
                inline=False,
            )
        embed.set_footer(text=f"Página {self.pagina + 1} de {self.total_paginas}")
        return embed

    async def interaction_check(self, interaction: nextcord.Interaction) -> bool:
        # Solo el dueño del inventario puede cambiar de página
        return interaction.user.id == self.user_id

    @nextcord.ui.button(label="Anterior", style=nextcord.ButtonStyle.red)
    async def anterior(self, button: Button, interaction: nextcord.Interaction):
        if self.pagina > 0:
            self.pagina -= 1
        await interaction.response.edit_message(embed=self.crear_embed(), view=self)

    @nextcord.ui.button(label="Siguiente", style=nextcord.ButtonStyle.green)
    async def siguiente(self, button: Button, interaction: nextcord.Interaction):
        if self.pagina < self.total_paginas - 1:
            self.pagina += 1
        await interaction.response.edit_message(embed=self.crear_embed(), view=self)
