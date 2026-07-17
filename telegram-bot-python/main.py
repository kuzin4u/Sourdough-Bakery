"""
Telegram-бот пекарни на закваске (Python) — полная версия:
общий API корзины, статусы заказов, стоп-лист, предзаказ на день выпечки,
подписки, промокоды/лояльность, онлайн-оплата (ЮKassa, опционально),
запрос отзыва, админ-команды.
"""

import os
import re
import json
import random
import string
import secrets
import threading
import asyncio
import time
import base64
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
SHEETS_WEBHOOK_URL = os.getenv("SHEETS_WEBHOOK_URL")
PORT = int(os.getenv("PORT", "3000"))
# --- Онлайн-оплата: выбор провайдера ---
# PAYMENT_PROVIDER переключает, какой обработчик платежей использует кнопка "Картой
# онлайн" — "yookassa" (по умолчанию) или "yoomoney". Оба блока переменных ниже можно
# держать заполненными одновременно — используется только тот, что указан в PAYMENT_PROVIDER,
# переключение между уже настроенными провайдерами не требует правки кода.
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "yookassa").strip().lower()

YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")

# ЮMoney (бывш. Яндекс.Деньги) — для физлиц: платежи принимаются на номер кошелька,
# без отдельного shop_id. YOOMONEY_NOTIFICATION_SECRET — секрет для проверки подписи
# HTTP-уведомлений об оплате (задаётся один раз в настройках кошелька, см. README).
YOOMONEY_WALLET = os.getenv("YOOMONEY_WALLET")
YOOMONEY_NOTIFICATION_SECRET = os.getenv("YOOMONEY_NOTIFICATION_SECRET")

RETURN_URL = os.getenv("RETURN_URL") or f"https://t.me/{os.getenv('BOT_USERNAME', '')}"
REVIEW_DELAY_HOURS = float(os.getenv("REVIEW_DELAY_HOURS", "4"))

# --- Режим связи с Telegram: webhook (рекомендуется на Render) или polling (fallback) ---
# USE_WEBHOOK=true включает webhook явно. Если переменная не задана, но Render сам
# прокинул RENDER_EXTERNAL_URL — тоже считаем, что webhook доступен и включаем его.
# WEBHOOK_SECRET защищает /telegram-webhook от подделки запросов; если не задан,
# генерируется случайно при каждом старте (тогда секрет не переживает рестарт —
# не проблема, т.к. setWebhook с новым секретом вызывается при каждом старте заново).
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "true" if RENDER_EXTERNAL_URL else "false").lower() == "true"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or secrets.token_urlsafe(32)
BAKE_WEEKDAYS = [int(x) for x in os.getenv("BAKE_WEEKDAYS", "2,4,6").split(",")]

