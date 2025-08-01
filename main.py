import os
import discord
from discord import app_commands
from discord.ext import commands
from keep_alive import keep_alive
import random
import asyncio

token = os.environ['TOKEN_BOT_DISCORD']

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="/", intents=intents)

duels = {}

ROULETTE_NUM_IMAGES = {
    "Pile": "https://i.imgur.com/JKbZT3L.png",
    "Face": "https://i.imgur.com/4ascC3Z.png"
}

# --- Check personnalisé pour rôle sleeping ---
def is_sleeping():
    async def predicate(interaction: discord.Interaction) -> bool:
        role = discord.utils.get(interaction.guild.roles, name="sleeping")
        return role in interaction.user.roles
    return app_commands.check(predicate)

class RejoindreView(discord.ui.View):
    def __init__(self, message_id, joueur1, choix_joueur1, montant):
        super().__init__(timeout=None)
        self.message_id = message_id
        self.joueur1 = joueur1
        self.choix_joueur1 = choix_joueur1
        self.montant = montant

    @discord.ui.button(label="🎯 Rejoindre le duel", style=discord.ButtonStyle.green)
    async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
        joueur2 = interaction.user

        if joueur2.id == self.joueur1.id:
            await interaction.response.send_message("❌ Tu ne peux pas rejoindre ton propre duel.", ephemeral=True)
            return

        duel_data = duels.get(self.message_id)
        if duel_data is None:
            await interaction.response.send_message("❌ Ce duel n'existe plus ou a déjà été joué.", ephemeral=True)
            return

        for data in duels.values():
            if data["joueur1"].id == joueur2.id or (
                "joueur2" in data and data["joueur2"] and data["joueur2"].id == joueur2.id
            ):
                await interaction.response.send_message(
                    "❌ Tu participes déjà à un autre duel. Termine-le avant d’en rejoindre un autre.",
                    ephemeral=True
                )
                return

        duel_data["joueur2"] = joueur2
        self.rejoindre.disabled = True
        await interaction.response.defer()
        original_message = await interaction.channel.fetch_message(self.message_id)

        # Mettre à jour l'embed immédiatement après que le joueur 2 a rejoint
        player2_joined_embed = discord.Embed(
            title="🤝 Duel en attente de lancement...",
            description=(
                f"{self.joueur1.mention} (Choix: **{self.choix_joueur1}**) et {joueur2.mention} sont prêts ! "
                f"Montant: **{self.montant:,}".replace(",", " ") + " kamas** 💰\n\n"
                f"Le pile ou face va commencer dans un instant..."
            )
            color=discord.Color.blue()
        )
        player2_joined_embed.set_footer(text="Préparation du tirage...")
        await original_message.edit(embed=player2_joined_embed, view=None)

        # Ajouter un délai de 3 secondes ici
        await asyncio.sleep(5)

        suspense_embed = discord.Embed(
            title="🪙 Le pile ou face est en cours...",
            description="On croise les doigts 🤞🏻 !",
            color=discord.Color.greyple()
        )
        suspense_embed.set_image(url="https://www.cliqueduplateau.com/wordpress/wp-content/uploads/2015/12/flip.gif")  # Gif suspense

        await original_message.edit(embed=suspense_embed, view=None)

        for i in range(10, 0, -1):
            await asyncio.sleep(1)
            # Uniquement l'emoji pile 🪙 durant le suspense
            suspense_embed.title = f"🪙  Tirage en cours ..."
            await original_message.edit(embed=suspense_embed)

        resultat = random.choice(["Pile", "Face"])
        resultat_emoji = "🪙" if resultat == "Pile" else "🧿"

        # Déterminer gagnant
        choix_joueur2 = "Face" if self.choix_joueur1 == "Pile" else "Pile"
        choix_joueur1_emoji = "🪙" if self.choix_joueur1 == "Pile" else "🧿"
        choix_joueur2_emoji = "🪙" if choix_joueur2 == "Pile" else "🧿"

        gagnant = None
        if resultat == self.choix_joueur1:
            gagnant = self.joueur1
        else:
            gagnant = joueur2

        result_embed = discord.Embed(
            title="🎲 Résultat du Duel Pile ou Face",
            description=f"{resultat_emoji} Le résultat est : **{resultat}** !",
            color=discord.Color.green() if gagnant == joueur2 else discord.Color.red()
        )

        # ✅ Ajout de l'image en haut à droite selon le résultat
        if resultat in ROULETTE_NUM_IMAGES:
            result_embed.set_thumbnail(url=ROULETTE_NUM_IMAGES[resultat])

        # Joueur 1
        result_embed.add_field(
            name="👤 Joueur 1",
            value=f"{self.joueur1.mention}\nChoix : **{self.choix_joueur1} {choix_joueur1_emoji}**",
            inline=True
        )

        # Joueur 2
        result_embed.add_field(
            name="👤 Joueur 2",
            value=f"{joueur2.mention}\nChoix : **{choix_joueur2} {choix_joueur2_emoji}**",
            inline=False
        )

        result_embed.add_field(
            name=" ",
            value="─" * 20,
            inline=False
        )

        # Montant misé
        result_embed.add_field(
            name="💰 Montant misé",
            value=f"**{self.montant:,}".replace(",", " ") + " kamas** par joueur ",
            inline=False
        )

        # Gagnant
        result_embed.add_field(
            name="**🏆 Gagnant**",
            value=f"**{gagnant.mention} remporte {2 * self.montant:,}".replace(",", " ") + " kamas 💰**",
            inline=False
        )

        result_embed.set_footer(text="🪙 Duel terminé • Bonne chance pour le prochain !")

        await original_message.edit(embed=result_embed, view=None)
        duels.pop(self.message_id, None)


