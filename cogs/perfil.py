"""Comando de perfil: /p (crea el perfil la primera vez)."""
import nextcord
from nextcord.ext import commands

from database.conexion import users_collection
from models.usuario import Usuario


class Perfil(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @nextcord.slash_command(name="p", description="Ver información del perfil")
    async def p(self, interaction: nextcord.Interaction):
        user = interaction.user
        doc = users_collection.find_one({"user_id": user.id})
        nuevo = doc is None

        if nuevo:
            usuario = Usuario(user_id=user.id, nombre=user.name, avatar_url=user.display_avatar.url)
            users_collection.insert_one(usuario.to_dict())
        else:
            usuario = Usuario.desde_dict(doc)
            usuario.nombre, usuario.avatar_url = user.name, user.display_avatar.url
            users_collection.update_one(
                {"user_id": user.id},
                {"$set": {"nombre": usuario.nombre, "avatar_url": usuario.avatar_url}},
            )

        await interaction.response.defer()
        try:
            avatar = await user.display_avatar.read()
        except nextcord.HTTPException:
            avatar = None

        imagen = usuario.imagen_perfil(avatar=avatar, nuevo=nuevo)
        await interaction.followup.send(file=nextcord.File(imagen, filename="perfil.png"))


def setup(bot: commands.Bot):
    bot.add_cog(Perfil(bot))
