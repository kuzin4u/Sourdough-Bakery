"""
VK-бот «Масса Матере» — Long Poll режим
========================================
Использует VK Long Poll API вместо Callback — сам опрашивает VK,
не засыпает на Render Starter плане (как Telegram-бот).

Настройка env vars:
  VK_TOKEN          — ключ доступа сообщества
  VK_GROUP_ID       — ID сообщества (число)
  VK_ADMIN_ID       — VK user_id администратора для уведомлений
  SHEETS_WEBHOOK_URL — URL Apps Script
  BAKE_WEEKDAYS     — дни выпечки (2,4,6 = Вт,Чт,Сб)
"""

import os
import json
import time
import random
import string
import logging
import requests
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ─── Конфигурация ─────────────────────────────────────────────────
VK_TOKEN      = os.getenv("VK_TOKEN", "")
VK_GROUP_ID   = os.getenv("VK_GROUP_ID", "")
SHEETS_URL    = os.getenv("SHEETS_WEBHOOK_URL", "") or os.getenv("REVIEWS_WEBHOOK_URL", "")
BAKE_WEEKDAYS = [int(x) for x in os.getenv("BAKE_WEEKDAYS", "2,4,6").split(",")]
ADMIN_ID      = os.getenv("VK_ADMIN_ID", "")
VK_API_V      = "5.199"
MSK           = timezone(timedelta(hours=3))

# ─── Хранилище ────────────────────────────────────────────────────
DATA_DIR = os.path.dirname(os.path.abspath(__file__))

def load_json(filename, default):
    try:
        with open(os.path.join(DATA_DIR, filename), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(filename, data):
    with open(os.path.join(DATA_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data_lock = threading.Lock()
carts     = load_json("vk_carts.json", {})
orders    = load_json("vk_orders.json", [])
sessions  = {}

def save_carts():  save_json("vk_carts.json", carts)
def save_orders(): save_json("vk_orders.json", orders)

# ─── Товары ───────────────────────────────────────────────────────
PRODUCTS = [
    {"id": "wheat",      "name": "Тартин",                    "weight": 650, "price": 380, "emoji": "🍞"},
    {"id": "rye",        "name": "Заварной ржано-пшеничный",  "weight": 500, "price": 425, "emoji": "🫓"},
    {"id": "seeds",      "name": "Бородинский",               "weight": 400, "price": 340, "emoji": "🍞"},
    {"id": "wholegrain", "name": "Тартин сырный",             "weight": 650, "price": 468, "emoji": "🧀"},
]

def load_products_from_sheets():
    global PRODUCTS
    if not SHEETS_URL:
        return
    try:
        r = requests.get(SHEETS_URL, params={"action": "products"}, timeout=15)
        data = r.json()
        if isinstance(data, list) and data:
            PRODUCTS = [{"id": p["id"], "name": p["name"],
                         "weight": int(p.get("weight", 0)),
                         "price": int(p.get("price", 0)),
                         "emoji": p.get("emoji", "🍞")} for p in data if p.get("id")]
            logger.info(f"VK Long Poll: загружено {len(PRODUCTS)} товаров")
    except Exception as e:
        logger.warning(f"Не удалось загрузить товары: {e}")

load_products_from_sheets()

# ─── Корзина ──────────────────────────────────────────────────────
def get_cart(uid):
    return carts.get(str(uid), {})

def set_cart(uid, items):
    with data_lock:
        carts[str(uid)] = items
        save_carts()

def cart_total(items):
    return sum((next((p["price"] for p in PRODUCTS if p["id"]==pid), 0)) * qty
               for pid, qty in items.items())

def cart_text(items):
    lines = []
    for pid, qty in items.items():
        p = next((x for x in PRODUCTS if x["id"] == pid), None)
        if p:
            lines.append(f"{p['emoji']} {p['name']} × {qty} = {p['price']*qty} ₽")
    return "\n".join(lines) if lines else "Корзина пуста"

# ─── VK API ───────────────────────────────────────────────────────
def vk_api(method, **params):
    params.update({"access_token": VK_TOKEN, "v": VK_API_V})
    try:
        r = requests.post(f"https://api.vk.com/method/{method}", data=params, timeout=15)
        resp = r.json()
        if "error" in resp:
            logger.error(f"VK API {method} error: {resp['error']}")
        return resp.get("response")
    except Exception as e:
        logger.error(f"VK API {method} exception: {e}")
        return None

def send_message(user_id, text, keyboard=None):
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": random.randint(0, 2**31),
    }
    if keyboard:
        params["keyboard"] = json.dumps(keyboard, ensure_ascii=False)
    return vk_api("messages.send", **params)

def notify_admin(text):
    if ADMIN_ID:
        send_message(ADMIN_ID, text)

# ─── Клавиатуры ───────────────────────────────────────────────────
def kb_main():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "🛒 Каталог", "payload": '{"cmd":"catalog"}'},  "color": "primary"}],
            [{"action": {"type": "text", "label": "🧺 Корзина", "payload": '{"cmd":"cart"}'},     "color": "secondary"},
             {"action": {"type": "text", "label": "📦 Мои заказы", "payload": '{"cmd":"orders"}'}, "color": "secondary"}],
        ]
    }

