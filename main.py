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

        # On affiche un embed avec les choix des deux joueurs avant suspense
        choix_joueur1_emoji = "🪙" if self.choix_joueur1 == "Pile" else "🧿"
        choix_joueur2 = "Face" if self.choix_joueur1 == "Pile" else "Pile"
        choix_joueur2_emoji = "🪙" if choix_joueur2 == "Pile" else "🧿"

        embed_choix = discord.Embed(
            title="🪙 Duel Pile ou Face démarré",
            description=f"Montant : **{self.montant:,} kamas** 💰",
            color=discord.Color.orange()
        )
        embed_choix.add_field(
            name="👤 Joueur 1",
            value=f"{self.joueur1.mention}\nChoix : **{self.choix_joueur1} {choix_joueur1_emoji}**",
            inline=True
        )
        embed_choix.add_field(
            name="👤 Joueur 2",
            value=f"{joueur2.mention}\nChoix : **{choix_joueur2} {choix_joueur2_emoji}**",
            inline=True
        )
        embed_choix.set_footer(text=f"📋 Duel lancé par {self.joueur1.display_name}")

        await original_message.edit(embed=embed_choix, view=self)

        # Pause de 3 secondes avant de lancer le suspense
        await asyncio.sleep(3)

        suspense_embed = discord.Embed(
            title="🪙 Le pile ou face est en cours...",
            description="On croise les doigts 🤞🏻 !",
            color=discord.Color.greyple()
        )
        suspense_embed.set_image(url="https://www.cliqueduplateau.com/wordpress/wp-content/uploads/2015/12/flip.gif")

        await original_message.edit(embed=suspense_embed, view=None)

        for i in range(10, 0, -1):
            await asyncio.sleep(1)
            suspense_embed.title = f"🪙  Tirage en cours ..."
            await original_message.edit(embed=suspense_embed)

        resultat = random.choice(["Pile", "Face"])
        resultat_emoji = "🪙" if resultat == "Pile" else "🧿"

        gagnant = self.joueur1 if resultat == self.choix_joueur1 else joueur2

        result_embed = discord.Embed(
            title="🎲 Résultat du Duel Pile ou Face",
            description=f"{resultat_emoji} Le résultat est : **{resultat}** !",
            color=discord.Color.green() if gagnant == joueur2 else discord.Color.red()
        )
        result_embed.add_field(
            name="👤 Joueur 1",
            value=f"{self.joueur1.mention}\nChoix : **{self.choix_joueur1} {choix_joueur1_emoji}**",
            inline=True
        )
        result_embed.add_field(
            name="👤 Joueur 2",
            value=f"{joueur2.mention}\nChoix : **{choix_joueur2} {choix_joueur2_emoji}**",
            inline=True
        )
        result_embed.add_field(name=" ", value="─" * 20, inline=False)
        result_embed.add_field(name="🏆 Gagnant", value=f"**{gagnant.mention}** remporte **{2 * self.montant:,} kamas** 💰", inline=False)
        result_embed.set_footer(text="🪙 Duel terminé • Bonne chance pour le prochain !")

        await original_message.edit(embed=result_embed, view=None)
        duels.pop(self.message_id, None)

class PariView(discord.ui.View):
    def __init__(self, interaction, montant):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.montant = montant

    @discord.ui.button(label="Pile 🪙", style=discord.ButtonStyle.primary)
    async def pile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "Pile")

    @discord.ui.button(label="Face 🧿", style=discord.ButtonStyle.secondary)
    async def face(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.lock_in_choice(interaction, "Face")

    async def lock_in_choice(self, interaction, choix):
    if interaction.user.id != self.interaction.user.id:
        await interaction.response.send_message("❌ Seul le joueur qui a lancé le duel peut choisir.", ephemeral=True)
        return

    joueur1 = self.interaction.user

    embed = discord.Embed(
        title="🪙 Nouveau Duel Pile ou Face",
        description=f"Montant : **{self.montant:,} kamas** 💰",
        color=discord.Color.orange()
    )
    embed.add_field(name="👤 Joueur 1", value=f"{joueur1.mention}", inline=True)
    embed.add_field(name="👤 Joueur 2", value="🕓 En attente...", inline=True)
    embed.set_footer(text=f"📋 Pari pris : {joueur1.display_name}")

    role = discord.utils.get(interaction.guild.roles, name="sleeping")
    mention = role.mention if role else "@sleeping"

    # Envoie un message mention + embed DUEL dans le channel (nouveau message)
    await interaction.followup.send(content=f"{mention} — Un nouveau duel est prêt !", embed=embed)

    # Edit la réponse initiale de l'interaction (celle avec les boutons) pour retirer la vue
    await interaction.response.edit_message(view=None)

    duels[interaction.message.id] = {
        "joueur1": joueur1,
        "montant": self.montant,
        "choix_joueur1": choix,
        "joueur2": None
    }


        await interaction.response.edit_message(embed=embed, view=None)

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
            duel_data.get("joueur2") and duel_data["joueur2"] and duel_data["joueur2"].id == interaction.user.id
        ):
            await interaction.response.send_message(
                "❌ Tu participes déjà à un autre duel. Termine-le ou utilise `/quit` pour l'annuler.",
                ephemeral=True
            )
            return

    embed = discord.Embed(
        title="🪙 Nouveau Duel Pile ou Face",
        description=f"{interaction.user.mention} veut lancer un duel pour **{montant:,} kamas** 💰",
        color=discord.Color.gold()
    )
    embed.add_field(name="Choix", value="Clique sur un bouton ci-dessous : Pile / Face", inline=False)

    view = PariView(interaction, montant)
    # --- On répond une seule fois avec send_message ---
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="quit", description="Annule ton duel en cours.")
async def quit_duel(interaction: discord.Interaction):
    # Exemple simple pour retrouver un duel en cours (à adapter selon ta structure)
    duel = None
    for duel_data in duels.values():
        if duel_data["joueur1"].id == interaction.user.id or (
            duel_data.get("joueur2") and duel_data["joueur2"].id == interaction.user.id
        ):
            duel = duel_data
            break

    if duel is None:
        # Première réponse avec send_message car c’est la toute première réponse
        await interaction.response.send_message("❌ Tu n'as aucun duel en attente à annuler.", ephemeral=True)
        return

    # Supprime ou annule le duel
    duels.pop(duel.get("message_id"), None)

    # Envoie la confirmation en réponse (toujours la première réponse dans une commande)
    await interaction.response.send_message("✅ Ton duel a bien été annulé.", ephemeral=True)


    # Puis éditer le message sans répondre à l'interaction (donc pas interaction.response)
    try:
        channel = interaction.channel
        message = await channel.fetch_message(duel_a_annuler)
        embed = message.embeds[0]
        embed.color = discord.Color.red()
        embed.title += " (Annulé)"
        embed.description = "⚠️ Ce duel a été annulé par son créateur."
        await message.edit(embed=embed, view=None)
    except Exception as e:
        print(f"Erreur lors de l'édition du message d'annulation : {e}")


@bot.event
async def on_ready():
    print(f"{bot.user} est prêt !")
    try:
        await bot.tree.sync()
        print("✅ Commandes synchronisées.")
    except Exception as e:
        print(f"Erreur lors de la synchronisation : {e}")

keep_alive()
bot.run(token)
