/**
 * GOOGLE APPS SCRIPT — ЕДИНЫЙ ЭНДПОИНТ (ЗАКАЗЫ + ОТЗЫВЫ + СТАТИСТИКА)
 * =====================================================================
 * Объединяет doPost (приём заказов/отзывов) и doGet (чтение данных для кабинета).
 * ЗАМЕНЯЕТ sheets-apps-script.gs и reviews-apps-script.gs — один файл, один URL.
 *
 * GET-запросы (для кабинета и виджетов):
 *   ?action=orders              → все заказы (для кабинета продавца)
 *   ?action=orders&limit=50     → последние 50 заказов
 *   ?action=reviews             → одобренные отзывы (для виджета на сайте)
 *   ?action=reviews&sku=tartin  → отзывы по конкретному SKU
 *   ?action=stats               → сводная статистика (для дашборда)
 *
 * POST-запросы (из бота и сайта):
 *   {_type: "order", ...}   → запись заказа (существующая логика)
 *   {_type: "review", ...}  → запись отзыва
 *   {_type: "status", orderId: "MM-0047", status: "Готовится"} → смена статуса
 *
 * ПОДКЛЮЧЕНИЕ:
 * 1. В Apps Script проект таблицы вставьте этот код ВМЕСТО старого
 * 2. Развернуть → Управление развертываниями → Обновить версию
 * 3. Один URL = SHEETS_WEBHOOK_URL = REVIEWS_WEBHOOK_URL = ORDERS_API_URL
 */

const SPREADSHEET_ID = "1MmgGW3bAWkfKuOCbUhSBm7T3Ek-7r2RkeP05ij6a0H4";

// ─── GET ──────────────────────────────────────────────────

function doGet(e) {
  const action = (e.parameter.action || '').toLowerCase();
  try {
    if (action === 'orders')  return getOrders(e);
    if (action === 'reviews') return getReviews(e);
    if (action === 'stats')   return getStats(e);
    return json({ error: 'Unknown action. Use: orders, reviews, stats' });
  } catch (err) {
    return json({ error: err.message });
  }
}

function getOrders(e) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getActiveSheet();
  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return json([]);

  const limit = parseInt(e.parameter.limit || '200', 10);
  const rows = data.slice(1);
  const orders = [];

  for (let i = rows.length - 1; i >= 0 && orders.length < limit; i--) {
    const r = rows[i];
    orders.push({
      date:      r[0]  || '',
      channel:   r[1]  || '',
      id:        r[2]  || '',
      status:    r[3]  || 'Принят',
      bakeDate:  r[4]  || '',
      name:      r[5]  || '',
      phone:     maskPhone(String(r[6] || '')),
      address:   r[7]  || '',
      items:     r[8]  || '',
      delivery:  r[9]  || '',
      payment:   r[10] || '',
      discount:  r[11] || '',
      total:     r[12] || 0,
      comment:   r[13] || '',
      _row:      i + 2,  // 1-based строка в таблице (для обновления статуса)
    });
  }
  return json(orders);
}

function getReviews(e) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = ss.getSheetByName("Отзывы");
  if (!sheet) return json([]);

  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return json([]);

  const limit = parseInt(e.parameter.limit || '50', 10);
  const skuFilter = (e.parameter.sku || '').toLowerCase();
  const rows = data.slice(1);
  const reviews = [];

  for (let i = rows.length - 1; i >= 0 && reviews.length < limit; i--) {
    const r = rows[i];
    if (String(r[7] || '').trim().toLowerCase() !== 'approved') continue;
    const sku = String(r[4] || '').trim().toLowerCase();
    if (skuFilter && sku !== skuFilter) continue;
    reviews.push({
      date:    fmtDate(r[0]),
      name:    r[1] || 'Покупатель',
      score:   parseInt(r[2], 10) || 5,
      text:    r[3] || '',
      sku:     r[4] || '',
      orderId: r[5] || '',
    });
  }
  return json(reviews);
}