def kb_catalog():
    buttons = []
    for p in PRODUCTS:
        buttons.append([{"action": {"type": "text",
            "label": f"{p['emoji']} {p['name']} — {p['price']} ₽",
            "payload": json.dumps({"cmd": "add", "id": p["id"]})}, "color": "secondary"}])
    buttons.append([{"action": {"type": "text", "label": "🧺 В корзину →", "payload": '{"cmd":"cart"}'},  "color": "primary"}])
    buttons.append([{"action": {"type": "text", "label": "« Назад",        "payload": '{"cmd":"back"}'}, "color": "negative"}])
    return {"one_time": False, "buttons": buttons}

def kb_cart(uid):
    items = get_cart(uid)
    buttons = []
    for pid, qty in items.items():
        p = next((x for x in PRODUCTS if x["id"] == pid), None)
        if p:
            buttons.append([
                {"action": {"type": "text", "label": f"− {p['name']}", "payload": json.dumps({"cmd": "remove", "id": pid})}, "color": "negative"},
                {"action": {"type": "text", "label": f"{qty} шт",      "payload": '{"cmd":"noop"}'},                          "color": "secondary"},
                {"action": {"type": "text", "label": f"+ {p['name']}", "payload": json.dumps({"cmd": "add", "id": pid})},    "color": "positive"},
            ])
    if items:
        buttons.append([{"action": {"type": "text", "label": "✅ Оформить заказ", "payload": '{"cmd":"checkout"}'}, "color": "primary"}])
        buttons.append([{"action": {"type": "text", "label": "🗑 Очистить",        "payload": '{"cmd":"clear"}'},    "color": "negative"}])
    buttons.append([{"action": {"type": "text", "label": "« Назад", "payload": '{"cmd":"back"}'}, "color": "secondary"}])
    return {"one_time": False, "buttons": buttons}

# ─── Следующая дата выпечки ───────────────────────────────────────
def next_bake_date():
    now = datetime.now(MSK)
    day_names = ["понедельник","вторник","среду","четверг","пятницу","субботу","воскресенье"]
    py_bake = [(d - 1) % 7 for d in BAKE_WEEKDAYS]
    for i in range(1, 8):
        d = now.replace(hour=0, minute=0, second=0, microsecond=0)
        d = d.__class__(d.year, d.month, d.day, tzinfo=d.tzinfo)
        import datetime as dt
        day = now.date() + dt.timedelta(days=i)
        weekday = day.weekday()
        if weekday in py_bake:
            return f"{day_names[weekday]}, {day.strftime('%d.%m')}"
    return "скоро"

