"""
MAC Bot - Envoi des messages Telegram

Règles de formatage :
- Le message de signal NE MENTIONNE JAMAIS le nom de la stratégie interne
  (ni "retest_ema50", ni "croisement_rejection", ni aucun terme technique révélant
  la mécanique exacte utilisée)
- Entrée/SL/TP sont en `code` Markdown pour être copiables d'un tap sur Telegram
- Chaque signal doit être accompagné d'une image (géré depuis main.py, pas ici)
"""

import logging
import requests

import config

logger = logging.getLogger("macbot.telegram_sender")

API_BASE = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"


def _post(endpoint: str, data: dict = None, files: dict = None) -> dict:
    url = f"{API_BASE}/{endpoint}"
    try:
        response = requests.post(url, data=data, files=files, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Échec envoi Telegram ({endpoint}): {e}")
        return {"ok": False, "error": str(e)}


def envoyer_message(texte: str, chat_id: str = None, parse_mode: str = "Markdown") -> dict:
    return _post("sendMessage", data={
        "chat_id": chat_id or config.TELEGRAM_CHAT_ID,
        "text": texte,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    })


def envoyer_photo(chemin_image: str, legende: str = "", chat_id: str = None, parse_mode: str = "Markdown") -> dict:
    with open(chemin_image, "rb") as photo:
        return _post("sendPhoto", data={
            "chat_id": chat_id or config.TELEGRAM_CHAT_ID,
            "caption": legende,
            "parse_mode": parse_mode,
        }, files={"photo": photo})


def envoyer_message_avec_boutons(texte: str, chat_id: str, boutons: list, parse_mode: str = "Markdown") -> dict:
    """
    boutons: liste de listes de dicts {"text": "...", "callback_data": "..."} pour un clavier inline.
    """
    import json
    return _post("sendMessage", data={
        "chat_id": chat_id,
        "text": texte,
        "parse_mode": parse_mode,
        "reply_markup": json.dumps({"inline_keyboard": boutons}),
    })


def repondre_callback(callback_query_id: str, texte: str = None) -> dict:
    """Accuse réception d'un clic sur un bouton inline (évite le petit sablier qui tourne)."""
    data = {"callback_query_id": callback_query_id}
    if texte:
        data["text"] = texte
    return _post("answerCallbackQuery", data=data)


def definir_commandes_menu() -> dict:
    """
    Enregistre les commandes visibles dans le menu Telegram (le petit "/" à côté
    de la zone de texte). Appelé une fois au démarrage du serveur.
    """
    import json
    commandes = [
        {"command": "start", "description": "Démarrer / message de bienvenue"},
        {"command": "inscrire", "description": "Créer votre compte"},
        {"command": "connexion", "description": "Vous connecter"},
        {"command": "signaux", "description": "Voir les positions du jour"},
        {"command": "support", "description": "Contacter le créateur"},
        {"command": "canaux", "description": "Canaux Telegram connectés"},
    ]
    return _post("setMyCommands", data={"commands": json.dumps(commandes)})


# ============================================================
# FORMATAGE DES MESSAGES DE SIGNAL
# ============================================================

def formater_message_signal(display: str, direction: str, niveaux) -> str:
    """
    IMPORTANT : ne mentionne jamais quelle stratégie interne a généré le signal.
    Entrée/SL/TP en `code` pour être copiables.
    """
    emoji = "🟢 ACHAT" if direction == "ACHAT" else "🔴 VENTE"

    lignes = [
        f"{emoji} — *{display}*",
        "",
        f"Entrée : `{niveaux.prix_entree}`",
        f"Stop Loss : `{niveaux.stop_loss}` ({niveaux.pips_risque} pips)",
        f"Take Profit : `{niveaux.take_profit}` ({niveaux.pips_recompense} pips — RR {niveaux.ratio_rr})",
        "",
        "_Données de marché avec un léger délai selon l'actif (Twelve Data)._",
        "_Ceci est un outil d'aide à la décision, pas un conseil financier._",
    ]
    return "\n".join(lignes)


def formater_message_evenement(display: str, evenement: str, niveau_touche: float) -> str:
    if evenement == "TP_TOUCHE":
        return f"✅ *{display}* — Take Profit touché (`{niveau_touche}`)\n\n_Rappel : suivi basé sur des données avec un léger délai._"
    return f"❌ *{display}* — Stop Loss touché (`{niveau_touche}`)\n\n_Rappel : suivi basé sur des données avec un léger délai._"


def formater_message_matin() -> str:
    return (
        "☀️ *Bonjour !*\n\n"
        "MAC Bot est actif et surveille les marchés. "
        "Les signaux valides seront envoyés ici dès qu'un setup est confirmé.\n\n"
        "Bonne journée de trading 📊"
    )


def formater_bilan_soir(positions_fermees_du_jour: list, positions_encore_ouvertes: list) -> str:
    if not positions_fermees_du_jour and not positions_encore_ouvertes:
        return (
            "🌙 *Bilan du soir*\n\n"
            "Aucune position ouverte ou clôturée aujourd'hui — le marché n'a pas offert "
            "de setup validé.\n\n"
            "_Rappel : mieux vaut aucun signal qu'un signal forcé._"
        )

    total_pips = sum(p["resultat_pips"] for p in positions_fermees_du_jour if p.get("resultat_pips") is not None)
    gagnantes = [p for p in positions_fermees_du_jour if (p.get("resultat_pips") or 0) > 0]
    perdantes = [p for p in positions_fermees_du_jour if (p.get("resultat_pips") or 0) <= 0]

    lignes = ["🌙 *Bilan du soir*", ""]

    if positions_fermees_du_jour:
        lignes.append(f"Positions clôturées : {len(positions_fermees_du_jour)}")
        lignes.append(f"✅ Gagnantes : {len(gagnantes)}  |  ❌ Perdantes : {len(perdantes)}")
        signe = "+" if total_pips >= 0 else ""
        lignes.append(f"Résultat net (pips/USD selon actif) : {signe}{round(total_pips, 1)}")
        lignes.append("")
        for p in positions_fermees_du_jour:
            emoji = "✅" if (p.get("resultat_pips") or 0) > 0 else "❌"
            signe_p = "+" if (p.get("resultat_pips") or 0) >= 0 else ""
            lignes.append(f"{emoji} {p['display']} ({p['direction']}) : {signe_p}{round(p.get('resultat_pips') or 0, 1)}")

    if positions_encore_ouvertes:
        lignes.append("")
        lignes.append(f"⏳ Positions encore ouvertes ce soir : {len(positions_encore_ouvertes)}")
        for p in positions_encore_ouvertes:
            lignes.append(f"— {p['display']} ({p['direction']}), ouverte à `{p['prix_entree']}`")

    lignes += [
        "",
        "_Rappel : ces chiffres reflètent les niveaux techniques suivis par le robot, "
        "pas nécessairement l'exécution réelle sur ton compte de trading._",
    ]
    return "\n".join(lignes)
