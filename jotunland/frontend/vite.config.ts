import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  // base "./" → das Build funktioniert unter jedem Pfad, z. B. unter Ingress oder /local/jotunland/
  base: "./",
  plugins: [react()],
  // .env.local im Projektordner nur im Entwicklungsmodus lesen – ein Token darf nie ins Build geraten
  envDir: command === "serve" ? "../.." : "./.kein-env",
  // fs.allow: das HA-Paket liegt außerhalb von frontend/ und wird per ?raw eingebunden
  server: { host: true, port: 5173, fs: { allow: [".."] } },
}));
