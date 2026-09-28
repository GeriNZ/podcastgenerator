// Runs Apps Script logic against in-memory Sheets stubs; no Google/GPU calls.
const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const rows = [];
let locked = false;
const sheet = {
  getLastRow: () => rows.length,
  getRange: (r, c, n = 1, m = 1) => ({
    getValues: () => Array.from({length: n}, (_, i) => Array.from({length: m}, (_, j) => rows[r-1+i]?.[c-1+j] ?? '')),
    getValue: () => rows[r-1]?.[c-1] ?? '',
    setValues: values => {
      assert.ok(locked, 'writes must hold lock');
      values.forEach((valuesRow, i) => { rows[r-1+i] ??= []; valuesRow.forEach((v, j) => { rows[r-1+i][c-1+j] = v; }); });
    }
  })
};
const context = vm.createContext({
  PropertiesService: {getScriptProperties: () => ({getProperty: key => key === 'TRACKER_SECRET' ? 'secret' : 'sheet'})},
  SpreadsheetApp: {openById: () => ({getSheetByName: () => sheet}), flush: () => {}},
  LockService: {getScriptLock: () => ({waitLock: () => { assert.ok(!locked); locked = true; }, hasLock: () => locked, releaseLock: () => { locked = false; }})},
  ContentService: {MimeType: {JSON: 'json'}, createTextOutput: text => ({setMimeType: () => text})}
});
vm.runInContext(fs.readFileSync(__dirname + '/UsageTracker.gs', 'utf8'), context);
const id = '12345678-1234-1234-1234-123456789abc';
const call = (secret, action, record) => JSON.parse(context.doPost({postData: {contents: JSON.stringify({secret, action, record})}}));
assert.equal(call('wrong', 'check').ok, false);
assert.equal(rows.length, 0);
assert.equal(call('secret', 'check').ok, true);
assert.equal(rows.length, 1);
assert.equal(call('secret', 'upsert', {request_id: id, status: 'started', title: '=1+1'}).ok, true);
assert.equal(rows[1][3], "'=1+1");
assert.equal(call('secret', 'upsert', {request_id: id, status: 'completed', estimated_cost_usd: .01}).ok, true);
assert.equal(rows.length, 2);
call('secret', 'upsert', {request_id: id, status: 'started'});
assert.equal(rows[1][4], 'completed');
assert.equal(call('secret', 'upsert', {request_id: 'bad', status: 'started'}).ok, false);
assert.equal(locked, false);
console.log('Tracker tests passed: auth, check, locking, deduplication, no downgrade, formula escaping.');
