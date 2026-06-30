#!/usr/bin/env bash
# Build-скрипт для Render Static Site.
# Render выполняет этот файл перед публикацией (buildCommand в render.yaml) и
# подставляет значение переменной окружения BOT_API_URL прямо в HTML —
# конечному пользователю не нужно вручную вписывать адрес бота в настройках (⚙).
#
# Как это работает: в sourdough-shop.html зашит плейсхолдер __BOT_API_URL__ (ровно
# одно вхождение, в строке присвоения переменной). Подстановка выполняется ВСЕГДА,
# даже если BOT_API_URL не задана — тогда подставляется пустая строка, и сайт ведёт
# себя как раньше: адрес можно вписать вручную в настройках (⚙).

set -e

# Приоритет: явно заданный BOT_API_URL (например, для кастомного домена бота) важнее
# автоматически собранного из BOT_HOST (тот появляется через fromService в render.yaml
# при деплое монорепозитория, см. корневой render.yaml в репозитории).
if [ -z "$BOT_API_URL" ] && [ -n "$BOT_HOST" ]; then
  BOT_API_URL="https://${BOT_HOST}.onrender.com"
  echo "BOT_API_URL не задан явно — собрал из BOT_HOST: $BOT_API_URL"
fi

if [ -z "$BOT_API_URL" ]; then
  echo "ВНИМАНИЕ: ни BOT_API_URL, ни BOT_HOST не заданы — поле 'Адрес сервера"
  echo "бота' в настройках (⚙) останется пустым, пользователю придётся вписать его вручную."
else
  echo "Подставляю BOT_API_URL=$BOT_API_URL в sourdough-shop.html"
fi

# sed с разделителем | (а не /), т.к. в самом URL есть символ / — выполняется в любом
# случае: при пустой $BOT_API_URL подставится пустая строка.
sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" sourdough-shop.html

# Публикуем тот же файл ещё и как index.html — так сайт открывается по корню домена
# (https://ваш-сайт.onrender.com/) без необходимости настраивать routes/rewrite.
cp sourdough-shop.html index.html

echo "Сборка завершена."
