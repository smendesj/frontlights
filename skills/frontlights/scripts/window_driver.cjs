#!/usr/bin/env node
// Driver of `serve.py window` (issue 8): the visible Chrome window of the watched run, driven over CDP by the
// Playwright the project already has. Nothing is installed: `serve.py` resolves the Playwright package and passes
// its path; this file only `require`s it. It never judges a pass or a failure: it opens, holds, prints and reports.
//
// Usage: node window_driver.cjs <open|hold|shot> ; one JSON object on stdin, one JSON line on stdout.
//   input: {playwright, cdpUrl, baseUrl?, strip?, login?, check?, minutes?, path?}
//   login credentials come only from FRONTLIGHTS_WINDOW_USER / FRONTLIGHTS_WINDOW_PASSWORD, never from argv or stdin.
'use strict';

const STRIP_ID = '__frontlights_faixa';

function stripScript(text) {
  const colour = text.startsWith('DEPOIS') ? '#1b5e20' : text.startsWith('MAIN LOCAL') ? '#4a148c' : '#0d47a1';
  return `(() => {
    const id = ${JSON.stringify(STRIP_ID)};
    const put = () => {
      if (!document.documentElement) return;
      let el = document.getElementById(id);
      if (el) return;
      el = document.createElement('div');
      el.id = id;
      el.textContent = ${JSON.stringify(text)};
      el.style.cssText = 'position:fixed;top:0;left:0;right:0;height:22px;line-height:22px;z-index:2147483647;' +
        'background:${colour};color:#fff;font:bold 13px sans-serif;text-align:center;pointer-events:none;margin:0;';
      document.documentElement.appendChild(el);
    };
    put();
    document.addEventListener('DOMContentLoaded', put);
    new MutationObserver(put).observe(document, { childList: true, subtree: true });
  })();`;
}

function readInput() {
  return new Promise((resolve) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => { data += chunk; });
    process.stdin.on('end', () => resolve(data ? JSON.parse(data) : {}));
  });
}

function out(value) {
  process.stdout.write(JSON.stringify(value) + '\n');
}

async function connect(input) {
  const { chromium } = require(input.playwright);
  const browser = await chromium.connectOverCDP(input.cdpUrl);
  const context = browser.contexts()[0] || await browser.newContext({ viewport: null });
  return { browser, context };
}

async function activePage(context) {
  const pages = context.pages();
  for (const page of pages) {
    try {
      if (await page.evaluate(() => document.visibilityState === 'visible' && document.hasFocus())) return page;
    } catch (error) { /* a page that is closing */ }
  }
  return pages[pages.length - 1] || await context.newPage();
}

async function applyStrip(context, strip) {
  if (!strip) return;
  const script = stripScript(strip);
  await context.addInitScript(script);
  for (const page of context.pages()) {
    try { await page.evaluate(script); } catch (error) { /* about:blank or a closing page */ }
  }
}

async function measure(page) {
  return page.evaluate((id) => {
    const strip = document.getElementById(id);
    const rect = strip ? strip.getBoundingClientRect() : null;
    const doc = document.documentElement;
    return {
      innerWidth: window.innerWidth, innerHeight: window.innerHeight,
      outerWidth: window.outerWidth, outerHeight: window.outerHeight,
      availWidth: screen.availWidth, availHeight: screen.availHeight,
      scrollWidth: doc ? doc.scrollWidth : 0,
      strip: rect ? { top: rect.top, width: rect.width } : null,
    };
  }, STRIP_ID);
}

function fits(m) {
  // the whole page and the strip inside the window, and the window inside the screen (a little slack for borders)
  return m.scrollWidth <= m.innerWidth && m.outerWidth <= m.availWidth + 16 && m.outerHeight <= m.availHeight + 16 &&
    (!m.strip || (m.strip.top >= 0 && m.strip.width >= m.innerWidth - 1));
}

async function login(page, input) {
  const spec = input.login;
  const user = process.env.FRONTLIGHTS_WINDOW_USER;
  const password = process.env.FRONTLIGHTS_WINDOW_PASSWORD;
  if (!spec || !user || !password) return 'condutor';
  if (spec.url) await page.goto(new URL(spec.url, input.baseUrl).toString());
  await page.fill(spec.user, user);
  await page.fill(spec.password, password);
  await Promise.all([page.waitForLoadState('load').catch(() => {}), page.click(spec.submit)]);
  return 'script';
}

async function open(input) {
  const { browser, context } = await connect(input);
  await applyStrip(context, input.strip);
  const page = await activePage(context);
  await page.goto(input.baseUrl);
  const loggedBy = await login(page, input);
  try { await page.evaluate(stripScript(input.strip || '')); } catch (error) { /* already there */ }
  const m = await measure(page);
  if (input.check) await page.screenshot({ path: input.check });
  out({ ok: true, fits: fits(m), measure: m, checkShot: input.check || null, login: loggedBy });
  await browser.close();   // over CDP this only disconnects: the window stays
}

async function hold(input) {
  const { browser, context } = await connect(input);
  await applyStrip(context, input.strip);
  context.on('page', (page) => page.evaluate(stripScript(input.strip || '')).catch(() => {}));
  const ended = await new Promise((resolve) => {
    browser.on('disconnected', () => resolve('disconnected'));
    if (input.minutes) setTimeout(() => resolve('prazo'), input.minutes * 60 * 1000);
  });
  out({ ok: true, ended_by: ended });
  if (ended === 'prazo') await browser.close().catch(() => {});
}

async function shot(input) {
  const { browser, context } = await connect(input);
  const page = await activePage(context);
  await page.screenshot({ path: input.path });
  out({ ok: true, path: input.path, url: page.url() });
  await browser.close();
}

async function executable(input) {
  const { chromium } = require(input.playwright);
  out({ ok: true, executable: chromium.executablePath() });
}

const COMMANDS = { open, hold, shot, executable };

(async () => {
  const command = COMMANDS[process.argv[2]];
  if (!command) {
    out({ ok: false, error: 'comando desconhecido: use open, hold, shot ou executable' });
    process.exit(2);
  }
  try {
    await command(await readInput());
    process.exit(0);
  } catch (error) {
    out({ ok: false, error: String(error && error.message || error).slice(0, 400) });
    process.exit(1);
  }
})();
