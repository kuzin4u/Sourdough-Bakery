#!/usr/bin/env bash
# Build-скрипт для Render Static Site.
set -e

# ─── BOT_API_URL ───
if [ -z "$BOT_API_URL" ] && [ -n "$BOT_HOST" ]; then
  BOT_API_URL="https://${BOT_HOST}.onrender.com"
  echo "BOT_API_URL собран из BOT_HOST: $BOT_API_URL"
fi
echo "BOT_API_URL=${BOT_API_URL:-НЕ ЗАДАН}"

# ─── Функция безопасной подстановки ───
safe_replace() {
  local placeholder="$1"
  local value="$2"
  local file="$3"
  if [ -f "$file" ] && [ -n "$value" ]; then
    # Экранируем спецсимволы sed в value
    local escaped
    escaped=$(printf '%s\n' "$value" | sed 's/[&/\]/\\&/g')
    sed -i "s|${placeholder}|${escaped}|g" "$file"
    echo "  → $file"
  fi
}

# ─── Подстановка BOT_API_URL ───
for f in sourdough-shop.html shop.html sourdough-showcase.html showcase.html sourdough-admin.html admin.html catalog.html; do
  safe_replace "__BOT_API_URL__" "$BOT_API_URL" "$f"
done
for f in card-*.html; do
  [ -f "$f" ] && safe_replace "__BOT_API_URL__" "$BOT_API_URL" "$f"
done

# ─── REVIEWS_API_URL ───
echo "REVIEWS_API_URL=${REVIEWS_API_URL:-НЕ ЗАДАН}"
safe_replace "__REVIEWS_API_URL__" "$REVIEWS_API_URL" "reviews-widget.html"
safe_replace "__REVIEWS_API_URL__" "$REVIEWS_API_URL" "catalog.html"
safe_replace "__REVIEWS_API_URL__" "$REVIEWS_API_URL" "card.html"
for f in sourdough-shop.html shop.html; do
  safe_replace "__REVIEWS_API_URL__" "$REVIEWS_API_URL" "$f"
done
for f in card-*.html; do
  [ -f "$f" ] && safe_replace "__REVIEWS_API_URL__" "$REVIEWS_API_URL" "$f"
done

# ─── ORDERS_API_URL (кабинет продавца) ───
ORDERS_API_URL="${ORDERS_API_URL:-$REVIEWS_API_URL}"
echo "ORDERS_API_URL=${ORDERS_API_URL:-НЕ ЗАДАН}"
safe_replace "__ORDERS_API_URL__" "$ORDERS_API_URL" "cabinet-orders.html"
safe_replace "__ORDERS_API_URL__" "$ORDERS_API_URL" "cabinet-analytics.html"

# ─── index.html = каталог покупателя (Ozon-формат) ───
if [ -f "catalog.html" ]; then
  cp catalog.html index.html
elif [ -f "sourdough-shop.html" ]; then
  cp sourdough-shop.html index.html
fi

echo "Сборка завершена."
