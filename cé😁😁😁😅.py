# -*- coding: utf-8 -*-
"""
FlashBoost Bot – version compacte et optimisée
python-telegram-bot v20+

Fonctions incluses :
- Achat (conversation)
- Retrait Like (récap + confirmation + admin + remboursement si rejet)
- Parrainage (lien / start payload + bonus + /mesfilleuls)
- Admin : prix, paiements, messages, canaux requis (persistants), diffusion, crédit/débit
- Vérification d’abonnement aux canaux avant accès menu
"""

import asyncio
import json
import logging
import os
import re
import html
from datetime import datetime
from typing import Any, Dict, Optional, List

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# =========================
# -------- CONFIG ---------
# =========================

# --- Admins & canaux ---
ADMINS = [7827581652, 6114819292]       # <-- Remplace par tes IDs admin
ADMIN_CHANNEL_ID = -1003076956244       # <-- Canal où les admins valident (peut être un PV admin)
SUIVI_CHANNEL_ID = -1002834854293       # <-- Canal de suivi public/privé

# --- Seuils Retrait ---
MIN_RETRAIT = 1000        # minimum de likes pour un retrait
MAX_RETRAIT = 100_000 # maximum de likes pour un retrait

# --- Fichiers / Token ---
DB_FILE = "db.json"
TOKEN = "7912783785:AAGy39S9SfPIfQt5KCRb8l-Gqpv1QIJoRLg"  # <-- Mets ton token ici

# =========================
# ----- PERSISTENCE -------
# =========================

DEFAULT_PRICES = {
    "TikTok":   {"Abonnés": 2000, "Likes": 800,  "Vues": 500},
    "Facebook": {"Abonnés": 2500, "Likes": 700,  "Vues": 700},
    "Instagram":{"Abonnés": 3500, "Likes": 1200, "Vues": 700},
    "Telegram": {"Followers": 2500, "Likes": 500, "Vues": 500},
    "WhatsApp": {"Followers": 4500},
}
DEFAULT_PAYMENTS = {
    "MTN": "+2290159152677",
    "Moov": "+2290160731390",
    "Crypto": "Contactez @boosts_services",
    "Wave": "+2250170659274"
}
DEFAULT_MESSAGES = {
    "welcome": (
        "👋 <b>Bienvenue !</b>\n\n"
        "Ici, tu peux acheter des <b>abonnés</b>, <b>likes</b> et <b>vues</b> pour booster tes réseaux 📱.\n"
        "Sélectionne une option ci-dessous 👇"
    ),
    "support": "🆘 <b>Support</b>\n\n✍️ Écris-nous sur <b>@boosts_services</b>.",
    "parrainage": (
        "🎉 <b>Bienvenue dans Flash Boost Service</b> 🚀\n\n"
        "🌟 Ton accélérateur de <b>visibilité</b> sur les réseaux sociaux !\n\n"
        "🎁 <b>Gagne  50 Likes</b> à chaque ami invité qui s’inscrit grâce à ton lien.\n"
        "💰 Tu pourras retirer tes gains à partir de <b> 500 Likes</b> cumulés.\n\n"
        "🔗 Voici ton lien unique d’invitation :\n{INVITE_LINK}\n\n"
        "👉 Partage-le dès maintenant et profite de Likes gratuits 🎯"
    ),
}
DEFAULT_REQUIRED_CHANNELS = [-1002379469108, -1002834854293]
DEFAULT_REQUIRED_LINKS = ["https://t.me/flashboost1", "https://t.me/flashboost03"]

def load_db() -> Dict[str, Any]:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning("DB invalide, recréation: %s", e)
    return {
        "users": {},
        "prices": DEFAULT_PRICES,
        "payments": DEFAULT_PAYMENTS,
        "messages": DEFAULT_MESSAGES,
        "required_channels": DEFAULT_REQUIRED_CHANNELS,
        "required_channel_links": DEFAULT_REQUIRED_LINKS
    }

def save_db(db: Dict[str, Any]):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

DB: Dict[str, Any] = load_db()

def ensure_defaults():
    changed = False
    for key, default in [
        ("users", {}),
        ("prices", DEFAULT_PRICES),
        ("payments", DEFAULT_PAYMENTS),
        ("messages", DEFAULT_MESSAGES),
        ("required_channels", DEFAULT_REQUIRED_CHANNELS),
        ("required_channel_links", DEFAULT_REQUIRED_LINKS),
    ]:
        if key not in DB:
            DB[key] = default
            changed = True
    if changed:
        save_db(DB)

ensure_defaults()

def ensure_user(uid: int):
    s = str(uid)
    if s not in DB["users"]:
        DB["users"][s] = {
            "balance": 0,
            "referrer": None,      # id du parrain (str) ou None
            "ref_given": [],       # liste des filleuls déjà crédités (ids str)
            "orders": [],          # commandes
            "retraits": [],        # retraits
        }
        save_db(DB)

# Helpers d’accès
def get_prices() -> Dict[str, Dict[str, int]]:
    return DB.get("prices", DEFAULT_PRICES)

def get_payments() -> Dict[str, str]:
    return DB.get("payments", DEFAULT_PAYMENTS)

def get_messages() -> Dict[str, str]:
    return DB.get("messages", DEFAULT_MESSAGES)

def get_required_channels() -> List[int]:
    return DB.get("required_channels", DEFAULT_REQUIRED_CHANNELS)

def get_required_channel_links() -> List[str]:
    return DB.get("required_channel_links", DEFAULT_REQUIRED_LINKS)

# =========================
# --------- UI ------------
# =========================

def main_menu(user_id: int) -> ReplyKeyboardMarkup:
    base = [
        ["🛒 Achat", "📜 Historique"],
        ["🔗 Lien de parrainage", "👥 Mes filleuls"],
        ["💰 Solde Like", "💸 Retrait Like"],
        ["🆘 Support"]
    ]
    if user_id in ADMINS:
        base.append(["👑 Admin"])
    return ReplyKeyboardMarkup(base, resize_keyboard=True)
