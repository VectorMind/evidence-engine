import { defineConfig } from 'astro/config';
import node from '@astrojs/node';
import react from '@astrojs/react';

// Fully SSR (plan D5: nothing baked at build time — data reads happen at
// request time so a data update never requires a rebuild). Standalone node
// adapter so `node dist/server/entry.mjs` is directly runnable by
// `even serve` without an express wrapper (deviation from astro-huge-doc's
// 'middleware' mode, which exists there only to host auth middleware).
export default defineConfig({
  output: 'server',
  integrations: [react()],
  adapter: node({
    mode: 'standalone',
  }),
  vite: {
    ssr: {
      external: ['better-sqlite3'],
    },
    optimizeDeps: {
      exclude: ['better-sqlite3'],
    },
  },
});