# ─── Заказ ────────────────────────────────────────────────────────
def push_to_sheets(order):
    if not SHEETS_URL:
        return
    try:
        requests.post(SHEETS_URL, json={**order, "_type": "order"}, timeout=15)
    except Exception as e:
        logger.error(f"Sheets push error: {e}")

def create_order(uid, name, phone, address):
    items = get_cart(uid)
    if not items:
        return None
    order_id = "VK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    total = cart_total(items)
    items_list = [{"name": next((p["name"] for p in PRODUCTS if p["id"]==pid), pid),
                   "qty": qty, "subtotal": next((p["price"] for p in PRODUCTS if p["id"]==pid), 0)*qty}
                  for pid, qty in items.items()]
    order = {
        "id": order_id, "channel": "VKontakte",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "status": "Принят", "bakeDate": next_bake_date(),
        "name": name, "phone": phone, "address": address,
        "items": items_list, "total": total,
        "delivery": "Доставка",
        "payment": session.get("draft", {}).get("payment", "При получении"),
        "vkId": str(uid),
    }
    with data_lock:
        orders.append(order)
        save_orders()
    set_cart(uid, {})
    threading.Thread(target=push_to_sheets, args=(order,), daemon=True).start()
    return order

# ─── Сессии ───────────────────────────────────────────────────────
def get_session(uid):
    if uid not in sessions:
        sessions[uid] = {"stage": "idle", "draft": {}}
    return sessions[uid]

