#!/usr/bin/env node
// Findet und prüft die Geräte im Heimnetz: Home Assistant, go-e Charger, Enphase Envoy, my-PV AC THOR.
// Liest nur – schaltet nichts. Ergebnis zusätzlich in lokal/geraete.json (nicht im Git).
import https from "node:https";
import net from "node:net";
import os from "node:os";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, loadEnv } from "./env.mjs";

const HILFE = `Nutzung:
  node tools/geraete.mjs                 Geräte unter den IPs aus .env.local prüfen (GOE_IP, ENVOY_IP, ACTHOR_IP)
  node tools/geraete.mjs suchen [netz]   Heimnetz durchsuchen, z. B. suchen 192.168.178.0/24
                                         (ohne Angabe: das Netz dieses PCs)`;

loadEnv();

/* ------------------------------------------------------------ Abfragen ---- */

async function http(url, { timeout = 2500, headers = {} } = {}) {
  if (url.startsWith("https:")) return httpsInsecure(url, { timeout, headers });
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(timeout) });
    return { status: res.status, text: await res.text() };
  } catch {
    return null;
  }
}

// Envoy nutzt ein selbst signiertes Zertifikat – nur für dieses lokale Gerät wird es akzeptiert.
function httpsInsecure(url, { timeout, headers }) {
  return new Promise((resolve) => {
    const req = https.get(url, { rejectUnauthorized: false, timeout, headers }, (res) => {
      let text = "";
      res.on("data", (c) => (text += c));
      res.on("end", () => resolve({ status: res.statusCode, text }));
    });
    req.on("timeout", () => req.destroy());
    req.on("error", () => resolve(null));
  });
}

const json = (r) => {
  try {
    return r && r.status === 200 ? JSON.parse(r.text) : null;
  } catch {
    return null;
  }
};

function portOpen(host, port, timeout = 700) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port, timeout });
    const done = (ok) => (s.destroy(), resolve(ok));
    s.on("connect", () => done(true));
    s.on("timeout", () => done(false));
    s.on("error", () => done(false));
  });
}

/* -------------------------------------------------------------- Geräte ---- */

const CAR = { 0: "unbekannt", 1: "bereit, kein Auto", 2: "lädt", 3: "wartet auf Auto", 4: "fertig", 5: "Fehler" };
const FRC = { 0: "neutral", 1: "aus (nicht laden)", 2: "an (laden)" };

async function goe(host) {
  const v2 = json(await http(`http://${host}/api/status?filter=car,amp,frc,alw,nrg,wh,eto,psm,fwv,sse,typ`));
  if (v2 && v2.car !== undefined) {
    return {
      typ: "go-e Charger",
      api: "v2",
      host,
      werte: {
        Zustand: `${CAR[v2.car] ?? v2.car} (car=${v2.car})`,
        Ladestrom: `${v2.amp} A (amp)`,
        Freigabe: `${FRC[v2.frc] ?? v2.frc} (frc=${v2.frc})`,
        Leistung: v2.nrg ? `${v2.nrg[11]} W (nrg[11])` : "–",
        "Geladen seit Anstecken": v2.wh !== undefined ? `${(v2.wh / 1000).toFixed(2)} kWh (wh)` : "–",
        "Gesamt geladen": v2.eto !== undefined ? `${(v2.eto / 1000).toFixed(0)} kWh (eto)` : "–",
        Phasenmodus: `psm=${v2.psm} (1 = 1-phasig, 2 = 3-phasig)`,
        Firmware: v2.fwv,
        Seriennummer: v2.sse,
      },
    };
  }
  const v1 = json(await http(`http://${host}/status`));
  if (v1 && v1.car !== undefined && v1.amp !== undefined) {
    return { typ: "go-e Charger", api: "v1", host, hinweis: "Nur alte API v1 aktiv. In der go-e App „HTTP API v2“ aktivieren (Internet → Erweiterte Einstellungen).", werte: { Zustand: CAR[v1.car] ?? v1.car, Ladestrom: `${v1.amp} A` } };
  }
  return null;
}