def admin_main_keyboard() -> ReplyKeyboardMarkup:
    rows = [
        ["💵 Prix", "🏦 Paiements"],
        ["📝 Messages", "➕ Crédit/Débit"],
        ["📌 Canaux requis", "📢 Diffuser"],
        ["⬅️ Retour", "❌ Fermer"],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

# =========================
# --- ACCÈS & CANAUX ------
# =========================

def channels_required_configured() -> bool:
    chans = get_required_channels()
    links = get_required_channel_links()
    return bool(chans) and bool(links) and len(chans) == len(links)

async def check_all_memberships(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not channels_required_configured():
        return True
    try:
        for chat_id in get_required_channels():
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        return True
    except Exception as e:
        logging.warning("check_all_memberships error: %s", e)
        return False

async def prompt_join_channels(update_or_query, context: ContextTypes.DEFAULT_TYPE):
    if not channels_required_configured():
        return
    join_buttons = [
        [InlineKeyboardButton(f"🔗 Canal {i+1}", url=link)]
        for i, link in enumerate(get_required_channel_links())
    ]
    join_buttons.append([InlineKeyboardButton("✅ J'ai rejoint", callback_data="joined_ok")])

    txt = (
        "👋 <b>Bienvenue !</b>\n\n"
        "🔒 Pour accéder au menu, rejoins d’abord nos canaux, puis appuie sur "
        "« <b>✅ J'ai rejoint</b> ».\n\n"
        "Merci pour ton soutien 💙"
    )
    msg = getattr(update_or_query, "message", None)
    if msg:
        await msg.reply_text(txt, reply_markup=InlineKeyboardMarkup(join_buttons), parse_mode=ParseMode.HTML)
    else:
        await update_or_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(join_buttons), parse_mode=ParseMode.HTML)

async def ensure_access_or_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    ensure_user(user.id)
    if not channels_required_configured():
        return True
    if await check_all_memberships(context, user.id):
        return True
    await prompt_join_channels(update, context)
    return False

# =========================
# ------- RÉFÉRENT -------
# =========================

def parse_start_payload(text: str) -> Optional[int]:
    m = re.search(r"ref_(\d+)", text or "")
    return int(m.group(1)) if m else None

async def maybe_award_ref_bonus(user, context):
    """
    Crédite +50 likes au parrain si c'est la première fois que ce filleul débloque l'accès.
    Protection renforcée : empêche un même filleul de donner le bonus plusieurs fois,
    même après un redémarrage du bot.
    """
    u = DB["users"][str(user.id)]
    ref = u.get("referrer")
    if not ref:
        return

    # Initialisation de la mémoire globale si absente
    if "all_ref_links" not in DB:
        DB["all_ref_links"] = []

    ref_user = DB["users"].get(ref)
    if not ref_user:
        ensure_user(int(ref))
        ref_user = DB["users"][ref]

    # Vérification anti-double bonus
    if str(user.id) in ref_user.get("ref_given", []):
        return
    if f"{ref}_{user.id}" in DB["all_ref_links"]:
        return

    # Attribution du bonus
    ref_user["balance"] = int(ref_user.get("balance", 0)) + 50
    ref_user.setdefault("ref_given", []).append(str(user.id))
    DB["all_ref_links"].append(f"{ref}_{user.id}")
    save_db(DB)

    # Notification au parrain
    try:
        await context.bot.send_message(
            int(ref),
            f"🎁 <b>Bonus parrainage</b> : +50 Likes (filleul : {html.escape(user.full_name)})",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass
# =========================
# ------- ÉTATS -----------
# =========================

# Achat
CHOIX_PRODUIT, CHOIX_PLATEFORME, SAISIE_QTE, SAISIE_LIEN, CHOIX_PAIEMENT, ENVOI_TRANSACTION = range(6)
# Retrait
RETRAIT_PLATEFORME, RETRAIT_QTE, RETRAIT_LIEN, RETRAIT_CONFIRM = range(10, 14)
# Admin
ADMIN_MENU, AP_PRICE_PLAT, AP_PRICE_PRODUCT, AP_PRICE_VALUE, AP_PAYMENT_METHOD, AP_PAYMENT_VALUE, AP_MESSAGE_KEY, AP_MESSAGE_VALUE, AP_CREDIT_USER_ID, AP_CREDIT_AMOUNT, AP_REQCHAN_ADD_ID, AP_REQCHAN_ADD_LINK, AP_BROADCAST = range(100, 113)

# =========================
# ------- COMMANDES -------
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)

    # /start ref_<id>
    payload = update.message.text if update.message else ""
    ref_id = parse_start_payload(payload)
    if ref_id and ref_id != user.id:
        me = DB["users"][str(user.id)]
        if me["referrer"] is None:
            me["referrer"] = str(ref_id)
            save_db(DB)

    # Si canaux requis → vérification
    if channels_required_configured():
        if await check_all_memberships(context, user.id):
            await maybe_award_ref_bonus(user, context)
            await update.message.reply_text(
                "✅ <b>Accès débloqué.</b>\n\n" + get_messages().get("welcome", DEFAULT_MESSAGES["welcome"]),
                reply_markup=main_menu(user.id),
                parse_mode=ParseMode.HTML
            )
        else:
            await prompt_join_channels(update, context)
        return

    # Pas de canaux requis → accueil direct + bonus éventuel
    await maybe_award_ref_bonus(user, context)
    await update.message.reply_text(
        get_messages().get("welcome", DEFAULT_MESSAGES["welcome"]),
        reply_markup=main_menu(user.id),
        parse_mode=ParseMode.HTML
    )

async def after_joined_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    ensure_user(user.id)

    if not channels_required_configured():
        await query.edit_message_text("✅ Accès déjà disponible.", parse_mode=ParseMode.HTML)
        await context.bot.send_message(chat_id=user.id, text="🏠 Menu principal", reply_markup=main_menu(user.id))
        return

    if not await check_all_memberships(context, user.id):
        await query.edit_message_text("❌ Abonnement non détecté. Rejoins tous les canaux puis réessaie.", parse_mode=ParseMode.HTML)
        return

    await maybe_award_ref_bonus(user, context)
    await query.edit_message_text("✅ Merci ! <b>Accès débloqué.</b>", parse_mode=ParseMode.HTML)
    await context.bot.send_message(chat_id=user.id, text="🏠 Menu principal", reply_markup=main_menu(user.id))

# =========================
# ----- MENU / ROUTES -----
# =========================

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)
    text = (update.message.text or "").strip()

    if not await ensure_access_or_prompt(update, context):
        return

    if text == "📜 Historique":
        await show_history(update, context)

    elif text == "🔗 Lien de parrainage":
        await parrainage(update, context)

    elif text == "👥 Mes filleuls":
        await mes_filleuls(update, context)

    elif text == "💰 Solde Like":
        bal = DB["users"][str(user.id)]["balance"]
        await update.message.reply_text(
            f"💳 <b>Solde Likes</b> : <b>{bal}</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(user.id)
        )

    elif text == "🆘 Support":
        await update.message.reply_text(
            get_messages().get("support", DEFAULT_MESSAGES["support"]),
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu(user.id)
        )

    elif text == "👑 Admin":
        if user.id not in ADMINS:
            await update.message.reply_text(
                "⛔ Accès réservé à l’admin.",
                reply_markup=main_menu(user.id)
            )
            return
        await admin_entry(update, context)
        return

    elif text == "🛒 Achat" or text == "💸 Retrait Like":
        return

    else:
        await update.message.reply_text(
            "❓ Choix inconnu. Utilise le menu ci-dessous.",
            reply_markup=main_menu(user.id)
        )
