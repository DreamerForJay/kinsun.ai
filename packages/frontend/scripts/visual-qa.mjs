/**
 * Visual QA for the checks MASTER.md §7 and §13 make that only a rendered page
 * can answer. `tsc`, vitest, `next build` and eslint see none of this.
 *
 *   node scripts/visual-qa.mjs [baseUrl]
 *
 * Needs the dev server already running (default http://localhost:3000). Writes
 * PNGs to .visual-qa/ and prints a pass/fail table.
 *
 * Only unauthenticated rendering is covered: without Core running, the data
 * pages fall back to their NotLoggedIn state. That still exercises the elder
 * sign-in journey end to end, which is the part §5.1 and §6.1 constrain most
 * tightly. Data-bearing states (tables, StateCards) need a seeded Core and are
 * NOT checked here — do not read a green run as covering them.
 */

import { mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const BASE = process.argv[2] ?? 'http://localhost:3000';
/* fileURLToPath, not `new URL(...).pathname`: the latter leaves the path
   percent-encoded and drive-prefixed on Windows, so the screenshots landed in a
   directory literally named "%E7%89%B9..." next to the real one. */
const OUT = fileURLToPath(new URL('../.visual-qa/', import.meta.url));

/** §7.1 breakpoints, plus the landscape case §7.2 says must not be locked out. */
const VIEWPORTS = [
  { name: '390-phone', width: 390, height: 844 },
  { name: '768-tablet-portrait', width: 768, height: 1024 },
  { name: '1024-tablet-landscape', width: 1024, height: 768 },
  { name: '1280-desktop', width: 1280, height: 900 },
];

const ROUTES = [
  { path: '/sign-in', surface: 'voice' },
  { path: '/elder/start', surface: 'voice' },
  { path: '/consent', surface: 'voice' },
  { path: '/onboarding/resolve', surface: 'voice' },
  { path: '/', surface: 'voice' },
  { path: '/family/join', surface: 'family' },
  { path: '/family/sign-in', surface: 'family' },
  { path: '/family', surface: 'family' },
  { path: '/staff/sign-in', surface: 'care' },
  { path: '/dashboard', surface: 'care' },
];

/** §6.1 minimums. The page is checked against the surface it actually renders. */
const TOUCH_MIN = { voice: 64, care: 48, family: 48 };

/** Runs in the page. Returns everything a static read of the source cannot. */
function audit() {
  const doc = document.documentElement;
  /* The LAST [data-surface] in document order, not the first. <body> now
     declares the voice default, so `querySelector` would always answer "voice"
     and every care/family page would be measured against the 64px elder
     minimum — the audit would invent failures that are not there. */
  const surfaceNodes = [...document.querySelectorAll('[data-surface]')];
  const surface = surfaceNodes.at(-1)?.getAttribute('data-surface') ?? null;

  const interactive = [...document.querySelectorAll('a, button, [role="button"], input, select')];
  const small = interactive
    .filter((el) => el.offsetParent !== null || el.getClientRects().length > 0)
    .map((el) => {
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName.toLowerCase(),
        text: (el.textContent ?? '').trim().slice(0, 28),
        w: Math.round(r.width),
        h: Math.round(r.height),
      };
    })
    .filter((el) => el.h > 0);

  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) =>
    Number(h.tagName[1]),
  );

  const iconOnly = [...document.querySelectorAll('button, a')]
    .filter((el) => {
      const hasText = (el.textContent ?? '').trim().length > 0;
      const hasLabel = el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby');
      const hasGraphic = el.querySelector('svg, img') !== null;
      return hasGraphic && !hasText && !hasLabel;
    })
    .map((el) => el.outerHTML.slice(0, 80));

  return {
    surface,
    scrollWidth: doc.scrollWidth,
    clientWidth: doc.clientWidth,
    horizontalScroll: doc.scrollWidth > doc.clientWidth + 1,
    computedBaseFontPx: parseFloat(getComputedStyle(document.body).fontSize),
    targets: small,
    headings,
    iconOnly,
  };
}