# ================= КАТАЛОГ =================
PRODUCTS = [
    {"id": "wheat", "name": "Пшеничный на закваске", "weight": 740, "price": 400,
     "desc": "Классика: мука, вода, закваска, соль. Лёгкая кислинка."},
    {"id": "rye", "name": "Ржано-пшеничный на закваске", "weight": 800, "price": 450,
     "desc": "Тёмный, плотный мякиш, насыщенный вкус."},
    {"id": "wholegrain", "name": "Цельнозерновой на закваске", "weight": 700, "price": 480,
     "desc": "Больше клетчатки, ореховый привкус."},
    {"id": "seeds", "name": "С семечками и орехами", "weight": 750, "price": 520,
     "desc": "Подсолнечник, тыквенные семечки, грецкий орех."},
]
DISTRICTS = [
    {"id": "pickup", "name": "Самовывоз (бесплатно)", "fee": 0},
    {"id": "center", "name": "Центральный район (+150 ₽)", "fee": 150},
    {"id": "north", "name": "Северный район (+200 ₽)", "fee": 200},
    {"id": "south", "name": "Южный район (+200 ₽)", "fee": 200},
    {"id": "east", "name": "Восточный район (+250 ₽)", "fee": 250},
]
WEEKDAY_NAMES = ["Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
ORDER_STATUSES = ["Принят", "Готовится", "Готов / в пути", "Доставлен", "Отменён"]

# ================= БАЗА ЗНАНИЙ FAQ (сведена из двух источников, см. примечание) =================
# Сведена из двух исходных FAQ-документов пользователя. Спорные/неподтверждённые пункты
# (точные медицинские заявления, бизнес-политики вроде цены закваски или возврата)
# исключены или смягчены — см. сопроводительный markdown-файл с полным разбором.
FAQ_KNOWLEDGE = """
СОСТАВ И ТЕХНОЛОГИЯ:
- Закваска (масса матере/massa madre) — это культура диких дрожжей и молочнокислых бактерий на муке и воде, которую выращивают и подкармливают неделями.
- В отличие от обычного хлеба, тут нет промышленных дрожжей — тесто поднимается только закваской.
- Ферментация занимает 12-24 часа, отсюда более выраженный вкус, плотный мякиш и долгий срок свежести.
- Состав предельно простой: мука, вода, закваска, соль. Без сахара, консервантов, разрыхлителей.
- Кисловатый привкус — нормальная и ожидаемая черта такого хлеба, от молочной и уксусной кислот при ферментации.

ПОЛЬЗА И ОСОБЕННОСТИ (умеренные формулировки, без медицинских гарантий):
- Длительная ферментация частично расщепляет фитиновую кислоту, поэтому минералы (железо, магний, цинк) усваиваются из такого хлеба лучше, чем из обычного дрожжевого — это поддерживается научными данными о фитатах.
- Из-за той же ферментации гликемический отклик у такого хлеба обычно мягче, чем у быстрого дрожжевого — но это не медицинская рекомендация и не подходит как замена консультации с врачом при диабете.
- Хлеб НЕ безопасен для людей с целиакией — глютен ферментация не убирает полностью, только частично расщепляет, что может незначительно облегчить переваривание у людей с обычной чувствительностью к глютену (не с диагностированной целиакией).
- Не стоит заявлять, что хлеб содержит "живые пробиотики" — после выпечки при высокой температуре культуры закваски не выживают, как и в любом печёном хлебе. Корректно говорить о пользе самого процесса ферментации, а не о пробiotическом эффекте готового продукта.

ХРАНЕНИЕ:
- При комнатной температуре, в бумаге или тканевом мешке (не в полиэтилене!) — 4-5 дней.
- В холодильнике, в бумаге — до 7-10 дней, можно дольше, вкус только насыщеннее.
- В морозилке — нарезать ломтиками, плотно завернуть, до 3 месяцев. Размораживать при комнатной температуре или слегка подогреть в тостере/духовке.
- Освежить подсохший хлеб: сбрызнуть водой, в духовку на 180°C на 5-7 минут.

ВКУС, ТЕКСТУРА, ИСПОЛЬЗОВАНИЕ:
- Мякиш плотный, влажный, с неравномерной пористостью — это нормально и характерно именно для заквасочного хлеба (в отличие от воздушного дрожжевого).
- Корочка хрустящая, плотная.
- Хорошо держит форму для бутербродов и тостов, не размокает и не крошится при правильной нарезке.
- Резать лучше остывшим, острым ножом с зубчатым лезвием, лёгкими пилящими движениями.
- Подсохший хлеб отлично идёт на гренки, сухарики и панировку — подсушить кубиками в духовке при 150°C.

ДЛЯ КОГО ПОДХОДИТ:
- Подходит как обычный пшеничный хлеб взрослым и детям без специфических противопоказаний.
- Возраст введения любого хлеба в детский прикорм — вопрос к педиатру конкретного ребёнка, единых универсальных рекомендаций по точному возрасту нет, и бот не должен называть конкретный возраст от своего имени.
- Не подходит при диагностированной целиакии.
- В умеренных порциях вписывается в рацион при правильном питании — заквасочный хлеб часто рекомендуют как более "дружелюбную" альтернативу обычному дрожжевому.
"""

def build_system_prompt():
    available = [p for p in PRODUCTS if not is_out_of_stock(p["id"])]
    stopped = [p["name"] for p in PRODUCTS if is_out_of_stock(p["id"])]
    available_text = "\n".join(f"- {p['name']}, {p['weight']} г, {p['price']} ₽: {p['desc']}" for p in available) or "- сегодня временно ничего нет в наличии"
    stopped_text = f"\nВРЕМЕННО НЕТ В НАЛИЧИИ (не предлагай эти виды): {', '.join(stopped)}" if stopped else ""
    return f"""Ты — дружелюбный консультант пекарни, продающей хлеб на закваске (массе матере) в Telegram.

АССОРТИМЕНТ СЕГОДНЯ В НАЛИЧИИ:
{available_text}
{stopped_text}

БАЗА ЗНАНИЙ ДЛЯ ОТВЕТОВ НА ВОПРОСЫ:
{FAQ_KNOWLEDGE}

ТВОЯ ЗАДАЧА:
1. Отвечай на вопросы о составе, хранении, отличиях между видами хлеба, пользе — кратко, тепло, без канцелярита (2-4 предложения), используя базу знаний выше. Не утверждай того, чего там нет.
2. Если человек хочет заказать хлеб — скажи, что нужно набрать команду /menu, и не пытайся сама принимать заказ текстом.
3. Если спросят про подписку — скажи, что есть команда /subscribe.
4. Мягкий upsell не больше одного раза за разговор.
5. Максимум 1 эмодзи на сообщение, и не всегда. Только русский язык, 2-5 предложений."""

# ================= ОБЩИЕ JSON-ХРАНИЛИЩА =================
def jpath(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)

def load_json(name, fallback):
    try:
        with open(jpath(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return fallback

def save_json(name, data):
    with open(jpath(name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data_lock = threading.Lock()  # общий замок: доступ идёт из потоков Flask, планировщика и asyncio-бота

carts = load_json("carts.json", {})
orders = load_json("orders.json", [])
stoplist = load_json("stoplist.json", {})
links = load_json("links.json", {})
subscriptions = load_json("subscriptions.json", [])
promocodes = load_json("promocodes.json", {})
pending_reviews = load_json("pendingReviews.json", [])
drafts = load_json("drafts.json", {})  # { phone: {"stage":..., "draft":..., "savedAt":...} }

def save_carts(): save_json("carts.json", carts)
def save_orders_file(): save_json("orders.json", orders)
def save_stoplist(): save_json("stoplist.json", stoplist)
def save_links(): save_json("links.json", links)
def save_subscriptions(): save_json("subscriptions.json", subscriptions)
def save_promocodes(): save_json("promocodes.json", promocodes)
def save_pending_reviews(): save_json("pendingReviews.json", pending_reviews)
def save_drafts(): save_json("drafts.json", drafts)
def save_draft(phone, stage, draft):
    if stage == "idle" or not phone:
        drafts.pop(phone, None)
    else:
        drafts[phone] = {"stage": stage, "draft": draft, "savedAt": datetime.now(timezone.utc).isoformat()}
    save_drafts()

# ---------------- ТЕЛЕФОН ----------------
def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits

def link_phone_to_chat(phone, chat_id):
    with data_lock:
        links[phone] = chat_id
        save_links()

def get_chat_id_for_phone(phone):
    return links.get(phone)

# ---------------- КОРЗИНА ----------------
def get_cart(phone):
    with data_lock:
        if phone not in carts:
            carts[phone] = {"items": {}, "updatedAt": datetime.now(timezone.utc).isoformat()}
        return carts[phone]

def set_cart_items(phone, items):
    with data_lock:
        carts[phone] = {"items": items, "updatedAt": datetime.now(timezone.utc).isoformat()}
        save_carts()
        return carts[phone]

def add_items_to_cart(phone, items_to_add):
    cart = get_cart(phone)
    items = dict(cart["items"])
    for pid, qty in items_to_add.items():
        items[pid] = items.get(pid, 0) + qty
    return set_cart_items(phone, items)

def cart_total(items):
    total = 0
    for pid, qty in items.items():
        p = next((x for x in PRODUCTS if x["id"] == pid), None)
        if p:
            total += p["price"] * qty
    return total

def cart_text(items):
    if not items:
        return "Корзина пуста."
    lines = []
    for pid, qty in items.items():
        p = next(x for x in PRODUCTS if x["id"] == pid)
        lines.append(f"{p['name']} × {qty} — {p['price'] * qty} ₽")
    return "\n".join(lines) + f"\n\nИтого: {cart_total(items)} ₽"

def build_order_summary(session):
    district = session["draft"]["district"]
    items = get_cart(session["phone"])["items"]
    subtotal = cart_total(items) + district["fee"]
    discount = compute_discount(subtotal, session["phone"], session["draft"].get("promoCode"))
    total = max(0, subtotal - discount["amount"])
    discount_line = f"Скидка: −{discount['amount']} ₽ ({discount['label']})\n" if discount["amount"] > 0 else ""
    bake_date_str = format_bake_date(datetime.fromisoformat(session["draft"]["bakeDate"]).date()) if session["draft"].get("bakeDate") else "—"
    return (
        f"Проверьте заказ:\n{cart_text(items)}\n"
        f"Дата выпечки: {bake_date_str}\n"
        f"Доставка: {district['name']}\nАдрес: {session['draft'].get('address') or '—'}\n"
        f"Оплата: {session['draft']['payment']}\nИмя: {session['draft']['name']}\nТелефон: {session['draft']['phone']}\n"
        f"{discount_line}\nИтого к оплате: {total} ₽"
    )

# ---------------- СТОП-ЛИСТ ----------------
def is_out_of_stock(pid):
    return bool(stoplist.get(pid))

def set_stock(pid, out_of_stock):
    with data_lock:
        if out_of_stock:
            stoplist[pid] = True
        else:
            stoplist.pop(pid, None)
        save_stoplist()

def available_products():
    return [p for p in PRODUCTS if not is_out_of_stock(p["id"])]

# ---------------- ЗАКАЗЫ ----------------
def save_order(order):
    with data_lock:
        orders.insert(0, order)
        save_orders_file()

def find_order(order_id):
    return next((o for o in orders if o["id"] == order_id), None)

def update_order_status(order_id, status):
    order = find_order(order_id)
    if not order:
        return None
    with data_lock:
        order["status"] = status
        save_orders_file()
    return order

def orders_today():
    today = datetime.now(timezone.utc).date().isoformat()
    return [o for o in orders if (o.get("createdAt") or "")[:10] == today]

def loyalty_order_count(phone):
    return len([o for o in orders if o.get("phone") == phone and o.get("status") != "Отменён"])

# ---------------- ПРОМОКОДЫ И ЛОЯЛЬНОСТЬ ----------------
def get_promo(code):
    promo = promocodes.get((code or "").upper().strip())
    return promo if promo and promo.get("active") else None

def compute_discount(subtotal, phone, promo_code):
    promo_discount = 0
    promo = get_promo(promo_code)
    if promo:
        promo_discount = round(subtotal * promo["value"] / 100) if promo["type"] == "percent" else promo["value"]
    future_order_number = loyalty_order_count(phone) + 1
    loyalty_discount = round(subtotal * 0.10) if future_order_number % 5 == 0 else 0
    if promo_discount >= loyalty_discount and promo_discount > 0:
        return {"amount": promo_discount, "label": f"промокод {promo_code.upper()}"}
    if loyalty_discount > 0:
        return {"amount": loyalty_discount, "label": f"скидка за {future_order_number}-й заказ (10%)"}
    return {"amount": 0, "label": None}

# ---------------- ПРЕДЗАКАЗ НА ДЕНЬ ВЫПЕЧКИ ----------------
def upcoming_bake_dates(count=3):
    dates = []
    cursor = datetime.now().date()
    while len(dates) < count:
        # Python: Monday=0..Sunday=6; приводим к нумерации как в Node getDay() (0=вс..6=сб)
        node_weekday = (cursor.weekday() + 1) % 7
        if node_weekday in BAKE_WEEKDAYS:
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates

def format_bake_date(d):
    node_weekday = (d.weekday() + 1) % 7
    return f"{WEEKDAY_NAMES[node_weekday]}, {d.day:02d}.{d.month:02d}"

# ================= CLAUDE API (FAQ) =================
def ask_claude(history):
    if not ANTHROPIC_API_KEY:
        return "Консультант временно недоступен (не задан ANTHROPIC_API_KEY). Загляните в /menu, чтобы посмотреть каталог."
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 600,
                "system": build_system_prompt(),
                "messages": history,
            },
            timeout=30,
        )
        data = resp.json()
        for block in data.get("content", []):
            if block.get("type") == "text":
                return block["text"]
        return "Не получилось сформулировать ответ, спросите ещё раз?"
    except Exception as e:
        print("Ошибка Claude API:", e)
        return "Не получилось ответить — попробуйте ещё раз через минуту."

def send_telegram_message(chat_id, text, reply_markup=None):
    """Прямой вызов Telegram Bot API через HTTP — используется из потоков планировщика
    и Flask, где нет доступа к event loop python-telegram-bot. Внутри обычных async
    хендлеров используйте context.bot.send_message как обычно."""
    try:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup is not None:
            rm = reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup
            payload["reply_markup"] = json.dumps(rm)
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=payload, timeout=15)
    except Exception as e:
        print("Ошибка отправки сообщения в Telegram:", e)

chat_histories = {}

# ================= УВЕДОМЛЕНИЯ =================
def status_buttons_keyboard(order_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Готовится", callback_data=f"status:{order_id}:Готовится"),
        InlineKeyboardButton("Готов/в пути", callback_data=f"status:{order_id}:Готов / в пути"),
        InlineKeyboardButton("Доставлен", callback_data=f"status:{order_id}:Доставлен"),
    ]])

