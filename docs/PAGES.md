# Масса Мадре — страницы и структура репозитория

> Репозиторий: `Sourdough-Bakery` · Версия: 0.4 · Дата: 2026-09-24
> Составлено по реальному дереву файлов, сверено с кодом 2026-09-24 (`/verify`); устройство сайта подтверждено владельцем
> 24.09.2026 (DECISIONS, 2026-09-24). Метка ⟦уточнить⟧ — факт не виден из репозитория.

## Путь покупателя
massamadre.ru → `catalog.html` (главная, `index.html`) → выбор товара → `sourdough-shop.html` (оформление заказа, чат ИИ)
→ заказ. Из каталога и из оформления можно перейти в Telegram-бот @Sourdough_Bakery_Bot и заказать там;
корзина общая — хранится в боте (`/api/cart`).

## Корень
| Путь | Что это |
|---|---|
| `render.yaml` | Blueprint Render: сервисы `sourdough-bakery-bot` и `sourdough-bakery-website` |
| `MONOREPO_RENDER.md` | Как устроен монорепозиторий и деплой |
| `README.md` | Описание проекта |
| `semavi_deployment_map.png` | Схема развёртывания SeMaVi |
| `.gitignore` | Создан при установке конфигурации Claude (журнал хуков, .DS_Store) |

## Папки
| Папка | Содержимое |
|---|---|
| `website/` | Сайт: каталог, оформление заказа, карточки, кабинет, админ-панель, сборка |
| `telegram-bot-python/` | Telegram-бот (main.py), `sheets-unified-api.gs` (копия Apps Script, отстаёт от развёрнутой), `reviews-apps-script.gs` (прежний скрипт отзывов), requirements.txt, runtime.txt (сервис описан в корневом render.yaml) |
| `vk-bot/` | VK-бот (vk_bot.py) и зависимости; сервис создан в панели Render вручную; `vk-render.yaml` — не используется Render, удаляется при переносе VK-бота в корневой render.yaml |
| `assets/` | Фото хлеба (Тартин, Заварной, Тартин сырный, Бородинский), логотип, ХЛЕБ.pdf |
| `docs/` | FAQ_unified.md + документы ядра (этот набор) |

## Страницы покупателя (`website/`)
| Файл | Назначение |
|---|---|
| `catalog.html` | **Главная сайта.** Каталог в формате Ozon, таймер до выпечки, корзина (синхронизация через `/api/cart` бота), ссылка на бота. При сборке копируется в `index.html` — открывается по корню домена. Защищена хуком `guard.py` |
| `sourdough-shop.html` | **Оформление заказа.** Корзина, стоп-лист, чат ИИ (`/api/ask-faq` бота; ключ Anthropic — только на сервере бота, в странице его нет), оплата (`/api/create-payment`), «Мои заказы», ссылка на бота. `catalog.html` переводит сюда корзину. Защищена хуком `guard.py` |
| `card.html` | Универсальная карточка товара из Sheets (`card.html?id=`) |
| `card-tartin.html`, `card-zavarnoj.html`, `card-syrnyj.html`, `card-borodinskij.html` | Статические карточки четырёх товаров. Используются: `catalog.html` ссылается на них через поле `card` (из `config.json` или встроенного списка), без поля — на `card.html?id=`; на них же ссылается `sourdough-shop.html` |
| `sourdough-showcase.html` | Витрина-киоск (стоп-лист через `/api/stock` бота) |
| `taplink.html` | Страница ссылок: бот, магазин, витрина, промокод |
| `reviews-widget.html` | Виджет отзывов |
| `alpha-demo-standalone.html` | Автономное демо конфигуратора каналов Системы |

## Бэкофис (`website/cabinet-*.html`, `schedule.html`) и админ-панель
Открываются по прямым адресам: massamadre.ru/cabinet-orders.html и т. д.
`cabinet-orders` (заказы) · `cabinet-products` (товары) · `cabinet-card` (карточка) ·
`cabinet-prices` (цены) · `cabinet-stock` (склад / FBS, план выпечки) · `cabinet-promo` (продвижение) ·
`cabinet-reviews` (отзывы) · `cabinet-analytics` (аналитика) · `cabinet-funnel` (воронка) ·
`schedule.html` (расписание выпечки, `?action=schedule`) —
кабинет SeMaVi; работает **напрямую с Apps Script** (товары, цены, остатки, заказы, статистика, отзывы, расписание).
`sourdough-admin.html` — панель пекарни: работает **с API бота** (`/api/health`), хранит в браузере адреса бота
и Apps Script, модель Claude и пароль входа (проверка пароля — только в браузере).

## Служебное в `website/`
| Файл | Назначение |
|---|---|
| `build.sh` | Сборка: заменяет плейсхолдеры `__BOT_API_URL__`, `__REVIEWS_API_URL__`, `__ORDERS_API_URL__` (safe_replace) и копирует `catalog.html` в `index.html`. **Лежит в `website/`, не в корне** |
| `config.json` | Бренд, ссылка на бота, дни выпечки, промокоды REELS и ЗАВТРА, каталог из 4 товаров — запасной источник для `catalog.html`, если Sheets недоступен |
| `render.yaml` | Старое описание сервиса сайта (с `BOT_API_URL`); дублирует блок в корневом `render.yaml` |
| `README.md` | Инструкция по деплою сайта |
| `cabinet_old/` | Прежняя версия кабинета (admin, index, shop, showcase) — архив, не трогать |

## Правила
- `catalog.html` и `sourdough-shop.html` не редактируются без явного «да» владельца (хук; разрешение — `ALLOW_MAIN_EDIT=1`).
- Адреса API в страницах запрещены — только плейсхолдеры, их подставляет `website/build.sh` (хук ловит только `*.onrender.com`).
- Данные товаров — в Google Sheets, не в коде страниц.
