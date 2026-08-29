# MAC Bot — Robot d'analyse BTMM avec alertes Telegram

## ⚠️ À lire avant de déployer

1. **Régénère le token Telegram** avant de le mettre en production — il a été partagé en clair dans la conversation qui a servi à construire ce projet. Sur BotFather : `/mybots` → `macbottrading_bot` → API Token → Revoke current token.
2. **Change le mot de passe "Canaux"** (`78100302`) — même raison.
3. **Les données Twelve Data (plan gratuit) ne sont pas du temps réel exact** — délai documenté d'environ 1 à 15 minutes selon l'actif. C'est plus rapide que Yahoo Finance en général, mais ce n'est toujours pas instantané.
4. **Aucune stratégie technique ne garantit un gain.** Ce robot est un outil d'aide à la décision, pas un système infaillible.

## Architecture

- **Render (web service gratuit)** héberge le code Flask en permanence
- **cron-job.org (gratuit)** appelle `https://ton-app.onrender.com/cron/<CRON_SECRET>` toutes les 20 minutes → déclenche l'analyse
- **Telegram webhook** pointe vers `https://ton-app.onrender.com/webhook/<TELEGRAM_BOT_TOKEN>` → reçoit les commandes du bot en direct

Le plan gratuit Render met le service en veille après 15 minutes d'inactivité. Le premier appel après une pause (cron ou message utilisateur) prend 30 à 60 secondes de plus le temps que le service se réveille — normal, pas un bug.

## Étape 1 — Déployer sur Render

1. Crée un repo GitHub avec tous les fichiers de ce projet (structure conservée)
2. Sur [render.com](https://render.com), crée un compte, puis **New → Web Service**
3. Connecte ton repo GitHub
4. Render détecte `render.yaml` automatiquement (Blueprint) — sinon configure manuellement :
   - Build command : `pip install -r requirements.txt`
   - Start command : `gunicorn main:app --bind 0.0.0.0:$PORT --timeout 120`

## Étape 2 — Configurer les variables d'environnement

Dans Render, section **Environment** :

| Variable | Valeur |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Ton nouveau token (après régénération) |
| `TELEGRAM_CHAT_ID` | `-1004475850376` |
| `TWELVE_DATA_KEY_1` à `4` | Tes 4 clés API Twelve Data |
| `CRON_SECRET` | Une chaîne aléatoire longue de ton choix (ex: générée sur [randomkeygen.com](https://randomkeygen.com)) |
| `PASSWORD_CANAUX_TELEGRAM` | Ton nouveau mot de passe (après changement) |
| `CANAL_SIGNAUX_URL` | Le lien public `t.me/...` de ton canal de signaux (à créer si pas encore fait) |

## Étape 3 — Activer le webhook Telegram

Une fois Render déployé (tu as une URL du style `https://mac-bot-xxxx.onrender.com`), ouvre dans un navigateur (remplace les valeurs) :

```
https://api.telegram.org/bot<TON_TOKEN>/setWebhook?url=https://mac-bot-xxxx.onrender.com/webhook/<TON_TOKEN>
```

Tu dois voir `{"ok":true,"result":true,"description":"Webhook was set"}`.

## Étape 4 — Configurer le cron externe (cron-job.org)

1. Crée un compte gratuit sur [cron-job.org](https://cron-job.org)
2. Nouveau cronjob :
   - URL : `https://mac-bot-xxxx.onrender.com/cron/<TON_CRON_SECRET>`
   - Intervalle : toutes les 20 minutes
3. Sauvegarde et active

## Étape 5 — Enregistrer le menu de commandes (une seule fois)

Dans un terminal Python ou via un simple appel API, exécute une fois :

```python
import requests
requests.post(f"https://api.telegram.org/bot<TON_TOKEN>/setMyCommands", json={
    "commands": [
        {"command": "start", "description": "Démarrer / message de bienvenue"},
        {"command": "inscrire", "description": "Créer votre compte"},
        {"command": "connexion", "description": "Vous connecter"},
        {"command": "signaux", "description": "Voir les positions du jour"},
        {"command": "support", "description": "Contacter le créateur"},
        {"command": "canaux", "description": "Canaux Telegram connectés"},
    ]
})
```

## Les deux stratégies (résumé technique interne)

Le bot analyse 24 actifs en M15 avec deux setups indépendants, jamais nommés dans les messages envoyés aux utilisateurs :

1. **Retest EMA50 + confirmation TDI** : tendance déterminée par l'écart EMA50/EMA200, entrée sur retest du prix à l'EMA50 confirmé par un rebond du RSI sur sa ligne médiane (50)
2. **Croisement EMA50/EMA200 + rejection** : après un croisement récent des deux moyennes, entrée sur un retest de la zone avec une bougie de rejection (mèche significative)

Dans les deux cas, le Take Profit vise le swing high/low le plus récent, et **aucun signal n'est envoyé si le ratio risque:récompense résultant sort de l'intervalle [1.50, 3.50]** — ce garde-fou est non-négociable et a été testé explicitement (voir les tests dans le code).

## Limites connues

- **Persistance SQLite sur Render gratuit** : le disque configuré (`disk` dans `render.yaml`) survit aux redémarrages normaux du service, mais un changement de plan ou une reconfiguration profonde peut le réinitialiser. Pour un usage sérieux à long terme, envisager une vraie base externe (Supabase, Railway Postgres) à terme.
- **Limite Twelve Data** : 8 appels/minute et 800/jour par clé. Avec 24 actifs analysés toutes les 20 minutes (soit 72 cycles/jour), la consommation théorique est d'environ 1728 appels/jour, dans la limite des 3200 disponibles avec 4 clés — mais une clé qui tombe en panne réduit cette marge.