def build_admin_notification_text(order):
    discount_line = f"Скидка: −{order['discount']['amount']} ₽ ({order['discount']['label']})\n" if order.get("discount") else ""
    bake_line = f"Дата выпечки: {order['bakeDate']}\n" if order.get("bakeDate") else ""
    items_text = "\n".join(f"• {i['name']} × {i['qty']} — {i['subtotal']} ₽" for i in order["items"])
    return (
        f"🥖 Новый заказ №{order['id']} [{order.get('status', 'Принят')}]\n{items_text}\n"
        f"{bake_line}Доставка: {order['delivery']} ({order['deliveryFee']} ₽)\n"
        f"Оплата: {order['payment']}\n{discount_line}Итого: {order['total']} ₽\n\n"
        f"Клиент: {order['name']}\nТелефон: {order['phone']}\nАдрес: {order.get('address') or '—'}\n"
        f"Комментарий: {order.get('comment') or '—'}\n"
        f"Telegram: @{order.get('username') or '—'} (id {order.get('chatId', '—')})"
    )

async def notify_admin(order, bot):
    if not ADMIN_CHAT_ID:
        return
    text = build_admin_notification_text(order)
    try:
        await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text, reply_markup=status_buttons_keyboard(order["id"]))
    except Exception as e:
        print("Не удалось уведомить администратора:", e)

async def notify_customer_status(order, bot):
    chat_id = order.get("chatId") or get_chat_id_for_phone(order.get("phone"))
    if not chat_id:
        return
    try:
        await bot.send_message(chat_id=chat_id, text=f"Статус заказа №{order['id']} обновлён: {order['status']}")
    except Exception as e:
        print("Не удалось уведомить клиента о статусе:", e)

def push_to_sheets(order):
    if not SHEETS_WEBHOOK_URL:
        return
    try:
        requests.post(SHEETS_WEBHOOK_URL, json=order, timeout=15)
    except Exception as e:
        print("Не удалось записать заказ в Google Sheets:", e)

# ================= ОНЛАЙН-ОПЛАТА (провайдер выбирается через PAYMENT_PROVIDER) =================

# ---- ЮKassa ----
def yookassa_configured():
    return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)

def create_yookassa_payment(order):
    auth = base64.b64encode(f"{YOOKASSA_SHOP_ID}:{YOOKASSA_SECRET_KEY}".encode()).decode()
    resp = requests.post(
        "https://api.yookassa.ru/v3/payments",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}",
            "Idempotence-Key": order["id"],
        },
        json={
            "amount": {"value": f"{order['total']:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": RETURN_URL},
            "capture": True,
            "description": f"Заказ №{order['id']} — пекарня на закваске",
            "metadata": {"orderId": order["id"]},
        },
        timeout=20,
    )
    data = resp.json()
    if not resp.ok:
        raise RuntimeError(data.get("description", "Ошибка создания платежа ЮKassa"))
    return {"confirmation_url": data["confirmation"]["confirmation_url"], "payment_id": data.get("id")}

# ---- ЮMoney (для физлиц, оплата на номер кошелька) ----
def yoomoney_configured():
    return bool(YOOMONEY_WALLET)

def create_yoomoney_payment(order):
    # ЮMoney для физлиц не требует серверного вызова API для создания платежа — формируется
    # прямая ссылка на форму Quickpay. label = order.id — по нему сопоставляем оплату
    # с заказом, когда придёт HTTP-уведомление на /api/yoomoney-webhook.
    params = {
        "receiver": YOOMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": f"Заказ №{order['id']}",
        "paymentType": "AC",  # AC = банковская карта; PC = кошелёк ЮMoney
        "sum": f"{order['total']:.2f}",
        "label": order["id"],
        "successURL": RETURN_URL,
    }
    url = "https://yoomoney.ru/quickpay/confirm.xml?" + urllib.parse.urlencode(params)
    return {"confirmation_url": url, "payment_id": None}

# ---- Единый интерфейс, используемый остальным кодом бота ----
def online_payment_configured():
    if PAYMENT_PROVIDER == "yookassa":
        return yookassa_configured()
    if PAYMENT_PROVIDER == "yoomoney":
        return yoomoney_configured()
    return False

def create_online_payment(order):
    if PAYMENT_PROVIDER == "yookassa":
        return create_yookassa_payment(order)
    if PAYMENT_PROVIDER == "yoomoney":
        return create_yoomoney_payment(order)
    raise RuntimeError(f"Платёжный провайдер '{PAYMENT_PROVIDER}' не поддерживается")

def payment_provider_label():
    return {"yookassa": "ЮKassa", "yoomoney": "ЮMoney"}.get(PAYMENT_PROVIDER, "онлайн")

