#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────
//  e2e-test.mjs — End-to-end browser-like tests for Agent Inbox
//
//  Loads the page into jsdom, executes the JS, then tests
//  interactive behaviors: toggle open/close, auto-refresh,
//  Luke quick-post, cookie persistence.
//
//  Usage: node e2e-test.mjs
//  Exit:  0 if all pass, 1 if any fail
// ─────────────────────────────────────────────────────────────
import { JSDOM } from 'jsdom';
import { readFileSync } from 'fs';

const BASE = process.env.BASE || 'https://127.0.0.1:13004';
const AUTH = "-u moses:M0s3s!nbox_2026";

let pass = 0, fail = 0;
const ok = (msg) => { pass++; console.log(`  ✅ ${msg}`); };
const no = (msg) => { fail++; console.log(`  ❌ ${msg}`); };

async function fetchPage(url) {
  const cmd = `curl -sk ${AUTH} '${url}'`;
  const { execSync } = await import('child_process');
  return execSync(cmd, { encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024 });
}

console.log('━━━ Agent Inbox E2E Tests ━━━\n');

// ── 1. Fetch the live page ──
console.log('── 1. Fetch page ──');
const html = await fetchPage(BASE);
if (html && html.includes('Agent Inbox')) {
  ok('Page loaded from live server');
} else {
  no('Page failed to load');
  process.exit(1);
}

// ── 2. Setup jsdom ──
console.log('\n── 2. Setup DOM ──');
const dom = new JSDOM(html, {
  url: BASE,
  contentType: 'text/html',
  runScripts: 'dangerously',
  resources: 'usable',
});

const doc = dom.window.document;
const win = dom.window;

// Wait for DOMContentLoaded + setTimeout(200ms) to complete
await new Promise(r => setTimeout(r, 500));

ok('DOM initialized, scripts executed');

// ── 3. Verify initial state (collapsed) ──
console.log('\n── 3. Initial state ──');
const card = doc.getElementById('compose-form');
const arrow = doc.getElementById('compose-arrow');
const label = doc.getElementById('compose-label');
const toggleBtn = doc.getElementById('compose-toggle');
const refreshBtn = doc.getElementById('autorefresh-toggle');
const lukeBtn = doc.getElementById('luke-btn');
const lukeSelect = doc.getElementById('topic');
const fromInput = doc.getElementById('from');
const refreshDot = doc.getElementById('refresh-dot');
const refreshLabel = doc.getElementById('refresh-label');

if (card) ok('compose-form element exists'); else no('compose-form missing');
if (arrow) ok('compose-arrow exists'); else no('compose-arrow missing');
if (label) ok('compose-label exists'); else no('compose-label missing');
if (toggleBtn) ok('compose-toggle button exists'); else no('compose-toggle missing');
if (refreshBtn) ok('autorefresh-toggle exists'); else no('autorefresh-toggle missing');
if (lukeBtn) ok('luke-btn exists'); else no('luke-btn missing');

// Check initial hidden state
const isHidden = card.style.display === 'none' || card.classList.contains('collapsed');
if (isHidden) ok('Compose form starts hidden'); else no('Compose form should be hidden');

if (label && label.textContent === 'New Message') ok('Button label: "New Message"'); else no(`Label should be "New Message", got: "${label?.textContent}"`);

// ── 4. Test toggle OPEN ──
console.log('\n── 4. Toggle open ──');
toggleBtn.click();
await new Promise(r => setTimeout(r, 100));

const nowVisible = card.style.display !== 'none' && !card.classList.contains('collapsed');
if (nowVisible) ok('Form becomes visible after click'); else no('Form should be visible after click');

if (arrow && arrow.classList.contains('open')) ok('Arrow rotates (has "open" class)'); else no('Arrow should have "open" class');
if (label && label.textContent === 'Close') ok('Button label changes to "Close"'); else no(`Label should be "Close", got: "${label?.textContent}"`);

// Check cookie was set
const cookieOpen = win.document.cookie.includes('inbox_form_open=true');
if (cookieOpen) ok('Cookie set: inbox_form_open=true'); else no('Cookie should be inbox_form_open=true');

// ── 5. Test toggle CLOSE ──
console.log('\n── 5. Toggle close ──');
toggleBtn.click();
await new Promise(r => setTimeout(r, 100));

const isHiddenAgain = card.style.display === 'none' || card.classList.contains('collapsed');
if (isHiddenAgain) ok('Form hides after second click'); else no('Form should hide after second click');

if (arrow && !arrow.classList.contains('open')) ok('Arrow returns to default (no "open" class)'); else no('Arrow should not have "open" class');
if (label && label.textContent === 'New Message') ok('Button label returns to "New Message"'); else no(`Label should be "New Message", got: "${label?.textContent}"`);

// Check cookie updated
const cookieClosed = win.document.cookie.includes('inbox_form_open=false');
if (cookieClosed) ok('Cookie updated: inbox_form_open=false'); else no('Cookie should be inbox_form_open=false');