# ─── Обработчик сообщений ─────────────────────────────────────────
def handle_message(user_id, text, payload):
    uid = str(user_id)
    session = get_session(uid)
    text = (text or "").strip()
    cmd = payload.get("cmd") if payload else None
    pid = payload.get("id") if payload else None
    logger.info(f"VK msg uid={user_id} text='{text}' cmd={cmd} payload={payload}")

    # Выбор оплаты через кнопку (cmd=pay) — обрабатываем в любом stage
    if cmd == "pay" and payload and payload.get("val"):
        payment = payload.get("val")
        session["draft"]["payment"] = payment
        session["stage"] = "idle"
        name    = session["draft"].get("name", "")
        phone   = session["draft"].get("phone", "")
        address = session["draft"].get("address", "")
        order   = create_order(uid, name, phone, address)
        if order:
            lines = "\n".join(f"{i['name']} × {i['qty']}" for i in order["items"])
            send_message(user_id,
                f"✅ Заказ #{order['id']} принят!\n\n"
                f"📋 Состав:\n{lines}\n\n"
                f"💰 Сумма: {order['total']} ₽\n"
                f"🗓 Выпечка: {order['bakeDate']}\n"
                f"💳 Оплата: {payment}\n"
                f"📞 Свяжемся по номеру {phone}\n\nСпасибо! 🙏", kb_main())
            notify_admin(
                f"🔔 Новый заказ VK #{order['id']}\n"
                f"👤 {name} · {phone}\n📍 {address}\n"
                f"💳 {payment} · 💰 {order['total']} ₽ · {order['bakeDate']}"
            )
        return

    if cmd == "catalog" or text.lower() in ["каталог", "меню", "хлеб"]:
        menu = "🍞 Наш хлеб на закваске:\n\n"
        for p in PRODUCTS:
            menu += f"{p['emoji']} {p['name']} — {p['price']} ₽ / {p['weight']} г\n"
        menu += "\nНажмите на хлеб чтобы добавить в корзину 👇"
        send_message(user_id, menu, kb_catalog())
        return

    if cmd == "add" and pid:
        items = get_cart(uid)
        items[pid] = items.get(pid, 0) + 1
        set_cart(uid, items)
        p = next((x for x in PRODUCTS if x["id"] == pid), None)
        if p:
            send_message(user_id,
                f"✅ {p['name']} добавлен!\nВсего: {sum(items.values())} шт на {cart_total(items)} ₽",
                kb_catalog())
        return

    if cmd == "remove" and pid:
        items = get_cart(uid)
        if items.get(pid, 0) > 1:
            items[pid] -= 1
        else:
            items.pop(pid, None)
        set_cart(uid, items)
        if items:
            send_message(user_id, f"🧺 Корзина:\n\n{cart_text(items)}\n\n💰 Итого: {cart_total(items)} ₽", kb_cart(uid))
        else:
            send_message(user_id, "Корзина пуста", kb_main())
        return

    if cmd == "cart" or text.lower() in ["корзина", "заказ"]:
        items = get_cart(uid)
        if not items:
            send_message(user_id, "🧺 Корзина пуста\n\nВыберите хлеб в каталоге 👇", kb_main())
        else:
            send_message(user_id,
                f"🧺 Ваша корзина:\n\n{cart_text(items)}\n\n💰 Итого: {cart_total(items)} ₽",
                kb_cart(uid))
        return

    if cmd == "clear":
        set_cart(uid, {})
        send_message(user_id, "🗑 Корзина очищена", kb_main())
        return

    if cmd == "checkout" or text.lower() in ["оформить", "заказать"]:
        items = get_cart(uid)
        if not items:
            send_message(user_id, "Корзина пуста. Выберите хлеб сначала.", kb_main())
            return
        session["stage"] = "awaiting_name"
        session["draft"] = {}
        send_message(user_id,
            f"📝 Оформление заказа\n\n{cart_text(items)}\n💰 Итого: {cart_total(items)} ₽\n\nВведите ваше имя:")
        return

    if cmd == "orders" or text.lower() in ["заказы", "мои заказы"]:
        my = [o for o in orders if str(o.get("vkId", "")) == uid
              or str(o.get("phone","")).replace("+","").endswith(uid[-6:] if len(uid)>6 else uid)][-5:]
        if not my:
            send_message(user_id, "У вас пока нет заказов.\n\nСделайте первый заказ через каталог 🍞", kb_main())
        else:
            out = "📦 Ваши заказы:\n\n"
            for o in reversed(my):
                out += f"#{o['id']} — {o['status']}\n{o.get('bakeDate','?')} · {o['total']} ₽\n\n"
            send_message(user_id, out, kb_main())
        return

    if cmd in ("back", "start") or text.lower() in ["/start", "старт", "начало", "привет", "start"]:
        session["stage"] = "idle"
        send_message(user_id,
            "👋 Привет! Я бот пекарни Масса Матере 🍞\n\n"
            "Хлеб на закваске — выпечка вт/чт/сб.\n"
            "Следующая выпечка: " + next_bake_date() + "\n\n"
            "Выберите действие:", kb_main())
        return

    if session["stage"] == "awaiting_name":
        session["draft"]["name"] = text
        session["stage"] = "awaiting_phone"
        send_message(user_id, f"Спасибо, {text}! Введите номер телефона:")
        return

    if session["stage"] == "awaiting_phone":
        session["draft"]["phone"] = text
        session["stage"] = "awaiting_address"
        send_message(user_id, "Введите адрес доставки (или «самовывоз»):")
        return

    if session["stage"] == "awaiting_address":
        session["draft"]["address"] = text
        session["stage"] = "awaiting_payment"
        send_message(user_id,
            "Выберите способ оплаты:",
            {"one_time": True, "buttons": [
                [{"action": {"type": "text", "label": "💵 Наличными", "payload": '{"cmd":"pay","val":"Наличными"}'}, "color": "secondary"}],
                [{"action": {"type": "text", "label": "💳 Картой при получении", "payload": '{"cmd":"pay","val":"Картой при получении"}'}, "color": "secondary"}],
                [{"action": {"type": "text", "label": "📱 СБП", "payload": '{"cmd":"pay","val":"СБП"}'}, "color": "secondary"}],
            ]})
        return

    if session["stage"] == "awaiting_payment":
        # Если payload с cmd=pay уже обработан выше — сюда не дойдём
        # Fallback: пользователь написал текст вместо кнопки
        payment = text if text else "При получении"
        session["draft"]["payment"] = payment
        session["stage"] = "idle"
        name    = session["draft"].get("name", "")
        phone   = session["draft"].get("phone", "")
        address = session["draft"].get("address", "")
        order   = create_order(uid, name, phone, address)
        if order:
            lines = "\n".join(f"{i['name']} × {i['qty']}" for i in order["items"])
            send_message(user_id,
                f"✅ Заказ #{order['id']} принят!\n\n"
                f"📋 Состав:\n{lines}\n\n"
                f"💰 Сумма: {order['total']} ₽\n"
                f"🗓 Выпечка: {order['bakeDate']}\n"
                f"💳 Оплата: {payment}\n"
                f"📞 Свяжемся по номеру {phone}\n\nСпасибо! 🙏", kb_main())
            notify_admin(
                f"🔔 Новый заказ VK #{order['id']}\n"
                f"👤 {name} · {phone}\n📍 {address}\n"
                f"💳 {payment} · 💰 {order['total']} ₽ · {order['bakeDate']}"
            )
        return

    send_message(user_id, "Используйте кнопки меню 👇", kb_main())

