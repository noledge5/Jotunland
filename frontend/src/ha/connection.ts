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
  const envUrl = import.meta.env.VITE_HA_URL as string | undefined;
  const envToken = import.meta.env.VITE_HA_TOKEN as string | undefined;
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