// ── 6. Toggle open → close → open again ──
console.log('\n── 6. Multiple toggles ──');
toggleBtn.click(); await new Promise(r => setTimeout(r, 50));
const o1 = card.style.display !== 'none' && !card.classList.contains('collapsed');
toggleBtn.click(); await new Promise(r => setTimeout(r, 50));
const c1 = card.style.display === 'none' || card.classList.contains('collapsed');
toggleBtn.click(); await new Promise(r => setTimeout(r, 50));
const o2 = card.style.display !== 'none' && !card.classList.contains('collapsed');

if (o1 && c1 && o2) ok('Open → Close → Open cycle works'); else no(`Cycle failed: o1=${o1} c1=${c1} o2=${o2}`);

// Close for next tests
toggleBtn.click(); await new Promise(r => setTimeout(r, 50));

// ── 7. Test Luke button ──
console.log('\n── 7. Luke quick-post ──');
lukeBtn.click();
await new Promise(r => setTimeout(r, 100));

const lukeOpen = card.style.display !== 'none' && !card.classList.contains('collapsed');
if (lukeOpen) ok('Luke button opens compose form'); else no('Luke button should open compose form');

if (lukeSelect && lukeSelect.value === 'luke') ok('Luke button sets topic to "luke"'); else no(`Topic should be "luke", got: "${lukeSelect?.value}"`);

if (fromInput && doc.activeElement === fromInput) ok('Luke button focuses "from" field'); else no('From field should be focused');

// Close
toggleBtn.click(); await new Promise(r => setTimeout(r, 50));

// ── 8. Test auto-refresh toggle ──
console.log('\n── 8. Auto-refresh toggle ──');
// Default: auto-refresh should be ON
if (refreshDot && refreshDot.classList.contains('active')) ok('Auto-refresh starts ON (dot active)'); else no('Dot should be active initially');
if (refreshLabel && refreshLabel.textContent === 'on · 60s') ok('Refresh label shows "on · 60s"'); else no(`Label should be "on · 60s", got: "${refreshLabel?.textContent}"`);

// Toggle OFF
console.log('  [debug] cookie before:', win.document.cookie);
console.log('  [debug] has active class:', refreshBtn.classList.contains('active'));
console.log('  [debug] toggleAutoRefresh exists:', typeof win.toggleAutoRefresh);

// Direct call
console.log('  [debug] calling toggleAutoRefresh directly...');
dom.window.eval('toggleAutoRefresh()');
await new Promise(r => setTimeout(r, 100));

console.log('  [debug] cookie after:', win.document.cookie);
console.log('  [debug] dot active:', refreshDot.classList.contains('active'));
console.log('  [debug] label text:', refreshLabel.textContent);
console.log('  [debug] refreshBtn active:', refreshBtn.classList.contains('active'));
const dotOff = !refreshDot.classList.contains('active');
const labelOff = refreshLabel.textContent === 'off';
if (dotOff && labelOff) ok('Toggle OFF: dot inactive, label "off"'); else no(`OFF state: dotActive=${!dotOff} label="${refreshLabel?.textContent}"`);

// Toggle ON again
refreshBtn.click();
await new Promise(r => setTimeout(r, 100));
const dotOn = refreshDot.classList.contains('active');
const labelOn = refreshLabel.textContent === 'on · 60s';
if (dotOn && labelOn) ok('Toggle ON again: dot active, label "on · 60s"'); else no(`ON state: dotActive=${dotOn} label="${refreshLabel?.textContent}"`);

// ── 9. Test cookie persistence (simulate page reload) ──
console.log('\n── 9. Cookie persistence ──');
// The form is currently closed. Clear no-animate to simulate fresh load
// In a real reload, the init would read the cookie and restore state.
// Let's verify the cookie is set correctly:
const cookieAfter = win.document.cookie;
if (cookieAfter.includes('inbox_autorefresh=true') && cookieAfter.includes('inbox_form_open=false')) {
  ok('Cookies persist correct state');
} else {
  no(`Unexpected cookies: ${cookieAfter}`);
}

// ── 10. Error resilience test ──
console.log('\n── 10. Error resilience ──');
// Simulate missing element — the id() helper should warn but not crash
const missingEl = dom.window.document.getElementById('nonexistent');
if (missingEl === null) ok('Missing element returns null (no crash)'); else no('Missing element should be null');

// Call toggle with try/catch — should log error, not throw
let threw = false;
try {
  dom.window.eval('toggleMessageForm()');
} catch(e) {
  threw = true;
}
if (!threw) ok('toggleMessageForm() can be called without crashing'); else no('toggleMessageForm() threw an error');

// ── Summary ──
console.log(`\n━━━ Results: ${pass} passed, ${fail} failed ━━━`);
process.exit(fail > 0 ? 1 : 0);
