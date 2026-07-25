#!/usr/bin/env bash
# Build-скрипт для Render Static Site.
# Подставляет BOT_API_URL и REVIEWS_API_URL в HTML-файлы при сборке.

set -e

# ─── BOT_API_URL ───
if [ -z "$BOT_API_URL" ] && [ -n "$BOT_HOST" ]; then
  BOT_API_URL="https://${BOT_HOST}.onrender.com"
  echo "BOT_API_URL собран из BOT_HOST: $BOT_API_URL"
fi

if [ -z "$BOT_API_URL" ]; then
  echo "ВНИМАНИЕ: BOT_API_URL не задан — поле адреса бота останется пустым."
else
  echo "BOT_API_URL=$BOT_API_URL"
fi

# ─── Подстановка BOT_API_URL ───
sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" sourdough-shop.html
sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" sourdough-showcase.html
sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" sourdough-admin.html
sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" card-*.html 2>/dev/null || true

# ─── REVIEWS_API_URL ───
if [ -n "$REVIEWS_API_URL" ]; then
  echo "REVIEWS_API_URL=$REVIEWS_API_URL"
  sed -i "s|__REVIEWS_API_URL__|${REVIEWS_API_URL}|g" reviews-widget.html 2>/dev/null || true
  sed -i "s|__REVIEWS_API_URL__|${REVIEWS_API_URL}|g" card-*.html 2>/dev/null || true
else
  echo "REVIEWS_API_URL не задан — виджет отзывов покажет демо-данные."
fi

# ─── index.html = shop ───
cp sourdough-shop.html index.html

echo "Сборка завершена."
