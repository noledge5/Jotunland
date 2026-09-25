#!/usr/bin/env node
// Findet und prüft die Geräte im Heimnetz: Home Assistant, Enphase Envoy, my-PV AC THOR, go-e Charger –
// und listet bei "suchen" alle übrigen Geräte mit Hersteller, Namen und offenen Diensten.
// Liest nur – schaltet nichts. Ergebnis zusätzlich in lokal/geraete.json (nicht im Git).
import dgram from "node:dgram";
import https from "node:https";
import net from "node:net";
import os from "node:os";
import tls from "node:tls";
import { execFile } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, loadEnv } from "./env.mjs";

const HILFE = `Nutzung:
  node tools/geraete.mjs                 Geräte unter den IPs aus .env.local prüfen (GOE_IP, ENVOY_IP, ACTHOR_IP)
  node tools/geraete.mjs suchen [netz]   Heimnetz durchsuchen, z. B. suchen 192.168.178.0/24
                                         (ohne Angabe: das Netz dieses PCs)
  node tools/geraete.mjs hersteller      Herstellerliste der IEEE laden (lokal/oui.csv, ca. 5 MB) –
                                         danach nennt "suchen" den Hersteller jedes Geräts`;

loadEnv();

/* ------------------------------------------------------------ Abfragen ---- */

async function http(url, { timeout = 2500, headers = {}, redirect = "follow" } = {}) {
  if (url.startsWith("https:")) return httpsInsecure(url, { timeout, headers });
  try {
    const res = await fetch(url, { headers, redirect, signal: AbortSignal.timeout(timeout) });
    return { status: res.status, headers: Object.fromEntries(res.headers), text: await res.text() };
  } catch {
    return null;
  }
}

// Envoy und viele andere Heimgeräte nutzen selbst signierte Zertifikate – nur lokal und nur lesend akzeptiert.
function httpsInsecure(url, { timeout, headers }) {
  return new Promise((resolve) => {
    const req = https.get(url, { rejectUnauthorized: false, timeout, headers }, (res) => {
      let text = "";
      res.on("data", (c) => (text += c));
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, text }));
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

// "offen", "zu" (Gerät antwortet, Port geschlossen – das Gerät existiert also) oder null (keine Antwort).
// Die Wartezeit ist großzügig: macOS löst beim ersten Kontakt erst die MAC-Adresse auf (ARP),
// bei vielen gleichzeitigen Verbindungen dauert das deutlich länger als eine Sekunde.
function portState(host, port, timeout = 2000) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    const done = (state) => (clearTimeout(t), s.destroy(), resolve(state));
    const t = setTimeout(() => done(null), timeout);
    s.on("connect", () => done("offen"));
    s.on("error", (e) => done(e.code === "ECONNREFUSED" ? "zu" : null));
  });
}

