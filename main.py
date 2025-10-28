import os
import discord
from discord import app_commands
from discord.ext import commands
from keep_alive import keep_alive
import sqlite3
import re
import asyncio

# --- CONFIGURATION & CONSTANTES ---
token = os.environ['TOKEN_BOT_DISCORD']

# ID du salon de log de la roulette
ID_SALON_LOG_COMMISSION = 1366384335615164529
# ID du bot de roulette (À REMPLACER par l'ID copié !)
ID_BOTS_DE_JEU = {
    1394959403144314940, # Ancien ID_BOT_ROULETTE
    1234567890123456789, # NOUVEAU Bot de jeu 1
    9876543210987654321  # NOUVEAU Bot de jeu 2
}

ID_HUMAINS_AUTORISES = {
    114811427377774600, # ID Utilisateur 1
    9876543210987654320, # ID Utilisateur 2
}
# ID du rôle des Croupiers (À REMPLACER)
ID_ROLE_CROUPIER = 1401471414262829066 # <<<<< REMPLACEZ CECI PAR L'ID DU RÔLE CROUPIER >>>>>
if ID_ROLE_CROUPIER == 0:
    print("⚠️ ATTENTION : L'ID du rôle croupier (ID_ROLE_CROUPIER) doit être défini.")


# --- BASE DE DONNÉES (SQLite) ---
DB_NAME = "leaderboard_mises.db"