# =========================
# ---- PARRAINAGE ----------
# =========================

async def parrainage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)

    me = await context.bot.get_me()
    lien_invite = f"https://t.me/{me.username}?start=ref_{user.id}"

    texte = get_messages().get("parrainage", DEFAULT_MESSAGES["parrainage"]).replace(
        "{INVITE_LINK}", f"<code>{html.escape(lien_invite)}</code>"
    )

    await update.message.reply_text(texte, parse_mode=ParseMode.HTML, reply_markup=main_menu(user.id))

async def mes_filleuls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)
    # On compte combien de users ont referrer == user.id
    total = sum(1 for u in DB["users"].values() if u.get("referrer") == str(user.id))
    await update.message.reply_text(f"👥 <b>Filleuls total</b> : <b>{total}</b>", parse_mode=ParseMode.HTML)

# =========================
# -------- HISTORIQUE -----
# =========================

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    u = DB["users"][user_id]
    orders = u.get("orders", [])
    retraits = u.get("retraits", [])

    if not orders and not retraits:
        await update.message.reply_text("📭 <b>Aucun historique</b> pour le moment.", parse_mode=ParseMode.HTML, reply_markup=main_menu(int(user_id)))
        return

    lines = []
    if orders:
        lines.append("🛒 <b>Commandes récentes</b> :")
        for o in orders[-10:]:
            lines.append(
                f"• <b>{o['id']}</b> • {o['produit']} - {o['plateforme']} • {o['qte']} • "
                f"{o['prix']} F CFA • {o['status']}"
            )
    if retraits:
        lines.append("\n💸 <b>Retraits récents</b> :")
        for r in retraits[-10:]:
            lines.append(
                f"• <b>{r['id']}</b> • {r['plateforme']} • {r['montant']} Likes • {r['status']}"
            )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=main_menu(int(user_id)))

# =========================
# --------- ACHAT ---------
# =========================

async def achat_entry_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await ensure_access_or_prompt(update, context):
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("📈 Vues", callback_data="Vues")],
        [InlineKeyboardButton("❤️ Likes", callback_data="Likes")],
        [InlineKeyboardButton("👥 Abonnés/Followers", callback_data="Abonnés")],
    ]
    await update.message.reply_text(
        "🛒 <b>Nouvelle commande</b>\n\nQuel type de service souhaites-tu lancer ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML,
    )
    return CHOIX_PRODUIT


async def choix_produit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)

    if channels_required_configured() and not await check_all_memberships(context, user_id):
        await prompt_join_channels(query, context)
        return ConversationHandler.END

    produit = query.data
    context.user_data["produit"] = produit

    plateformes = list(get_prices().keys())
    buttons = [[InlineKeyboardButton(p, callback_data=p)] for p in plateformes]
    buttons.append([InlineKeyboardButton("🔙 Retour menu", callback_data="menu")])

    await query.edit_message_text(
        f"✅ Produit choisi : <b>{html.escape(produit)}</b>\n\n"
        "Choisis une <b>plateforme</b> :",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )
    return CHOIX_PLATEFORME


async def choix_plateforme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu":
        await query.edit_message_text("🏠 Retour au menu principal.", parse_mode=ParseMode.HTML)
        await context.bot.send_message(query.from_user.id, "Menu :", reply_markup=main_menu(query.from_user.id))
        return ConversationHandler.END

    plateforme = query.data
    context.user_data["plateforme"] = plateforme
    produit = context.user_data["produit"]

    cle_produit = produit if not (produit == "Abonnés" and plateforme in ["Telegram", "WhatsApp"]) else "Followers"
    prices = get_prices()

    if plateforme not in prices or cle_produit not in prices[plateforme]:
        await query.edit_message_text("❌ Option non disponible pour cette plateforme.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    await query.edit_message_text(
        f"🌐 Plateforme : <b>{html.escape(plateforme)}</b>\n"
        f"📱 Produit : <b>{html.escape(produit)}</b>\n\n"
        "➡️ Saisis la <b>quantité</b> souhaitée (minimum <b>1000</b>) :",
        parse_mode=ParseMode.HTML,
    )
    return SAISIE_QTE


async def saisie_quantite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texte = (update.message.text or "").strip()
    if not texte.isdigit():
        await update.message.reply_text("⚠️ Saisis un <b>nombre entier</b> valide.", parse_mode=ParseMode.HTML)
        return SAISIE_QTE

    qte = int(texte)
    if qte < 1000:
        await update.message.reply_text("⚠️ Le minimum est <b>1000</b>. Veuillez réessayer 🙏✨.", parse_mode=ParseMode.HTML)
        return SAISIE_QTE

    context.user_data["quantite"] = qte
    produit = context.user_data["produit"]
    plateforme = context.user_data["plateforme"]
    cle_produit = produit if not (produit == "Abonnés" and plateforme in ["Telegram", "WhatsApp"]) else "Followers"
    prices = get_prices()
    prix_1k = prices[plateforme][cle_produit]
    prix_total = int((qte / 1000) * prix_1k)
    context.user_data["prix_total"] = prix_total

    await update.message.reply_text(
        f"🧾 <b>Récapitulatif</b>\n"
        f"• Produit : <b>{html.escape(produit)}</b>\n"
        f"• Plateforme : <b>{html.escape(plateforme)}</b>\n"
        f"• Quantité : <b>{qte}</b>\n"
        f"• Prix total : <b>{prix_total} F CFA</b>\n\n"
        "➡️ Envoie maintenant le <b>lien</b> du compte / post / vidéo :",
        parse_mode=ParseMode.HTML,
    )
    return SAISIE_LIEN