async function pool(items, n, fn) {
  const out = [];
  let i = 0;
  await Promise.all(
    Array.from({ length: Math.min(n, items.length) }, async () => {
      while (i < items.length) {
        const k = i++;
        out[k] = await fn(items[k]);
      }
    }),
  );
  return out;
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

const PORTS = {
  22: "SSH", 53: "DNS", 80: "HTTP", 443: "HTTPS", 445: "Dateifreigabe", 502: "Modbus TCP", 554: "Video (RTSP)",
  1400: "Sonos", 1883: "MQTT", 5000: "HTTP", 5001: "HTTPS", 6053: "ESPHome", 7000: "AirPlay", 8009: "Chromecast",
  8080: "HTTP", 8123: "Home Assistant", 8443: "HTTPS", 8883: "MQTT (TLS)", 62078: "Apple-Gerät",
};

// Kleine eingebaute Herstellerliste (erste 3 Bytes der MAC). Vollständig mit "node tools/geraete.mjs hersteller".
const OUI_KLEIN = {
  "00:1d:c0": "Enphase Energy",
  "2c:cf:67": "Raspberry Pi", "b8:27:eb": "Raspberry Pi", "dc:a6:32": "Raspberry Pi", "e4:5f:01": "Raspberry Pi", "d8:3a:dd": "Raspberry Pi",
  "00:11:32": "Synology", "90:09:d0": "Synology",
  "00:0e:58": "Sonos", "5c:aa:fd": "Sonos", "94:9f:3e": "Sonos", "48:a6:b8": "Sonos", "b8:e9:37": "Sonos",
  "00:17:88": "Philips Hue (Signify)", "ec:b5:fa": "Philips Hue (Signify)",
  "24:0a:c4": "Espressif", "30:ae:a4": "Espressif", "84:cc:a8": "Espressif", "a4:cf:12": "Espressif", "24:6f:28": "Espressif",
  "3c:61:05": "Espressif", "7c:9e:bd": "Espressif", "8c:aa:b5": "Espressif", "98:f4:ab": "Espressif", "c8:c9:a3": "Espressif",
  "ec:fa:bc": "Espressif", "48:3f:da": "Espressif", "08:3a:f2": "Espressif", "94:b9:7e": "Espressif", "e8:db:84": "Espressif",
  "5c:cf:7f": "Espressif", "18:fe:34": "Espressif", "2c:3a:e8": "Espressif", "dc:4f:22": "Espressif", "84:f3:eb": "Espressif",
  "bc:dd:c2": "Espressif", "c4:4f:33": "Espressif", "40:22:d8": "Espressif", "34:94:54": "Espressif", "10:52:1c": "Espressif",
};

let ouiListe;
function vendorOf(mac) {
  if (!mac) return null;
  if (parseInt(mac.slice(0, 2), 16) & 2) return "private Adresse";
  if (ouiListe === undefined) {
    ouiListe = null;
    const file = join(ROOT, "lokal", "oui.csv");
    if (existsSync(file)) {
      ouiListe = new Map();
      for (const line of readFileSync(file, "utf8").split(/\r?\n/)) {
        const m = /^MA-L,([0-9A-F]{6}),(?:"([^"]*)"|([^,]*))/.exec(line);
        if (m) ouiListe.set(m[1].toLowerCase(), (m[2] ?? m[3]).trim());
      }
    }
  }
  return ouiListe?.get(mac.slice(0, 8).replace(/:/g, "")) ?? OUI_KLEIN[mac.slice(0, 8)] ?? null;
}

async function loadOui() {
  const res = await fetch("https://standards-oui.ieee.org/oui/oui.csv", {
    headers: { "User-Agent": "Mozilla/5.0 (jotunland-tools)" },
    signal: AbortSignal.timeout(90000),
  });
  if (!res.ok) throw new Error(`IEEE antwortet mit ${res.status}`);
  const text = await res.text();
  mkdirSync(join(ROOT, "lokal"), { recursive: true });
  writeFileSync(join(ROOT, "lokal", "oui.csv"), text);
  console.log(`Herstellerliste gespeichert: lokal/oui.csv (${text.split("\n").length - 1} Hersteller-Kennungen)`);
}

function localAddress() {
  for (const list of Object.values(os.networkInterfaces())) {
    for (const i of list ?? []) {
      if (i.family === "IPv4" && !i.internal && /^(10|192\.168|172\.(1[6-9]|2\d|3[01]))\./.test(i.address)) return i.address;
    }
  }
  return null;
}

const localNet = () => localAddress()?.replace(/\.\d+$/, ".0/24") ?? null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ipNum = (ip) => ip.split(".").reduce((a, o) => a * 256 + Number(o), 0);
const normMac = (m) => m.toLowerCase().split(/[:-]/).map((b) => b.padStart(2, "0")).join(":");

function hostsOf(cidr) {
  const [base, bits = "24"] = cidr.split("/");
  const n = Number(bits);
  if (n < 22 || n > 32) throw new Error("Bitte ein Netz zwischen /22 und /32 angeben, z. B. 192.168.178.0/24");
  if (n === 32) return [base];
  const ip = base.split(".").reduce((a, o) => (a << 8) + Number(o), 0) >>> 0;
  const mask = (~0 << (32 - n)) >>> 0;
  const start = (ip & mask) >>> 0;
  const out = [];
  for (let i = 1; i < 2 ** (32 - n) - 1; i++) {
    const a = (start + i) >>> 0;
    out.push([a >>> 24, (a >>> 16) & 255, (a >>> 8) & 255, a & 255].join("."));
  }
  return out;
}

