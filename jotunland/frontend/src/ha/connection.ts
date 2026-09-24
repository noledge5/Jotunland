import {
  createConnection,
  createLongLivedTokenAuth,
  getAuth,
  type AuthData,
  type Connection,
} from "home-assistant-js-websocket";

export type ConnMode = "auto" | "token" | "demo";

export interface ConnSettings {
  mode: ConnMode;
  /** Basis-URL von Home Assistant, z. B. http://homeassistant.local:8123 */
  url?: string;
  /** Langlebiges Zugriffstoken (nur Modus "token") */
  token?: string;
}

const SETTINGS_KEY = "jotunland.connection";
const TOKENS_KEY = "jotunland.tokens";

function storageGet(store: Storage | undefined, key: string): string | null {
  try {
    return store?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* privater Modus o. Ä. – dann eben ohne Speichern */
  }
}

/** Liegt das Frontend unter /local/… bzw. /hacsfiles/… direkt auf Home Assistant? */
export function servedFromHomeAssistant(): boolean {
  return /\/(local|hacsfiles)\//.test(window.location.pathname);
}

export function loadSettings(): ConnSettings {
  const raw = storageGet(localStorage, SETTINGS_KEY);
  if (raw) {
    try {
      return JSON.parse(raw) as ConnSettings;
    } catch {
      /* ignorieren */
    }
  }
  // Nur im Entwicklungsmodus (npm run dev) – im Build gibt es diese Werte nicht
  const envUrl = import.meta.env.DEV ? (import.meta.env.VITE_HA_URL as string | undefined) : undefined;
  const envToken = import.meta.env.DEV ? (import.meta.env.VITE_HA_TOKEN as string | undefined) : undefined;
  if (envUrl && envToken) return { mode: "token", url: envUrl, token: envToken };
  if (servedFromHomeAssistant()) return { mode: "auto" };
  if (new URLSearchParams(window.location.search).has("demo")) return { mode: "demo" };
  return { mode: "auto", url: envUrl };
}

export function saveSettings(s: ConnSettings | null) {
  storageSet(SETTINGS_KEY, s ? JSON.stringify(s) : null);
}

export function logout() {
  storageSet(TOKENS_KEY, null);
  saveSettings(null);
}

/** Braucht der Nutzer noch den Einrichtungsdialog? */
export function needsSetup(s: ConnSettings): boolean {
  if (s.mode === "demo") return false;
  if (s.mode === "token") return !s.url || !s.token;
  // "auto" = Anmeldung über den HA-Login. Ohne URL nur möglich, wenn wir auf HA selbst liegen.
  return !s.url && !servedFromHomeAssistant() && !new URLSearchParams(location.search).has("auth_callback");
}

export async function connect(s: ConnSettings): Promise<Connection> {
  if (s.mode === "token") {
    const auth = createLongLivedTokenAuth(s.url!.replace(/\/$/, ""), s.token!);
    return createConnection({ auth });
  }

  const hassUrl = (s.url || window.location.origin).replace(/\/$/, "");
  const auth = await getAuth({
    hassUrl,
    saveTokens: (data) => storageSet(TOKENS_KEY, data ? JSON.stringify(data) : null),
    loadTokens: async () => {
      // 1. eigene Tokens, 2. die der HA-Oberfläche (gleiche Domain, "Angemeldet bleiben")
      for (const [store, key] of [
        [localStorage, TOKENS_KEY],
        [localStorage, "hassTokens"],
        [sessionStorage, "hassTokens"],
      ] as const) {
        const raw = storageGet(store, key);
        if (!raw) continue;
        try {
          const data = JSON.parse(raw) as AuthData;
          if (data.hassUrl?.replace(/\/$/, "") === hassUrl) return data;
        } catch {
          /* weiter */
        }
      }
      return null;
    },
  });
  // auth_callback-Parameter nach erfolgreichem Login aus der URL entfernen
  if (location.search.includes("auth_callback=1")) {
    history.replaceState(null, "", location.pathname);
  }
  return createConnection({ auth });
}

/* ------------------------------------------------------------ Add-on ---- */

export interface AddonStatus {
  addon: true;
  package: { installed: boolean; version: number | null; path: string | null };
  blueprint: boolean;
  setup: { automatic: boolean; note: string };
  pending_defaults: boolean;
  /** Fehler, die HA beim Laden des Pakets gemeldet hat */
  load_errors: string[];
  last_install?: number;
}

/** Läuft Jotunland als Home-Assistant-Add-on? Dann gibt es ./jotunland/status. */
export async function probeAddon(): Promise<AddonStatus | null> {
  try {
    const res = await fetch("./jotunland/status", { cache: "no-store", signal: AbortSignal.timeout(3000) });
    if (!res.ok) return null;
    const data = await res.json();
    return data?.addon ? (data as AddonStatus) : null;
  } catch {
    return null;
  }
}

export async function addonApi<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`./jotunland/${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data?.error ?? `Fehler ${res.status}`), { data });
  return data as T;
}

/** Im Add-on meldet der Server sich bei HA an – die Oberfläche braucht kein Token. */
export function connectAddon(): Promise<Connection> {
  const base = new URL(".", window.location.href).href.replace(/\/$/, "");
  return createConnection({ auth: createLongLivedTokenAuth(base, "addon") });
}
