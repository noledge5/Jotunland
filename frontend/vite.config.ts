import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" → das Build funktioniert unter jedem Pfad, z. B. /local/jotunland/
export default defineConfig({
  base: "./",
  plugins: [react()],
  // fs.allow: das HA-Paket liegt außerhalb von frontend/ und wird per ?raw eingebunden
  server: { host: true, port: 5173, fs: { allow: [".."] } },
});
