import telebot
import requests
import time
import threading

# --- CONFIGURATION ---
# ⚠️ REPLACE THIS TOKEN! If it's the one from your first message, it may be compromised.
BOT_TOKEN = "8677076181:AAHmYoPVbZpR4u9T1paxpVlfXt1Lca5lx6A" 
ALLOWED_GROUP_ID = -1003025804858
VIP_USERS = {6379620342}

bot = telebot.TeleBot(BOT_TOKEN)

# Trackers
like_request_tracker = {}

# --- HELPER FUNCTIONS ---

def call_api(region, uid):
    url = f"http://druu-likes-15-day.vercel.app/like?uid={uid}&server_name={region}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code != 200 or not response.text.strip():
            return "API_ERROR"
        return response.json()
    except:
        return "API_ERROR"

def process_like(message, region, uid, is_auto=False):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Check daily limit (Skip for VIPs or Auto-tasks)
    if not is_auto and user_id not in VIP_USERS and like_request_tracker.get(user_id, False):
        bot.reply_to(message, "⚠️ Daily limit exceeded! Try again tomorrow.")
        return

    # Manual feedback
    processing_msg = None
    if not is_auto:
        processing_msg = bot.reply_to(message, "⏳ Processing request... 🔄")

    response = call_api(region, uid)

    if response == "API_ERROR":
        err_msg = "🚨 API ERROR! System maintenance. Try again in 8 hours."
        if is_auto:
            bot.send_message(chat_id, f"❌ Autolike failed for `{uid}`: Server Error.")
        else:
            bot.edit_message_text(err_msg, chat_id, processing_msg.message_id)
        return

    if response.get("status") == 1:
        if not is_auto:
            like_request_tracker[user_id] = True
            
        success_text = (
            f"✅ **Like Added Successfully!** {'(Auto-Run)' if is_auto else ''}\n"
            f"🔹 **UID:** `{response.get('UID', 'N/A')}`\n"
            f"🔸 **Nickname:** `{response.get('PlayerNickname', 'N/A')}`\n"
            f"🔸 **Likes After:** `{response.get('LikesafterCommand', 'N/A')}`\n\n"
            "🗿 **SHARE US:** https://youtube.com/@teamxcutehack"
        )
        
        if is_auto:
            bot.send_message(chat_id, success_text, parse_mode="Markdown")
        else:
            bot.edit_message_text(success_text, chat_id, processing_msg.message_id, parse_mode="Markdown")
    else:
        fail_text = f"💔 UID `{uid}` has reached max likes for today."
        if is_auto:
            bot.send_message(chat_id, fail_text)
        else:
            bot.edit_message_text(fail_text, chat_id, processing_msg.message_id)

# --- BACKGROUND TASK FOR AUTOLIKE ---

def run_autolike_loop(message, region, uid, total_days):
    bot.send_message(message.chat.id, f"📅 **Autolike Activated!**\nUID: `{uid}`\nDuration: {total_days} days.", parse_mode="Markdown")
    
    for day in range(1, total_days + 1):
        process_like(message, region, uid, is_auto=True)
        # Wait 24 hours (86400 seconds)
        # We check every hour so the thread doesn't just hang totally
        for _ in range(24):
            time.sleep(3600) 
            
    bot.send_message(message.chat.id, f"🏁 Autolike schedule finished for `{uid}`.")

# --- COMMAND HANDLERS ---

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "🤖 **Bot is Online!**\n\nCommands:\n/like {reg} {uid}\n/autolike {reg} {uid} {days}", parse_mode="Markdown")

@bot.message_handler(commands=['like'])
def handle_like_cmd(message):
    # Allow if in the correct group OR if the sender is a VIP (for private testing)
    if message.chat.id != ALLOWED_GROUP_ID and message.from_user.id not in VIP_USERS:
        bot.reply_to(message, "🚫 Access Denied. Use the official group.")
        return

    args = message.text.split()
    if len(args) != 3:
        bot.reply_to(message, "❌ Use: `/like ind 12345`", parse_mode="Markdown")
        return

    threading.Thread(target=process_like, args=(message, args[1], args[2])).start()

@bot.message_handler(commands=['autolike'])
def handle_autolike_cmd(message):
    if message.from_user.id not in VIP_USERS:
        bot.reply_to(message, "🚫 This is a VIP-only feature.")
        return

    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(message, "❌ Use: `/autolike ind 12345 30`", parse_mode="Markdown")
        return

    region, uid, days = args[1], args[2], args[3]
    if not days.isdigit():
        bot.reply_to(message, "❌ Days must be a number!")
        return

    # Start the 24-hour cycle background thread
    threading.Thread(target=run_autolike_loop, args=(message, region, uid, int(days)), daemon=True).start()

# --- RUN BOT ---
print("Bot started successfully...")
bot.polling(none_stop=True)