# ================= КЛАВИАТУРЫ =================
def catalog_keyboard(items):
    rows = []
    for p in PRODUCTS:
        if is_out_of_stock(p["id"]):
            rows.append([InlineKeyboardButton(f"🚫 {p['name']} — нет в наличии", callback_data="noop")])
        else:
            qty = items.get(p["id"], 0)
            label = f"{p['name']} — {p['price']} ₽" + (f" (в корзине: {qty})" if qty else "")
            rows.append([InlineKeyboardButton(label, callback_data=f"add:{p['id']}")])
    rows.append([InlineKeyboardButton("🛒 Корзина / Оформить заказ", callback_data="checkout")])
    return InlineKeyboardMarkup(rows)

def bakedate_keyboard():
    dates = upcoming_bake_dates(3)
    return InlineKeyboardMarkup([[InlineKeyboardButton(format_bake_date(d), callback_data=f"bakeday:{d.isoformat()}")] for d in dates])

def district_keyboard():
    return InlineKeyboardMarkup([[InlineKeyboardButton(d["name"], callback_data=f"district:{d['id']}")] for d in DISTRICTS])

def payment_keyboard():
    rows = [
        [InlineKeyboardButton("Наличными", callback_data="pay:cash")],
        [InlineKeyboardButton("Картой при получении", callback_data="pay:card")],
    ]
    label = "Картой онлайн" if online_payment_configured() else "Картой онлайн (пока недоступно)"
    rows.append([InlineKeyboardButton(label, callback_data="pay:online")])
    return InlineKeyboardMarkup(rows)

def confirm_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить заказ", callback_data="confirm")],
        [InlineKeyboardButton("✏️ Изменить", callback_data="edit_order"), InlineKeyboardButton("✖ Отмена", callback_data="cancel")],
    ])

def resume_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("▶️ Продолжить", callback_data="resume_draft"),
        InlineKeyboardButton("🗑 Начать заново", callback_data="discard_draft"),
    ]])

async def prompt_for_stage(bot, chat_id, session):
    stage = session["stage"]
    if stage == "choosing_bakeday":
        await bot.send_message(chat_id, "На какой день выпечки оформляем?", reply_markup=bakedate_keyboard())
    elif stage == "choosing_district":
        await bot.send_message(chat_id, "Как вам удобно получить заказ?", reply_markup=district_keyboard())
    elif stage == "awaiting_name":
        await bot.send_message(chat_id, "Как вас зовут?")
    elif stage == "awaiting_address":
        await bot.send_message(chat_id, "Укажите адрес доставки:")
    elif stage == "awaiting_payment":
        await bot.send_message(chat_id, "Как будете оплачивать?", reply_markup=payment_keyboard())
    elif stage == "awaiting_promo":
        await bot.send_message(chat_id, 'Есть промокод? Напишите код или отправьте "нет".')
    elif stage == "confirming":
        await bot.send_message(chat_id, build_order_summary(session), reply_markup=confirm_keyboard())
    else:
        session["stage"] = "idle"
        items = get_cart(session["phone"])["items"]
        await bot.send_message(chat_id, "Выберите хлеб (можно несколько видов):", reply_markup=catalog_keyboard(items))

def weekday_keyboard(prefix):
    return InlineKeyboardMarkup([[InlineKeyboardButton(WEEKDAY_NAMES[n], callback_data=f"{prefix}:{n}")] for n in [1,2,3,4,5,6,0]])

def review_keyboard(order_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton("⭐" * n, callback_data=f"review:{order_id}:{n}") for n in range(1,6)]])

# ================= СОСТОЯНИЕ ДИАЛОГОВ =================
sessions = {}
def get_session(chat_id):
    if chat_id not in sessions:
        sessions[chat_id] = {"phone": None, "stage": "idle", "draft": {}}
    return sessions[chat_id]

def is_admin(chat_id):
    return ADMIN_CHAT_ID and str(chat_id) == str(ADMIN_CHAT_ID)

# ================= КОМАНДЫ =================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Это пекарня на закваске 🍞\nКоманды: /menu — каталог, /cart — корзина, "
        "/orders — мои заказы, /subscribe — еженедельная подписка, /phone — изменить привязанный номер телефона."
    )

async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    if not session["phone"]:
        session["stage"] = "linking_phone"
        await update.message.reply_text("Чтобы корзина совпадала с корзиной на сайте, укажите номер телефона:")
        return
    saved = drafts.get(session["phone"])
    if saved and session["stage"] == "idle":
        await update.message.reply_text(
            "👋 У вас есть незавершённый заказ — продолжить оформление или начать заново?",
            reply_markup=resume_keyboard(),
        )
        return
    items = get_cart(session["phone"])["items"]
    await update.message.reply_text("Выберите хлеб (можно несколько видов):", reply_markup=catalog_keyboard(items))

async def cart_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    if not session["phone"]:
        await update.message.reply_text("Сначала наберите /menu и укажите телефон.")
        return
    await update.message.reply_text(cart_text(get_cart(session["phone"])["items"]))

async def orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    if not session["phone"]:
        await update.message.reply_text("Сначала наберите /menu и укажите телефон, чтобы я знал, чьи заказы показывать.")
        return
    mine = [o for o in orders if o.get("phone") == session["phone"]][:10]
    if not mine:
        await update.message.reply_text("Заказов пока не было — самое время исправить через /menu 🥖")
        return
    blocks = []
    for o in mine:
        items_line = ", ".join(f"{i['name']} ×{i['qty']}" for i in o["items"])
        date = datetime.fromisoformat(o["createdAt"]).strftime("%d.%m.%Y")
        blocks.append(f"№{o['id']} ({date}) [{o['status']}] — {o['channel']}\n{items_line}\nСумма: {o['total']} ₽")
    await update.message.reply_text("Ваши последние заказы:\n\n" + "\n\n".join(blocks))

async def phone_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    current = f" Сейчас привязан: +{session['phone']}." if session["phone"] else ""
    session["stage"] = "linking_phone"
    await update.message.reply_text(f"Укажите новый номер телефона для синхронизации с сайтом.{current}")

# Временное хранилище черновика рассылки на время подтверждения (не переживает
# рестарт бота — это осознанно: рассылка должна подтверждаться заново после каждого
# перезапуска, чтобы старый неотправленный черновик не улетел случайно).
pending_broadcasts = {}  # {admin_chat_id: text}

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        return
    text = update.message.text.partition(" ")[2].strip()
    if not text:
        await update.message.reply_text(
            "Использование: /broadcast Текст сообщения для рассылки всем клиентам.\n\n"
            "Разошлётся всем, у кого есть привязанный Telegram (т.е. кто хоть раз писал боту). "
            "Перед отправкой попрошу подтверждение."
        )
        return
    recipients = list(set(links.values()))  # уникальные chat_id, links = {phone: chat_id}
    pending_broadcasts[chat_id] = text
    preview = text if len(text) <= 500 else text[:500] + "…"
    await update.message.reply_text(
        f"📢 Предпросмотр рассылки ({len(recipients)} получател{'ей' if len(recipients)!=1 else 'ь'}):\n\n{preview}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Отправить всем", callback_data="broadcast_confirm"),
            InlineKeyboardButton("✖ Отмена", callback_data="broadcast_cancel"),
        ]]),
    )