class PariView(discord.ui.View):
    def __init__(self, interaction, montant):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.montant = montant

    async def lock_in_choice(self, interaction, choix):
        if interaction.user.id != self.interaction.user.id:
            await interaction.response.send_message("❌ Seul le joueur qui a lancé le duel peut choisir.", ephemeral=True)
            return

        joueur1 = self.interaction.user
        choix_emoji = "🪙" if choix == "Pile" else "🧿"

        embed = discord.Embed(
            title="🪙 Nouveau Duel Pile ou Face",
            description=f"{joueur1.mention} a choisi : **{choix} {choix_emoji}**\nMontant : **{self.montant:,}".replace(",", " ") + " kamas** 💰",
            color=discord.Color.orange()
        )
        embed.add_field(name="👤 Joueur 1", value=f"{joueur1.mention} - {choix}", inline=True)
        embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
        embed.set_footer(text=f"📋 Pari pris : {joueur1.display_name} - {choix}")

        await interaction.response.edit_message(embed=embed, view=None)

        rejoindre_view = RejoindreView(message_id=None, joueur1=joueur1, choix_joueur1=choix, montant=self.montant)
        
        # ✅ Mention du rôle "sleeping" dans le même message que l'embed
        role = discord.utils.get(interaction.guild.roles, name="sleeping")
        message = await interaction.channel.send(
            content=f"{role.mention} — Un nouveau duel est prêt !",
            embed=embed,
            view=rejoindre_view,
            allowed_mentions=discord.AllowedMentions(roles=True)
        )

        rejoindre_view.message_id = message.id

        duels[message.id] = {
            "joueur1": joueur1,
            "montant": self.montant,
            "choix": choix
        }

    @discord.ui.button(label="Pile 🪙", style=discord.ButtonStyle.primary)
    async def pile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "Pile")

    @discord.ui.button(label="Face 🧿", style=discord.ButtonStyle.secondary)
    async def face(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "Face")


@bot.tree.command(name="sleeping", description="Lancer un duel pile ou face avec un montant.")
@is_sleeping()
@app_commands.describe(montant="Montant misé en kamas")
async def sleeping(interaction: discord.Interaction, montant: int):
    if interaction.channel.name != "pile-ou-face-sleeping":
        await interaction.response.send_message("❌ Tu dois utiliser cette commande dans le salon `#pile-ou-face-sleeping`.", ephemeral=True)
        return

    if montant <= 0:
        await interaction.response.send_message("❌ Le montant doit être supérieur à 0.", ephemeral=True)
        return

    for duel_data in duels.values():
        if duel_data["joueur1"].id == interaction.user.id or (
            "joueur2" in duel_data and duel_data["joueur2"] and duel_data["joueur2"].id == interaction.user.id
        ):
            await interaction.response.send_message(
                "❌ Tu participes déjà à un autre duel. Termine-le ou utilise `/quit` pour l'annuler.",
                ephemeral=True
            )
            return

    embed = discord.Embed(
        title="🪙 Nouveau Duel Pile ou Face",
        description=f"{interaction.user.mention} veut lancer un duel pour **{montant:,}".replace(",", " ") + " kamas** 💰",
        color=discord.Color.gold()
    )
    embed.add_field(name="Choix", value="Clique sur un bouton ci-dessous : Pile / Face", inline=False)

    view = PariView(interaction, montant)

    # Ici tu peux soit répondre directement, soit defer et followup
    # Mais pas les deux à la fois et surtout pas après un send_message déjà appelé

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="quit", description="Annule le duel en cours que tu as lancé.")
@is_sleeping()
async def quit_duel(interaction: discord.Interaction):
    if interaction.channel.name != "pile-ou-face-sleeping":
        await interaction.response.send_message("❌ Tu dois utiliser cette commande dans le salon `#pile-ou-face-sleeping`.", ephemeral=True)
        return

    duel_a_annuler = None
    for message_id, duel_data in duels.items():
        if duel_data["joueur1"].id == interaction.user.id:
            duel_a_annuler = message_id
            break

    if duel_a_annuler is None:
        await interaction.response.send_message("❌ Tu n'as aucun duel en attente à annuler.", ephemeral=True)
        return

    # ✅ On répond tout de suite pour éviter les erreurs
    await interaction.response.defer(ephemeral=True)

    duels.pop(duel_a_annuler)

    try:
        channel = interaction.channel
        message = await channel.fetch_message(duel_a_annuler)
        if message.embeds:
            embed = message.embeds[0]
            embed.color = discord.Color.red()
            embed.title += " (Annulé)"
            embed.description = "⚠️ Ce duel a été annulé par son créateur."
            await message.edit(embed=embed, view=None)
    except Exception:
        pass

    await interaction.followup.send("✅ Ton duel a bien été annulé.", ephemeral=True)


keep_alive()
bot.run(token)