function getStats(e) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getActiveSheet();
  const data = sheet.getDataRange().getValues();
  if (data.length <= 1) return json({});

  const rows = data.slice(1);
  const now = new Date();
  const weekAgo = new Date(now.getTime() - 7 * 86400000);
  const monthAgo = new Date(now.getTime() - 30 * 86400000);

  let total = 0, weekOrders = 0, monthOrders = 0;
  let weekRevenue = 0, monthRevenue = 0;
  const channels = {}, statuses = {}, skuCount = {};

  for (const r of rows) {
    const d = new Date(r[0]);
    const sum = parseFloat(r[12]) || 0;
    const ch = r[1] || 'Не указан';
    const st = r[3] || 'Принят';
    const items = String(r[8] || '');

    total++;
    channels[ch] = (channels[ch] || 0) + 1;
    statuses[st] = (statuses[st] || 0) + 1;

    // SKU подсчёт из строки "Тартин ×2; Заварной ×1"
    const parts = items.split(';');
    for (const p of parts) {
      const m = p.trim().match(/^(.+?)\s*×\s*(\d+)/);
      if (m) skuCount[m[1].trim()] = (skuCount[m[1].trim()] || 0) + parseInt(m[2], 10);
    }

    if (d >= weekAgo) { weekOrders++; weekRevenue += sum; }
    if (d >= monthAgo) { monthOrders++; monthRevenue += sum; }
  }

  return json({
    total,
    weekOrders,
    weekRevenue,
    monthOrders,
    monthRevenue,
    avgCheck: total > 0 ? Math.round(monthRevenue / monthOrders) : 0,
    channels,
    statuses,
    skuCount,
  });
}

// ─── POST ─────────────────────────────────────────────────

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const type = data._type || 'order';

    if (type === 'review') return postReview(data);
    if (type === 'status') return postStatus(data);
    return postOrder(data);
  } catch (err) {
    return json({ status: 'error', message: err.message });
  }
}

function postOrder(order) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getActiveSheet();

  const headers = [
    'Дата', 'Канал', 'Номер заказа', 'Статус', 'Дата выпечки', 'Имя', 'Телефон', 'Адрес',
    'Состав заказа', 'Доставка', 'Оплата', 'Скидка', 'Сумма', 'Комментарий'
  ];
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);

  const itemsText = (order.items || [])
    .map(i => i.name + ' ×' + i.qty + ' (' + i.subtotal + ' ₽)')
    .join('; ');

  const discountText = order.discount
    ? '−' + order.discount.amount + ' ₽ (' + order.discount.label + ')'
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

  return json({ status: 'ok' });
}

function postReview(data) {
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  let sheet = ss.getSheetByName("Отзывы");
  if (!sheet) {
    sheet = ss.insertSheet("Отзывы");
    sheet.getRange(1, 1, 1, 8).setValues([[
      'Дата', 'Имя', 'Оценка', 'Текст', 'SKU', 'Заказ', 'Канал', 'Статус'
    ]]);
  }
  const score = parseInt(data.score, 10) || 5;
  sheet.appendRow([
    new Date().toISOString(),
    data.name || 'Покупатель',
    score,
    data.text || '',
    data.sku || '',
    data.orderId || '',
    data.channel || 'telegram',
    data.status || (score >= 4 ? 'approved' : 'pending'),
  ]);
  return json({ status: 'ok' });
}

function postStatus(data) {
  // Обновление статуса заказа из кабинета
  // Формат: {_type: "status", orderId: "MM-0047", status: "Готовится"}
  const ss = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = ss.getActiveSheet();
  const rows = sheet.getDataRange().getValues();

  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][2]).trim() === String(data.orderId).trim()) {
      sheet.getRange(i + 1, 4).setValue(data.status);  // Колонка D = Статус
      return json({ status: 'ok', row: i + 1 });
    }
  }
  return json({ status: 'error', message: 'Order not found: ' + data.orderId });
}

// ─── Helpers ──────────────────────────────────────────────

function maskPhone(phone) {
  if (phone.length < 7) return phone;
  return phone.slice(0, 4) + ' ···· ' + phone.slice(-4);
}

function fmtDate(val) {
  if (!val) return '';
  const d = new Date(val);
  if (isNaN(d.getTime())) return String(val);
  const m = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
  return d.getDate() + ' ' + m[d.getMonth()] + ' ' + d.getFullYear();
}

function json(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
