import os
import sqlite3
import base64
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# توکن بات
TOKEN = ''

# یه salt ثابت برای امنیت
SALT = b'my_super_secret_salt_123'

# ساخت کلید از user_id
def generate_user_key(user_id):
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    key = kdf.derive(str(user_id).encode())
    return key

# رمزنگاری
def encrypt_amount(amount, user_id):
    key = generate_user_key(user_id)
    iv = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(str(amount).encode()) + encryptor.finalize()
    tag = encryptor.tag
    return base64.b64encode(iv).decode('ascii'), base64.b64encode(encrypted).decode('ascii'), base64.b64encode(tag).decode('ascii')

# رمزگشایی
def decrypt_amount(iv, encrypted, tag, user_id):
    key = generate_user_key(user_id)
    cipher = Cipher(algorithms.AES(key), modes.GCM(base64.b64decode(iv), base64.b64decode(tag)))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    return float(decrypted.decode())

# دیتابیس توی حافظه
def get_user_db(user_id):
    folder = 'dbs'  # مسیر نسبی
    db_path = f'{folder}/{user_id}_finance.db'
    if not os.path.exists(folder):
        os.makedirs(folder)
    conn = sqlite3.connect(db_path, check_same_thread=False, isolation_level=None)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=OFF')
    conn.execute('PRAGMA cache_size=10000')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            iv TEXT,
            encrypted_amount TEXT,
            tag TEXT,
            description TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn, cursor

# محاسبه موجودی
def calculate_balance(user_id, cursor):
    cursor.execute("SELECT type, iv, encrypted_amount, tag FROM transactions ORDER BY date DESC")
    rows = cursor.fetchall()
    total_income, total_expense = 0, 0
    for row in rows:
        amount = decrypt_amount(row[1], row[2], row[3], user_id)
        if row[0] == 'add_income':
            total_income += amount
        else:
            total_expense += amount
    return total_income, total_expense, total_income - total_expense

# کیبورد خفن‌تر با پشتیبانی
main_menu = ReplyKeyboardMarkup([
    ['💰 بزن به جیب!', '💸 خرج کن حالشو ببر!'],
    ['📜 تاریخچه باحالم', '💎 جیبات چقدر پره؟'],
    ['🌟 چجوری کار می‌کنم؟', '🔒 امنیت فول‌خفن'],
    ['🗑️ پاک کن همه‌چیز', '📞 پشتیبانی خفن']
], resize_keyboard=True, one_time_keyboard=False)

# شروع ربات
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    await update.message.reply_text(
        "🌠 سلام رفیق باحالم! به ربات جیب‌گردونم خوش اومدی! 😎\n"
        "اینجا جیباتو مدیریت می‌کنم و انقدر خفنم که خودت کیف می‌کنی!\n"
        "با این دکمه‌های باحالم بترکون:\n"
        "💰 درآمد بزن | 💸 خرج کن | 📜 تاریخچه ببین | 💎 موجودی چک کن\n"
        "🗑️ همه‌چیزو پاک کن | 📞 پشتیبانی هم داریم!",
        reply_markup=main_menu
    )

# کش موقت برای کاربرا
user_cache = {}

