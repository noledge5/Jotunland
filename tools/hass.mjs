// Verbindung zu Home Assistant (REST und WebSocket) für die Werkzeuge.
// Zugangsdaten aus .env.local – loadEnv() muss vorher gelaufen sein.
import { need } from "./env.mjs";

let cfg;
function config() {
  cfg ??= {
    url: need("HA_URL").replace(/\/$/, ""),
    token: need("HA_TOKEN", "Home Assistant → Profil → Sicherheit → Langlebige Zugriffstoken."),
  };
  return cfg;
}

export async function api(method, path, body) {
  const { url, token } = config();
  const res = await fetch(`${url}/api/${path}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = text;
  }
  if (!res.ok) throw new Error(`${method} /api/${path} → HTTP ${res.status}: ${typeof data === "string" ? data : JSON.stringify(data)}`);
  return data;
}

export async function socket() {
  const { url, token } = config();
  const ws = new WebSocket(url.replace(/^http/, "ws") + "/api/websocket");
  const pending = new Map();
  const listeners = new Map();
  let nextId = 1;
  await new Promise((resolve, reject) => {
    ws.addEventListener("error", () => reject(new Error(`WebSocket zu ${url} fehlgeschlagen`)));
    ws.addEventListener("message", (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "auth_required") ws.send(JSON.stringify({ type: "auth", access_token: token }));
      else if (msg.type === "auth_ok") resolve();
      else if (msg.type === "auth_invalid") reject(new Error("Token ungültig"));
      else if (msg.type === "result" && pending.has(msg.id)) {
        const { ok, fail } = pending.get(msg.id);
        pending.delete(msg.id);
        msg.success ? ok(msg.result) : fail(new Error(msg.error?.message ?? "Fehler"));
      } else if (msg.type === "event") listeners.get(msg.id)?.(msg.event);
    });
  });
  const send = (msg) =>
    new Promise((ok, fail) => {
      const id = nextId++;
      pending.set(id, { ok, fail });
      ws.send(JSON.stringify({ id, ...msg }));
    });
  const subscribe = async (msg, onEvent) => {
    const id = nextId;
    listeners.set(id, onEvent);
    await send(msg);
  };
  return { send, subscribe, close: () => ws.close() };
}
