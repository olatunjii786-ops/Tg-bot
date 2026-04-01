import telebot
import requests
import time
import threading
import os
from flask import Flask
from pymongo import MongoClient
from datetime import datetime, timedelta

# --- CONFIGURATION ---
# Your official Token and MongoDB URI
BOT_TOKEN = "8677076181:AAHmYoPVbZpR4u9T1paxpVlfXt1Lca5lx6A"
MONGO_URI = "mongodb+srv://Iniesta:iniesta123@cluster0.lkrpknm.mongodb.net/?retryWrites=true&w=majority"

ALLOWED_GROUP_ID = -1003025804858
VIP_USERS = {6379620342}

# --- DATABASE SETUP ---
try:
    client = MongoClient(MONGO_URI)
    db = client['bot_database']
    users_col = db['users']       # Stores daily like limits
    autos_col = db['autolikes']   # Stores scheduled tasks
    print("✅ Connected to MongoDB Atlas")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- WEB SERVER (To keep Render alive) ---
@app.route('/')
def index():
    return "Bot is running with MongoDB Persistence!"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# --- API LOGIC ---
def call_api(region, uid):
    url = f"http://druu-likes-15-day.vercel.app/like?uid={uid}&server_name={region}"
    try:
        response = requests.get(url, timeout=15)
        return response.json() if response.status_code == 200 else "API_ERROR"
    except:
        return "API_ERROR"

# --- CORE PROCESSING ---
def process_like(message, region, uid, is_auto=False, user_id_override=None):
    chat_id = message.chat.id if message else ALLOWED_GROUP_ID
    user_id = str(user_id_override) if user_id_override else str(message.from_user.id)

    # Limit Check (Non-VIPs)
    if not is_auto and int(user_id) not in VIP_USERS:
        user_data = users_col.find_one({"user_id": user_id})
        if user_data and user_data.get("last_like_date") == datetime.now().strftime("%Y-%m-%d"):
            bot.send_message(chat_id, "⚠️ Daily limit reached! Try again tomorrow.")
            return

    processing_msg = None
    if not is_auto and message:
        processing_msg = bot.reply_to(message, "⏳ Processing your request...")

    response = call_api(region, uid)

    if response == "API_ERROR":
        if not is_auto and processing_msg:
            bot.edit_message_text("🚨 API Error! Server maintenance. Try later.", chat_id, processing_msg.message_id)
        return

    if response.get("status") == 1:
        # Save limit data to DB
        if not is_auto:
            users_col.update_one(
                {"user_id": user_id},
                {"$set": {"last_like_date": datetime.now().strftime("%Y-%m-%d")}},
                upsert=True
            )
        
        res_text = (f"✅ **Like Added Successfully!** {'(Auto)' if is_auto else ''}\n"
                    f"🔹 **UID:** `{uid}`\n"
                    f"🔸 **Nickname:** `{response.get('PlayerNickname', 'N/A')}`\n"
                    f"🔸 **Likes After:** `{response.get('LikesafterCommand', 'N/A')}`\n\n"
                    "🗿 **SHARE US:** https://youtube.com/@teamxcutehack")
        
        if is_auto:
            bot.send_message(chat_id, res_text, parse_mode="Markdown")
        elif processing_msg:
            bot.edit_message_text(res_text, chat_id, processing_msg.message_id, parse_mode="Markdown")
    else:
        fail_text = f"💔 UID `{uid}` has reached max likes for today."
        if is_auto: bot.send_message(chat_id, fail_text)
        elif processing_msg: bot.edit_message_text(fail_text, chat_id, processing_msg.message_id)

# --- PERSISTENT AUTOLIKE ENGINE ---
def autolike_scheduler():
    """Background task: checks DB every hour for due likes"""
    while True:
        try:
            now = datetime.now()
            # Find tasks where days left > 0 and next_run is now or in the past
            tasks = autos_col.find({"days_left": {"$gt": 0}, "next_run": {"$lte": now}})
            
            for task in tasks:
                process_like(None, task['region'], task['uid'], is_auto=True, user_id_override=task['user_id'])
                
                # Schedule next run for exactly 24 hours from now
                new_next_run = now + timedelta(hours=24)
                autos_col.update_one(
                    {"_id": task["_id"]},
                    {"$inc": {"days_left": -1}, "$set": {"next_run": new_next_run}}
                )
        except Exception as e:
            print(f"Scheduler Error: {e}")
        
        time.sleep(3600) # Check every 1 hour

# --- COMMAND HANDLERS ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "🤖 **INIESTA البوت متصل بالإنترنت!**\n\nCommands:\n/like {reg} {uid}\n/autolike {reg} {uid} {days}", parse_mode="Markdown")

@bot.message_handler(commands=['like'])
def handle_like(message):
    if message.chat.id != ALLOWED_GROUP_ID and message.from_user.id not in VIP_USERS:
        bot.reply_to(message, "🚫 Access Denied. Use the official group.")
        return
    args = message.text.split()
    if len(args) == 3:
        threading.Thread(target=process_like, args=(message, args[1], args[2])).start()
    else:
        bot.reply_to(message, "❌ Use: `/like ind 12345`", parse_mode="Markdown")

@bot.message_handler(commands=['autolike'])
def handle_autolike(message):
    if message.from_user.id not in VIP_USERS:
        bot.reply_to(message, "🚫 This is a VIP-only feature.")
        return
    args = message.text.split()
    if len(args) == 4:
        region, uid, days = args[1], args[2], int(args[3])
        # Save to DB so it survives Render restarts
        autos_col.insert_one({
            "user_id": str(message.from_user.id),
            "region": region,
            "uid": uid,
            "days_left": days,
            "next_run": datetime.now()
        })
        bot.reply_to(message, f"📅 **Autolike Activated!**\nUID: `{uid}`\nDuration: {days} days.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Use: `/autolike ind 12345 30`", parse_mode="Markdown")

# --- EXECUTION ---
if __name__ == "__main__":
    # 1. Start Flask web server for Render health checks
    threading.Thread(target=run_flask).start()
    
    # 2. Start Persistent Scheduler for Autolikes
    threading.Thread(target=autolike_scheduler, daemon=True).start()
    
    # 3. Start Telegram Bot Polling
    print("Bot started successfully...")
    bot.polling(none_stop=True)
