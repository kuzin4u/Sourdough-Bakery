/**
 * ШАБЛОН WEB APP ДЛЯ GOOGLE ТАБЛИЦ — ОБЩАЯ БАЗА ЗАКАЗОВ
 * -------------------------------------------------------
 * Принимает POST с JSON заказа и дописывает строку. Один и тот же URL используется
 * браузерным виджетом и Telegram-ботом — поэтому заказы из обоих каналов оказываются
 * в одной таблице, с колонкой "Канал". Также пишет статус, дату выпечки и скидку,
 * если они есть в заказе (актуально для заказов из Telegram-бота).
 *
 * Таблица указывается ЯВНО по ID (см. SPREADSHEET_ID ниже) — это надёжнее, чем
 * SpreadsheetApp.getActiveSpreadsheet(), который работает только если скрипт создан
 * "внутри" таблицы (через Расширения → Apps Script) и не работает для отдельно
 * созданных (standalone) скриптов — там "активной" таблицы просто нет.
 *
 * КАК ПОДКЛЮЧИТЬ (один раз):
 * 1. Откройте (или создайте) Google Таблицу для заказов.
 * 2. Скопируйте её ID из адресной строки браузера:
 *    https://docs.google.com/spreadsheets/d/ЭТА_ЧАСТЬ_И_ЕСТЬ_ID/edit
 * 3. Вставьте этот ID в SPREADSHEET_ID ниже, между кавычками.
 * 4. В любом Apps Script проекте (свежем или уже существующем) вставьте этот код целиком.
 * 5. "Развернуть" → "Новое развертывание" → тип "Веб-приложение", доступ "Все".
 * 6. Скопируйте URL — это SHEETS_WEBHOOK_URL.
 * 7. Вставьте этот же URL в .env бота и в настройки (⚙) браузерного виджета.
 */

const SPREADSHEET_ID = "1MmgGW3bAWkfKuOCbUhSBm7T3Ek-7r2RkeP05ij6a0H4";

function doPost(e) {
  try {
    const order = JSON.parse(e.postData.contents);
    const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getActiveSheet();

    const headers = [
      'Дата', 'Канал', 'Номер заказа', 'Статус', 'Дата выпечки', 'Имя', 'Телефон', 'Адрес',
      'Состав заказа', 'Доставка', 'Оплата', 'Скидка', 'Сумма', 'Комментарий'
    ];
    // Заголовки перезаписываются на каждый вызов, а не только при пустой таблице —
    // это самовосстанавливающаяся защита: если схема колонок когда-то поменяется
    // в коде (добавится/уберётся столбец), первая строка сама подстроится и данные
    // не "сдвинутся" относительно старых, оставшихся от прошлой версии подписей.
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

    const itemsText = (order.items || [])
      .map(i => `${i.name} ×${i.qty} (${i.subtotal} ₽)`)
      .join('; ');

    const discountText = order.discount
      ? `−${order.discount.amount} ₽ (${order.discount.label})`
      : '';

    sheet.appendRow([
      order.createdAt || new Date().toISOString(),
      order.channel || 'Не указан',
      order.id || '',
      order.status || 'Принят',
      order.bakeDate || '',
      order.name || '',
      order.phone || '',
      order.address || '',
      itemsText,
      order.delivery || '',
      order.payment || '',
      discountText,
      order.total || '',
      order.comment || ''
    ]);

    return ContentService
      .createTextOutput(JSON.stringify({ status: 'ok' }))
      .setMimeType(ContentService.MimeType.JSON);

  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ status: 'error', message: err.message }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
