# Масса Мадре — журнал решений

> Репозиторий: `Sourdough-Bakery` · Версия: 0.1 · Дата: 2026-09-22
> Статус: ЧЕРНОВИК — собран по рабочим записям, **не по коду**. Перед использованием сверить с репозиторием (см. `docs/VERIFY_PROMPT.md`). Метка ⟦уточнить⟧ — факт неизвестен.
> Новые — в конец.


## ⟦дата⟧ — Render Web Service для бота
Нужен публичный HTTP API для синхронизации корзины, поэтому не Background Worker.

## ⟦дата⟧ — Сайт: Render Static Site, всё в `website/` (вариант A)
Без разделения на GitHub Pages.

## 2026-07-25 — Кабинет продавца: Ozon-first + элементы WB

## ⟦дата⟧ — Google Sheets — единый источник истины

## ⟦дата⟧ — Каноническое название «Масса Мадре»

## ⟦дата⟧ — Вход в Систему: вариант 2
Своя витрина + коннектор, расчёты в Системе.

## 2026-09-23 — Без docs/RULES.md: инварианты в SPEC, DECISIONS и CLAUDE.md
**Решение:** в Sourdough-Bakery файла docs/RULES.md не будет. Ревью сверяет инварианты по docs/SPEC.md, docs/DECISIONS.md и CLAUDE.md.
**Почему:** RULES.md ведётся только в репозитории marketplace-api. Ссылка на него пришла из общего комплекта конфигурации и здесь вела на несуществующий файл.
**Что меняет:** из .claude/agents/reviewer.md и .claude/commands/audit.md убраны упоминания RULES.md. В audit.md вместо него в список документов для подагента добавлен CLAUDE.md. Код и поведение сайта и ботов не меняются. Копии этих файлов в комплекте (~/Downloads/sourdough-kit) по-прежнему упоминают RULES.md, поэтому повторная загрузка комплекта вернёт старые ссылки.
**Отменяет:** —

## 2026-09-23 — Сервисы Render: корневой render.yaml — источник истины
**Решение:** конфигурация сервисов Render описывается только в корневом render.yaml (Blueprint): sourdough-bakery-website и sourdough-bakery-bot. Файл telegram-bot-python/render.yaml удаляется; vk-bot/vk-render.yaml удаляется в задаче добавления VK-бота в корневой render.yaml, когда его переменные переедут туда. VK-бот Sourdough-Bakery-vk-bot, созданный в панели Render вручную вне Blueprint, отдельной задачей добавляется в корневой render.yaml, чтобы конфигурация всех трёх сервисов жила в репозитории.
**Почему:** Render эти файлы не использует, а имена сервисов в них (sourdough-bakery-bot-python, massa-madre-vk-bot) не совпадают с реальными, поэтому они вводят в заблуждение.
**Что меняет:** удаляется telegram-bot-python/render.yaml, его упоминания в telegram-bot-python/README.md ведут на корневой render.yaml. В docs/ARCHITECTURE.md снимается метка ⟦уточнить⟧ о расхождении имён, а в разделе «Сборка» исправляется «render.yaml в корне и в каждой папке». В docs/PAGES.md исправляются упоминания render.yaml у telegram-bot-python/ и vk-bot/. В CLAUDE.md:50 и MONOREPO_RENDER.md убираются упоминания render.yaml в папках. Код и поведение сервисов не меняются. Отдельная задача: блок VK-бота в корневом render.yaml.
**Отменяет:** —

## 2026-09-24 — Устройство massamadre.ru: главная — catalog.html
**Решение:** главная сайта — website/catalog.html: build.sh копирует её в index.html, она открывается по корню домена. Из каталога покупатель переходит к оформлению заказа на sourdough-shop.html; там же чат ИИ: страница вызывает /api/ask-faq бота, ключ ANTHROPIC_API_KEY лежит только в Environment сервиса sourdough-bakery-bot на Render — в страницах и в репозитории его нет и быть не должно. Бэкофис — cabinet-*.html (товары, склад/FBS, цены, заказы, аналитика, воронка, продвижение, отзывы) и schedule.html, открываются по прямым адресам вида massamadre.ru/cabinet-orders.html. Telegram-бот @Sourdough_Bakery_Bot вызывается из каталога и из оформления, заказы можно делать и в боте; бот и sourdough-shop.html работают на одну корзину. Хук guard.py защищает catalog.html и sourdough-shop.html.
**Почему:** владелец проверил устройство сайта 24.09.2026. Сборка уже публикует catalog.html по корню, а прежнее правило «главная — sourdough-shop.html» не совпадало ни с кодом, ни с реальным сайтом.
**Что меняет:** в CLAUDE.md правило «главная — sourdough-shop.html» заменяется правилом о двух защищённых страницах: catalog.html (главная) и sourdough-shop.html (оформление заказа); добавляется правило о ключе ANTHROPIC_API_KEY. В .claude/hooks/guard.py защита распространяется на catalog.html, в test_guard.py добавляются тесты. docs/PAGES.md и docs/ARCHITECTURE.md приводятся к новому устройству, schedule.html переносится в бэкофис. В docs/STATUS.md закрывается расхождение «Главная — sourdough-shop.html». Код сайта и сборка не меняются.
**Отменяет:** правило «sourdough-shop.html — главная, голый домен редиректит сюда» из CLAUDE.md; в журнале решений записи о нём не было.
