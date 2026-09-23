# Масса Мадре — архитектура

> Репозиторий: `Sourdough-Bakery` · Версия: 0.2 · Дата: 2026-09-24
> Статус: сверен с кодом 2026-09-24 (`/verify`). Метка ⟦уточнить⟧ — факт не виден из репозитория.
> Расхождения «должно быть ≠ есть» — в `docs/STATUS.md`, раздел «Расхождения».


## Состав
| Компонент | Технология | Примечание |
|---|---|---|
| Сайт | статика, папка `website/` | главная — каталог `catalog.html` (по корню домена), оформление заказа `sourdough-shop.html` с чатом ИИ, карточки, бэкофис (9 страниц `cabinet-*` и `schedule.html`), админ-панель, taplink, витрина-киоск |
| Telegram-бот | Python 3.12.7, Flask + Waitress, `telegram-bot-python/main.py` | Render Web Service: HTTP API для сайта (корзина, стоп-лист, FAQ-консультант, оплата) + webhook Telegram |
| VK-бот | Python, Flask + Waitress, `vk-bot/vk_bot.py` | **Long Poll** (не Callback): каталог, корзина, заказ, «Мои заказы», оплата только при получении |
| MAX-бот | — | кода нет |
| Данные | Google Sheets + Apps Script (один URL для заказов, отзывов, товаров, статистики) | копия скрипта в репозитории отстаёт от развёрнутой — см. ниже |

### HTTP API Telegram-бота (`main.py`)
GET `/api/health` · GET/POST `/api/cart/<phone>` · POST `/api/cart/<phone>/clear` · GET `/api/stock` ·
POST `/api/ask-faq` · GET `/api/orders/<phone>` · POST `/api/notify-order` · POST `/api/create-payment` ·
POST `/api/yookassa-webhook` · POST `/api/yoomoney-webhook` · POST `/telegram-webhook` · GET `/`.
Кто вызывает: `sourdough-shop.html` (корзина, стоп-лист, FAQ, заказы, оплата), `catalog.html` (корзина),
`sourdough-admin.html` (`/api/health`),
`sourdough-showcase.html` (`/api/stock`).
Ключ `ANTHROPIC_API_KEY` — только в Environment сервиса `sourdough-bakery-bot` на Render (`render.yaml`: `sync: false`);
чат сайта ходит через `/api/ask-faq`, в страницах и репозитории ключа нет (DECISIONS, 2026-09-24).

### Apps Script
- Переменные: бот — `SHEETS_WEBHOOK_URL`, `REVIEWS_WEBHOOK_URL` (по умолчанию = первый); VK-бот — `SHEETS_WEBHOOK_URL`;
  сайт — `REVIEWS_API_URL`, `ORDERS_API_URL` (по умолчанию = `REVIEWS_API_URL`).
- `telegram-bot-python/sheets-unified-api.gs` — копия в репозитории: GET `orders`, `reviews`, `stats`;
  POST `_type` = `order` (по умолчанию), `review`, `status`.
- Клиенты вызывают больше, чем умеет эта копия: GET `products`, `products&id=`, `schedule`, `baketask`;
  POST `_type` = `product`, `prices`, `stock`, `bake_plan`, `schedule`, `review_action`, `review_reply`,
  `payment_status`, `ask`. Значит, развёрнут более новый скрипт, которого в репозитории нет ⟦уточнить: выгрузить
  развёрнутый код в репозиторий⟧.
- `telegram-bot-python/reviews-apps-script.gs` — прежний отдельный скрипт отзывов; по заголовку unified-скрипта заменён им.

## Сборка
Монорепозиторий: сайт, Telegram-бот и VK-бот — отдельные сервисы Render из одного репозитория (Blueprint — корневой `render.yaml`; порядок описан в `MONOREPO_RENDER.md`).
`website/build.sh` (в папке website, не в корне) с `safe_replace` заменяет плейсхолдеры при сборке:
- `__BOT_API_URL__` → `sourdough-shop.html`, `sourdough-showcase.html`, `sourdough-admin.html`, `catalog.html`, `card-*.html`
  (а также `shop.html`, `showcase.html`, `admin.html`, которых в `website/` нет);
- `__REVIEWS_API_URL__` → `reviews-widget.html`, `catalog.html`, `card.html`, `schedule.html`, `sourdough-shop.html`, `card-*.html`;
- `__ORDERS_API_URL__` → `cabinet-orders.html`, `cabinet-analytics.html`.
Фактически плейсхолдеры `__REVIEWS_API_URL__` есть только в `reviews-widget.html` и `card-*.html`; адрес Apps Script
вписан прямо в 13 страниц (`catalog`, `card`, `schedule`, `sourdough-shop`, все `cabinet-*`) — см. «Расхождения».
В конце `build.sh` копирует `catalog.html` в `index.html` (если его нет — `sourdough-shop.html`): каталог — главная
сайта (DECISIONS, 2026-09-24). Хук `guard.py` защищает `catalog.html` и `sourdough-shop.html`.

## Сервисы Render
Три сервиса работают как одна система:
| Сервис | Назначение | Папка |
|---|---|---|
| `sourdough-bakery-website` | сайт | `website/` |
| `sourdough-bakery-bot` | Telegram-бот | `telegram-bot-python/` |
| `Sourdough-Bakery-vk-bot` | VK-бот | `vk-bot/` |

Адрес бота сайт получает при сборке через `BOT_HOST`: корневой `render.yaml` передаёт слаг сервиса
`sourdough-bakery-bot`, `website/build.sh` собирает из него `https://<BOT_HOST>.onrender.com`
(если `BOT_API_URL` задан явно — берётся он).
VK-бот создан в панели Render вручную и в корневом `render.yaml` пока не описан — добавить отдельной задачей
(см. DECISIONS, 2026-09-23).

## Хостинг и домен
massamadre.ru — Reg.ru, A-запись → 216.24.57.9 (Render) ⟦уточнить: DNS из репозитория не виден⟧.
Решение: Render Static Site, всё в `website/`. Следов GitHub Pages в репозитории нет (нет `CNAME` и workflow);
с GitHub берутся только фото товаров — `raw.githubusercontent.com/kuzin4u/Sourdough-Bakery/main/assets/…`.

## Решённые проблемы (не повторять расследования)
Python 3.12.7 (`runtime.txt` + `PYTHON_VERSION`) и asyncio; Waitress для продакшена; секрет вебхука —
`secrets.token_urlsafe(32)`, если `WEBHOOK_SECRET` не задан; Apps Script standalone vs container-bound;
CORS — POST в Apps Script с `Content-Type: text/plain`.
