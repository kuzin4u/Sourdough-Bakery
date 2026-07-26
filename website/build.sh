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
# Поддерживаем оба варианта имён (sourdough-* и короткие)
for f in sourdough-shop.html shop.html sourdough-showcase.html showcase.html sourdough-admin.html admin.html; do
  [ -f "$f" ] && sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" "$f" && echo "  → $f"
done
sed -i "s|__BOT_API_URL__|${BOT_API_URL}|g" card-*.html 2>/dev/null || true

# ─── REVIEWS_API_URL ───
if [ -n "$REVIEWS_API_URL" ]; then
  echo "REVIEWS_API_URL=$REVIEWS_API_URL"
  [ -f "reviews-widget.html" ] && sed -i "s|__REVIEWS_API_URL__|${REVIEWS_API_URL}|g" reviews-widget.html
  sed -i "s|__REVIEWS_API_URL__|${REVIEWS_API_URL}|g" card-*.html 2>/dev/null || true
else
  echo "REVIEWS_API_URL не задан — виджет отзывов покажет демо-данные."
fi

# ─── ORDERS_API_URL (кабинет продавца) ───
ORDERS_API_URL="${ORDERS_API_URL:-$REVIEWS_API_URL}"
if [ -n "$ORDERS_API_URL" ]; then
  echo "ORDERS_API_URL=$ORDERS_API_URL"
  [ -f "cabinet-orders.html" ] && sed -i "s|__ORDERS_API_URL__|${ORDERS_API_URL}|g" cabinet-orders.html
  [ -f "cabinet-analytics.html" ] && sed -i "s|__ORDERS_API_URL__|${ORDERS_API_URL}|g" cabinet-analytics.html
else
  echo "ORDERS_API_URL не задан — кабинет покажет заглушку."
fi

# ─── index.html = магазин ───
# Поддерживаем оба имени
if [ -f "sourdough-shop.html" ]; then
  cp sourdough-shop.html index.html
elif [ -f "shop.html" ]; then
  cp shop.html index.html
fi

echo "Сборка завершена."
