"""
MAC Bot - Serveur Flask principal

Deux rôles distincts hébergés sur le même service Render :
  1. Endpoint /cron/<CRON_SECRET> - appelé par cron-job.org toutes les 20 minutes,
     lance l'analyse des 24 actifs + le suivi des positions ouvertes + les
     messages programmés (7h/20h Burkina Faso).
  2. Endpoint /webhook/<TELEGRAM_BOT_TOKEN> - reçoit les updates Telegram (messages,
     clics sur boutons) et gère les commandes du bot (/start, /inscrire, etc.)

Les deux endpoints utilisent le token/secret dans le chemin de l'URL, conformément
à la recommandation officielle Telegram pour sécuriser un webhook sans certificat
dédié - personne d'autre ne connaît ces valeurs.
"""

import os
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo

from flask import Flask, request, jsonify

import config
import database
import data_fetcher
import strategy
import position_manager
import telegram_sender
import chart_generator
import indicators

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("macbot.main")

app = Flask(__name__)

DOSSIER_GRAPHIQUES_TEMP = "data/graphiques_temp"

# ============================================================
# ÉTAT EN MÉMOIRE POUR LE FLUX D'INSCRIPTION/CONNEXION
# ============================================================
# Petits états conversationnels simples (ex: "on attend que cet utilisateur tape
# son nom après avoir cliqué sur /inscrire"). En mémoire uniquement : si le
# service redémarre au milieu d'une inscription, l'utilisateur devra recommencer
# la commande - acceptable pour un flux aussi court.
_etats_conversation = {}

# Accès "Canaux Telegram" déjà validés (le mot de passe n'a besoin d'être tapé
# qu'une fois par utilisateur, pas à chaque fois).
_acces_canaux_valides = set()


def _heure_actuelle_burkina() -> datetime:
    return datetime.now(ZoneInfo(config.TIMEZONE_BF))


def _deja_envoye_aujourdhui(nom_evenement: str) -> bool:
    chemin = f"data/marqueur_{nom_evenement}.txt"
    aujourdhui = date.today().isoformat()
    if os.path.exists(chemin):
        with open(chemin, "r") as f:
            if f.read().strip() == aujourdhui:
                return True
    os.makedirs("data", exist_ok=True)
    with open(chemin, "w") as f:
        f.write(aujourdhui)
    return False


# ============================================================
# LOGIQUE D'ANALYSE (appelée par le cron externe)
# ============================================================

def _traiter_messages_programmes():
    maintenant_bf = _heure_actuelle_burkina()

    if maintenant_bf.hour == config.MORNING_HOUR_BF and not _deja_envoye_aujourdhui("matin"):
        logger.info("Envoi du message du matin")
        telegram_sender.envoyer_message(telegram_sender.formater_message_matin())

    if maintenant_bf.hour == config.EVENING_HOUR_BF and not _deja_envoye_aujourdhui("soir"):
        logger.info("Envoi du bilan du soir")
        fermees = database.positions_fermees_aujourdhui()
        ouvertes = database.lister_positions_ouvertes()
        telegram_sender.envoyer_message(telegram_sender.formater_bilan_soir(fermees, ouvertes))


def _suivre_positions_ouvertes():
    positions = database.lister_positions_ouvertes()

    for position in positions:
        try:
            prix = data_fetcher.prix_actuel(position["symbol"])
        except (data_fetcher.DonneesInsuffisantesError, data_fetcher.ToutesLesClesEpuiseesError) as e:
            logger.warning(f"Impossible de vérifier {position['symbol']}: {e}")
            continue

        if position_manager.verifier_expiration_day_trading(position):
            resultat = round((prix - position["prix_entree"]) if position["direction"] == "ACHAT"
                              else (position["prix_entree"] - prix), 5)
            position_manager.cloturer_position(position, resultat, "FERMEE_EXPIREE")
            telegram_sender.envoyer_message(
                f"⏰ *{position['display']}* — Position clôturée (durée max atteinte)"
            )
            continue

        evenement, resultat_pips = position_manager.verifier_position(position, prix)

        if evenement == "SL_TOUCHE":
            telegram_sender.envoyer_message(
                telegram_sender.formater_message_evenement(position["display"], "SL_TOUCHE", position["stop_loss"])
            )
            position_manager.cloturer_position(position, resultat_pips, "FERMEE_SL")

        elif evenement == "TP_TOUCHE":
            telegram_sender.envoyer_message(
                telegram_sender.formater_message_evenement(position["display"], "TP_TOUCHE", position["take_profit"])
            )
            position_manager.cloturer_position(position, resultat_pips, "FERMEE_TP")