# ─── Long Poll ────────────────────────────────────────────────────
def get_long_poll_server():
    resp = vk_api("groups.getLongPollServer", group_id=VK_GROUP_ID)
    if not resp:
        return None, None, None
    return resp.get("server"), resp.get("key"), resp.get("ts")

def long_poll_loop():
    logger.info("VK Long Poll: запускаю цикл...")
    server, key, ts = get_long_poll_server()
    if not server:
        logger.error("Не удалось получить Long Poll сервер")
        return

    while True:
        try:
            r = requests.get(server, params={"act": "a_check", "key": key, "ts": ts, "wait": 25}, timeout=30)
            data = r.json()

            if "failed" in data:
                failed = data["failed"]
                logger.warning(f"Long Poll failed={failed}")
                if failed == 1:
                    ts = data.get("ts", ts)
                elif failed in (2, 3):
                    server, key, ts = get_long_poll_server()
                    if not server:
                        time.sleep(5)
                continue

            ts = data.get("ts", ts)
            for event in data.get("updates", []):
                if event.get("type") == "message_new":
                    msg = event.get("object", {}).get("message", {})
                    user_id = msg.get("from_id")
                    text    = msg.get("text", "")
                    raw_payload = msg.get("payload", "{}")
                    try:
                        if isinstance(raw_payload, dict):
                            payload = raw_payload
                        else:
                            payload = json.loads(raw_payload or "{}")
                    except Exception:
                        payload = {}
                    logger.info(f"VK event uid={user_id} text='{text}' payload={payload}")
                    if user_id and user_id > 0:
                        threading.Thread(target=handle_message, args=(user_id, text, payload), daemon=True).start()

        except requests.exceptions.Timeout:
            continue
        except Exception as e:
            logger.error(f"Long Poll error: {e}")
            time.sleep(5)
            server, key, ts = get_long_poll_server()

# ─── Flask health check ───────────────────────────────────────────
app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify({"status": "ok", "mode": "longpoll", "products": len(PRODUCTS)})

@app.route("/")
def index():
    return jsonify({"bot": "Масса Матере VK Long Poll", "status": "running"})

# ─── Старт ────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Long Poll в отдельном потоке
    lp_thread = threading.Thread(target=long_poll_loop, daemon=True)
    lp_thread.start()

    PORT = int(os.getenv("PORT", 8080))
    logger.info(f"VK Long Poll бот запущен на порту {PORT}")
    from waitress import serve
    serve(app, host="0.0.0.0", port=PORT)
