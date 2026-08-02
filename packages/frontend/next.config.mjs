import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    // Next.js 14 keeps this option under `experimental`. The frontend imports
    // the shared workspace package, so tracing must start at the monorepo root.
    outputFileTracingRoot: fileURLToPath(new URL('../..', import.meta.url)),
  },
  reactStrictMode: true,
  transpilePackages: ['@elderly-care/shared'],
  headers: async () => [
    {
      source: '/sw.js',
      headers: [
        { key: 'Content-Type', value: 'application/javascript; charset=utf-8' },
        { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
        { key: 'Service-Worker-Allowed', value: '/' },
      ],
    },
  ],
};

export default nextConfig;
