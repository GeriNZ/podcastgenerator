// Paste into Extensions > Apps Script in your tracking spreadsheet.
const HEADERS = ['request_id', 'started_utc', 'finished_utc', 'title', 'status',
  'voice_a', 'voice_b', 'words', 'predicted_audio_seconds', 'audio_seconds',
  'worker_seconds', 'client_seconds', 'estimated_compute_seconds',
  'predicted_cost_usd', 'estimated_cost_usd', 'gpu', 'gpu_usd_hour',
  'cpu_usd_core_hour', 'memory_usd_gib_hour', 'assumed_cpu_cores',
  'assumed_memory_gib', 'cost_basis'];

// Run ONCE from the editor before deploying. No cloud project/key files needed.
function setup() {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  if (!book) throw new Error('Open this script through your spreadsheet.');
  const props = PropertiesService.getScriptProperties();
  props.setProperty('SPREADSHEET_ID', book.getId());
  if (!props.getProperty('TRACKER_SECRET')) {
    props.setProperty('TRACKER_SECRET', Utilities.getUuid() + Utilities.getUuid());
  }
  const sheet = book.getSheetByName('Usage') || book.insertSheet('Usage');
  prepare_(sheet);
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold').setBackground('#dceef0');
  sheet.getRange('N:O').setNumberFormat('0.000000');
  SpreadsheetApp.getUi().alert('Ready. Copy TRACKER_SECRET from Project Settings > Script properties into Streamlit Secrets.');
}

function prepare_(sheet) {
  if (sheet.getLastRow() === 0) sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
  const existing = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  if (JSON.stringify(existing) !== JSON.stringify(HEADERS)) throw new Error('Usage headers do not match.');
}

function reply_(value) {
  return ContentService.createTextOutput(JSON.stringify(value)).setMimeType(ContentService.MimeType.JSON);
}

function safeCell_(value) {
  if (value === undefined || value === null) return '';
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value !== 'string' || value.length > 2000) throw new Error('Invalid field.');
  // setValues interprets leading '=' as formulas; preserve all input as text.
  return /^[\s]*[=+@-]/.test(value) ? "'" + value : value;
}

function doGet() {
  return reply_({ok: false, message: 'Use the authenticated tracker connection check in the podcast app.'});
}

function doPost(e) {
  let lock;
  try {
    if (!e || !e.postData || e.postData.contents.length > 16000) return reply_({ok: false});
    const body = JSON.parse(e.postData.contents);
    const props = PropertiesService.getScriptProperties();
    const secret = props.getProperty('TRACKER_SECRET');
    if (!secret || typeof body.secret !== 'string' || body.secret !== secret) return reply_({ok: false});
    if (!['check', 'upsert'].includes(body.action)) return reply_({ok: false});
    lock = LockService.getScriptLock();
    lock.waitLock(10000);
    const sheet = SpreadsheetApp.openById(props.getProperty('SPREADSHEET_ID')).getSheetByName('Usage');
    if (!sheet) throw new Error('Run setup first.');
    prepare_(sheet);
    if (body.action === 'check') return reply_({ok: true});
    const record = body.record;
    if (!record || !/^[0-9a-f-]{36}$/i.test(record.request_id || '')) throw new Error('Invalid request ID.');
    if (!['started', 'completed', 'failed_or_unknown', 'not_submitted_logging_error'].includes(record.status)) throw new Error('Invalid status.');
    const values = HEADERS.map(key => safeCell_(record[key]));
    const count = sheet.getLastRow() - 1;
    const ids = count > 0 ? sheet.getRange(2, 1, count, 1).getValues() : [];
    const found = [];
    ids.forEach((row, i) => { if (row[0] === record.request_id) found.push(i + 2); });
    if (found.length > 1) throw new Error('Duplicate ID.');
    const row = found.length ? found[0] : sheet.getLastRow() + 1;
    if (found.length) {
      const previous = sheet.getRange(row, 5).getValue();
      // An old/retried start must never erase a completed outcome.
      if (previous === 'completed' && record.status !== 'completed') return reply_({ok: true, request_id: record.request_id});
    }
    sheet.getRange(row, 1, 1, HEADERS.length).setValues([values]);
    SpreadsheetApp.flush();
    return reply_({ok: true, request_id: record.request_id});
  } catch (error) {
    // Never log request bodies, secrets, or titles.
    return reply_({ok: false, message: 'Tracker could not save. Check setup and sheet permissions.'});
  } finally {
    if (lock && lock.hasLock()) lock.releaseLock();
  }
}
