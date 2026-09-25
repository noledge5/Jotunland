#!/usr/bin/env node
// Jotunland-Werkzeug für Home Assistant – für dich und für Claude Code im Heimnetz.
// Zugangsdaten kommen aus .env.local (Vorlage: .env.example).
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { basename } from "node:path";
import YAML from "yaml";
import { loadEnv, need } from "./env.mjs";
import { api, socket } from "./hass.mjs";

const HILFE = `Nutzung: node tools/ha.mjs <befehl> …

  states [muster]              Entitäten mit Zustand auflisten (muster = Regex auf ID/Name)
  get <entity_id>              Zustand und alle Attribute als JSON
  watch [muster] [sekunden]    Zustandsänderungen live mitschreiben (Strg+C beendet)
  call <domain.dienst> [json]  Dienst aufrufen, z. B. call light.turn_on '{"entity_id":"light.kueche"}'
  validate <datei.yaml>        Automationen/Skripte prüfen + unbekannte entity_ids melden
  check                        Gesamte HA-Konfiguration prüfen
  trace <automation>           Letzten Durchlauf einer Automation zeigen (ID oder entity_id)
  reload                       Automationen, Skripte, Templates und Helfer neu laden
  deploy <datei.yaml> [ziel]   Prüfen → per SSH nach /config/packages/ kopieren → Konfig prüfen
                               (bei Fehler zurück) → neu laden. Braucht HA_SSH in .env.local.`;

loadEnv();
const [cmd, ...args] = process.argv.slice(2);
if (!cmd || cmd === "hilfe" || cmd === "--help") {
  console.log(HILFE);
  process.exit(0);
}
/* ------------------------------------------------------------- Helfer ---- */

const pad = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s.padEnd(n));
const time = () => new Date().toLocaleTimeString("de-DE");
const withUnit = (e) => `${e.state}${e.attributes?.unit_of_measurement ? " " + e.attributes.unit_of_measurement : ""}`;

// HA-eigene YAML-Tags beim Einlesen einfach als Text behalten
const HA_TAGS = ["!input", "!secret", "!include", "!include_dir_named", "!include_dir_merge_named", "!include_dir_list", "!include_dir_merge_list", "!env_var"].map((tag) => ({
  tag,
  resolve: (value) => `${tag} ${value}`,
}));

function readYaml(file) {
  return YAML.parse(readFileSync(file, "utf8"), { customTags: HA_TAGS }) ?? {};
}

