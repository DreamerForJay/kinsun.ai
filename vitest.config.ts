import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  resolve: {
    // Only packages/frontend uses `@/...` imports (its own tsconfig path
    // alias, mirrored in packages/frontend/vitest.config.ts) — running its
    // tests from this root config otherwise fails to resolve them.
    alias: { '@': fileURLToPath(new URL('./packages/frontend/src', import.meta.url)) },
  },
  test: {
    include: ['packages/**/src/**/*.{test,spec}.ts'],
    exclude: ['**/node_modules/**', '**/dist/**', '**/.next/**'],
    environment: 'node',
    globals: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['packages/**/src/**/*.ts'],
      exclude: ['**/*.test.ts', '**/*.spec.ts', '**/types/**'],
    },
  },
});
