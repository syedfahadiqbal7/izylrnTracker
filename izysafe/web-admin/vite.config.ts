import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    host: true,
    // In Docker on Windows/macOS, bind-mount file events don't reach the
    // container, so Vite never hot-reloads. CHOKIDAR_USEPOLLING (set on the
    // web-admin compose service) switches the watcher to polling so edits are
    // picked up. Harmless/unset for normal local dev.
    watch: process.env.CHOKIDAR_USEPOLLING
      ? { usePolling: true, interval: 300 }
      : undefined,
  },
});
