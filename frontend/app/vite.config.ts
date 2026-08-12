import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API is proxied rather than called cross-origin so the browser sends a
// same-origin request: no CORS preflight in dev, and the production build can
// sit behind the same gateway without changing a single fetch call.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } },
  },
});