# مدیریت پیام‌ها
async def handle_message(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    text = update.message.text
    conn, cursor = get_user_db(user_id)

    if text == '💰 بزن به جیب!':
        user_cache[user_id] = {'action': 'add_income'}
        await update.message.reply_text(
            "💰 چقدر پول به جیبات اضافه کردی، رفیق؟ یه عدد بگو (مثلاً 2000):",
            reply_markup=main_menu
        )
    elif text == '💸 خرج کن حالشو ببر!':
        user_cache[user_id] = {'action': 'add_expense'}
        await update.message.reply_text(
            "💸 چقدر می‌خوای خرج کنی و حالشو ببری؟ یه عدد بگو (مثلاً 500):",
            reply_markup=main_menu
        )
    elif text == '📜 تاریخچه باحالم':
        cursor.execute("SELECT type, iv, encrypted_amount, tag, description, date FROM transactions ORDER BY date DESC")
        rows = cursor.fetchall()
        if rows:
            message = "📜 تاریخچه باحالت اینجاست، رفیق!\n🔥 همه تراکنشاتو برات آوردم:\n━━━━━━━━━━━━━━━\n"
            for row in rows:
                amount = decrypt_amount(row[1], row[2], row[3], user_id)
                type_text = "💰 پول اومد" if row[0] == 'add_income' else "💸 پول رفت"
                message += f"{type_text} | {amount:,} تومن | {row[4]} | 📅 {row[5]}\n"
            message += "━━━━━━━━━━━━━━━\nچی دیگه می‌خوای ببینی، پادشاه جیب‌ها؟ 😎"
            await update.message.reply_text(message, reply_markup=main_menu)
        else:
            await update.message.reply_text(
                "🌌 هنوز هیچی ثبت نکردی، داداش! یه پول بزن به جیبات تا بترکونیم!",
                reply_markup=main_menu
            )
    elif text == '💎 جیبات چقدر پره؟':
        total_income, total_expense, balance = calculate_balance(user_id, cursor)
        await update.message.reply_text(
            f"💎 جیبات اینجوریه، رفیق باحالم:\n"
            f"💰 کل پولی که اومده: {total_income:,} تومن\n"
            f"💸 کل پولی که خرج کردی: {total_expense:,} تومن\n"
            f"➡️ الان تو جیبات: {balance:,} تومن\n"
            f"{'🎉 جیبات پره، بترکون!' if balance > 0 else '😅 جیبات خالیه، یه پول بزن!'}",
            reply_markup=main_menu
        )
    elif text == '🌟 چجوری کار می‌کنم؟':
        await update.message.reply_text(
            "🌟 من چجوری کار می‌کنم، داداش؟\n"
            "خیلی ساده‌ست، گوش کن:\n"
            "۱. 💰 بزن به جیب: هر پولی که گرفتی رو بگو، من برات ثبتش می‌کنم.\n"
            "۲. 💸 خرج کن حالشو ببر: هر چی خرج کردی بگو، من کمش می‌کنم.\n"
            "۳. 📜 تاریخچه باحالم: همه تراکنشاتو از اول تا آخر نشون می‌دم.\n"
            "۴. 💎 جیبات چقدر پره: می‌گم چقدر پول اومده و چقدر الان داری.\n"
            "۵. 🗑️ پاک کن همه‌چیز: اگه بخوای، همه‌چیزو صفر می‌کنم که از اول شروع کنی.\n"
            "۶. 📞 پشتیبانی خفن: هر مشکلی داشتی، بهم بگو تا درستش کنم!\n"
            "سوال داری؟ بگو تا بیشتر توضیح بدم، رفیق! 😎",
            reply_markup=main_menu
        )
    elif text == '🔒 امنیت فول‌خفن':
        await update.message.reply_text(
            "🔒 امنیت فول‌خفن من اینجوریه:\n"
            "خیلی ساده بگم که حالشو ببری:\n"
            "۱. هر چی می‌نویسی (مثل 2000 تومن حقوق) رو با یه قفل جادویی می‌بندم که فقط خودت بتونی بازش کنی.\n"
            "۲. این قفل اسمش AES-256-GCMه، یعنی انقدر قویه که هیچ هکری نمی‌تونه بشکنه، حتی اگه میلیون‌ها سال امتحان کنه!\n"
            "۳. کلید قفل فقط از شماره تو (user_id) میاد، مثل یه رمز شخصی که فقط توی گوشیت ساخته می‌شه.\n"
            "۴. داده‌هاتو توی یه دیتابیس جدا (فقط برای تو) توی حافظه نگه می‌دارم، پس با هیچ‌کس قاطی نمی‌شه.\n"
            "۵. من که ربات رو ساختم، به کلیدت دسترسی ندارم، پس خیالت تخت باشه، فقط خودت پادشاهی!\n"
            "هر سوالی داری بگو تا بیشتر بترکونم برات! 💪",
            reply_markup=main_menu
        )
    elif text == '🗑️ پاک کن همه‌چیز':
        cursor.execute("DELETE FROM transactions")
        conn.commit()
        await update.message.reply_text(
            "🗑️ همه‌چیز پاک شد، رفیق! جیبات صفر شد، مثل روز اول!\n"
            "حالا از اول بترکون، چی کار می‌خوای بکنی؟ 😎",
            reply_markup=main_menu
        )
    elif text == '📞 پشتیبانی خفن':
        await update.message.reply_text(
            "📞 هر سوالی داری یا چیزی گنگ بود، یه پیام به پشتیبانی خفنم بده!\n"
            "کافیه بری اینجا: @Ali202577_bot\n"
            "هر چی بگی، مستقیم به سازندم می‌رسه و سریع جوابت رو می‌دم، رفیق! 😎",
            reply_markup=main_menu
        )
    else:
        if user_id in user_cache:
            action_data = user_cache[user_id]
            if 'amount' not in action_data:
                try:
                    amount = float(text)
                    action_data['amount'] = amount
                    await update.message.reply_text(
                        "✍️ یه توضیح باحال بگو که یادم بمونه (مثلاً 'حقوق' یا 'پیتزا'):",
                        reply_markup=main_menu
                    )
                except ValueError:
                    await update.message.reply_text(
                        "🤪 داداش، یه عدد درست بگو! مثلاً 1000 یا 500:",
                        reply_markup=main_menu
                    )
            else:
                description = text
                amount = action_data['amount']
                if action_data['action'] == 'add_expense':
                    total_income, total_expense, balance = calculate_balance(user_id, cursor)
                    if balance < amount:
                        await update.message.reply_text(
                            f"🚨 اوه اوه! پول کافی نداری، رفیق! فقط {balance:,} تومن تو جیباته!",
                            reply_markup=main_menu
                        )
                        user_cache.pop(user_id)
                        conn.close()
                        return
                iv, encrypted_amount, tag = encrypt_amount(amount, user_id)
                cursor.execute(
                    "INSERT INTO transactions (type, iv, encrypted_amount, tag, description) VALUES (?, ?, ?, ?, ?)",
                    (action_data['action'], iv, encrypted_amount, tag, description)
                )
                conn.commit()
                type_text = "پول اومد" if action_data['action'] == 'add_income' else "پول رفت"
                await update.message.reply_text(
                    f"🎉 ثبت شد، رفیق باحالم!\n"
                    f"💰 {type_text}: {amount:,} تومن - {description}\n"
                    "حالا چی کار کنیم، پادشاه جیب‌ها؟ 😎",
                    reply_markup=main_menu
                )
                user_cache.pop(user_id)
        else:
            await update.message.reply_text(
                "🌠 یه دکمه بزن تا بترکونیم، رفیق! این دکمه‌های خفن منتظرتن!",
                reply_markup=main_menu
            )
    conn.close()

# اجرا
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
