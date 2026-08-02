import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

/**
 * MASTER.md §13 requires every page to clear 4.5:1 for body text and 3:1 for
 * large text and UI component boundaries. Nothing checked it, so a token edit
 * could quietly drop a pair below the line — the failure is invisible to tsc,
 * to the tests, and to anyone not running a contrast tool by hand.
 *
 * This reads the real tokens.css rather than a copy: a duplicated palette would
 * pass while the shipped one regressed.
 */

const css = readFileSync(fileURLToPath(new URL('./tokens.css', import.meta.url)), 'utf8');

/** Resolves `--token` through any number of `var(--other)` hops to a hex. */
function token(name: string): string {
  const seen = new Set<string>();
  let current = name;
  for (;;) {
    if (seen.has(current)) throw new Error(`cyclic token: ${current}`);
    seen.add(current);
    const match = new RegExp(`--${current}:\\s*([^;]+);`).exec(css);
    if (!match) throw new Error(`token not found in tokens.css: --${current}`);
    const value = match[1].trim();
    const hex = /^#[0-9a-fA-F]{6}$/.exec(value);
    if (hex) return value.toLowerCase();
    const ref = /^var\(--([\w-]+)\)$/.exec(value);
    if (!ref) throw new Error(`--${current} is not a hex or a var() reference: ${value}`);
    current = ref[1];
  }
}

const channel = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high + 0.05) / (low + 0.05);
}

const BODY = 4.5;
const LARGE_OR_UI = 3;

describe('token contrast (MASTER.md §13)', () => {
  it.each([
    ['foreground on the voice background', 'color-foreground', 'cyan-50', BODY],
    ['foreground on the care background', 'color-foreground', 'slate-25', BODY],
    ['foreground on the family background', 'color-foreground', 'cyan-25', BODY],
    ['foreground on a card', 'color-foreground', 'color-surface', BODY],
    /* §4.1 calls --color-muted-foreground the floor for secondary text and says
       it must not go lighter. These are the pairs that pin that claim. */
    ['muted text on a card', 'color-muted-foreground', 'color-surface', BODY],
    ['muted text on the care background', 'color-muted-foreground', 'slate-25', BODY],
    ['muted text on the family background', 'color-muted-foreground', 'cyan-25', BODY],
    ['link text on a card', 'color-primary-text', 'color-surface', BODY],
    ['error text on a card', 'color-destructive', 'color-surface', BODY],
    /* White on --color-primary is only 3.68:1, so a filled button whose label is
       under 24px must use --color-primary-strong instead (§4.1, §13). */
    ['button label on a strong fill', 'color-on-primary', 'color-primary-strong', BODY],
    [
      'button label on a primary fill, ≥24px only',
      'color-on-primary',
      'color-primary',
      LARGE_OR_UI,
    ],
    ['focus ring against a card', 'color-ring', 'color-surface', LARGE_OR_UI],
    ['focus ring against the care background', 'color-ring', 'slate-25', LARGE_OR_UI],
  ])('%s clears %s:1', (_label, fg, bg, required) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(required);
  });

  /* §4.2 fixes both the foreground and the background of each workflow state,
     and §13 requires 4.5:1. Two of the six pairs it specifies do not reach it —
     see the characterisation test below. The four that do are pinned here. */
  it.each([
    ['Needs review', 'state-review-fg', 'state-review-bg'],
    ['Confirmed', 'state-confirmed-fg', 'state-confirmed-bg'],
    ['Published', 'state-published-fg', 'state-published-bg'],
  ])('workflow state %s clears 4.5:1', (_label, fg, bg) => {
    expect(contrast(token(fg), token(bg))).toBeGreaterThanOrEqual(BODY);
  });

  /**
   * Characterisation, not approval. MASTER.md §4.2 names these exact colours and
   * §13 demands 4.5:1; both cannot hold at once, and the resolution is a
   * design-system decision rather than something to fix by quietly deviating
   * from the spec. Pinned so the numbers cannot drift further while the question
   * is open, and so raising them turns this test red on purpose.
   */
  it.each([
    ['Candidate', 'state-candidate-fg', 'state-candidate-bg', 4.34],
    ['Withdrawn', 'state-withdrawn-fg', 'state-withdrawn-bg', 4.41],
  ])('workflow state %s is still below 4.5:1 (open §4.2 vs §13 conflict)', (_l, fg, bg, known) => {
    const measured = contrast(token(fg), token(bg));
    expect(measured).toBeCloseTo(known, 2);
    expect(measured).toBeLessThan(BODY);
  });
});