def _analyser_et_signaler():
    os.makedirs(DOSSIER_GRAPHIQUES_TEMP, exist_ok=True)

    for nom_actif, infos in config.ASSETS.items():
        symbol = infos["symbol"]

        if database.symbole_a_deja_une_position_ouverte(symbol):
            continue

        try:
            df = data_fetcher.recuperer_bougies(
                symbol, config.TIMEFRAME, config.CANDLES_REQUESTED, config.MIN_CANDLES_REQUIRED
            )
        except data_fetcher.ToutesLesClesEpuiseesError as e:
            logger.warning(f"Toutes les clés API épuisées, arrêt du cycle d'analyse: {e}")
            break  # inutile de continuer à essayer les autres actifs ce cycle
        except data_fetcher.DonneesInsuffisantesError as e:
            logger.warning(str(e))
            continue

        try:
            signal = strategy.analyser_actif(symbol, infos["type"], df)
        except Exception as e:
            logger.error(f"Erreur d'analyse sur {symbol}: {e}")
            continue

        if signal is None:
            continue

        logger.info(f"Signal validé sur {symbol}: {signal.direction} (stratégie interne: {signal.strategie}, RR={signal.niveaux.ratio_rr})")

        position_manager.ouvrir_position(symbol, infos["display"], infos["type"], signal)

        message = telegram_sender.formater_message_signal(infos["display"], signal.direction, signal.niveaux)

        df_ind = indicators.calculer_tous_indicateurs(
            df, config.EMA_FAST, config.EMA_SLOW, config.ATR_PERIOD,
            config.TDI_RSI_PERIOD, config.TDI_RSI_PRICE_LINE, config.TDI_TRADE_SIGNAL_LINE, config.TDI_VOLATILITY_BAND,
        )
        chemin_image = f"{DOSSIER_GRAPHIQUES_TEMP}/{nom_actif}.png"

        try:
            chart_generator.generer_graphique(
                df_ind, infos["display"], signal.direction,
                signal.niveaux.prix_entree, signal.niveaux.stop_loss, signal.niveaux.take_profit, chemin_image,
            )
            telegram_sender.envoyer_photo(chemin_image, legende=message)
        except Exception as e:
            logger.error(f"Échec génération/envoi du graphique pour {symbol}: {e} - envoi du texte seul")
            telegram_sender.envoyer_message(message)


# ============================================================
# ENDPOINT CRON (appelé par cron-job.org toutes les 20 minutes)
# ============================================================

