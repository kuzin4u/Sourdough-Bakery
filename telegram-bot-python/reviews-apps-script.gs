/**
 * GOOGLE APPS SCRIPT — ЛИСТ «ОТЗЫВЫ»
 * ====================================
 * Два режима:
 *   GET  → возвращает JSON массив одобренных отзывов (для виджета на сайте)
 *   POST → принимает новый отзыв из Telegram-бота
 *
 * Таблица: лист «Отзывы» в той же таблице заказов (SPREADSHEET_ID).
 * Колонки: Дата | Имя | Оценка | Текст | Заказ | Канал | Статус
 * Статус: "approved" / "pending" / "hidden"
 *   — бот пишет "approved" (автомодерация: 4-5★ = approved, 1-3★ = pending)
 *   — админ может поменять вручную в таблице
 *
 * ПОДКЛЮЧЕНИЕ:
 * 1. Откройте Apps Script проект с таблицей заказов
 * 2. Создайте НОВЫЙ файл (напр. Reviews.gs) и вставьте этот код
 * 3. ВАЖНО: если в проекте уже есть функции doGet/doPost (для заказов),
 *    объедините их в один роутер (см. пример ниже)
 * 4. Развернуть → Новое развертывание → Веб-приложение → Доступ: Все
 * 5. URL этого развертывания = REVIEWS_WEBHOOK_URL для бота
 *
 * ОБЪЕДИНЕНИЕ С СУЩЕСТВУЮЩИМ doPost (заказы):
 * ------------------------------------
 * function doPost(e) {
 *   const data = JSON.parse(e.postData.contents);
 *   if (data._type === 'review') return handleReviewPost(data);
 *   return handleOrderPost(data);  // ваш текущий doPost
 * }
 * function doGet(e) {
 *   return handleReviewGet(e);
 * }
 * ------------------------------------
 */

const SPREADSHEET_ID = "1MmgGW3bAWkfKuOCbUhSBm7T3Ek-7r2RkeP05ij6a0H4";
const REVIEWS_SHEET = "Отзывы";

/**
 * GET — возвращает одобренные отзывы в JSON.
 * Параметры: ?limit=10&sku=tartin
 */
function doGet(e) {
  return handleReviewGet(e);
}

function handleReviewGet(e) {
  try {
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet = ss.getSheetByName(REVIEWS_SHEET);

    // Если листа нет — создаём с заголовками
    if (!sheet) {
      sheet = ss.insertSheet(REVIEWS_SHEET);
      sheet.getRange(1, 1, 1, 8).setValues([[
        'Дата', 'Имя', 'Оценка', 'Текст', 'SKU', 'Заказ', 'Канал', 'Статус'
      ]]);
    }

    const data = sheet.getDataRange().getValues();
    if (data.length <= 1) {
      return jsonResponse([]);
    }

    const headers = data[0];
    const rows = data.slice(1);
    const limit = parseInt((e && e.parameter && e.parameter.limit) || '50', 10);
    const skuFilter = (e && e.parameter && e.parameter.sku) || '';

    const reviews = [];
    for (let i = rows.length - 1; i >= 0 && reviews.length < limit; i--) {
      const row = rows[i];
      const status = (row[7] || '').toString().trim().toLowerCase();
      if (status !== 'approved') continue;

      const sku = (row[4] || '').toString().trim().toLowerCase();
      if (skuFilter && sku !== skuFilter.toLowerCase()) continue;

      reviews.push({
        date: formatDate(row[0]),
        name: row[1] || 'Покупатель',
        score: parseInt(row[2], 10) || 5,
        text: row[3] || '',
        sku: row[4] || '',
        orderId: row[5] || '',
      });
    }

    return jsonResponse(reviews);

  } catch (err) {
    return jsonResponse({ error: err.message });
  }
}

/**
 * POST — принимает отзыв из бота.
 * JSON: { _type: "review", name, score, text, sku, orderId, channel, status }
 */
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  if (data._type === 'review') return handleReviewPost(data);
  // Если не review — передать в обработчик заказов (handleOrderPost)
  // return handleOrderPost(data);
  return ContentService
    .createTextOutput(JSON.stringify({ status: 'error', message: 'Unknown _type' }))
    .setMimeType(ContentService.MimeType.JSON);
}

function handleReviewPost(data) {
  try {
    const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
    let sheet = ss.getSheetByName(REVIEWS_SHEET);

    if (!sheet) {
      sheet = ss.insertSheet(REVIEWS_SHEET);
      sheet.getRange(1, 1, 1, 8).setValues([[
        'Дата', 'Имя', 'Оценка', 'Текст', 'SKU', 'Заказ', 'Канал', 'Статус'
      ]]);
    }

    const score = parseInt(data.score, 10) || 5;
    // Автомодерация: 4-5★ = approved, 1-3★ = pending (требует ручной проверки)
    const status = data.status || (score >= 4 ? 'approved' : 'pending');

    sheet.appendRow([
      new Date().toISOString(),
      data.name || 'Покупатель',
      score,
      data.text || '',
      data.sku || '',
      data.orderId || '',
      data.channel || 'telegram',
      status,
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

// ─── Helpers ──────────────────────────────────────────────

function formatDate(val) {
  if (!val) return '';
  const d = new Date(val);
  if (isNaN(d.getTime())) return String(val);
  const months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
}

function jsonResponse(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