// Nachbartabelle des Betriebssystems (IP → MAC). Enthält auch Geräte ohne offene Ports, z. B. Handys.
function arpTable() {
  const [cmd, args] = process.platform === "linux" ? ["ip", ["neigh"]] : ["arp", [process.platform === "win32" ? "-a" : "-an"]];
  return new Promise((resolve) => {
    execFile(cmd, args, { timeout: 5000 }, (_err, stdout = "") => {
      const map = new Map();
      for (const line of stdout.split(/\r?\n/)) {
        const ip = /(\d+\.\d+\.\d+\.\d+)/.exec(line)?.[1];
        const mac = /\b([0-9a-f]{1,2}(?:[:-][0-9a-f]{1,2}){5})\b/i.exec(line)?.[1];
        if (ip && mac && !/^(ff:ff|01:00:5e)/.test(normMac(mac))) map.set(ip, normMac(mac));
      }
      resolve(map);
    });
  });
}

/* --- mDNS (Bonjour): Gerätenamen und angebotene Dienste --- */

function dnsQuery(names) {
  const head = Buffer.alloc(12);
  head.writeUInt16BE(names.length, 4);
  const qs = names.map((name) => {
    const labels = name.split(".").flatMap((l) => [Buffer.from([Buffer.byteLength(l)]), Buffer.from(l)]);
    return Buffer.concat([...labels, Buffer.from([0, 0, 12, 0, 1])]); // Typ PTR, Klasse IN
  });
  return Buffer.concat([head, ...qs]);
}

function readName(buf, off) {
  const labels = [];
  let next = null;
  for (let guard = 0; guard < 128; guard++) {
    const len = buf[off];
    if (len === undefined) throw new Error("DNS-Paket unvollständig");
    if (len === 0) return [labels.join("."), next ?? off + 1];
    if ((len & 0xc0) === 0xc0) {
      next ??= off + 2;
      off = ((len & 0x3f) << 8) | buf[off + 1];
    } else {
      labels.push(buf.toString("utf8", off + 1, off + 1 + len));
      off += 1 + len;
    }
  }
  throw new Error("DNS-Name zu lang");
}

function parseDns(buf) {
  const records = [];
  let off = 12;
  for (let i = buf.readUInt16BE(4); i > 0; i--) off = readName(buf, off)[1] + 4;
  const count = buf.readUInt16BE(6) + buf.readUInt16BE(8) + buf.readUInt16BE(10);
  for (let i = 0; i < count; i++) {
    const [name, o] = readName(buf, off);
    const type = buf.readUInt16BE(o);
    const d = o + 10;
    const len = buf.readUInt16BE(o + 8);
    let data = null;
    if (type === 1 && len === 4) data = [...buf.subarray(d, d + 4)].join(".");
    else if (type === 12) data = readName(buf, d)[0];
    else if (type === 16) {
      data = [];
      for (let p = d; p < d + len; p += 1 + buf[p]) if (buf[p]) data.push(buf.toString("utf8", p + 1, p + 1 + buf[p]));
    }
    records.push({ name, type, data });
    off = d + len;
  }
  return records;
}

