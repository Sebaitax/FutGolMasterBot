"""Comandos de cartas: /claim y /cartas."""
import os
from datetime import datetime, timedelta

import nextcord
from nextcord.ext import commands

from cartas.generador import carta_a_bytes
from database.conexion import cards_collection, users_collection
from models.carta import Carta
from models.paginacion import Paginacion

# Tiempo de espera entre claims (configurable en .env)
COOLDOWN_CLAIM = timedelta(seconds=int(os.getenv("CLAIM_COOLDOWN_SEGUNDOS", "10")))


def _formatear_espera(restante: timedelta) -> str:
    horas, resto = divmod(int(restante.total_seconds()), 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas} hora(s), {minutos} minuto(s) y {segundos} segundo(s)"


class Cartas(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @nextcord.slash_command(name="cartas", description="Muestra tus cartas obtenidas")
    async def cartas(self, interaction: nextcord.Interaction):
        usuario = users_collection.find_one({"user_id": interaction.user.id})
        if not usuario:
            await interaction.response.send_message(
                "No puedes usar este comando sin un perfil, utiliza `/p` para crear tu perfil."
            )
            return

        cartas = usuario.get("jugadores", [])
        if not cartas:
            await interaction.response.send_message("No tienes cartas en tu inventario.")
            return

        vista = Paginacion(cartas, interaction.user.id)
        await interaction.response.send_message(embed=vista.crear_embed(), view=vista)

    @nextcord.slash_command(name="claim", description="Reclamar una carta")
    async def claim(self, interaction: nextcord.Interaction):
        user_id = interaction.user.id
        usuario = users_collection.find_one({"user_id": user_id})
        if not usuario:
            await interaction.response.send_message(
                "No puedes usar este comando sin un perfil, utiliza `/p` para crear tu perfil."
            )
            return

        last_claim = usuario.get("last_claim")
        if last_claim:
            transcurrido = datetime.utcnow() - last_claim
            if transcurrido < COOLDOWN_CLAIM:
                await interaction.response.send_message(
                    f"❌ Debes esperar {_formatear_espera(COOLDOWN_CLAIM - transcurrido)} antes de reclamar nuevamente.",
                    ephemeral=True,
                )
                return

        muestra = list(cards_collection.aggregate([{"$sample": {"size": 1}}]))
        if not muestra:
            await interaction.response.send_message("⚠️ No hay cartas cargadas en la base de datos.")
            return

        doc = muestra[0]
        carta = Carta.desde_dict(doc)
        users_collection.update_one(
            {"user_id": user_id},
            {
                "$inc": {"cartas": 1},
                "$push": {"jugadores": doc},
                "$set": {"last_claim": datetime.utcnow()},
            },
        )

        archivo = nextcord.File(carta_a_bytes(carta), filename="carta.png")
        embed = nextcord.Embed(
            title="¡Has reclamado una carta!",
            description=f"Has obtenido a **{carta.nombre}** ({carta.ovr} · {carta.posicion})",
            color=nextcord.Color.green(),
        )
        embed.set_image(url="attachment://carta.png")
        await interaction.response.send_message(embed=embed, file=archivo)


def setup(bot: commands.Bot):
    bot.add_cog(Cartas(bot))
