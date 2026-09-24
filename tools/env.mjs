// Liest .env.local aus dem Projektordner (KEY=WERT je Zeile). Werte aus der Umgebung haben Vorrang.
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

export function loadEnv() {
  const file = join(ROOT, ".env.local");
  if (!existsSync(file)) return;
  for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (m && !line.trimStart().startsWith("#") && process.env[m[1]] === undefined) {
      process.env[m[1]] = m[2].replace(/^["']|["']$/g, "");
    }
  }
}

export function need(name, hint) {
  const v = process.env[name];
  if (!v) {
    console.error(`✗ ${name} fehlt – in .env.local eintragen (Vorlage: .env.example). ${hint ?? ""}`);
    process.exit(2);
  }
  return v;
}