async function mdns(localIp, hosts) {
  const info = new Map();
  const add = (ip, key, v) => {
    if (!v) return;
    if (!info.has(ip)) info.set(ip, { namen: new Set(), dienste: new Set(), txt: new Set() });
    info.get(ip)[key].add(v);
  };
  const types = new Set();
  const onMessage = (msg, rinfo) => {
    if (msg.length < 12 || !(msg.readUInt16BE(2) & 0x8000)) return; // nur Antworten
    let records;
    try {
      records = parseDns(msg);
    } catch {
      return;
    }
    for (const r of records) {
      if (r.type === 12 && r.name === "_services._dns-sd._udp.local") types.add(r.data);
      else if (r.type === 12 && r.name.endsWith(".in-addr.arpa")) add(r.name.split(".").slice(0, 4).reverse().join("."), "namen", r.data.replace(/\.local$/, ""));
      else if (r.type === 12 && r.name.startsWith("_") && !r.name.includes("._sub.")) {
        const art = r.name.replace(/\.local$/, "");
        const i = r.data.indexOf(`.${art}`);
        add(rinfo.address, "dienste", `${i > 0 ? r.data.slice(0, i) : r.data} (${art})`);
      } else if (r.type === 1) add(r.data, "namen", r.name.replace(/\.local$/, ""));
      else if (r.type === 16) for (const t of r.data) if (/^(md|model|am|fn|manufacturer|vendor|mf|ty|product)=./i.test(t)) add(rinfo.address, "txt", t);
    }
  };
  // Ein Socket lauscht auf 5353 (Antworten per Multicast), einer fragt von einem freien Port (Antworten per Unicast).
  const listen = dgram.createSocket({ type: "udp4", reuseAddr: true });
  const ask = dgram.createSocket("udp4");
  for (const s of [listen, ask]) s.on("message", onMessage).on("error", () => {});
  await new Promise((r) => {
    listen.once("error", r);
    listen.bind(5353, () => {
      try {
        listen.addMembership("224.0.0.251", localIp);
      } catch {}
      r();
    });
  });
  await new Promise((r) => ask.bind(0, r));
  try {
    ask.setMulticastInterface(localIp);
  } catch {}
  const query = (names) => {
    for (let i = 0; i < names.length; i += 20) ask.send(dnsQuery(names.slice(i, i + 20)), 5353, "224.0.0.251");
  };
  query(["_services._dns-sd._udp.local"]);
  await sleep(1500);
  query([...types]);
  query(hosts.map((h) => `${h.split(".").reverse().join(".")}.in-addr.arpa`));
  await sleep(2500);
  listen.close();
  ask.close();
  return info;
}

/* --- UPnP/SSDP: Router, Fernseher, NAS, Lautsprecher melden Name, Hersteller und Modell --- */

async function ssdp(localIp) {
  const orte = new Map();
  const s = dgram.createSocket("udp4");
  s.on("error", () => {});
  s.on("message", (msg, rinfo) => {
    const t = msg.toString();
    const e = orte.get(rinfo.address) ?? { urls: new Set(), server: null };
    const loc = /^location:\s*(\S+)/im.exec(t)?.[1];
    // Beschreibung nur vom antwortenden Gerät selbst laden
    if (loc && new URL(loc, "http://x").hostname === rinfo.address) e.urls.add(loc);
    e.server ??= /^server:\s*(.+?)\s*$/im.exec(t)?.[1] ?? null;
    orte.set(rinfo.address, e);
  });
  await new Promise((r) => s.bind(0, r));
  try {
    s.setMulticastInterface(localIp);
  } catch {}
  const msg = Buffer.from('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n');
  s.send(msg, 1900, "239.255.255.250");
  await sleep(700);
  s.send(msg, 1900, "239.255.255.250");
  await sleep(2800);
  s.close();
  const out = new Map();
  await pool([...orte], 8, async ([ip, e]) => {
    const u = { server: e.server };
    for (const url of [...e.urls].slice(0, 3)) {
      const r = await http(url, { timeout: 2500 });
      const tag = (n) => (r?.text ? new RegExp(`<${n}>\\s*([^<]{1,80}?)\\s*</${n}>`, "i").exec(r.text)?.[1] : undefined);
      u.name ??= tag("friendlyName");
      u.hersteller ??= tag("manufacturer");
      u.modell ??= [tag("modelName"), tag("modelNumber")].filter(Boolean).join(" ") || undefined;
    }
    out.set(ip, u);
  });
  return out;
}

/* --- Dienste eines Geräts näher ansehen --- */

function certOf(host, port) {
  return new Promise((resolve) => {
    const s = tls.connect({ host, port, rejectUnauthorized: false, timeout: 3000 }, () => {
      const c = s.getPeerCertificate();
      s.destroy();
      resolve([c?.subject?.CN, c?.subject?.O].filter(Boolean).join(" / ") || null);
    });
    s.on("timeout", () => (s.destroy(), resolve(null)));
    s.on("error", () => resolve(null));
  });
}