async def saisie_lien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lien = (update.message.text or "").strip()
    context.user_data["lien"] = lien
    safe_lien = html.escape(lien)

    pays = list(get_payments().keys())
    buttons = [[
        InlineKeyboardButton(
            f"{'💛' if m=='MTN' else '💙' if m=='MOOV' else '🌊' if m=='WAVE' else '🪙' if m=='CRYPTO' else ''} {m}",
            callback_data=m
        )
    ] for m in pays]

    buttons.append([InlineKeyboardButton("🔙 Retour menu", callback_data="menu")])

    await update.message.reply_text(
        f"🔗 Lien reçu ✅\n<code>{safe_lien}</code>\n\n"
        "👉 Choisis maintenant ta <b>méthode de paiement</b> :",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode=ParseMode.HTML,
    )

    return CHOIX_PAIEMENT


async def choix_paiement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "menu":
        await query.edit_message_text("🏠 Retour au menu principal.", parse_mode=ParseMode.HTML)
        await context.bot.send_message(query.from_user.id, "Menu :", reply_markup=main_menu(query.from_user.id))
        return ConversationHandler.END

    methode = query.data
    context.user_data["paiement"] = methode
    coord = get_payments().get(methode, "N/A")

    await query.edit_message_text(
        f"✅ Méthode choisie : <b>{html.escape(methode)}</b>\n\n"
        f"➡️ Paye sur : <code>{html.escape(coord)}</code>\n"
        f"Puis envoie <b>l’ID de transaction</b> ici 👇",
        parse_mode=ParseMode.HTML,
    )

    return ENVOI_TRANSACTION


async def reception_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tx_id = (update.message.text or "").strip()
    tx_id_safe = html.escape(tx_id)
    user = update.message.from_user
    ensure_user(user.id)

    produit = context.user_data.get("produit", "N/A")
    plateforme = context.user_data.get("plateforme", "N/A")
    qte = context.user_data.get("quantite", 0)
    prix = context.user_data.get("prix_total", 0)
    lien_raw = context.user_data.get("lien", "N/A")
    lien = html.escape(lien_raw)
    paiement = context.user_data.get("paiement", "N/A")

    u = DB["users"][str(user.id)]
    code_cmd = f"CMD{user.id}-{len(u['orders'])+1}"

    context.user_data["pending_order"] = {
        "id": code_cmd,
        "produit": produit,
        "plateforme": plateforme,
        "qte": qte,
        "prix": prix,
        "lien": lien_raw,
        "paiement": paiement,
        "txid": tx_id,
    }

    recap = (
        "🧾 <b>Récapitulatif de ta commande</b>\n\n"
        f"📱 Produit : <b>{html.escape(produit)}</b>\n"
        f"🌐 Plateforme : <b>{html.escape(plateforme)}</b>\n"
        f"🔢 Quantité : <b>{qte}</b>\n"
        f"🔗 Lien : <code>{lien}</code>\n"
        f"💰 Prix : <b>{prix} F CFA</b>\n"
        f"💳 Paiement : <b>{html.escape(paiement)}</b>\n"
        f"🧾 Transaction ID : <code>{tx_id_safe}</code>\n\n"
        f"➡️ Confirme ta commande ou annule."
    )

    buttons = [
        [InlineKeyboardButton("✅ Confirmer", callback_data="cmd_user_confirm")],
        [InlineKeyboardButton("❌ Annuler", callback_data="cmd_user_cancel")],
    ]

    await update.message.reply_text(
        recap,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    return ENVOI_TRANSACTION


async def commande_confirmer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)

    pending = context.user_data.get("pending_order")
    if not pending:
        await query.edit_message_text("⚠️ Aucune commande en attente.")
        return ConversationHandler.END

    # Sauvegarde commande dans la DB
    u = DB["users"][str(user_id)]
    pending["status"] = "En attente admin"
    u["orders"].append(pending)
    save_db(DB)

    # Boutons ADMIN pour la validation commande
    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmer", callback_data=f"confirmer_cmd_{user_id}_{pending['id']}")],
        [InlineKeyboardButton("❌ Rejeter", callback_data=f"rejeter_cmd_{user_id}_{pending['id']}")],
    ])

    txt_admin = (
        "🆕 <b>Nouvelle commande</b>\n\n"
        f"🆔 ID : <b>{pending['id']}</b>\n"
        f"👤 User : <code>{user_id}</code>\n\n"
        f"📦 Produit   : {pending['produit']}\n"
        f"🌐 Plateforme: {pending['plateforme']}\n"
        f"🔢 Quantité  : {pending['qte']}\n"
        f"💰 Prix      : {pending['prix']} F CFA\n"
        f"🔗 Lien      : <code>{html.escape(pending['lien'])}</code>\n"
        f"💳 Paiement  : {pending['paiement']}\n"
        f"📄 TxID      : <code>{html.escape(pending['txid'])}</code>"
    )

    # Envoi au canal admin (ou aux ADMINS en fallback)
    try:
        await context.bot.send_message(ADMIN_CHANNEL_ID, txt_admin, parse_mode=ParseMode.HTML, reply_markup=admin_kb)
    except Exception:
        for a in ADMINS:
            try:
                await context.bot.send_message(a, txt_admin, parse_mode=ParseMode.HTML, reply_markup=admin_kb)
            except Exception:
                pass

    # Message utilisateur
    await query.edit_message_text("✅ Commande envoyée à l’admin pour validation.")
    return ConversationHandler.END


async def commande_annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_order", None)
    await query.edit_message_text("❌ Commande annulée.")
    return ConversationHandler.END

  #=========================
# --------- RETRAIT -------
# =========================

async def retrait_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)

    plats = ["Telegram", "Facebook", 'Tiktok']
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(p, callback_data=f"ret_pf_{p}")] for p in plats] +
        [[InlineKeyboardButton("⬅️ Menu", callback_data="ret_pf_menu")]]
    )
    await update.message.reply_text("💸 <b>Retrait Like</b>\n\nChoisis la plateforme :", parse_mode=ParseMode.HTML, reply_markup=kb)
    return RETRAIT_PLATEFORME