async function envoy(host) {
  const info = await http(`https://${host}/info`, { timeout: 3000 });
  if (!info || info.status !== 200 || !/envoy|<sn>/i.test(info.text)) return null;
  const sn = /<sn>(\w+)<\/sn>/.exec(info.text)?.[1];
  const sw = /<software>([^<]+)<\/software>/.exec(info.text)?.[1];
  const major = Number(/D?(\d+)\./.exec(sw ?? "")?.[1] ?? 0);
  const headers = process.env.ENVOY_TOKEN ? { Authorization: `Bearer ${process.env.ENVOY_TOKEN}` } : {};
  const result = { typ: "Enphase Envoy", host, werte: { Seriennummer: sn, Firmware: sw } };
  const prod = json(await http(`https://${host}/production.json?details=1`, { headers, timeout: 4000 }));
  if (prod) {
    const inv = prod.production?.find((p) => p.type === "eim") ?? prod.production?.[0];
    const total = prod.consumption?.find((c) => c.measurementType === "total-consumption");
    const netc = prod.consumption?.find((c) => c.measurementType === "net-consumption");
    Object.assign(result.werte, {
      "PV-Leistung": inv ? `${Math.round(inv.wNow)} W` : "–",
      "PV heute": inv?.whToday !== undefined ? `${(inv.whToday / 1000).toFixed(1)} kWh` : "–",
      Hausverbrauch: total ? `${Math.round(total.wNow)} W` : "keine Verbrauchs-Stromwandler (CTs)",
      Netz: netc ? `${Math.round(netc.wNow)} W (+ Bezug / − Einspeisung)` : "–",
    });
  } else if (major >= 7 && !process.env.ENVOY_TOKEN) {
    result.hinweis = `Firmware ${sw} braucht ein Token: auf https://entrez.enphaseenergy.com erzeugen und als ENVOY_TOKEN in .env.local eintragen. (Die HA-Integration holt es mit deinen Enlighten-Zugangsdaten selbst.)`;
  } else {
    result.hinweis = "Produktionsdaten nicht lesbar – Token prüfen.";
  }
  return result;
}

async function acthor(host) {
  const d = json(await http(`http://${host}/data.jsn`));
  if (!d || typeof d !== "object") return null;
  // Feldnamen unterscheiden sich je nach Firmware – alle Zahlenwerte ausgeben, die interessant klingen
  const werte = {};
  for (const [k, v] of Object.entries(d)) {
    if ((typeof v === "number" || typeof v === "string") && /power|temp|ww|boost|device|fwversion|screen|state|status|load|volt|freq/i.test(k)) werte[k] = v;
  }
  return { typ: "my-PV (AC THOR / ELWA)", host, hinweis: "Temperaturen meldet my-PV meist in Zehntel-Grad (z. B. temp1=545 → 54,5 °C).", werte };
}

async function homeAssistant(host) {
  const r = await http(`http://${host}:8123/manifest.json`, { timeout: 1500 });
  return r?.status === 200 && /home assistant/i.test(r.text) ? { typ: "Home Assistant", host, werte: { Adresse: `http://${host}:8123` } } : null;
}

/* --------------------------------------------------------------- Suche ---- */

function localNet() {
  for (const list of Object.values(os.networkInterfaces())) {
    for (const i of list ?? []) {
      if (i.family === "IPv4" && !i.internal && /^(10|192\.168|172\.(1[6-9]|2\d|3[01]))\./.test(i.address)) return i.address.replace(/\.\d+$/, ".0/24");
    }
  }
  return null;
}