# Fonction thread-safe pour l'initialisation de la DB
def setup_db():
    """Crée la table de mises si elle n'existe pas."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS total_mises (
        user_id INTEGER PRIMARY KEY,
        mises_cumulees INTEGER NOT NULL DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

# Appel de la fonction de configuration au démarrage
setup_db()


# --- INITIALISATION DU BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Regex pour analyser le message de log et extraire Joueurs et Mise
# Utilisation de \s+ au lieu de ' ' pour correspondre à n'importe quel espace (y compris les espaces insécables)
LOG_REGEX = re.compile(
    # NOTE: J'utilise \s* pour correspondre à zéro ou plusieurs espaces/tabulations
    r'\|\s*Duel\s*:\s*'
    # Capture du Joueur 1 (Groupe 1) : mention Discord
    r'(<@!?\d+>)\s*vs\s*'
    # Capture du Joueur 2 (Groupe 2) : mention Discord
    r'(<@!?\d+>)\s*'
    # Capture de la Mise (Groupe 3) : permet n'importe quel type de séparation numérique
    # J'utilise [ \s]+ pour capturer les chiffres séparés par n'importe quel espace
    r'\(Mise\s*:\s*([\d\s]+)\s*kamas\s*par\s*joueur\)'
)

def extract_id(mention):
    match = re.search(r'<@!?(\d+)>', mention)
    return int(match.group(1)) if match else None

# --- FONCTIONS THREAD-SAFE CORRIGÉES POUR LA BASE DE DONNÉES ---

def _update_single_user_mises(c, user_id: int, montant: int):
    """
    Met à jour la mise pour un seul utilisateur en utilisant un curseur existant.
    CORRIGE l'IntegrityError en utilisant UPDATE or INSERT.
    """
    # 1. Tenter la mise à jour (si l'utilisateur existe)
    c.execute("UPDATE total_mises SET mises_cumulees = mises_cumulees + ? WHERE user_id = ?", (montant, user_id))

    # 2. Si aucune ligne n'a été modifiée (l'utilisateur n'existe pas), faire un INSERT
    if c.rowcount == 0:
        c.execute("INSERT INTO total_mises (user_id, mises_cumulees) VALUES (?, ?)", (user_id, montant))

def process_duel_mises(player1_id: int, player2_id: int, mise_amount: int):
    """
    Traite les deux mises dans une seule transaction DB (CORRIGE l'erreur 'database is locked').
    """
    conn = sqlite3.connect(DB_NAME) 
    c = conn.cursor()

    # Mise à jour des deux joueurs dans la même connexion
    _update_single_user_mises(c, player1_id, mise_amount)
    _update_single_user_mises(c, player2_id, mise_amount)

    conn.commit()
    conn.close()

def get_leaderboard_data():
    """Récupère toutes les données du classement de manière thread-safe."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    c.execute("""
        SELECT user_id, mises_cumulees
        FROM total_mises
        ORDER BY mises_cumulees DESC
    """)
    all_players = c.fetchall()

    conn.close()
    return all_players


# --- CLASSE DE VUE POUR LA PAGINATION (Inchangée) ---

class TopMisesView(discord.ui.View):
    def __init__(self, entries):
        super().__init__(timeout=None)
        self.entries = entries
        self.page = 0
        self.entries_per_page = 10
        total_entries = len(entries)
        # Calcule la dernière page possible (max_page est l'index de la dernière page)
        self.max_page = (total_entries - 1) // self.entries_per_page if total_entries > 0 else 0
        self.update_buttons()

    def update_buttons(self):
        """Désactive les boutons quand on atteint les limites du classement."""
        if self.max_page > 0:
            # Boutons 'Début' (0) et 'Précédent' (1)
            is_first_page = self.page == 0
            self.children[0].disabled = is_first_page
            self.children[1].disabled = is_first_page
            
            # Boutons 'Suivant' (2) et 'Fin' (3)
            is_last_page = self.page == self.max_page
            self.children[2].disabled = is_last_page
            self.children[3].disabled = is_last_page
        else:
            # Si une seule page ou aucun joueur, tout désactiver
            for button in self.children:
                button.disabled = True

    def get_embed(self):
        """Génère l'Embed pour la page actuelle."""
        start = self.page * self.entries_per_page
        end = start + self.entries_per_page
        slice_entries = self.entries[start:end]

        embed = discord.Embed(
            title="👑 Leaderboard des Mises Cumulées 💰",
            description="Classement des joueurs avec le plus de Kamas misés.",
            color=discord.Color.blue()
        )

        if not slice_entries:
            embed.description = "Aucune donnée à afficher sur cette page."
            embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1}")
            return embed

        rank_messages = []
        for i, (user_id, total_mises) in enumerate(slice_entries):
            rank = start + i + 1
            # Formatage des nombres avec espaces insécables (ex: 1 234 567)
            formatted_mises = f"{total_mises:,}".replace(",", "\u202F") 

            rank_messages.append(
                f"**#{rank}** <@{user_id}> : **{formatted_mises}** Kamas"
            )

        embed.description += "\n\n" + "\n".join(rank_messages)
        embed.set_footer(text=f"Page {self.page + 1}/{self.max_page + 1} | Total de {len(self.entries)} joueurs classés.")
        return embed

    async def _update_and_respond(self, interaction: discord.Interaction):
        """Met à jour l'état de la vue et répond à l'interaction."""
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    # --- Boutons de Navigation ---

    @discord.ui.button(label="⏮️ Début", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page != 0:
            self.page = 0
            await self._update_and_respond(interaction)
        else:
            # Répondre silencieusement si aucune action n'est nécessaire
            await interaction.response.defer()

    @discord.ui.button(label="◀️ Précédent", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self._update_and_respond(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Suivant ▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_page:
            self.page += 1
            await self._update_and_respond(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Fin ⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page != self.max_page:
            self.page = self.max_page
            await self._update_and_respond(interaction)
        else:
            await interaction.response.defer()


# --- FONCTION COMMUNE DE LOGIQUE DU LEADERBOARD ASYNCHRONE (Inchangée) ---

async def get_and_display_leaderboard(interaction: discord.Interaction, is_ephemeral: bool):
    """Gère la récupération des données thread-safe et l'affichage paginé."""

    await interaction.response.defer(ephemeral=is_ephemeral, thinking=True)

    all_players = await bot.loop.run_in_executor(
        None, 
        get_leaderboard_data
    )

    if not all_players:
        await interaction.followup.send("❌ Aucune mise enregistrée pour l'instant dans le leaderboard.", ephemeral=is_ephemeral)
        return

    view = TopMisesView(all_players)
    await interaction.followup.send(embed=view.get_embed(), view=view, ephemeral=is_ephemeral)


# --- COMMANDES SLASH (Inchangées) ---

@bot.tree.command(name="leaderboard", description="Affiche votre classement privé des mises cumulées.")
async def leaderboard_public(interaction: discord.Interaction):
    await get_and_display_leaderboard(interaction, is_ephemeral=True)

@bot.tree.command(name="leaderboardcroup", description="Affiche le classement publiquement (Réservé aux Croupiers).")
@app_commands.checks.has_role(ID_ROLE_CROUPIER) 
async def leaderboardcroup(interaction: discord.Interaction):
    await get_and_display_leaderboard(interaction, is_ephemeral=False)

@leaderboardcroup.error
async def leaderboardcroup_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingRole):
        await interaction.response.send_message("❌ Vous n'êtes pas autorisé à utiliser cette commande. Elle est réservée aux Croupiers.", ephemeral=True)
    else:
        print(f"Erreur dans /leaderboardcroup: {error}")
        await interaction.response.send_message("Une erreur inconnue s'est produite.", ephemeral=True)


# --- ÉVÉNEMENTS DU BOT (CORRIGÉ) ---

@bot.event
async def on_message(message):
    """Analyse les messages de log et met à jour les mises en une seule transaction."""

    # 1. FILTRAGE BOT: On ignore si l'auteur est le bot Leaderboard lui-même.
    if message.author == bot.user:
        await bot.process_commands(message)
        return

    # 2. FILTRAGE CANAL: Le message doit venir du salon de log.
    is_log_channel = message.channel.id == ID_SALON_LOG_COMMISSION
    if not is_log_channel:
        await bot.process_commands(message)
        return

    # 3. FILTRAGE AUTEUR: Vérifie si l'auteur est autorisé.
    # a) Est-ce un bot de jeu ?
    is_game_bot = message.author.id in ID_BOTS_DE_JEU
    # b) Est-ce un humain autorisé manuellement ?
    is_allowed_human = message.author.id in ID_HUMAINS_AUTORISES

    # Si l'auteur n'est NI un bot de jeu, NI un humain autorisé, on ignore.
    if not is_game_bot and not is_allowed_human:
        # On peut optionally envoyer un message d'erreur si l'on voulait, 
        # mais ici on veut simplement ignorer les messages non-log.
        await bot.process_commands(message)
        return

    # NOTE IMPORTANTE SUR LA REGEX :
    # La regex actuelle (LOG_REGEX) est très spécifique au format "Duel : <@J1> vs <@J2> (Mise : X kamas par joueur)".
    # Si les messages des NOUVEAUX bots de jeu ont un format différent, 
    # vous devrez :
    # a) Soit adapter la regex pour les capturer tous (plus complexe).
    # b) Soit ajouter d'autres conditions/regex pour traiter les formats spécifiques de chaque bot.
    # Pour l'instant, on suppose que le format de log est le même.

    # 2. LOGIQUE REGEX (inchangée)
    match = LOG_REGEX.search(message.content)
    # ... (le reste du code est inchangé)

    if match:
        player1_id = extract_id(match.group(1))
        player2_id = extract_id(match.group(2))
        mise_text = match.group(3)

        try:
            cleaned_mise_text = mise_text.replace(' ', '').replace('\u00A0', '').replace('\u202F', '')
            mise_amount = int(cleaned_mise_text)
        except ValueError:
            print(f"❌ Erreur: Le montant de mise n'est pas valide : {mise_text!r}")
            return

        if player1_id and player2_id and mise_amount > 0:
            # Appel de la fonction process_duel_mises pour une seule transaction
            await bot.loop.run_in_executor(
                None, 
                process_duel_mises, 
                player1_id, 
                player2_id, 
                mise_amount
            )

    await bot.process_commands(message)


keep_alive()
bot.run(token)
