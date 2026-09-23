import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
MUAPI_KEY = os.getenv("MUAPI_KEY")

# --- MongoDB Setup ---
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["higgsfield_studio"]
users_col = db["users"]
generations_col = db["generations"]

def get_or_create_user(user_id, username):
    user = users_col.find_one({"_id": user_id})
    if not user:
        user = {
            "_id": user_id,
            "username": username or "Unknown",
            "credits": 10,
            "created_at": datetime.utcnow()
        }
        users_col.insert_one(user)
    return user

# --- Start Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)

    msg = (
        f"🎬 **Open-Higgsfield AI Studio** me aapka swagat hai, {user.first_name}!\n\n"
        f"💳 Balance: **{db_user['credits']} Credits**\n\n"
        "**Features & Commands:**\n"
        "🎨 `/image <prompt>` — 20+ Models (Flux / SDXL)\n"
        "🎥 `/cinema` — Cinematic Camera Presets & Styles\n"
        "🎬 `/video <prompt>` — Text-to-Video Engine\n"
        "💳 `/credits` — Check balance"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- /credits ---
async def credits_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)
    await update.message.reply_text(f"💳 Available Credits: **{db_user['credits']}**")

# --- Image Studio (/image) ---
async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = get_or_create_user(user.id, user.username)

    if db_user["credits"] < 1:
        await update.message.reply_text("❌ Insufficient credits.")
        return

    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("❌ Prompt missing: `/image a cinematic close up of a cyborg`", parse_mode="Markdown")
        return

    status = await update.message.reply_text("🎨 Studio render in progress (Flux)...")

    gen_doc = {
        "user_id": user.id,
        "type": "image",
        "prompt": prompt,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    gen_id = generations_col.insert_one(gen_doc).inserted_id

    try:
        headers = {"Authorization": f"Bearer {MUAPI_KEY}", "Content-Type": "application/json"}
        payload = {"model": "flux-schnell", "prompt": prompt, "width": 1024, "height": 1024}

        res = requests.post("https://api.muapi.ai/v1/images/generations", json=payload, headers=headers, timeout=60)
        data = res.json()
        img_url = data.get("data", [{}])[0].get("url")

        if img_url:
            users_col.update_one({"_id": user.id}, {"$inc": {"credits": -1}})
            generations_col.update_one({"_id": gen_id}, {"$set": {"status": "completed", "result_url": img_url}})
            
            caption = f"✨ **Prompt:** {prompt}\n💳 Credits Left: {db_user['credits'] - 1}"
            await update.message.reply_photo(photo=img_url, caption=caption, parse_mode="Markdown")
            await status.delete()
        else:
            generations_col.update_one({"_id": gen_id}, {"$set": {"status": "failed"}})
            await status.edit_text("⚠️ Generation failed. No credits deducted.")

    except Exception as e:
        generations_col.update_one({"_id": gen_id}, {"$set": {"status": "failed", "error": str(e)}})
        await status.edit_text(f"❌ Error: {e}")

# --- Cinema Studio (/cinema - Higgsfield Lenses & Presets) ---
async def cinema_presets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("🎥 35mm Anamorphic", callback_data="preset_35mm"),
            InlineKeyboardButton("🔭 85mm Portrait", callback_data="preset_85mm")
        ],
        [
            InlineKeyboardButton("🚁 Drone Aerial View", callback_data="preset_drone"),
            InlineKeyboardButton("🎞️ Kodak 35mm Film", callback_data="preset_film")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎬 **Cinema Studio Presets:**\nEk camera lens style choose karein:", reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    presets = {
        "preset_35mm": "shot on 35mm anamorphic lens, shallow depth of field, cinematic lighting, f/1.8",
        "preset_85mm": "85mm prime lens, ultra-detailed portrait, soft bokeh background, 8k resolution",
        "preset_drone": "wide-angle drone aerial view, cinematic landscape photography, dramatic shadows",
        "preset_film": "vintage 35mm film photography, Kodak Portra 400 grain, natural color grading"
    }

    style = presets.get(query.data, "")
    await query.edit_message_text(
        f"✅ Preset selected!\n\nIsko copy karke apne prompt ke aage lagayein:\n\n`/image <aapka subject>, {style}`",
        parse_mode="Markdown"
    )

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("credits", credits_handler))
    app.add_handler(CommandHandler("image", generate_image))
    app.add_handler(CommandHandler("cinema", cinema_presets))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🚀 Open-Higgsfield-AI Telegram Studio Live!")
    app.run_polling()

if __name__ == "__main__":
    main()