async def retrait_choix_plateforme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.replace("ret_pf_", "", 1)
    if data == "menu":
        await query.edit_message_text("🏠 Retour au menu.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END
    context.user_data["ret_plateforme"] = data
    await query.edit_message_text(f"🌐 Plateforme : <b>{html.escape(data)}</b>\n\nEnvoie la <b>quantité</b> de likes à retirer :", parse_mode=ParseMode.HTML)
    return RETRAIT_QTE

async def retrait_qte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().replace(" ", "")
    if not txt.isdigit():
        await update.message.reply_text("⚠️ Envoie un <b>entier</b> (ex: 150).", parse_mode=ParseMode.HTML)
        return RETRAIT_QTE
    qte = int(txt)
    if qte < MIN_RETRAIT or qte > MAX_RETRAIT:
        await update.message.reply_text(f"⚠️ La quantité doit être entre {MIN_RETRAIT} et {MAX_RETRAIT}.", parse_mode=ParseMode.HTML)
        return RETRAIT_QTE
    context.user_data["ret_qte"] = qte
    await update.message.reply_text("🔗 Envoie le <b>lien</b> (profil/publication) pour le retrait :", parse_mode=ParseMode.HTML)
    return RETRAIT_LIEN

async def retrait_lien(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)

    lien_raw = (update.message.text or "").strip()
    context.user_data["ret_lien"] = lien_raw

    qte = int(context.user_data.get("ret_qte", 0))
    plateforme = context.user_data.get("ret_plateforme", "N/A")

    u = DB["users"][str(user.id)]
    solde_actuel = int(u["balance"])

    recap = (
        "🧾 <b>Récapitulatif Retrait Like</b>\n\n"
        f"🌐 Plateforme : <b>{html.escape(plateforme)}</b>\n"
        f"🔗 Lien : <code>{html.escape(lien_raw)}</code>\n"
        f"🔢 Quantité : <b>{qte}</b>\n"
        f"💰 Solde actuel : <b>{solde_actuel}</b>\n\n"
        f"➡️ <b>Si tu confirmes, on débite immédiatement</b> <b>{qte}</b> de ton solde "
        "et on envoie la demande à l’admin pour validation."
    )

    buttons = [
        [InlineKeyboardButton("✅ Oui, confirmer", callback_data="ret_cf_yes")],
        [InlineKeyboardButton("❌ Non, annuler", callback_data="ret_cf_no")],
    ]

    await update.message.reply_text(
        recap,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return RETRAIT_CONFIRM

async def retrait_confirm_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    ensure_user(user_id)
    choice = query.data

    if choice == "ret_cf_no":
        await query.edit_message_text("❌ Retrait annulé. Retour au menu.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    # Débit + envoi admin
    u = DB["users"][str(user_id)]
    qte = int(context.user_data.get("ret_qte", 0))
    lien = context.user_data.get("ret_lien", "")
    pf = context.user_data.get("ret_plateforme", "")

    if int(u["balance"]) < qte:
        await query.edit_message_text("❌ Solde insuffisant pour ce retrait.", parse_mode=ParseMode.HTML)
        return ConversationHandler.END

    u["balance"] = int(u["balance"]) - qte
    ret_id = f"RET{int(datetime.now().timestamp())}"
    u["retraits"].append({
        "id": ret_id,
        "plateforme": pf,
        "montant": qte,
        "lien": lien,
        "status": "En attente admin",
    })
    save_db(DB)

    admin_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmer", callback_data=f"confirmer_ret_{user_id}_{ret_id}")],
        [InlineKeyboardButton("❌ Rejeter", callback_data=f"rejeter_ret_{user_id}_{ret_id}")],
    ])
    txt_admin = (
        f"💸 <b>Nouveau retrait</b>\n"
        f"User: <code>{user_id}</code>\n"
        f"ID: <b>{ret_id}</b>\n"
        f"Plateforme: {pf} • Montant: {qte}\n"
        f"Lien: <code>{html.escape(lien)}</code>"
    )
    try:
        await context.bot.send_message(ADMIN_CHANNEL_ID, txt_admin, parse_mode=ParseMode.HTML, reply_markup=admin_kb)
    except Exception:
        for a in ADMINS:
            try:
                await context.bot.send_message(a, txt_admin, parse_mode=ParseMode.HTML, reply_markup=admin_kb)
            except Exception:
                pass

    await query.edit_message_text("✅ Demande envoyée à l’admin. Tu seras notifié(e) après validation.", parse_mode=ParseMode.HTML)
    return ConversationHandler.END

# =========================
# ---- VALIDATION ADMIN ---
# =========================

# ===== Handler action Admin (Confirmer / Rejeter) =====
async def handle_admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    if admin_id not in ADMINS:
        await query.answer("⛔ Non autorisé.", show_alert=True)
        return

    data = (query.data or "")
    # confirmer_cmd_<uid>_<id> / rejeter_cmd_<uid>_<id>
    # confirmer_ret_<uid>_<id> / rejeter_ret_<uid>_<id>
    m = re.match(r"^(confirmer|rejeter)_(cmd|ret)_(\d+)_(.+)$", data)
    if not m:
        await query.edit_message_text("⚠️ Données incomplètes.", parse_mode=ParseMode.HTML)
        return

    action, kind, user_id_s, ident = m.groups()
    user_id = int(user_id_s)
    ensure_user(user_id)
    u = DB["users"][str(user_id)]

    if kind == "cmd":
        # Gestion commande
        target = None
        for o in u["orders"]:
            if o["id"] == ident:
                target = o
                break
        if not target:
            await query.edit_message_text("⚠️ Commande introuvable.", parse_mode=ParseMode.HTML)
            return
        if action == "confirmer":
            target["status"] = "Confirmée"
            txt = f"✅ Ta commande <b>{ident}</b> a été <b>validée</b>."

            # ➕ Envoi aussi dans le canal de suivi
            try:
                suivi_txt = (
                    f"📦 <b>Commande validée</b>\n\n"
                    f"🆔 ID : <b>{target['id']}</b>\n"
                    f"👤 User : <code>{user_id}</code>\n"
                    f"📱 Produit : {target.get('produit','—')}\n"
                    f"🌐 Plateforme : {target.get('plateforme','—')}\n"
                    f"🔢 Quantité : {target.get('qte','—')}\n"
                    f"💰 Prix : {target.get('prix','—')} F CFA\n"
                    f"🔗 Lien : <code>{html.escape(str(target.get('lien','')))}</code>\n"
                    f"💳 Paiement : {target.get('paiement','—')}\n"
                    f"📄 TxID : <code>{html.escape(str(target.get('txid','')))}</code>"
                )
                await context.bot.send_message(SUIVI_CHANNEL_ID, suivi_txt, parse_mode=ParseMode.HTML)
            except Exception:
                pass
        else:
            target["status"] = "Rejetée"
            txt = f"❌ Ta commande <b>{ident}</b> a été <b>rejetée</b>."
        save_db(DB)
        await query.edit_message_text(
            f"👌 Action sur commande <b>{ident}</b> : <b>{'validée' if action=='confirmer' else 'rejetée'}</b>.",
            parse_mode=ParseMode.HTML
        )
        try:
            await context.bot.send_message(user_id, txt, parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return

    # Gestion retrait
    target = None
    for r in u["retraits"]:
        if r["id"] == ident:
            target = r
            break
    if not target:
        await query.edit_message_text("⚠️ Retrait introuvable.", parse_mode=ParseMode.HTML)
        return
    if action == "confirmer":
        target["status"] = "Confirmé"
        txt = f"✅ Ton retrait <b>{ident}</b> a été <b>confirmé</b>."

        # ➕ Envoi aussi dans le canal de suivi
        try:
            suivi_txt = (
                f"💸 <b>Retrait validé</b>\n\n"
                f"🆔 ID : <b>{target['id']}</b>\n"
                f"👤 User : <code>{user_id}</code>\n"
                f"🌐 Plateforme : {target.get('plateforme','—')}\n"
                f"🔗 Lien : <code>{html.escape(str(target.get('lien','')))}</code>\n"
                f"🔢 Montant : <b>{target.get('montant','—')}</b> Likes"
            )
            await context.bot.send_message(SUIVI_CHANNEL_ID, suivi_txt, parse_mode=ParseMode.HTML)
        except Exception:
            pass

    else:
        target["status"] = "Rejeté"
        # Remboursement auto
        montant = int(target.get("montant", 0))
        u["balance"] = int(u["balance"]) + montant
        txt = f"❌ Ton retrait <b>{ident}</b> a été <b>rejeté</b>. 💰 <b>{montant}</b> Likes remboursés."
    save_db(DB)
    await query.edit_message_text(
        f"👌 Action sur retrait <b>{ident}</b> : <b>{'confirmé' if action=='confirmer' else 'rejeté'}</b>.",
        parse_mode=ParseMode.HTML
    )
    try:
        await context.bot.send_message(user_id, txt, parse_mode=ParseMode.HTML)
    except Exception:
        pass
  # =========================
# --------- ADMIN ---------
# =========================

async def admin_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMINS:
        await update.message.reply_text("⛔ Accès refusé.", reply_markup=main_menu(user.id))
        return ConversationHandler.END
    await update.message.reply_text("👑 <b>Panel Admin</b>", parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard())
    return ADMIN_MENU

async def admin_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text == "💵 Prix":
        plats = list(get_prices().keys())
        kb = ReplyKeyboardMarkup([plats] + [["⬅️ Retour"]], resize_keyboard=True)
        await update.message.reply_text("Choisis une <b>plateforme</b> :", parse_mode=ParseMode.HTML, reply_markup=kb)
        return AP_PRICE_PLAT

    if text == "🏦 Paiements":
        methods = list(get_payments().keys())
        kb = ReplyKeyboardMarkup([methods] + [["⬅️ Retour"]], resize_keyboard=True)
        await update.message.reply_text("Choisis une <b>méthode</b> :", parse_mode=ParseMode.HTML, reply_markup=kb)
        return AP_PAYMENT_METHOD

    if text == "📝 Messages":
        keys = list(get_messages().keys())
        kb = ReplyKeyboardMarkup([keys] + [["⬅️ Retour"]], resize_keyboard=True)
        await update.message.reply_text("Choisis la <b>clé</b> du message à modifier :", parse_mode=ParseMode.HTML, reply_markup=kb)
        return AP_MESSAGE_KEY

    if text == "➕ Crédit/Débit":
        await update.message.reply_text("Envoie l’<b>ID utilisateur</b> à créditer/débiter :", parse_mode=ParseMode.HTML)
        return AP_CREDIT_USER_ID

    if text == "📌 Canaux requis":
        chans = get_required_channels()
        links = get_required_channel_links()
        listing = "\n".join([f"• <code>{chans[i]}</code> → {links[i]}" for i in range(len(chans))]) or "Aucun"
        await update.message.reply_text(
            "📌 <b>Canaux requis</b>\n" + listing + "\n\n"
            "➡️ Envoie l’<b>ID de canal</b> (format : -100xxxxxxxxxx) pour en ajouter.",
            parse_mode=ParseMode.HTML
        )
        return AP_REQCHAN_ADD_ID

    if text == "📢 Diffuser":
        await update.message.reply_text("✍️ Envoie le <b>message</b> à diffuser à tous les utilisateurs (HTML autorisé).", parse_mode=ParseMode.HTML)
        return AP_BROADCAST

    if text == "⬅️ Retour":
        await update.message.reply_text("Retour.", reply_markup=main_menu(update.effective_user.id))
        return ConversationHandler.END

    if text == "❌ Fermer":
        await update.message.reply_text("Panel fermé.", reply_markup=main_menu(update.effective_user.id))
        return ConversationHandler.END

    await update.message.reply_text("Choisis une action.", reply_markup=admin_main_keyboard())
    return ADMIN_MENU

# -- PRICES flow --
async def admin_price_choose_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plat = (update.message.text or "").strip()
    if plat == "⬅️ Retour":
        await update.message.reply_text("Retour.", reply_markup=admin_main_keyboard())
        return ADMIN_MENU
    if plat not in get_prices():
        await update.message.reply_text("Plateforme inconnue. Recommence.", parse_mode=ParseMode.HTML)
        return AP_PRICE_PLAT
    context.user_data["ap_plat"] = plat
    prods = list(get_prices()[plat].keys())
    kb = ReplyKeyboardMarkup([prods] + [["⬅️ Retour"]], resize_keyboard=True)
    await update.message.reply_text(f"Plateforme <b>{html.escape(plat)}</b>.\nChoisis le <b>produit</b> :", parse_mode=ParseMode.HTML, reply_markup=kb)
    return AP_PRICE_PRODUCT

async def admin_price_choose_product(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prod = (update.message.text or "").strip()
    if prod == "⬅️ Retour":
        await update.message.reply_text("Retour.", reply_markup=admin_main_keyboard())
        return ADMIN_MENU
    plat = context.user_data.get("ap_plat")
    if not plat or prod not in get_prices().get(plat, {}):
        await update.message.reply_text("Produit inconnu. Recommence.", parse_mode=ParseMode.HTML)
        return AP_PRICE_PRODUCT
    context.user_data["ap_prod"] = prod
    current = get_prices()[plat][prod]
    await update.message.reply_text(
        f"✏️ Nouveau prix pour <b>{html.escape(plat)}</b> / <b>{html.escape(prod)}</b>\n"
        f"(Actuel: <b>{current}</b> F CFA / 1000)\n\n"
        "➡️ Envoie l’<b>entier</b> (ex: 800).",
        parse_mode=ParseMode.HTML
    )
    return AP_PRICE_VALUE

async def admin_price_set_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().replace(" ", "")
    if not txt.isdigit():
        await update.message.reply_text("Envoie un <b>entier</b>.", parse_mode=ParseMode.HTML)
        return AP_PRICE_VALUE
    new_val = int(txt)
    plat = context.user_data.get("ap_plat")
    prod = context.user_data.get("ap_prod")
    DB["prices"].setdefault(plat, {})
    DB["prices"][plat][prod] = new_val
    save_db(DB)
    await update.message.reply_text("✅ Prix mis à jour.", parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard())
    return ADMIN_MENU

# -- PAYMENTS flow --
async def admin_payment_choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    method = (update.message.text or "").strip()
    if method == "⬅️ Retour":
        await update.message.reply_text("Retour.", reply_markup=admin_main_keyboard())
        return ADMIN_MENU
    if method not in get_payments():
        await update.message.reply_text("Méthode inconnue. Recommence.", parse_mode=ParseMode.HTML)
        return AP_PAYMENT_METHOD
    context.user_data["ap_method"] = method
    current = get_payments().get(method, "N/A")
    await update.message.reply_text(
        f"✏️ <b>Mettre à jour</b> la méthode <b>{html.escape(method)}</b>\n"
        f"(Actuel : <code>{html.escape(current)}</code>)\n\n"
        "➡️ Envoie la <b>nouvelle valeur</b> (numéro/contact).",
        parse_mode=ParseMode.HTML
    )
    return AP_PAYMENT_VALUE

async def admin_payment_set_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = (update.message.text or "").strip()
    method = context.user_data.get("ap_method")
    if not method:
        await update.message.reply_text("⚠️ Contexte manquant, recommence.", parse_mode=ParseMode.HTML)
        return ADMIN_MENU
    DB["payments"][method] = value
    save_db(DB)
    await update.message.reply_text(
        f"✅ Méthode <b>{html.escape(method)}</b> mise à jour : <code>{html.escape(value)}</code>",
        parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard()
    )
    return ADMIN_MENU

# -- MESSAGES flow --
async def admin_message_choose_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = (update.message.text or "").strip()
    if key == "⬅️ Retour":
        await update.message.reply_text("Retour.", reply_markup=admin_main_keyboard())
        return ADMIN_MENU
    if key not in get_messages():
        await update.message.reply_text("Clé inconnue. Recommence.", parse_mode=ParseMode.HTML)
        return AP_MESSAGE_KEY
    context.user_data["ap_msg_key"] = key
    current = get_messages().get(key, "")
    await update.message.reply_text(
        f"✏️ <b>Modifier message</b> : <b>{html.escape(key)}</b>\n\n"
        "Envoie le <b>nouveau texte</b> (HTML autorisé)."
        f"\n\n<code>Actuel:</code>\n{current}",
        parse_mode=ParseMode.HTML
    )
    return AP_MESSAGE_VALUE

async def admin_message_set_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get("ap_msg_key")
    if not key:
        await update.message.reply_text("⚠️ Contexte manquant, recommence.", parse_mode=ParseMode.HTML)
        return ADMIN_MENU
    value = update.message.text or ""
    DB["messages"][key] = value
    save_db(DB)
    await update.message.reply_text(
        f"✅ Message <b>{html.escape(key)}</b> mis à jour.",
        parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard()
    )
    return ADMIN_MENU

# -- CREDIT flow --
async def admin_credit_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if not txt.isdigit():
        await update.message.reply_text("⚠️ Envoie un <b>ID utilisateur numérique</b>.", parse_mode=ParseMode.HTML)
        return AP_CREDIT_USER_ID
    uid = int(txt)
    context.user_data["ap_credit_uid"] = uid
    ensure_user(uid)
    bal = DB["users"][str(uid)]["balance"]
    await update.message.reply_text(
        f"👤 ID: <code>{uid}</code> (solde actuel: <b>{bal}</b>)\n\n"
        "➡️ Envoie le <b>montant</b> à appliquer.\n"
        "Exemples: <code>+150</code> pour créditer, <code>-50</code> pour débiter.",
        parse_mode=ParseMode.HTML
    )
    return AP_CREDIT_AMOUNT

async def admin_credit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().replace(" ", "")
    try:
        amount = int(txt)
    except ValueError:
        await update.message.reply_text("⚠️ Envoie un <b>entier</b> (ex: 100 ou -50).", parse_mode=ParseMode.HTML)
        return AP_CREDIT_AMOUNT

    uid = context.user_data.get("ap_credit_uid")
    if not uid:
        await update.message.reply_text("⚠️ Contexte manquant, recommence.", parse_mode=ParseMode.HTML)
        return ADMIN_MENU

    ensure_user(uid)
    DB["users"][str(uid)]["balance"] = int(DB["users"][str(uid)]["balance"]) + amount
    new_bal = DB["users"][str(uid)]["balance"]
    save_db(DB)
    try:
        sign = "crédité" if amount >= 0 else "débité"
        await update.message.reply_text(
            f"✅ Solde de <code>{uid}</code> {sign} de <b>{amount}</b> • Nouveau solde: <b>{new_bal}</b>",
            parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard()
        )
        try:
            await context.bot.send_message(uid, f"💳 Mise à jour de votre solde : {'+' if amount>=0 else ''}{amount} Likes • Nouveau solde: {new_bal}")
        except Exception:
            pass
    except Exception:
        await update.message.reply_text("⚠️ Erreur lors de la mise à jour.", parse_mode=ParseMode.HTML)
    return ADMIN_MENU

# -- REQUIRED CHANNELS flow --
async def admin_reqchan_add_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if txt == "⬅️ Retour":
        await update.message.reply_text("Retour.", reply_markup=admin_main_keyboard())
        return ADMIN_MENU
    if not txt.startswith("-100") or not txt[1:].isdigit():
        await update.message.reply_text("⚠️ Format d’ID invalide. Exemple: <code>-1001234567890</code>", parse_mode=ParseMode.HTML)
        return AP_REQCHAN_ADD_ID
    context.user_data["ap_reqchan_id"] = int(txt)
    await update.message.reply_text("🔗 Envoie maintenant le <b>lien</b> de ce canal :", parse_mode=ParseMode.HTML)
    return AP_REQCHAN_ADD_LINK

async def admin_reqchan_add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = (update.message.text or "").strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        await update.message.reply_text("⚠️ Lien invalide. Envoie un lien http(s).", parse_mode=ParseMode.HTML)
        return AP_REQCHAN_ADD_LINK
    cid = context.user_data.get("ap_reqchan_id")
    chans = get_required_channels()
    links = get_required_channel_links()
    chans.append(cid)
    links.append(link)
    DB["required_channels"] = chans
    DB["required_channel_links"] = links
    save_db(DB)
    await update.message.reply_text("✅ Canal requis ajouté.", parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard())
    return ADMIN_MENU

# -- BROADCAST flow --
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # point d’entrée géré déjà dans router -> AP_BROADCAST
    pass

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text or ""
    users = list(DB["users"].keys())
    sent = 0
    for uid in users:
        try:
            await update.get_bot().send_message(int(uid), msg, parse_mode=ParseMode.HTML)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await update.message.reply_text(f"📢 Diffusion envoyée à {sent} utilisateurs.", parse_mode=ParseMode.HTML, reply_markup=admin_main_keyboard())
    return ADMIN_MENU

# =========================
# ------- ANNULER ---------
# =========================

async def annuler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ <b>Opération annulée.</b>", parse_mode=ParseMode.HTML, reply_markup=main_menu(update.effective_user.id))
    return ConversationHandler.END

# =========================
# --------- MAIN ----------
# =========================

def build_application():
    app = ApplicationBuilder().token(TOKEN).build()
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Bouton "J'ai rejoint"
    app.add_handler(CallbackQueryHandler(after_joined_ok, pattern=r"^joined_ok$"))

# ---- Conversation ACHAT ----
    achat_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^🛒 Achat$"), achat_entry_from_menu),
            CommandHandler("achat", achat_entry_from_menu),
        ],
        states={
            CHOIX_PRODUIT: [CallbackQueryHandler(choix_produit)],
            CHOIX_PLATEFORME: [CallbackQueryHandler(choix_plateforme)],
            SAISIE_QTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_quantite)],
            SAISIE_LIEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, saisie_lien)],
            CHOIX_PAIEMENT: [CallbackQueryHandler(choix_paiement)],
            ENVOI_TRANSACTION: [
    MessageHandler(filters.TEXT & ~filters.COMMAND, reception_transaction),
    CallbackQueryHandler(commande_confirmer, pattern="^cmd_user_confirm$"),
    CallbackQueryHandler(commande_annuler, pattern="^cmd_user_cancel$"),
],
        },
        fallbacks=[CommandHandler("cancel", annuler)],
        allow_reentry=True,
    )
    app.add_handler(achat_conv)

