import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `/api` is proxied rather than called cross-origin: the browser makes a
// same-origin request (no CORS preflight in dev) and the production build can
// sit behind the same gateway without a single fetch call changing.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