async def subscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    if not session["phone"]:
        session["stage"] = "linking_phone"
        await update.message.reply_text("Сначала укажите номер телефона:")
        return
    items = get_cart(session["phone"])["items"]
    if not items:
        await update.message.reply_text("Сначала соберите нужный хлеб через /menu — то, что в корзине сейчас, станет вашим обычным еженедельным набором.")
        return
    session["stage"] = "subscribing"
    await update.message.reply_text(
        f"Оформляем подписку на:\n{cart_text(items)}\n\nВ какой день недели присылать напоминание?",
        reply_markup=weekday_keyboard("subday"),
    )

async def unsubscribe_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = get_session(chat_id)
    mine = [s for s in subscriptions if s["phone"] == session["phone"] and s["active"]]
    if not mine:
        await update.message.reply_text("У вас нет активных подписок.")
        return
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Отменить: {WEEKDAY_NAMES[s['weekday']]}", callback_data=f"unsub:{s['id']}")] for s in mine])
    await update.message.reply_text("Ваши подписки:", reply_markup=kb)

async def stock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = [f"{'🚫' if is_out_of_stock(p['id']) else '✅'} {p['name']}" for p in PRODUCTS]
    await update.message.reply_text("\n".join(lines))

async def stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    if not context.args:
        await update.message.reply_text(f"Использование: /stop <id>. Доступные: {', '.join(p['id'] for p in PRODUCTS)}")
        return
    pid = context.args[0]
    if not any(p["id"] == pid for p in PRODUCTS):
        await update.message.reply_text(f"Нет такого id. Доступные: {', '.join(p['id'] for p in PRODUCTS)}")
        return
    set_stock(pid, True)
    await update.message.reply_text(f"Отметил как «нет в наличии»: {pid}")

async def instock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    if not context.args:
        return
    set_stock(context.args[0], False)
    await update.message.reply_text(f"Вернул в наличие: {context.args[0]}")

async def addpromo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    if len(context.args) != 3 or context.args[1] not in ("percent", "fixed"):
        await update.message.reply_text("Использование: /addpromo КОД percent 10  (или fixed 100)")
        return
    code, ptype, value = context.args
    with data_lock:
        promocodes[code.upper()] = {"type": ptype, "value": int(value), "active": True}
        save_promocodes()
    await update.message.reply_text(f"Промокод {code.upper()} создан: {ptype} {value}{'%' if ptype=='percent' else '₽'}")

async def promos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    if not promocodes:
        await update.message.reply_text("Промокодов пока нет. Создать: /addpromo КОД percent 10")
        return
    text = "\n".join(f"{code}: {'активен' if p['active'] else 'выключен'}, {p['type']} {p['value']}" for code, p in promocodes.items())
    await update.message.reply_text(text)

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    if len(context.args) < 2:
        await update.message.reply_text(f"Использование: /status <orderId> <статус>. Статусы: {', '.join(ORDER_STATUSES)}")
        return
    order_id, status = context.args[0], " ".join(context.args[1:])
    if status not in ORDER_STATUSES:
        await update.message.reply_text(f"Статус должен быть одним из: {', '.join(ORDER_STATUSES)}")
        return
    order = update_order_status(order_id, status)
    if not order:
        await update.message.reply_text("Заказ не найден.")
        return
    await notify_customer_status(order, context.bot)
    await update.message.reply_text(f"Статус заказа №{order_id} обновлён: {status}")

async def today_orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    today_list = orders_today()
    if not today_list:
        await update.message.reply_text("Сегодня заказов пока нет.")
        return
    text = "\n".join(f"№{o['id']} [{o['status']}] {o['name']}, {o['phone']} — {o['total']} ₽ ({o['channel']})" for o in today_list)
    await update.message.reply_text(f"Заказы за сегодня ({len(today_list)}):\n{text}")

async def all_orders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    if not orders:
        await update.message.reply_text("Заказов пока нет.")
        return
    limit = 20
    try:
        if context.args and context.args[0].isdigit():
            limit = int(context.args[0])
    except Exception:
        pass
    recent = orders[:limit]  # orders уже хранится от новых к старым (insert(0, order))
    blocks = []
    for o in recent:
        date = datetime.fromisoformat(o["createdAt"]).strftime("%d.%m %H:%M")
        blocks.append(f"№{o['id']} ({date}) [{o['status']}] {o['name']}, {o['phone']} — {o['total']} ₽ ({o['channel']})")
    await update.message.reply_text(
        f"Последние заказы ({len(recent)} из {len(orders)} всего):\n\n" + "\n".join(blocks)
    )

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_chat.id):
        return
    today_list = orders_today()
    revenue_today = sum(o.get("total", 0) for o in today_list)
    revenue_all = sum(o.get("total", 0) for o in orders)
    by_channel = {}
    for o in orders:
        by_channel[o.get("channel", "—")] = by_channel.get(o.get("channel", "—"), 0) + 1
    channel_lines = "\n".join(f"  {ch}: {n}" for ch, n in by_channel.items())
    await update.message.reply_text(
        f"📊 Статистика\n\nСегодня: {len(today_list)} заказ(ов), {revenue_today} ₽\n"
        f"Всего: {len(orders)} заказ(ов), {revenue_all} ₽\n\nПо каналам:\n{channel_lines}"
    )