# ---- Conversation RETRAIT ----
    retrait_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^💸 Retrait Like$"), retrait_entry),
            CommandHandler("retrait", retrait_entry),
        ],
        states={
            RETRAIT_PLATEFORME: [
                CallbackQueryHandler(retrait_choix_plateforme, pattern=r"^ret_pf_(Telegram|Facebook|Tiktok|menu)$")
            ],
            RETRAIT_QTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, retrait_qte)],
            RETRAIT_LIEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, retrait_lien)],
            RETRAIT_CONFIRM: [CallbackQueryHandler(retrait_confirm_choice, pattern=r"^ret_cf_(yes|no)$")],
        },
        fallbacks=[CommandHandler("cancel", annuler)],
        allow_reentry=True,
        per_chat=True,
        per_user=True,
    )
    app.add_handler(retrait_conv)


    # ---- Conversation ADMIN ----
    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^👑 Admin$"), admin_entry),
            CommandHandler("admin", admin_entry),
        ],
        states={
            ADMIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_menu_router)],
            AP_PRICE_PLAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price_choose_platform)],
            AP_PRICE_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price_choose_product)],
            AP_PRICE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_price_set_value)],
            AP_PAYMENT_METHOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_payment_choose_method)],
            AP_PAYMENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_payment_set_value)],
            AP_MESSAGE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_choose_key)],
            AP_MESSAGE_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_set_value)],
            AP_CREDIT_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_credit_user_id)],
            AP_CREDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_credit_amount)],
            AP_REQCHAN_ADD_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reqchan_add_id)],
            AP_REQCHAN_ADD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reqchan_add_link)],
            AP_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler("cancel", annuler)],
        allow_reentry=True,
    )
    app.add_handler(admin_conv)

    # ---- Admin actions (confirmation/rejet) ----
    app.add_handler(CallbackQueryHandler(handle_admin_action, pattern=r"^(confirmer|rejeter)_(cmd|ret)_"))

    # ---- /start ----
    app.add_handler(CommandHandler("start", start))

    # ---- /mesfilleuls ---- (compteur seulement)
    app.add_handler(CommandHandler("mesfilleuls", mes_filleuls))

    # ---- Menu principal ----
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    return app

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("🤖 Bot démarré…")
    app = build_application()
    app.run_polling()

if __name__ == "__main__":
    main()