# Масса Мадре — статус

> Репозиторий: `Sourdough-Bakery` · Версия: 0.2 · Дата: 2026-09-24
> Статус: фазы — по рабочим записям до 21.08.2026; отметки о коде сверены 2026-09-24 (`/verify`). Метка ⟦уточнить⟧ — факт не виден из репозитория.


## Фаза 1 (волна 3.5, ~85%)
Готово (есть в коде): 4 карточки Ozon-формата с фото, аналитика из Sheets (кабинет, `?action=stats`),
управление заказами (бот + `cabinet-orders`), card.html, catalog.html с синхронизацией корзины, отзывы,
расписание, таймер (catalog.html), рассылка перед выпечкой, напоминания о брошенной корзине, VK-бот (код).
VK-бот развёрнут ⟦уточнить: из репозитория не видно⟧.
Осталось:
- [ ] ~~Подтверждение VK-бота (поддомен vk.massamadre.ru).~~ VK-бот работает через Long Poll — Callback и
      подтверждение сервера ему не нужны (см. «Расхождения»).
- [ ] MAX-бот (кода нет).
- [ ] Полный тест цикла.

## Фаза 2
- [ ] massamadre.online — кондитерское направление SeMaVi (не начато).

## Фаза 3
- LuckLyrics лендинг RU/EN/PT сделан ⟦уточнить: DNS, в репозитории лендинга нет⟧.

## Интеграция с Системой
- [ ] Выбрать механизм расчёта.
- [ ] Решить: один или два потока в cabinet-orders.
- [ ] Коннектор Sheets → API (source=EXTERNAL): в репозитории коннектора нет; развёрнутый Apps Script — расширить.

## Следующая сессия
Выгрузить развёрнутый Apps Script в репозиторий — от этого зависят остальные расхождения.

## Расхождения
Сверка 2026-09-24. Слева — «должно быть» (SPEC, DECISIONS, CLAUDE.md), справа — «есть» (код).

| Приоритет | Должно быть | Есть в коде | Где |
|---|---|---|---|
| критично | Копия Apps Script в репозитории = развёрнутый скрипт; товары — лист «Товары» через него | Копия умеет только `orders`, `reviews`, `stats` и POST `order`/`review`/`status`; листа «Товары» не читает. Страницы и боты вызывают `products`, `schedule`, `baketask` и POST `product`, `prices`, `stock`, `bake_plan`, `schedule`, `review_action`, `review_reply`, `payment_status`, `ask`. Если развернуть копию из репозитория — каталог и кабинет сломаются, а неизвестные POST запишутся как заказы | `telegram-bot-python/sheets-unified-api.gs` |
| ~~критично~~ закрыто 2026-09-24 | ~~Главная — `sourdough-shop.html`, голый домен ведёт на неё (CLAUDE.md)~~ | Решение 2026-09-24: главная — `catalog.html` (как в `build.sh`), `sourdough-shop.html` — оформление заказа; CLAUDE.md и хук приведены к этому | `website/build.sh`, `CLAUDE.md`, `.claude/hooks/guard.py` |
| критично | Адреса API в страницах — только плейсхолдеры, их подставляет `build.sh` (CLAUDE.md) | Адрес Apps Script `script.google.com/…/exec` вписан в 13 страниц; `build.sh` для них ничего не подставляет. Хук ловит только `*.onrender.com` | `catalog`, `card`, `schedule`, `sourdough-shop`, все 9 `cabinet-*.html` |
| важно | Данные товаров не дублируются в коде (CLAUDE.md, решение «Google Sheets — единый источник истины») | Каталог с ценами зашит в 5 местах как запасной; в `sourdough-admin.html` и `sourdough-showcase.html` — старый товар 740 г / 400 ₽ | `config.json`, `catalog.html`, `sourdough-shop.html`, `main.py`, `vk_bot.py` |
| важно | Каноническое название «Масса Мадре» (решение) | «Масса Матере» — в 20 файлах, включая оба бота и `config.json`; «Масса Мадре» — только в `cabinet-orders`, `cabinet-analytics`, `alpha-demo-standalone` | `website/*.html`, `main.py`, `vk_bot.py`, `config.json` |
| важно | Товары SKU-001…SKU-004 (SPEC, DATA_MODEL) | В коде id `wheat`, `rye`, `wholegrain`, `seeds`; `SKU-00x` не встречается | все места каталога |
| важно | FAQ = факты о товарах | FAQ: буханка 740 г за 400 ₽; в каталоге такого товара нет. Сроки хранения, брожения и калорийность на `card-*.html` расходятся с FAQ и базой знаний бота | `docs/FAQ_unified.md:94–100`, `card-*.html` |
| важно | Админ-панель защищена | Пароль проверяется только в браузере, пароль по умолчанию лежит в коде страницы | `website/sourdough-admin.html:285` |
| позже | VK-бот: подтверждение Callback через vk.massamadre.ru (STATUS, ARCHITECTURE до сверки) | VK-бот на Long Poll; `VK_SECRET`, `VK_CONFIRM_CODE` в `vk-render.yaml` не нужны | `vk-bot/vk_bot.py:4` |
| позже | VK-бот описан в корневом `render.yaml` (решение 2026-09-23) | Описан только в `vk-bot/vk-render.yaml` | `render.yaml` |
| позже | Описания сервисов только в корневом `render.yaml` | `website/render.yaml` дублирует сервис сайта (с `BOT_API_URL`) | `website/render.yaml` |
| позже | `build.sh` обрабатывает существующие страницы | В списках `shop.html`, `showcase.html`, `admin.html` — таких файлов нет | `website/build.sh` |
| позже | Докстринги соответствуют коду | `main.py:4` упоминает только ЮKassa (есть и ЮMoney); `website/README.md` и `render.yaml` ссылаются на несуществующий `telegram-bot-node/` | `main.py`, `website/README.md`, `render.yaml:6–7`, `MONOREPO_RENDER.md` |
| ~~позже~~ закрыто 2026-09-24 | ~~Хук не мешает чтению~~ | Условие сужено: в shell блокируется только запись, где защищённая страница — цель (`>`/`>>` перед именем, `sed -i`, `tee`, `cp` в неё, `mv`, `rm`, `truncate`, `dd of=`); три ложных срабатывания сессии добавлены в тесты | `.claude/hooks/guard.py`, `test_guard.py` |
