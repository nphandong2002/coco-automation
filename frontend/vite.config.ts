import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` proxies API/media to the backend on :8080
export default defineConfig({
  plugins: [react()],
  build: {
    // capture.html = headless 3D frame capture used by the render worker
    rollupOptions: { input: { main: resolve(__dirname, "index.html"), capture: resolve(__dirname, "capture.html") } },
  },
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": "http://localhost:8080", "/media": "http://localhost:8080" },
  },
});
