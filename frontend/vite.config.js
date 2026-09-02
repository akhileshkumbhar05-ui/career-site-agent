import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/webapp": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/autofill": "http://127.0.0.1:8000",
      "/agents": "http://127.0.0.1:8000",
      "/application-loop": "http://127.0.0.1:8000",
      "/application-sprints": "http://127.0.0.1:8000"
    }
  }
});