function banner(host, port) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    let buf = "";
    const done = (v) => (clearTimeout(t), s.destroy(), resolve(v));
    const t = setTimeout(() => done(null), 2500);
    s.on("data", (d) => {
      buf += d;
      if (buf.includes("\n")) done(buf.split(/\r?\n/)[0].slice(0, 60));
    });
    s.on("error", () => done(null));
  });
}

async function identify(host, ports) {
  const info = {};
  for (const [port, proto] of [[80, "http"], [443, "https"], [8080, "http"], [5000, "http"], [8443, "https"], [5001, "https"]]) {
    if (!ports.includes(port)) continue;
    const r = await http(`${proto}://${host}:${port}/`, { timeout: 3000, redirect: "manual" });
    if (!r) continue;
    info.titel ??= /<title[^>]*>\s*([^<]{1,80}?)\s*<\/title>/i.exec(r.text)?.[1];
    info.server ??= r.headers?.server;
    info.anmeldung ??= /realm="([^"]+)"/i.exec(r.headers?.["www-authenticate"] ?? "")?.[1];
    if (r.status >= 300 && r.status < 400 && r.headers?.location) info.weiterleitung ??= r.headers.location;
  }
  for (const port of [443, 8443, 5001]) if (ports.includes(port)) info.zertifikat ??= (await certOf(host, port)) ?? undefined;
  if (ports.includes(22)) info.ssh = (await banner(host, 22)) ?? undefined;
  return info;
}

async function probe(host, ports) {
  const found = [];
  if (ports.includes(8123)) found.push(await homeAssistant(host));
  if (ports.includes(80)) found.push((await goe(host)) ?? (await acthor(host)));
  if (ports.includes(443)) found.push(await envoy(host));
  return found.filter(Boolean);
}

const REGELN = [
  [/my-?pv|ac.?thor|\belwa\b/i, "my-PV (AC THOR / ELWA)"],
  [/free2move|esolutions|eprowallbox/i, "eProWallbox (Free2move eSolutions)"],
  [/go-?e ?charger|\bgo-e\b/i, "go-e Charger"],
  [/fr(oe|ö)ling/i, "Fröling"],
  [/gridbox|kiwigrid/i, "Kiwigrid gridBox (Energiemanager)"],
  [/starlink/i, "Starlink-Router"],
  [/omada|tp-?link/i, "TP-Link (Router / WLAN-Access-Point)"],
  [/synology|diskstation/i, "Synology NAS"],
  [/fritz!?/i, "FRITZ!Box / FRITZ!Repeater"],
  [/sonos/i, "Sonos-Lautsprecher"],
  [/shelly/i, "Shelly"],
  [/tasmota/i, "Tasmota-Gerät"],
  [/esphome/i, "ESPHome-Gerät"],
  [/\bhue\b|signify/i, "Philips Hue"],
  [/hisense|smart ?tv|bravia|webos|tizen/i, "Fernseher"],
  [/\bHP[0-9A-F]{6}\b|hewlett|laserjet|officejet|deskjet/i, "HP-Drucker"],
  [/_googlecast|chromecast/i, "Chromecast / Google-Lautsprecher"],
  [/_airplay|_raop/i, "AirPlay-Gerät (Apple TV, Lautsprecher, Mac)"],
  [/_ipp|_printer|_pdl-datastream/i, "Drucker"],
  [/slzb|conbee|zigbee|sonoff/i, "Zigbee-Gerät / -Koordinator"],
  [/raspberry/i, "Raspberry Pi"],
];

