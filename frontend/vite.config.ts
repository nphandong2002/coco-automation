import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: `npm run dev` proxies API/media to the backend on :8080
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: { "/api": "http://localhost:8080", "/media": "http://localhost:8080" },
  },
});