# ================= ОБРАБОТКА КНОПОК =================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat.id
    session = get_session(chat_id)
    data = query.data

    try:
        if data == "noop":
            await query.answer()
            return

        if data.startswith("add:"):
            if not session["phone"]:
                await query.answer("Сначала наберите /menu и укажите телефон", show_alert=True)
                return
            pid = data.split(":")[1]
            if is_out_of_stock(pid):
                await query.answer("Этого хлеба сегодня нет в наличии", show_alert=True)
                return
            cart = get_cart(session["phone"])
            items = dict(cart["items"])
            items[pid] = items.get(pid, 0) + 1
            set_cart_items(session["phone"], items)
            await query.edit_message_reply_markup(reply_markup=catalog_keyboard(items))
            await query.answer("Добавили в корзину")
            return

        if data == "checkout":
            items = get_cart(session["phone"])["items"]
            if not items:
                await query.answer("Корзина пуста — выберите хлеб", show_alert=True)
                return
            session["stage"] = "choosing_bakeday"
            session["draft"] = {}
            save_draft(session["phone"], session["stage"], session["draft"])
            await context.bot.send_message(chat_id, f"Ваш заказ:\n{cart_text(items)}\n\nНа какой день выпечки оформляем?", reply_markup=bakedate_keyboard())
            await query.answer()
            return

        if data.startswith("bakeday:"):
            session["draft"]["bakeDate"] = data.split(":", 1)[1]
            session["stage"] = "choosing_district"
            save_draft(session["phone"], session["stage"], session["draft"])
            await context.bot.send_message(chat_id, "Как вам удобно получить заказ?", reply_markup=district_keyboard())
            await query.answer()
            return

        if data.startswith("district:"):
            did = data.split(":")[1]
            session["draft"]["district"] = next(d for d in DISTRICTS if d["id"] == did)
            session["stage"] = "awaiting_name"
            save_draft(session["phone"], session["stage"], session["draft"])
            await context.bot.send_message(chat_id, "Как вас зовут?")
            await query.answer()
            return

        if data.startswith("pay:"):
            method = data.split(":")[1]
            if method == "online" and not online_payment_configured():
                await query.answer("Онлайн-оплата временно недоступна — выберите другой способ", show_alert=True)
                return
            session["draft"]["payment"] = "Наличными" if method == "cash" else "Картой при получении" if method == "card" else f"Картой онлайн ({payment_provider_label()})"
            session["stage"] = "awaiting_promo"
            save_draft(session["phone"], session["stage"], session["draft"])
            await context.bot.send_message(chat_id, 'Есть промокод? Напишите код или отправьте "нет".')
            await query.answer()
            return

        if data == "confirm":
            district = session["draft"]["district"]
            cart_items = get_cart(session["phone"])["items"]
            items = []
            for pid, qty in cart_items.items():
                p = next(x for x in PRODUCTS if x["id"] == pid)
                items.append({"name": p["name"], "weight": p["weight"], "qty": qty, "price": p["price"], "subtotal": p["price"] * qty})
            subtotal = cart_total(cart_items) + district["fee"]
            discount = compute_discount(subtotal, session["phone"], session["draft"].get("promoCode"))
            total = max(0, subtotal - discount["amount"])
            order_id = "TG-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

            bake_date_str = ""
            if session["draft"].get("bakeDate"):
                bake_date_str = format_bake_date(datetime.fromisoformat(session["draft"]["bakeDate"]).date())

            order = {
                "id": order_id, "channel": "Telegram-бот (Python)", "status": "Принят",
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "chatId": chat_id, "username": query.from_user.username or "",
                "name": session["draft"]["name"], "phone": session["draft"]["phone"],
                "address": session["draft"].get("address", ""), "comment": "",
                "bakeDate": bake_date_str, "delivery": district["name"], "deliveryFee": district["fee"],
                "payment": session["draft"]["payment"], "items": items, "total": total,
                "discount": discount if discount["amount"] > 0 else None,
            }

            save_order(order)
            link_phone_to_chat(session["phone"], chat_id)
            await notify_admin(order, context.bot)
            await asyncio.to_thread(push_to_sheets, order)
            set_cart_items(session["phone"], {})

            with data_lock:
                pending_reviews.append({
                    "orderId": order["id"], "phone": order["phone"], "chatId": chat_id,
                    "dueAt": (datetime.now(timezone.utc) + timedelta(hours=REVIEW_DELAY_HOURS)).isoformat(),
                    "sent": False,
                })
                save_pending_reviews()

            if order["payment"].startswith("Картой онлайн"):
                try:
                    payment = await asyncio.to_thread(create_online_payment, order)
                    url = payment["confirmation_url"]
                    await context.bot.send_message(chat_id, f"Заказ №{order_id} создан! Для оплаты перейдите по ссылке:\n{url}\n\nПосле оплаты мы свяжемся с вами по телефону {order['phone']}. Спасибо! 🥖")
                except Exception as e:
                    print(f"Ошибка платежа ({PAYMENT_PROVIDER}):", e)
                    await context.bot.send_message(chat_id, f"Заказ №{order_id} принят, но не удалось создать ссылку на оплату. Мы свяжемся с вами по телефону {order['phone']}, чтобы уточнить оплату.")
            else:
                await context.bot.send_message(chat_id, f"Заказ №{order_id} принят! Мы свяжемся с вами по телефону {order['phone']} для подтверждения. Спасибо! 🥖")

            session["draft"] = {}
            session["stage"] = "idle"
            save_draft(session["phone"], "idle", {})
            await query.answer()
            return

        if data == "cancel":
            session["stage"] = "idle"
            session["draft"] = {}
            save_draft(session["phone"], "idle", {})
            await context.bot.send_message(chat_id, "Заказ отменён. Корзина сохранена — наберите /menu, чтобы продолжить, или /cart, чтобы посмотреть, что уже выбрано.")
            await query.answer()
            return

        if data == "edit_order":
            session["stage"] = "idle"
            session["draft"] = {}
            save_draft(session["phone"], "idle", {})
            items = get_cart(session["phone"])["items"]
            await context.bot.send_message(chat_id, "Хорошо, начнём заново — корзина сохранена, можно поменять состав и оформить снова.")
            await context.bot.send_message(chat_id, "Выберите хлеб (можно несколько видов):", reply_markup=catalog_keyboard(items))
            await query.answer()
            return

        if data == "resume_draft":
            saved = drafts.get(session["phone"])
            if not saved:
                await query.answer("Черновик не найден")
                return
            session["stage"] = saved["stage"]
            session["draft"] = saved["draft"]
            await prompt_for_stage(context.bot, chat_id, session)
            await query.answer()
            return

        if data == "discard_draft":
            save_draft(session["phone"], "idle", {})
            session["stage"] = "idle"
            session["draft"] = {}
            items = get_cart(session["phone"])["items"]
            await context.bot.send_message(chat_id, "Начинаем заново. Выберите хлеб:", reply_markup=catalog_keyboard(items))
            await query.answer()
            return

        if data.startswith("subday:"):
            weekday = int(data.split(":")[1])
            items = get_cart(session["phone"])["items"]
            with data_lock:
                subscriptions.append({
                    "id": "SUB-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6)),
                    "phone": session["phone"], "chatId": chat_id, "items": items,
                    "weekday": weekday, "active": True, "lastTriggeredDate": None,
                })
                save_subscriptions()
            session["stage"] = "idle"
            await context.bot.send_message(chat_id, f"Готово! Каждую неделю в {WEEKDAY_NAMES[weekday].lower()} пришлю напоминание с этим набором. Отменить — /unsubscribe.")
            await query.answer()
            return

        if data.startswith("unsub:"):
            sub_id = data.split(":")[1]
            sub = next((s for s in subscriptions if s["id"] == sub_id), None)
            if sub:
                with data_lock:
                    sub["active"] = False
                    save_subscriptions()
            await context.bot.send_message(chat_id, "Подписка отменена.")
            await query.answer()
            return

        if data.startswith("status:"):
            if not is_admin(chat_id):
                await query.answer("Только для администратора")
                return
            _, order_id, status = data.split(":", 2)
            order = update_order_status(order_id, status)
            if order:
                await notify_customer_status(order, context.bot)
            await query.answer(f"Статус: {status}")
            return

        if data.startswith("review:"):
            _, order_id, score = data.split(":")
            print(f"Отзыв по заказу {order_id}: {score}/5")
            if ADMIN_CHAT_ID:
                await context.bot.send_message(ADMIN_CHAT_ID, f"⭐ Отзыв по заказу №{order_id}: {score}/5")
            await context.bot.send_message(chat_id, "Спасибо за оценку! 🙏")
            await query.answer()
            return

        if data == "broadcast_confirm":
            if not is_admin(chat_id):
                await query.answer("Только для администратора")
                return
            text = pending_broadcasts.pop(chat_id, None)
            if not text:
                await query.answer("Черновик рассылки не найден — начните заново через /broadcast")
                return
            recipients = list(set(links.values()))
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id, f"Отправляю {len(recipients)} получателям...")
            sent, failed = 0, 0
            for recipient_chat_id in recipients:
                try:
                    await context.bot.send_message(recipient_chat_id, text)
                    sent += 1
                except Exception as e:
                    failed += 1
                    print(f"Broadcast: не удалось отправить {recipient_chat_id}:", e)
                await asyncio.sleep(0.05)  # ~20 сообщений/сек — запас под лимиты Telegram (не более 30/сек)
            await context.bot.send_message(chat_id, f"✅ Рассылка завершена: доставлено {sent}, не удалось {failed}.")
            await query.answer()
            return

        if data == "broadcast_cancel":
            pending_broadcasts.pop(chat_id, None)
            await query.edit_message_reply_markup(reply_markup=None)
            await context.bot.send_message(chat_id, "Рассылка отменена.")
            await query.answer()
            return

    except Exception as e:
        print("Ошибка обработки кнопки:", e)
        await query.answer("Что-то пошло не так, попробуйте ещё раз.")