function slug(text) {
  return String(text)
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

/** Automationen und Skripte aus einem Paket (oder automations.yaml / scripts.yaml) */
function collect(doc) {
  const automations = Array.isArray(doc) ? doc : doc.automation ?? [];
  const scripts = !Array.isArray(doc) && doc.script ? doc.script : {};
  return { automations: Array.isArray(automations) ? automations : [], scripts };
}

/** Was das Paket selbst anlegt – diese IDs gibt es in HA erst nach dem Einspielen */
function definedIds(doc) {
  const ids = new Set();
  if (Array.isArray(doc)) return ids;
  for (const [domain, block] of Object.entries(doc)) {
    if (domain.startsWith("input_") && block && typeof block === "object") for (const key of Object.keys(block)) ids.add(`${domain}.${key}`);
  }
  for (const key of Object.keys(doc.script ?? {})) ids.add(`script.${key}`);
  for (const a of doc.automation ?? []) if (a?.alias) ids.add(`automation.${slug(a.alias)}`);
  // Szenen, die erst zur Laufzeit per scene.create entstehen
  for (const m of JSON.stringify(doc).matchAll(/"scene_id":"(\w+)"/g)) ids.add(`scene.${m[1]}`);
  for (const block of [doc.template ?? []].flat()) {
    for (const [kind, items] of Object.entries(block ?? {})) {
      if (Array.isArray(items)) for (const it of items) if (it?.name) ids.add(`${kind}.${slug(it.name)}`);
    }
  }
  return ids;
}

const ENTITY_RE = /\b(?:sensor|binary_sensor|switch|number|select|climate|light|cover|fan|lock|button|input_boolean|input_number|input_select|input_datetime|input_text|input_button|script|automation|scene|person|zone|device_tracker|water_heater|weather)\.[a-z0-9_]+\b/g;

async function validateFile(file, { quiet = false } = {}) {
  const doc = readYaml(file);
  const { automations, scripts } = collect(doc);
  const checks = [];
  for (const a of automations) {
    if (!a || typeof a !== "object") continue;
    const label = `Automation „${a.alias ?? a.id ?? "?"}“`;
    if (a.use_blueprint) {
      checks.push({ label, skip: `Blueprint ${a.use_blueprint.path}` });
      continue;
    }
    checks.push({ label, msg: { triggers: a.triggers ?? a.trigger ?? [], conditions: a.conditions ?? a.condition ?? [], actions: a.actions ?? a.action ?? [] } });
  }
  for (const [key, s] of Object.entries(scripts)) {
    if (s && typeof s === "object") checks.push({ label: `Skript „${s.alias ?? key}“`, msg: { actions: s.sequence ?? [] } });
  }

  const ws = await socket();
  let errors = 0;
  for (const c of checks) {
    if (c.skip) {
      if (!quiet) console.log(`  ·  ${c.label} (${c.skip}, prüft HA beim Laden)`);
      continue;
    }
    try {
      const res = await ws.send({ type: "validate_config", ...c.msg });
      const bad = Object.entries(res).filter(([, r]) => r && !r.valid);
      if (bad.length) {
        errors++;
        for (const [part, r] of bad) console.log(`  ✗  ${c.label} (${part}): ${r.error}`);
      } else if (!quiet) console.log(`  ✓  ${c.label}`);
    } catch (err) {
      errors++;
      console.log(`  ✗  ${c.label}: ${err.message}`);
    }
  }
  ws.close();

  // Verweise auf Entitäten, die es (noch) nicht gibt – Tippfehler oder falsche Zuordnung
  const states = new Set((await api("GET", "states")).map((e) => e.entity_id));
  const own = definedIds(doc);
  const text = readFileSync(file, "utf8")
    .split("\n")
    .filter((l) => !l.trimStart().startsWith("#"))
    .join("\n")
    .replace(/\b(action|service):\s*["']?[\w.]+/g, ""); // Dienstaufrufe wie switch.turn_on sind keine Entitäten
  const unknown = [...new Set(text.match(ENTITY_RE) ?? [])].filter((id) => !states.has(id) && !own.has(id) && !id.startsWith("automation."));
  if (unknown.length) {
    console.log(`  ⚠  ${unknown.length} entity_id(s) gibt es in Home Assistant nicht:`);
    for (const id of unknown) console.log(`       ${id}`);
  }
  console.log(errors ? `✗ ${errors} Fehler in ${checks.length} Prüfungen` : `✓ ${checks.filter((c) => !c.skip).length} Automationen/Skripte gültig`);
  return errors;
}

async function checkConfig() {
  const r = await api("POST", "config/core/check_config");
  if (r.result === "valid") console.log("✓ Konfiguration gültig" + (r.warnings ? `\n  Hinweise: ${r.warnings}` : ""));
  else console.log(`✗ Konfiguration ungültig:\n${r.errors}`);
  return r.result === "valid";
}

/** Konfigurationsfehler, die HA seit `since` protokolliert hat. Die Prüfung meldet z. B. fehlerhafte
 *  Template-Sensoren nicht – sie tauchen erst beim Laden im Protokoll auf. */
async function configErrorsSince(since, fileFilter) {
  const ws = await socket();
  const entries = await ws.send({ type: "system_log/list" });
  ws.close();
  return entries
    .filter((e) => e.timestamp >= since && ["ERROR", "CRITICAL"].includes(e.level))
    .flatMap((e) => e.message)
    .filter((m) => /Invalid config|Error loading|failed to setup|Setup failed/i.test(m) && (!fileFilter || m.includes(fileFilter)));
}

async function reload() {
  for (const svc of ["input_boolean", "input_number", "input_select", "input_datetime", "input_text", "template", "script", "automation"]) {
    try {
      await api("POST", `services/${svc}/reload`, {});
      console.log(`  ✓ ${svc} neu geladen`);
    } catch {
      console.log(`  ·  ${svc}: nicht geladen (Integration nicht aktiv – nach dem ersten Einspielen einmal HA neu starten)`);
    }
  }
}

function ssh(remoteCmd, input) {
  const target = need("HA_SSH", "z. B. HA_SSH=root@homeassistant.local (Add-on „Terminal & SSH“ mit deinem Schlüssel).");
  const port = process.env.HA_SSH_PORT ?? "22";
  return execFileSync("ssh", ["-p", port, target, remoteCmd], { encoding: "utf8", input });
}

/* ------------------------------------------------------------- Befehle ---- */

const commands = {
  async states(muster) {
    const re = muster ? new RegExp(muster, "i") : null;
    const list = (await api("GET", "states"))
      .filter((e) => !re || re.test(e.entity_id) || re.test(e.attributes.friendly_name ?? ""))
      .sort((a, b) => a.entity_id.localeCompare(b.entity_id));
    for (const e of list) console.log(`${pad(e.entity_id, 56)} ${pad(withUnit(e), 22)} ${e.attributes.friendly_name ?? ""}`);
    console.log(`— ${list.length} Entitäten`);
  },

  async get(id) {
    if (!id) throw new Error("entity_id fehlt");
    console.log(JSON.stringify(await api("GET", `states/${id}`), null, 2));
  },

  async watch(muster, sekunden) {
    const re = muster ? new RegExp(muster, "i") : null;
    const ws = await socket();
    console.log(`Beobachte ${muster ? `/${muster}/` : "alle Entitäten"}${sekunden ? ` für ${sekunden} s` : ""} … (Strg+C beendet)`);
    await ws.subscribe({ type: "subscribe_events", event_type: "state_changed" }, (ev) => {
      const { entity_id, old_state, new_state } = ev.data;
      if (re && !re.test(entity_id) && !re.test(new_state?.attributes?.friendly_name ?? "")) return;
      const before = old_state ? withUnit(old_state) : "–";
      const after = new_state ? withUnit(new_state) : "entfernt";
      if (before === after) return; // nur Attribut-Änderungen
      console.log(`${time()}  ${pad(entity_id, 50)} ${before} → ${after}`);
    });
    if (sekunden) setTimeout(() => (ws.close(), process.exit(0)), Number(sekunden) * 1000);
    else await new Promise(() => {});
  },

  async call(dienst, json) {
    const [domain, service] = (dienst ?? "").split(".");
    if (!domain || !service) throw new Error("Format: call domain.dienst '{json}'");
    const changed = await api("POST", `services/${domain}/${service}`, json ? JSON.parse(json) : {});
    console.log(`✓ ${dienst} ausgeführt – ${changed.length} Entität(en) geändert`);
    for (const e of changed) console.log(`   ${pad(e.entity_id, 50)} ${withUnit(e)}`);
  },

  async validate(file) {
    if (!file) throw new Error("Datei fehlt");
    process.exitCode = (await validateFile(file)) ? 1 : 0;
  },

  async check() {
    process.exitCode = (await checkConfig()) ? 0 : 1;
  },

  async trace(name) {
    if (!name) throw new Error("Automation fehlt (ID wie jotunland_heizzeiten oder entity_id)");
    let itemId = name;
    if (name.startsWith("automation.")) itemId = (await api("GET", `states/${name}`)).attributes.id;
    const ws = await socket();
    const runs = (await ws.send({ type: "trace/list", domain: "automation", item_id: itemId })).sort((a, b) => b.timestamp.start.localeCompare(a.timestamp.start));
    if (!runs.length) {
      console.log(`Kein Durchlauf von ${itemId} gespeichert.`);
      return ws.close();
    }
    const t = await ws.send({ type: "trace/get", domain: "automation", item_id: itemId, run_id: runs[0].run_id });
    console.log(`Automation ${itemId} – letzter von ${runs.length} Durchläufen`);
    console.log(`  Start:     ${new Date(t.timestamp.start).toLocaleString("de-DE")}`);
    console.log(`  Auslöser:  ${t.trigger ?? "–"}`);
    console.log(`  Ergebnis:  ${t.script_execution ?? t.state}${t.error ? ` – ${t.error}` : ""}`);
    for (const [path, steps] of Object.entries(t.trace ?? {})) {
      for (const step of steps) {
        const r = step.result ?? {};
        const info = step.error ? `✗ ${step.error}` : r.result === false ? "nein" : r.result === true ? "ja" : r.params ? `${r.params.domain}.${r.params.service} ${JSON.stringify(r.params.service_data ?? {})}` : "";
        console.log(`    ${pad(path, 28)} ${info}`);
      }
    }
    ws.close();
  },

  async reload() {
    const since = Date.now() / 1000 - 1;
    await reload();
    await new Promise((r) => setTimeout(r, 1500));
    for (const m of await configErrorsSince(since)) console.log(`  ✗ ${m}`);
  },

  async deploy(file, ziel) {
    if (!file) throw new Error("Datei fehlt");
    const target = `/config/${ziel ?? `packages/${basename(file)}`}`;
    if (/packages\/jotunland\.yaml$/.test(target)) {
      console.log("⚠  packages/jotunland.yaml verwaltet das Add-on – eigene Automationen besser in eine eigene Datei (z. B. packages/jotunland_haus.yaml).");
    }
    console.log(`1/4 Prüfen …`);
    if (await validateFile(file, { quiet: true })) throw new Error("Abgebrochen – erst die Fehler beheben.");
    console.log(`2/4 Kopieren nach ${target} (alte Fassung → .bak) …`);
    ssh(`mkdir -p "$(dirname '${target}')" && if [ -f '${target}' ]; then cp '${target}' '${target}.bak'; else rm -f '${target}.bak'; fi && cat > '${target}'`, readFileSync(file));
    console.log(`3/4 Konfiguration prüfen …`);
    if (!(await checkConfig())) {
      ssh(`if [ -f '${target}.bak' ]; then mv '${target}.bak' '${target}'; else rm -f '${target}'; fi`);
      throw new Error("Zurückgesetzt – Home Assistant läuft unverändert weiter.");
    }
    console.log(`4/4 Neu laden …`);
    const since = Date.now() / 1000 - 1;
    await reload();
    await new Promise((r) => setTimeout(r, 1500));
    const errors = await configErrorsSince(since, basename(target));
    if (errors.length) {
      for (const m of errors) console.log(`  ✗ ${m}`);
      ssh(`if [ -f '${target}.bak' ]; then mv '${target}.bak' '${target}'; else rm -f '${target}'; fi`);
      await reload();
      throw new Error("Home Assistant hat die Datei beim Laden abgelehnt – alte Fassung ist wieder aktiv.");
    }
    console.log(`✓ ${basename(file)} ist aktiv.`);
  },
};

const run = commands[cmd];
if (!run) {
  console.error(`Unbekannter Befehl „${cmd}“.\n\n${HILFE}`);
  process.exit(2);
}
run(...args).catch((err) => {
  console.error(`✗ ${err.message}`);
  process.exit(1);
});