function guess(g) {
  if (g.dieserRechner) return "dieser Rechner";
  if (g.bekannt.length) return g.bekannt.map((d) => d.typ).join(", ");
  const text = [g.titel, g.upnp?.name, g.upnp?.hersteller, g.upnp?.modell, g.upnp?.server, g.zertifikat, g.server, g.anmeldung,
    ...(g.mdns?.namen ?? []), ...(g.mdns?.dienste ?? []), ...(g.mdns?.txt ?? []), g.hersteller].filter(Boolean).join(" ");
  for (const [re, name] of REGELN) if (re.test(text)) return name;
  if (g.ports.includes(62078)) return "iPhone / iPad";
  if (g.ports.includes(502)) return "Modbus-Gerät (Wechselrichter, Heizstab, Wärmepumpe …)";
  if (g.ports.includes(6053)) return "ESPHome-Gerät";
  if (g.ports.includes(8009)) return "Chromecast / Google TV";
  if (/android/i.test(text)) return "Android-Gerät (TV-Box, Tablet …)";
  if (g.ports.length === 1 && g.ports[0] === 445) return "PC mit Dateifreigabe (meist Windows)";
  if (/espressif/i.test(g.hersteller ?? "")) return "Gerät mit ESP-Funkchip (Wallbox, Steckdose, Sensor …)";
  if (g.hersteller === "private Adresse") return "Handy, Tablet oder Laptop (private WLAN-Adresse)";
  return null;
}

async function search(cidr) {
  const localIp = localAddress();
  const hosts = hostsOf(cidr);
  const inNet = new Set(hosts);
  console.log(`Durchsuche ${cidr} (${hosts.length} Adressen) …`);
  // 1. Jede Adresse einmal ansprechen – das füllt die ARP-Tabelle. Gleichzeitig mDNS und UPnP abfragen.
  const [reached, mdnsInfo, ssdpInfo] = await Promise.all([
    pool(hosts, 64, async (h) => ((await portState(h, 80, 2500)) ? h : null)),
    localIp ? mdns(localIp, hosts) : new Map(),
    localIp ? ssdp(localIp) : new Map(),
  ]);
  const arp = await arpTable();
  const live = new Set([...reached.filter(Boolean), ...arp.keys(), ...mdnsInfo.keys(), ...ssdpInfo.keys()].filter((ip) => inNet.has(ip)));
  if (inNet.has(localIp)) live.add(localIp);
  console.log(`  ${live.size} aktive Geräte – prüfe Dienste …`);
  // 2. Jedes aktive Gerät: offene Ports, bekannte Geräte auslesen, sonst so gut wie möglich benennen.
  return pool([...live].sort((a, b) => ipNum(a) - ipNum(b)), 8, async (host) => {
    const states = await Promise.all(Object.keys(PORTS).map(async (p) => [Number(p), await portState(host, Number(p))]));
    const ports = states.filter(([, s]) => s === "offen").map(([p]) => p);
    const g = { host, mac: arp.get(host) ?? null, ports };
    if (host === localIp) g.dieserRechner = true;
    g.hersteller = vendorOf(g.mac);
    const m = mdnsInfo.get(host);
    if (m) g.mdns = { namen: [...m.namen], dienste: [...m.dienste], txt: [...m.txt] };
    if (ssdpInfo.has(host)) g.upnp = ssdpInfo.get(host);
    Object.assign(g, await identify(host, ports));
    g.bekannt = g.dieserRechner ? [] : await probe(host, ports);
    g.vermutung = guess(g);
    for (const d of g.bekannt) console.log(`  gefunden: ${d.typ} auf ${d.host}`);
    return g;
  });
}

/* ------------------------------------------------------------- Ausgabe ---- */