# ================= ОБЫЧНЫЕ СООБЩЕНИЯ =================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text
    chat_id = update.effective_chat.id
    session = get_session(chat_id)

    if session["stage"] == "linking_phone":
        session["phone"] = normalize_phone(text)
        session["stage"] = "idle"
        link_phone_to_chat(session["phone"], chat_id)
        items = get_cart(session["phone"])["items"]
        await update.message.reply_text("Готово! Корзина синхронизирована с сайтом 🥖")
        await update.message.reply_text("Выберите хлеб (можно несколько видов):", reply_markup=catalog_keyboard(items))
        return

    if session["stage"] == "awaiting_name":
        session["draft"]["name"] = text.strip()
        session["draft"]["phone"] = session["phone"]
        if session["draft"]["district"]["id"] != "pickup":
            session["stage"] = "awaiting_address"
            save_draft(session["phone"], session["stage"], session["draft"])
            await update.message.reply_text("Укажите адрес доставки:")
        else:
            session["stage"] = "awaiting_payment"
            save_draft(session["phone"], session["stage"], session["draft"])
            await update.message.reply_text("Как будете оплачивать?", reply_markup=payment_keyboard())
        return

    if session["stage"] == "awaiting_address":
        session["draft"]["address"] = text.strip()
        session["stage"] = "awaiting_payment"
        save_draft(session["phone"], session["stage"], session["draft"])
        await update.message.reply_text("Как будете оплачивать?", reply_markup=payment_keyboard())
        return

    if session["stage"] == "awaiting_promo":
        if text.strip().lower() not in ("нет", "-"):
            session["draft"]["promoCode"] = text.strip()
        session["stage"] = "confirming"
        save_draft(session["phone"], session["stage"], session["draft"])
        await update.message.reply_text(build_order_summary(session), reply_markup=confirm_keyboard())
        return

    # FAQ через Claude
    history = chat_histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": text})
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    reply = await asyncio.to_thread(ask_claude, history)
    history.append({"role": "assistant", "content": reply})
    await update.message.reply_text(reply)

# ================= ПЛАНИРОВЩИК: ПОДПИСКИ + ЗАПРОС ОТЗЫВОВ =================
def run_scheduled_tasks():
    today = datetime.now(timezone.utc).date().isoformat()
    today_weekday = (datetime.now().weekday() + 1) % 7  # 0=вс..6=сб, как getDay() в Node

    for sub in subscriptions:
        if not sub["active"] or sub["weekday"] != today_weekday or sub.get("lastTriggeredDate") == today:
            continue
        try:
            add_items_to_cart(sub["phone"], sub["items"])
            send_telegram_message(
                sub["chatId"],
                f"Сегодня день вашей подписки ({WEEKDAY_NAMES[sub['weekday']]})! В корзину добавлен ваш обычный набор — осталось оформить.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒 Оформить заказ", callback_data="checkout")]]),
            )
            with data_lock:
                sub["lastTriggeredDate"] = today
                save_subscriptions()
        except Exception as e:
            print("Ошибка напоминания о подписке:", e)

    now = datetime.now(timezone.utc)
    for review in pending_reviews:
        if review["sent"] or datetime.fromisoformat(review["dueAt"]) > now:
            continue
        try:
            send_telegram_message(
                review["chatId"], f"Как впечатления от заказа №{review['orderId']}? Оцените, пожалуйста:",
                reply_markup=review_keyboard(review["orderId"]),
            )
            with data_lock:
                review["sent"] = True
                save_pending_reviews()
        except Exception as e:
            print("Ошибка запроса отзыва:", e)

def scheduler_loop():
    while True:
        time.sleep(30 * 60)
        try:
            run_scheduled_tasks()
        except Exception as e:
            print("Ошибка планировщика:", e)

# ================= HTTP-СЕРВЕР: API КОРЗИНЫ + СТОП-ЛИСТ + WEBHOOK ЮKASSA =================
flask_app = Flask(__name__)

@flask_app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@flask_app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})

@flask_app.route("/api/cart/<raw_phone>", methods=["GET"])
def get_cart_route(raw_phone):
    phone = normalize_phone(raw_phone)
    if not phone:
        return jsonify({"error": "Некорректный номер телефона"}), 400
    return jsonify({"phone": phone, **get_cart(phone)})

@flask_app.route("/api/cart/<raw_phone>", methods=["POST"])
def set_cart_route(raw_phone):
    phone = normalize_phone(raw_phone)
    if not phone:
        return jsonify({"error": "Некорректный номер телефона"}), 400
    body = request.get_json(silent=True) or {}
    return jsonify({"phone": phone, **set_cart_items(phone, body.get("items", {}))})

@flask_app.route("/api/cart/<raw_phone>/clear", methods=["POST"])
def clear_cart_route(raw_phone):
    phone = normalize_phone(raw_phone)
    if not phone:
        return jsonify({"error": "Некорректный номер телефона"}), 400
    return jsonify({"phone": phone, **set_cart_items(phone, {})})

@flask_app.route("/api/stock", methods=["GET"])
def stock_route():
    return jsonify({"outOfStock": list(stoplist.keys())})

# FAQ-чат для браузерного виджета — ANTHROPIC_API_KEY остаётся на сервере.
# Прямой вызов api.anthropic.com из браузера работает только внутри превью Claude.ai;
# на реальном сайте у браузера нет доступа к ключу, поэтому виджет зовёт этот маршрут.
@flask_app.route("/api/ask-faq", methods=["POST"])
def ask_faq_route():
    body = request.get_json(silent=True) or {}
    messages = body.get("messages")
    if not isinstance(messages, list) or len(messages) == 0:
        return jsonify({"error": "Нет сообщений"}), 400
    try:
        reply = ask_claude(messages)
        return jsonify({"reply": reply})
    except Exception as e:
        print("Ошибка /api/ask-faq:", e)
        return jsonify({"error": "Не удалось получить ответ консультанта"}), 500

# Заказы конкретного покупателя по его номеру телефона — отдаёт только ЕГО заказы,
# не весь список (это безопасно раздавать публично, в отличие от /today_orders).
@flask_app.route("/api/orders/<raw_phone>", methods=["GET"])
def orders_route(raw_phone):
    phone = normalize_phone(raw_phone)
    if not phone:
        return jsonify({"error": "Некорректный номер телефона"}), 400
    mine = [o for o in orders if o.get("phone") == phone][:20]
    return jsonify({"phone": phone, "orders": mine})

# Уведомление администратору о заказе с САЙТА — токен бота остаётся на сервере,
# сайт никогда его не видит и не хранит. Заменяет прежний прямой вызов Telegram API
# из браузера (это было небезопасно: токен был виден в каждом сетевом запросе сайта).
@flask_app.route("/api/notify-order", methods=["POST"])
def notify_order_route():
    o = request.get_json(silent=True) or {}
    if not o.get("id"):
        return jsonify({"error": "Некорректные данные заказа"}), 400
    order = {
        "id": o["id"], "status": o.get("status", "Принят"),
        "items": o.get("items") if isinstance(o.get("items"), list) else [],
        "delivery": o.get("delivery", "—"), "deliveryFee": o.get("deliveryFee", 0),
        "payment": o.get("payment", "—"), "total": o.get("total", 0),
        "name": o.get("name", "—"), "phone": o.get("phone", "—"),
        "address": o.get("address", ""), "comment": o.get("comment", ""),
        "chatId": o.get("chatId", "—"), "username": o.get("username", ""),
        "discount": o.get("discount"), "bakeDate": o.get("bakeDate", ""),
    }
    if not ADMIN_CHAT_ID:
        return jsonify({"status": "skipped", "reason": "ADMIN_CHAT_ID не настроен"})
    text = build_admin_notification_text(order)
    send_telegram_message(ADMIN_CHAT_ID, text, reply_markup=status_buttons_keyboard(order["id"]))
    return jsonify({"status": "ok"})

