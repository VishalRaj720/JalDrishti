import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `/api` is proxied rather than called cross-origin: the browser makes a
// same-origin request (no CORS preflight in dev) and the production build can
// sit behind the same gateway without a single fetch call changing.
//
// `API_PROXY_TARGET` overrides where dev sends `/api`, and DEFAULTS TO WHAT IT
// ALWAYS WAS. It exists so a UI change can be checked against the deployed API
// without a local Postgres+PostGIS, which is the only way to see real bands,
// real determinand values and real coverage gaps on screen. Production routing
// is untouched by this: there, `worker/index.js` does the proxying and never
// reads a Vite config.
//
//   API_PROXY_TARGET=https://jaldrishti-api.onrender.com npm run dev
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