@app.route("/cron/<secret>", methods=["GET", "POST"])
def endpoint_cron(secret):
    if not config.CRON_SECRET or secret != config.CRON_SECRET:
        return jsonify({"error": "unauthorized"}), 403

    logger.info("=== MAC Bot - Démarrage du cycle d'analyse ===")
    try:
        _suivre_positions_ouvertes()
        _analyser_et_signaler()
        _traiter_messages_programmes()
    except Exception as e:
        logger.error(f"Erreur durant le cycle d'analyse: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

    logger.info("=== Cycle terminé ===")
    return jsonify({"status": "ok"}), 200


# ============================================================
# WEBHOOK TELEGRAM (commandes du bot)
# ============================================================

def _envoyer_menu_public(chat_id: int):
    texte = (
        "👋 *Bienvenue sur MAC Bot !*\n\n"
        "Utilise /inscrire pour créer ton compte, ou /connexion si tu en as déjà un."
    )
    telegram_sender.envoyer_message(texte, chat_id=str(chat_id))


def _envoyer_menu_connecte(chat_id: int):
    boutons = [
        [{"text": "📊 Signaux", "callback_data": "menu_signaux"}],
        [{"text": "🆘 Support", "callback_data": "menu_support"}],
        [{"text": "📡 Canaux Telegram", "callback_data": "menu_canaux"}],
    ]
    telegram_sender.envoyer_message_avec_boutons("Que veux-tu faire ?", str(chat_id), boutons)


def _gerer_commande_signaux(chat_id: int):
    positions = database.positions_ouvertes_ou_fermees_aujourdhui_pour_signaux()
    if not positions:
        telegram_sender.envoyer_message("Aucun signal envoyé aujourd'hui pour le moment.", chat_id=str(chat_id))
        return

    lignes = ["📊 *Signaux du jour*", ""]
    for p in positions:
        emoji = "🟢" if p["direction"] == "ACHAT" else "🔴"
        statut = p.get("statut") or p.get("statut_final") or "OUVERTE"
        lignes.append(f"{emoji} {p['display']} ({p['direction']}) — {statut}")
        lignes.append(f"   Entrée: `{p['prix_entree']}` | SL: `{p['stop_loss']}` | TP: `{p['take_profit']}`")
    telegram_sender.envoyer_message("\n".join(lignes), chat_id=str(chat_id))


def _gerer_commande_support(chat_id: int):
    texte = f"🆘 Pour toute question, contacte le créateur directement ici : {config.SUPPORT_TELEGRAM_URL}"
    telegram_sender.envoyer_message(texte, chat_id=str(chat_id))


def _gerer_commande_canaux(chat_id: int):
    if chat_id in _acces_canaux_valides:
        lien = config.CANAL_SIGNAUX_URL or "(lien du canal non configuré - voir CANAL_SIGNAUX_URL)"
        texte = f"📡 *Canal officiel connecté*\n\n{lien}"
        telegram_sender.envoyer_message(texte, chat_id=str(chat_id))
        return

    _etats_conversation[chat_id] = {"attente": "mot_de_passe_canaux"}
    telegram_sender.envoyer_message("🔒 Cette section est protégée. Entre le mot de passe :", chat_id=str(chat_id))


def _traiter_message_texte(chat_id: int, user_id: int, texte: str, nom_utilisateur: str, nom_profil: str):
    texte_propre = texte.strip()

    # --- Flux conversationnel en cours (attente d'une réponse à une question précédente) ---
    etat = _etats_conversation.get(chat_id)
    if etat:
        if etat["attente"] == "nom_inscription":
            database.inscrire_utilisateur(user_id, texte_propre, nom_profil)
            del _etats_conversation[chat_id]
            telegram_sender.envoyer_message(f"✅ Bienvenue {texte_propre} ! Ton compte est créé.", chat_id=str(chat_id))
            _envoyer_menu_connecte(chat_id)
            return

        if etat["attente"] == "mot_de_passe_canaux":
            if texte_propre == config.PASSWORD_CANAUX_TELEGRAM and config.PASSWORD_CANAUX_TELEGRAM:
                _acces_canaux_valides.add(chat_id)
                del _etats_conversation[chat_id]
                _gerer_commande_canaux(chat_id)
            else:
                telegram_sender.envoyer_message("❌ Mot de passe incorrect.", chat_id=str(chat_id))
            return

    # --- Commandes ---
    if texte_propre in ("/start",):
        if database.utilisateur_existe(user_id):
            _envoyer_menu_connecte(chat_id)
        else:
            _envoyer_menu_public(chat_id)
        return

    if texte_propre in ("/inscrire",):
        if database.utilisateur_existe(user_id):
            telegram_sender.envoyer_message("Tu as déjà un compte ! Utilise /connexion.", chat_id=str(chat_id))
            return
        _etats_conversation[chat_id] = {"attente": "nom_inscription"}
        telegram_sender.envoyer_message("Quel est ton nom ?", chat_id=str(chat_id))
        return

    if texte_propre in ("/connexion",):
        if database.utilisateur_existe(user_id):
            _envoyer_menu_connecte(chat_id)
        else:
            telegram_sender.envoyer_message("Aucun compte trouvé. Utilise /inscrire pour en créer un.", chat_id=str(chat_id))
        return

    if texte_propre in ("/signaux",):
        _gerer_commande_signaux(chat_id)
        return

    if texte_propre in ("/support",):
        _gerer_commande_support(chat_id)
        return

    if texte_propre in ("/canaux",):
        _gerer_commande_canaux(chat_id)
        return


def _traiter_callback_query(chat_id: int, callback_data: str, callback_query_id: str):
    telegram_sender.repondre_callback(callback_query_id)

    if callback_data == "menu_signaux":
        _gerer_commande_signaux(chat_id)
    elif callback_data == "menu_support":
        _gerer_commande_support(chat_id)
    elif callback_data == "menu_canaux":
        _gerer_commande_canaux(chat_id)


@app.route(f"/webhook/{config.TELEGRAM_BOT_TOKEN}", methods=["POST"])
def endpoint_webhook():
    update = request.get_json(silent=True)
    if not update:
        return jsonify({"ok": False}), 400

    try:
        if "message" in update and "text" in update["message"]:
            msg = update["message"]
            chat_id = msg["chat"]["id"]
            user_id = msg["from"]["id"]
            nom_profil = msg["from"].get("username", "")
            texte = msg["text"]
            _traiter_message_texte(chat_id, user_id, texte, msg["from"].get("first_name", ""), nom_profil)

        elif "callback_query" in update:
            cq = update["callback_query"]
            chat_id = cq["message"]["chat"]["id"]
            _traiter_callback_query(chat_id, cq.get("data", ""), cq["id"])

    except Exception as e:
        logger.error(f"Erreur de traitement du webhook: {e}")

    return jsonify({"ok": True}), 200


# ============================================================
# ENDPOINT DE SANTÉ (pour vérifier que le service tourne)
# ============================================================

@app.route("/", methods=["GET"])
def endpoint_racine():
    return jsonify({"status": "MAC Bot en ligne"}), 200


# ============================================================
# INITIALISATION
# ============================================================

database.initialiser_base()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