def mark_order_paid_and_notify(order_id, provider_name):
    """Общая логика для webhook'ов всех платёжных провайдеров: пометить заказ оплаченным
    и уведомить клиента и администратора. order_id должен совпадать с order['id']."""
    order = find_order(order_id) if order_id else None
    if not order:
        print(f"Webhook {provider_name}: не нашли заказ по id:", order_id)
        return False
    with data_lock:
        order["status"] = "Принят"
        order["paymentStatus"] = "Оплачено"
        save_orders_file()
    chat_id = order.get("chatId") or get_chat_id_for_phone(order.get("phone"))
    if chat_id:
        send_telegram_message(chat_id, f"Статус заказа №{order_id} обновлён: Оплачено, готовим заказ")
    if ADMIN_CHAT_ID:
        send_telegram_message(ADMIN_CHAT_ID, f"💳 Оплата через {provider_name} по заказу №{order_id} прошла успешно.")
    return True

@flask_app.route("/api/yookassa-webhook", methods=["POST"])
def yookassa_webhook():
    try:
        event = request.get_json(silent=True) or {}
        if event.get("event") == "payment.succeeded":
            order_id = (event.get("object") or {}).get("metadata", {}).get("orderId")
            mark_order_paid_and_notify(order_id, "ЮKassa")
        return "", 200
    except Exception as e:
        print("Ошибка обработки webhook ЮKassa:", e)
        return "", 200

# HTTP-уведомления ЮMoney приходят как application/x-www-form-urlencoded (не JSON!) —
# Flask разбирает такие данные автоматически в request.form. URL этого маршрута нужно
# один раз вручную указать в настройках кошелька на yoomoney.ru (см. README) — это
# делается через веб-интерфейс ЮMoney, а не через переменные окружения бота.
@flask_app.route("/api/yoomoney-webhook", methods=["POST"])
def yoomoney_webhook():
    try:
        data = request.form
        if YOOMONEY_NOTIFICATION_SECRET:
            # Проверка подписи по алгоритму из документации ЮMoney: sha1 от полей,
            # соединённых через "&", в строго заданном порядке, с секретом на предпоследнем месте.
            check_string = "&".join([
                data.get("notification_type", ""),
                data.get("operation_id", ""),
                data.get("amount", ""),
                data.get("currency", ""),
                data.get("datetime", ""),
                data.get("sender", ""),
                data.get("codepro", ""),
                YOOMONEY_NOTIFICATION_SECRET,
                data.get("label", ""),
            ])
            expected_hash = hashlib.sha1(check_string.encode("utf-8")).hexdigest()
            if expected_hash != data.get("sha1_hash"):
                print("Webhook ЮMoney: подпись не совпала — запрос отклонён")
                return "", 400
        else:
            print("ВНИМАНИЕ: YOOMONEY_NOTIFICATION_SECRET не задан — подпись webhook не проверяется")

        # codepro=true означает "защищённый" перевод, требующий доп. кода от отправителя —
        # такие переводы ещё не считаются подтверждённо принятыми, пропускаем их.
        if data.get("unaccepted") == "true":
            return "", 200

        order_id = data.get("label")  # мы сами передали order.id в параметре label при создании ссылки
        mark_order_paid_and_notify(order_id, "ЮMoney")
        return "", 200
    except Exception as e:
        print("Ошибка обработки webhook ЮMoney:", e)
        return "", 200

@flask_app.route("/", methods=["GET"])
def index_route():
    return "Sourdough bakery bot & cart API is running."

# ================= TELEGRAM WEBHOOK (через тот же Flask-сервер) =================
# Бот живёт в собственном asyncio event loop в отдельном фоновом потоке (создаём и
# запускаем его сами — Flask синхронный, поэтому "мостом" между ними служит
# asyncio.run_coroutine_threadsafe). Polling остаётся доступен как fallback —
# переключение через USE_WEBHOOK, без правок кода.
application = None       # создаётся в main(), используется маршрутом ниже
bot_loop = None          # event loop фонового потока бота (для webhook-режима)

@flask_app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook_route():
    if not application or not bot_loop:
        return "", 503
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if secret_header != WEBHOOK_SECRET:
        return "", 403
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run_coroutine_threadsafe(application.process_update(update), bot_loop)
    except Exception as e:
        print("Ошибка обработки Telegram webhook:", e)
    return "", 200

def run_bot_webhook_mode():
    """Фоновый поток: свой event loop, бот запущен и ждёт process_update() из Flask-маршрута."""
    global bot_loop
    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)

    async def _start():
        await application.initialize()
        await application.start()
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/telegram-webhook"
        await application.bot.set_webhook(
            url=webhook_url, secret_token=WEBHOOK_SECRET, drop_pending_updates=True
        )
        print(f"Бот пекарни слушает Telegram через webhook: {webhook_url}")

    bot_loop.run_until_complete(_start())
    bot_loop.run_forever()

def run_flask():
    # production WSGI-сервер вместо встроенного дев-сервера Flask
    from waitress import serve
    serve(flask_app, host="0.0.0.0", port=PORT)

# ================= ЗАПУСК =================
def main():
    global application

    if not TOKEN:
        raise SystemExit("Не задан TELEGRAM_BOT_TOKEN в .env — бот не может запуститься.")

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"HTTP-сервер (API корзины/стоп-листа) слушает порт {PORT}...")

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("menu", menu_cmd))
    application.add_handler(CommandHandler("cart", cart_cmd))
    application.add_handler(CommandHandler("phone", phone_cmd))
    application.add_handler(CommandHandler("broadcast", broadcast_cmd))
    application.add_handler(CommandHandler("orders", orders_cmd))
    application.add_handler(CommandHandler("subscribe", subscribe_cmd))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_cmd))
    application.add_handler(CommandHandler("stock", stock_cmd))
    application.add_handler(CommandHandler("stop", stop_cmd))
    application.add_handler(CommandHandler("instock", instock_cmd))
    application.add_handler(CommandHandler("addpromo", addpromo_cmd))
    application.add_handler(CommandHandler("promos", promos_cmd))
    application.add_handler(CommandHandler("status", status_cmd))
    application.add_handler(CommandHandler("today_orders", today_orders_cmd))
    application.add_handler(CommandHandler("all_orders", all_orders_cmd))
    application.add_handler(CommandHandler("stats", stats_cmd))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    threading.Thread(target=scheduler_loop, daemon=True).start()

    if USE_WEBHOOK and RENDER_EXTERNAL_URL:
        run_bot_webhook_mode()  # блокирует поток на loop.run_forever() — это ок, это и есть работа бота
    else:
        if USE_WEBHOOK and not RENDER_EXTERNAL_URL:
            print("USE_WEBHOOK=true, но RENDER_EXTERNAL_URL не задан — откатываюсь на polling.")
        # Защита от RuntimeError на Python 3.14: get_event_loop() больше не создаёт
        # loop автоматически, если его нет, а run_polling() внутри на это рассчитывает.
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        print("Бот пекарни слушает Telegram через polling...")
        application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