function hostsOf(cidr) {
  const [base, bits = "24"] = cidr.split("/");
  const n = Number(bits);
  if (n < 22 || n > 30) throw new Error("Bitte ein Netz zwischen /22 und /30 angeben, z. B. 192.168.178.0/24");
  const ip = base.split(".").reduce((a, o) => (a << 8) + Number(o), 0) >>> 0;
  const mask = n === 0 ? 0 : (~0 << (32 - n)) >>> 0;
  const start = (ip & mask) >>> 0;
  const out = [];
  for (let i = 1; i < 2 ** (32 - n) - 1; i++) {
    const a = (start + i) >>> 0;
    out.push([a >>> 24, (a >>> 16) & 255, (a >>> 8) & 255, a & 255].join("."));
  }
  return out;
}

async function probe(host) {
  const [p80, p443, p8123] = await Promise.all([portOpen(host, 80), portOpen(host, 443), portOpen(host, 8123)]);
  const found = [];
  if (p8123) found.push(await homeAssistant(host));
  if (p80) found.push((await goe(host)) ?? (await acthor(host)));
  if (p443) found.push(await envoy(host));
  return found.filter(Boolean);
}

async function search(cidr) {
  const hosts = hostsOf(cidr);
  console.log(`Durchsuche ${cidr} (${hosts.length} Adressen) …`);
  const found = [];
  let i = 0;
  await Promise.all(
    Array.from({ length: 48 }, async () => {
      while (i < hosts.length) {
        const host = hosts[i++];
        for (const d of await probe(host)) {
          found.push(d);
          console.log(`  gefunden: ${d.typ} auf ${d.host}`);
        }
      }
    }),
  );
  return found;
}

/* ------------------------------------------------------------- Ausgabe ---- */

function print(devices) {
  for (const d of devices) {
    console.log(`\n■ ${d.typ} – ${d.host}${d.api ? ` (API ${d.api})` : ""}`);
    for (const [k, v] of Object.entries(d.werte ?? {})) console.log(`    ${k.padEnd(24)} ${v}`);
    if (d.hinweis) console.log(`    ⚠ ${d.hinweis}`);
  }
  const env = [];
  const first = (typ) => devices.find((d) => d.typ.startsWith(typ))?.host;
  if (first("Home Assistant")) env.push(`HA_URL=http://${first("Home Assistant")}:8123`);
  if (first("go-e")) env.push(`GOE_IP=${first("go-e")}`);
  if (first("Enphase")) env.push(`ENVOY_IP=${first("Enphase")}`);
  if (first("my-PV")) env.push(`ACTHOR_IP=${first("my-PV")}`);
  if (env.length) console.log(`\nFür .env.local:\n  ${env.join("\n  ")}`);
  mkdirSync(join(ROOT, "lokal"), { recursive: true });
  writeFileSync(join(ROOT, "lokal", "geraete.json"), JSON.stringify({ zeit: new Date().toISOString(), geraete: devices }, null, 2));
  console.log(`\nGespeichert: lokal/geraete.json`);
}

const [cmd, arg] = process.argv.slice(2);
if (cmd === "hilfe" || cmd === "--help") {
  console.log(HILFE);
} else if (cmd === "suchen") {
  const cidr = arg ?? localNet();
  if (!cidr) {
    console.error("Kein Heimnetz erkannt – bitte angeben, z. B. suchen 192.168.178.0/24");
    process.exit(2);
  }
  const found = await search(cidr);
  if (!found.length) console.log("Nichts gefunden. Sind PC und Geräte im selben Netz?");
  print(found);
} else {
  const checks = [
    ["GOE_IP", goe, "go-e Charger"],
    ["ENVOY_IP", envoy, "Enphase Envoy"],
    ["ACTHOR_IP", acthor, "AC THOR"],
  ];
  const devices = [];
  for (const [key, fn, label] of checks) {
    const host = process.env[key];
    if (!host) {
      console.log(`·  ${label}: ${key} nicht gesetzt (node tools/geraete.mjs suchen findet die IP)`);
      continue;
    }
    const d = await fn(host);
    if (d) devices.push(d);
    else console.log(`✗  ${label}: unter ${host} nicht erreichbar oder kein ${label}`);
  }
  print(devices);
}
