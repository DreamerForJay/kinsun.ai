/**
 * Secondary navigation links sized as real touch targets.
 *
 * Two rules meet here, and missing either is easy:
 *
 * - §6.1 forbids asking for a precise tap, and a bare inline link renders about
 *   26px tall — roughly half the floor on every surface.
 * - The colour has to be declared. An `<a>` with only a size given still paints
 *   in the browser's default link blue, which is off-palette and which no lint
 *   rule catches, because it is not a raw hex in the source — it is the absence
 *   of one. Visual QA found several of these after the automated checks passed.
 *
 * --touch-min resolves per surface (64px voice, 48px care/family), so one style
 * is correct everywhere.
 */
export const touchLinkStyle = {
  alignItems: 'center',
  color: 'var(--color-primary-text)',
  display: 'inline-flex',
  fontSize: 'var(--text-base)',
  justifyContent: 'center',
  minHeight: 'var(--touch-min)',
  padding: '0 var(--space-3)',
};