function headingSkips(levels) {
  const problems = [];
  let previous = 0;
  for (const level of levels) {
    if (previous !== 0 && level > previous + 1) problems.push(`h${previous} → h${level}`);
    previous = level;
  }
  return problems;
}

const rows = [];
let failures = 0;

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();

/* §5.2 requires re-testing any English-bearing layout, because English strings
   run longer and are where a button or a table header wraps first. The voice
   surface is Chinese-only, so it is only checked in zh-Hant. */
const origin = new URL(BASE).hostname;
const LOCALES = ['zh-Hant', 'en'];

for (const viewport of VIEWPORTS) {
  for (const locale of LOCALES) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      deviceScaleFactor: 1,
      reducedMotion: 'reduce',
    });
    await context.addCookies([
      { name: 'kinsun_ui_locale', value: locale, domain: origin, path: '/' },
    ]);
    const page = await context.newPage();

    const routes = locale === 'en' ? ROUTES.filter((r) => r.surface !== 'voice') : ROUTES;

    for (const route of routes) {
      const url = `${BASE}${route.path}`;
      let result;
      try {
        /* Generous, and `load` rather than `networkidle`: against a dev server the
         first hit on a route pays for an on-demand compile, which is not a
         property of the page. */
        await page.goto(url, { waitUntil: 'load', timeout: 90_000 });
        // Client components resolve their config after mount; give them a beat so
        // the audit measures the settled page rather than the first paint.
        await page.waitForTimeout(400);
        result = await page.evaluate(audit);
      } catch (error) {
        rows.push({
          viewport: viewport.name,
          locale,
          route: route.path,
          problems: [`LOAD FAILED: ${String(error).split('\n')[0]}`],
        });
        failures += 1;
        continue;
      }

      await page.screenshot({
        path: join(
          OUT,
          `${route.path.replace(/\//g, '_') || '_root'}__${viewport.name}__${locale}.png`,
        ),
        fullPage: true,
      });

      const problems = [];

      // §7.4 — no horizontal scroll at any breakpoint. A hard rule, not a target.
      if (result.horizontalScroll) {
        problems.push(`horizontal scroll (${result.scrollWidth} > ${result.clientWidth})`);
      }

      // §6.1 — measured, not declared. A min-height that a flex parent overrides
      // only shows up here.
      const min = TOUCH_MIN[result.surface ?? route.surface] ?? 48;
      const tooSmall = result.targets.filter((t) => t.h < min);
      if (tooSmall.length > 0) {
        problems.push(
          `${tooSmall.length} target(s) under ${min}px: ` +
            tooSmall
              .slice(0, 4)
              .map((t) => `${t.tag}"${t.text}"=${t.h}px`)
              .join(', '),
        );
      }

      // §5.1 — the elder floor is 22px; the surface must actually be applied.
      if (route.surface === 'voice' && result.computedBaseFontPx < 22) {
        problems.push(`body font ${result.computedBaseFontPx}px < 22px floor`);
      }
      if (result.surface !== route.surface) {
        problems.push(`surface is "${result.surface}", expected "${route.surface}"`);
      }

      // §13 — heading levels must not skip, icon-only controls need a name.
      const skips = headingSkips(result.headings);
      if (skips.length > 0) problems.push(`heading skip: ${skips.join(', ')}`);
      if (result.iconOnly.length > 0) {
        problems.push(`${result.iconOnly.length} icon-only control(s) with no accessible name`);
      }

      if (problems.length > 0) failures += 1;
      rows.push({ viewport: viewport.name, locale, route: route.path, problems });
    }

    await context.close();
  }
}

await browser.close();

for (const row of rows) {
  const status = row.problems.length === 0 ? 'PASS' : 'FAIL';
  console.log(`${status}  ${row.viewport.padEnd(24)} ${row.locale.padEnd(8)} ${row.route}`);
  for (const problem of row.problems) console.log(`        - ${problem}`);
}
console.log(`\n${failures} failing page/viewport combination(s) of ${rows.length}`);
console.log(`screenshots: ${OUT}`);
