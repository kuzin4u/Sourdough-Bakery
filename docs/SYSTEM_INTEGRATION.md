# Масса Мадре — вход в Систему

> Репозиторий: `Sourdough-Bakery` · Версия: 0.2 · Дата: 2026-09-24
> Статус: целевая схема — по рабочим записям; раздел «Как есть в коде» сверен 2026-09-24 (`/verify`). Метка ⟦уточнить⟧ — факт не виден из репозитория.
> Детальные схемы — massamadre-catalog-settlement.html и massamadre-settlement-mechanisms.html в пуле marketplace-api.


## Выбранный вариант — 2: своя витрина + коннектор, расчёты в Системе
| Актив | Роль |
|---|---|
| Каталог (Sheets) | Зеркалится в каталог Системы как source=EXTERNAL (коннектор Apps Script → API) |
| Витрина massamadre.ru | Остаётся своей (visible_shop) |
| cabinet-orders.html | Получает два потока: прямые (ЮKassa, entry_point=SHOP → MIGRATED) и из Системы (entry_point=CATALOG → NETWORK → эскроу) |

## Три механизма расчёта
1. Всегда через Систему. 2. Выбор на каждом заказе (флаг settlement). 3. Только фулфилмент через Систему.
Механизм не выбран ⟦открыто⟧.

## Как есть в коде (2026-09-24)
- Коннектора Sheets → API Системы в репозитории нет: ни `source=EXTERNAL`, ни обращений к marketplace-api.
  Копия Apps Script (`sheets-unified-api.gs`) пишет только в Google Sheets.
- `cabinet-orders.html` получает один поток — заказы из Sheets (`?action=orders`); полей `entry_point` и `settlement` нет.
- Механизмы расчёта (`settlement: OWN / SYSTEM`) есть только в демо `website/alpha-demo-standalone.html`.

## Открыто
Свести оба потока заказов в один cabinet-orders или вести раздельно.