function printAlle(alle) {
  console.log(`\n━━ Alle Geräte im Netz (${alle.length}) ━━`);
  for (const g of alle) {
    console.log(`\n  ${g.host.padEnd(15)}  ${g.vermutung ?? "unbekannt"}`);
    const namen = [...new Set([...(g.mdns?.namen ?? []), g.upnp?.name].filter(Boolean))];
    const zeilen = [
      g.mac && `MAC ${g.mac}${g.hersteller ? ` – ${g.hersteller}` : ""}`,
      namen.length && `Name: ${namen.join(", ")}`,
      (g.upnp?.hersteller || g.upnp?.modell) && `Modell: ${[g.upnp.hersteller, g.upnp.modell].filter(Boolean).join(" ")}`,
      g.titel && `Webseite: „${g.titel}“`,
      g.zertifikat && `Zertifikat: ${g.zertifikat}`,
      (g.server || g.upnp?.server) && `Server: ${g.server ?? g.upnp.server}`,
      g.anmeldung && `Anmeldung: ${g.anmeldung}`,
      g.ssh,
      g.mdns?.dienste.length && `Dienste: ${g.mdns.dienste.slice(0, 4).join(", ")}${g.mdns.dienste.length > 4 ? " …" : ""}`,
      g.mdns?.txt.length && g.mdns.txt.slice(0, 4).join("  "),
      `Ports: ${g.ports.length ? g.ports.map((p) => `${p} ${PORTS[p]}`).join(", ") : "keine offen"}`,
    ].filter(Boolean);
    for (const z of zeilen) console.log(`    ${z}`);
  }
  if (!existsSync(join(ROOT, "lokal", "oui.csv"))) {
    console.log(`\nTipp: "node tools/geraete.mjs hersteller" lädt einmalig die Herstellerliste – dann steht bei jeder MAC der Hersteller.`);
  }
  const typen = alle.map((g) => g.vermutung ?? "");
  if (!typen.some((t) => /go-e|eProWallbox/.test(t))) {
    console.log(`\nWallbox: Die eProWallbox Move hat keine lokale Web-API. Sie ist nur per OCPP (sie verbindet sich selbst
  mit einem Server, z. B. Home Assistant) oder per Modbus RTU (Kabel) ansprechbar – im WLAN taucht sie
  höchstens als Gerät ohne offene Ports auf.`);
  }
  if (!typen.some((t) => /my-PV/.test(t))) {
    console.log(`\nAC THOR nicht gefunden: eingeschaltet und im Netz? In der my-PV-App bzw. am Display die IP ablesen und
  als ACTHOR_IP in .env.local eintragen.`);
  }
}

function print(devices, alle) {
  if (devices.length) console.log(`\n━━ Bekannte Geräte mit Messwerten ━━`);
  for (const d of devices) {
    console.log(`\n■ ${d.typ} – ${d.host}${d.api ? ` (API ${d.api})` : ""}`);
    for (const [k, v] of Object.entries(d.werte ?? {})) console.log(`    ${k.padEnd(24)} ${v}`);
    if (d.hinweis) console.log(`    ⚠ ${d.hinweis}`);
  }
  if (alle) printAlle(alle);
  const env = [];
  const first = (typ) => devices.find((d) => d.typ.startsWith(typ))?.host;
  if (first("Home Assistant")) env.push(`HA_URL=http://${first("Home Assistant")}:8123`);
  if (first("go-e")) env.push(`GOE_IP=${first("go-e")}`);
  if (first("Enphase")) env.push(`ENVOY_IP=${first("Enphase")}`);
  if (first("my-PV")) env.push(`ACTHOR_IP=${first("my-PV")}`);
  if (env.length) console.log(`\nFür .env.local:\n  ${env.join("\n  ")}`);
  mkdirSync(join(ROOT, "lokal"), { recursive: true });
  writeFileSync(join(ROOT, "lokal", "geraete.json"), JSON.stringify({ zeit: new Date().toISOString(), geraete: devices, alle: alle ?? [] }, null, 2));
  console.log(`\nGespeichert: lokal/geraete.json`);
}

const [cmd, arg] = process.argv.slice(2);
if (cmd === "hilfe" || cmd === "--help") {
  console.log(HILFE);
} else if (cmd === "hersteller") {
  await loadOui();
} else if (cmd === "suchen") {
  const cidr = arg ?? localNet();
  if (!cidr) {
    console.error("Kein Heimnetz erkannt – bitte angeben, z. B. suchen 192.168.178.0/24");
    process.exit(2);
  }
  const alle = await search(cidr);
  if (!alle.length) console.log("Nichts gefunden. Sind PC und Geräte im selben Netz? (macOS: Zugriff auf „Lokales Netzwerk“ erlauben)");
  print(alle.flatMap((g) => g.bekannt), alle);
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
