#!/usr/bin/env node
// Auswertung mit echten Daten aus Home Assistant: Energiebilanzen, Tagesprofile, Regelgüte des
// AC THOR, Heizung, Entscheidungs-Log. Liest nur. Welche Entität welches Signal liefert, steht in
// haus/signale.json (Vorlage: tools/signale.beispiel.json).
//
// Datenquellen: Langzeitstatistik (stündlich, bleibt für immer) für Bilanzen und Profile,
// Verlauf in voller Auflösung (so lange wie der Recorder aufhebt) für Regelgüte und Heizung.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { ROOT, loadEnv } from "./env.mjs";
import { api, socket } from "./hass.mjs";

const HILFE = `Nutzung: node tools/auswertung.mjs <bericht> …

  energie [monate]        Monatsbilanz (Standard 12): PV, Bezug, Einspeisung, Batterie, Verbrauch, Autarkie
  tage [tage]             Tagesbilanz der letzten Tage (Standard 14)
  profil [von] [bis]      Ø kWh pro Uhrzeit: PV, Bezug, Einspeisung, Batterie – z. B. profil 2026-06 2026-08
                          (Standard: letzte 30 Tage)
  warmwasser [tage]       AC THOR: Heizenergie nach Herkunft (PV/Batterie/Netz), ungenutzte Einspeisung,
                          Temperaturen, Sollwert-Wechsel (Standard 3 Tage)
  heizung [tage]          je Thermostat: Ist/Soll, Heizanteil, Aus-Zeit, dazu Außentemperatur (Standard 7)
  entscheidungen [tage]   Logbuch der Regelungen: Einträge "Jotunland …" und Wechsel "Speicher voll" (Standard 1)
  export <muster> [tage]  Verlauf aller passenden Entitäten als CSV nach lokal/ (Standard 1 Tag)

Signale: haus/signale.json (Vorlage tools/signale.beispiel.json)`;

loadEnv();
const [cmd, ...args] = process.argv.slice(2);
if (!cmd || cmd === "hilfe" || cmd === "--help") {
  console.log(HILFE);
  process.exit(0);
}

/* ------------------------------------------------------------- Helfer ---- */

function signale() {
  const file = join(ROOT, "haus", "signale.json");
  if (!existsSync(file)) {
    console.error("✗ haus/signale.json fehlt – Vorlage: tools/signale.beispiel.json");
    process.exit(2);
  }
  return JSON.parse(readFileSync(file, "utf8"));
}

const liste = (v) => (v == null ? [] : Array.isArray(v) ? v : [v]);
const TAG = 86_400_000;
const heuteMinus = (tage) => {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return new Date(d.getTime() - (tage - 1) * TAG);
};
const tagKey = (ms) => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const monatKey = (ms) => tagKey(ms).slice(0, 7);
const tagName = (key) => new Date(`${key}T12:00`).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
const monatName = (key) => new Date(`${key}-15T12:00`).toLocaleDateString("de-DE", { month: "short", year: "numeric" });
const zahl = (v, stellen = 1) => (v == null || !isFinite(v) ? "–" : v.toLocaleString("de-DE", { minimumFractionDigits: stellen, maximumFractionDigits: stellen }));
const prozent = (v) => (v == null || !isFinite(v) ? "–" : `${Math.round(v * 100)} %`);
const num = (s) => {
  const v = Number(s);
  return s === "" || s == null || isNaN(v) ? NaN : v;
};

/** Tabelle mit rechtsbündigen Zahlenspalten */
function tabelle(kopf, zeilen) {
  const breite = kopf.map((k, i) => Math.max(k.length, ...zeilen.map((z) => String(z[i]).length)));
  const fmt = (z) => z.map((c, i) => (i === 0 ? String(c).padEnd(breite[i]) : String(c).padStart(breite[i]))).join("  ");
  console.log(fmt(kopf));
  console.log(breite.map((b) => "─".repeat(b)).join("  "));
  for (const z of zeilen) console.log(fmt(z));
}

/** Parameter "2026-06" oder "2026-06-15" → Datum (Monatsende bei bis=true) */
function datum(text, bis = false) {
  if (/^\d{4}-\d{2}$/.test(text)) {
    const [y, m] = text.split("-").map(Number);
    return bis ? new Date(y, m, 1) : new Date(y, m - 1, 1);
  }
  const d = new Date(`${text}T00:00`);
  if (isNaN(d)) throw new Error(`Datum nicht erkannt: ${text} (Format 2026-06 oder 2026-06-15)`);
  return bis ? new Date(d.getTime() + TAG) : d;
}

/* ------------------------------------------------------ Datenquellen ---- */

async function statistik(ws, ids, start, end, period, types, units) {
  if (!ids.length) return {};
  return ws.send({
    type: "recorder/statistics_during_period",
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    period,
    statistic_ids: ids,
    types,
    units,
  });
}

/** Batterie: stündliche Mittelwerte aller Einheiten summieren → kWh laden/entladen je Stunde */
async function batterieStunden(ws, s, start, end) {
  const ids = liste(s.batterie_leistung);
  const r = await statistik(ws, ids, start, end, "hour", ["mean"], { power: "W" });
  const proStunde = new Map();
  for (const id of ids) for (const p of r[id] ?? []) proStunde.set(p.start, (proStunde.get(p.start) ?? 0) + (p.mean ?? 0));
  return proStunde; // Zeitstempel → W (+ = Entladen)
}

/** Verlauf in voller Auflösung: { entity_id: [{ t, s, a? }] } */
async function verlauf(ws, ids, start, end, attribute = false) {
  const r = await ws.send({
    type: "history/history_during_period",
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    entity_ids: ids,
    minimal_response: !attribute,
    no_attributes: !attribute,
    significant_changes_only: false,
  });
  const out = {};
  for (const [id, liste] of Object.entries(r)) out[id] = liste.map((e) => ({ t: e.lu * 1000, s: e.s, a: e.a }));
  return out;
}

/** Faktor nach W anhand der aktuellen Einheit (kW → 1000) */
async function wattFaktor(id) {
  const st = await api("GET", `states/${id}`);
  const u = st.attributes?.unit_of_measurement;
  return u === "kW" ? 1000 : u === "MW" ? 1e6 : 1;
}

/**
 * Läuft über alle Zustandswechsel mehrerer Reihen und ruft für jeden Abschnitt fn(werte, dtStunden, t) auf.
 * werte[schlüssel] ist der gerade gültige Wert (NaN, wenn unbekannt).
 */
function abschnitte(reihen, start, end, fn) {
  const ereignisse = [];
  for (const [key, punkte] of Object.entries(reihen)) for (const p of punkte) ereignisse.push({ t: Math.max(p.t, start.getTime()), key, v: p.v });
  ereignisse.sort((a, b) => a.t - b.t);
  const werte = Object.fromEntries(Object.keys(reihen).map((k) => [k, NaN]));
  let t0 = start.getTime();
  for (const e of ereignisse) {
    if (e.t > t0) fn(werte, (e.t - t0) / 3_600_000, t0);
    t0 = Math.max(t0, e.t);
    werte[e.key] = e.v;
  }
  if (end.getTime() > t0) fn(werte, (end.getTime() - t0) / 3_600_000, t0);
}

/* --------------------------------------------------------- Berichte ---- */

async function bilanz(period, start, end) {
  const s = signale();
  const felder = { pv: s.pv_energie, bezug: s.bezug_energie, einsp: s.einspeisung_energie, ww: s.warmwasser_energie, wb: s.wallbox_energie };
  const ws = await socket();
  const r = await statistik(ws, Object.values(felder).filter(Boolean), start, end, period, ["change"], { energy: "kWh" });
  const bat = await batterieStunden(ws, s, start, end);
  ws.close();

  const key = period === "month" ? monatKey : tagKey;
  const zeilen = new Map();
  const zeile = (k) => zeilen.get(k) ?? zeilen.set(k, { pv: 0, bezug: 0, einsp: 0, ww: 0, wb: 0, laden: 0, entladen: 0 }).get(k);
  for (const [feld, id] of Object.entries(felder)) for (const p of (id && r[id]) || []) zeile(key(p.start))[feld] += p.change ?? 0;
  for (const [t, w] of bat) {
    const z = zeile(key(t));
    if (w > 0) z.entladen += w / 1000;
    else z.laden += -w / 1000;
  }

  const summe = { pv: 0, bezug: 0, einsp: 0, ww: 0, wb: 0, laden: 0, entladen: 0 };
  const aus = (name, z) => {
    const verbrauch = z.pv + z.bezug - z.einsp - z.laden + z.entladen;
    return [name, zahl(z.pv, 0), zahl(z.bezug, 0), zahl(z.einsp, 0), zahl(z.laden, 0), zahl(z.entladen, 0), zahl(verbrauch, 0), felder.ww ? zahl(z.ww, 0) : "–", felder.wb ? zahl(z.wb, 0) : "–", prozent(z.pv > 0 ? (z.pv - z.einsp) / z.pv : NaN), prozent(verbrauch > 0 ? 1 - z.bezug / verbrauch : NaN)];
  };
  const rows = [...zeilen.keys()].sort().map((k) => {
    for (const f of Object.keys(summe)) summe[f] += zeilen.get(k)[f];
    return aus(period === "month" ? monatName(k) : tagName(k), zeilen.get(k));
  });
  rows.push(aus("Summe", summe));
  console.log(`Energiebilanz in kWh (${period === "month" ? "Monate" : "Tage"}). Batterie aus stündlichen Mittelwerten.\n`);
  tabelle(["", "PV", "Bezug", "Einspeis.", "Batt.laden", "Batt.entl.", "Verbrauch", "Warmwasser", "Wallbox", "Eigenverbr.", "Autarkie"], rows);
  console.log(`\nVerbrauch = PV + Bezug − Einspeisung − Batterie laden + entladen. Eigenverbrauch = Anteil der PV, der nicht
eingespeist wurde. Autarkie = Anteil des Verbrauchs, der nicht aus dem Netz kam. Lädt die Batterie aus dem Netz
(z. B. Heartbeat), steckt das in "Batt.laden" und "Bezug".`);
}

async function profil(von, bis) {
  const s = signale();
  const start = von ? datum(von) : heuteMinus(30);
  const end = bis ? datum(bis, true) : von ? datum(von, true) : new Date();
  const felder = { pv: s.pv_energie, bezug: s.bezug_energie, einsp: s.einspeisung_energie, ww: s.warmwasser_energie };
  const ws = await socket();
  const r = await statistik(ws, Object.values(felder).filter(Boolean), start, end, "hour", ["change"], { energy: "kWh" });
  const bat = await batterieStunden(ws, s, start, end);
  ws.close();
  const stunden = Array.from({ length: 24 }, () => ({ pv: 0, bezug: 0, einsp: 0, ww: 0, bat: 0 }));
  const tage = new Set();
  for (const [feld, id] of Object.entries(felder))
    for (const p of (id && r[id]) || []) {
      stunden[new Date(p.start).getHours()][feld] += p.change ?? 0;
      tage.add(tagKey(p.start));
    }
  for (const [t, w] of bat) stunden[new Date(t).getHours()].bat += w / 1000;
  const n = Math.max(tage.size, 1);
  console.log(`Ø kWh pro Tag und Uhrzeit, ${start.toLocaleDateString("de-DE")} – ${new Date(end.getTime() - 1).toLocaleDateString("de-DE")} (${tage.size} Tage)\n`);
  tabelle(
    ["Uhr", "PV", "Bezug", "Einspeis.", "Warmwasser", "Batterie"],
    stunden.map((h, i) => [`${String(i).padStart(2, "0")}–${String(i + 1).padStart(2, "0")}`, zahl(h.pv / n, 2), zahl(h.bezug / n, 2), zahl(h.einsp / n, 2), felder.ww ? zahl(h.ww / n, 2) : "–", zahl(h.bat / n, 2)]).concat([
      ["Tag", ...["pv", "bezug", "einsp", "ww", "bat"].map((f) => zahl(stunden.reduce((a, h) => a + h[f], 0) / n, 1))],
    ]),
  );
  console.log(`\nBatterie: + = Entladen, − = Laden (Saldo der Stunde).
Bezug und Einspeisung zählt der Envoy je Phase – nachts gleichzeitig Bezug und Einspeisung heißt meist: die Batterie
speist auf ihrer Phase ein, die anderen Phasen beziehen. Der Stromzähler rechnet über alle Phasen saldiert.`);
}

async function warmwasser(tage) {
  const s = signale();
  const start = heuteMinus(tage);
  const end = new Date();
  const bat = liste(s.batterie_leistung);
  const ids = [s.warmwasser_leistung, s.netz_leistung, ...bat, s.warmwasser_temperatur, s.warmwasser_voll, s.warmwasser_sollwert].filter(Boolean);
  const faktor = Object.fromEntries(await Promise.all([s.warmwasser_leistung, s.netz_leistung, ...bat].map(async (id) => [id, await wattFaktor(id)])));
  const ws = await socket();
  const h = await verlauf(ws, ids, start, end);
  ws.close();

  const reihe = (id, f = (x) => num(x)) => (h[id] ?? []).map((p) => ({ t: p.t, v: f(p.s) }));
  const reihen = {
    ac: reihe(s.warmwasser_leistung, (x) => num(x) * faktor[s.warmwasser_leistung]),
    netz: reihe(s.netz_leistung, (x) => num(x) * faktor[s.netz_leistung]),
    // 0 °C meldet der Fühler nur direkt nach dem Einschalten
    temp: reihe(s.warmwasser_temperatur, (x) => (num(x) > 1 ? num(x) : NaN)),
    voll: reihe(s.warmwasser_voll, (x) => (x === "on" ? 1 : x === "off" ? 0 : NaN)),
    soll: reihe(s.warmwasser_sollwert),
  };
  bat.forEach((id, i) => (reihen[`bat${i}`] = reihe(id, (x) => num(x) * faktor[id])));
  const maxW = s.warmwasser_max_w ?? 9000;

  const tag = new Map();
  const z = (k) => tag.get(k) ?? tag.set(k, { kwh: 0, pv: 0, batterie: 0, netz: 0, ungenutzt: 0, heiz: 0, voll: 0, tmin: Infinity, tmax: -Infinity, wechsel: 0 }).get(k);
  abschnitte(reihen, start, end, (w, dt, t) => {
    const d = z(tagKey(t));
    if (isFinite(w.temp)) (d.tmin = Math.min(d.tmin, w.temp)), (d.tmax = Math.max(d.tmax, w.temp));
    if (w.voll === 1) d.voll += dt;
    const batW = bat.reduce((a, _, i) => a + w[`bat${i}`], 0);
    if (![w.ac, w.netz, batW].every(isFinite)) return;
    const ac = Math.max(w.ac, 0);
    const ausNetz = Math.min(ac, Math.max(w.netz, 0));
    const ausBatterie = Math.min(ac - ausNetz, Math.max(batW, 0));
    d.kwh += (ac * dt) / 1000;
    d.netz += (ausNetz * dt) / 1000;
    d.batterie += (ausBatterie * dt) / 1000;
    d.pv += ((ac - ausNetz - ausBatterie) * dt) / 1000;
    if (ac > 100) d.heiz += dt;
    // Einspeisung, die der AC THOR noch hätte nehmen können (Speicher nicht voll, Leistung nicht am Anschlag)
    if (w.voll !== 1) d.ungenutzt += (Math.min(Math.max(-w.netz, 0), Math.max(maxW - ac, 0)) * dt) / 1000;
  });
  for (const p of reihen.soll) z(tagKey(p.t)).wechsel++;

  console.log(`Warmwasser (AC THOR), ${start.toLocaleDateString("de-DE")} bis jetzt\n`);
  const sum = { kwh: 0, pv: 0, batterie: 0, netz: 0, ungenutzt: 0 };
  const rows = [...tag.keys()].sort().map((k) => {
    const d = tag.get(k);
    for (const f of Object.keys(sum)) sum[f] += d[f];
    return [tagName(k), zahl(d.kwh), zahl(d.pv), zahl(d.batterie), zahl(d.netz), zahl(d.ungenutzt), zahl(d.heiz), zahl(d.voll), isFinite(d.tmin) ? `${zahl(d.tmin)}–${zahl(d.tmax)} °C` : "–", d.wechsel];
  });
  rows.push(["Summe", zahl(sum.kwh), zahl(sum.pv), zahl(sum.batterie), zahl(sum.netz), zahl(sum.ungenutzt), "", "", "", ""]);
  tabelle(["", "Heizen kWh", "aus PV", "aus Batt.", "aus Netz", "ungenutzt", "Heiz-h", "voll h", "Temp (Messwert)", "Sollw.-Wechsel"], rows);
  console.log(`
aus Batt./aus Netz: sollte ~0 sein – sonst heizt der AC THOR nicht nur mit Überschuss. Lädt die Batterie gleichzeitig
  aus dem Netz (Heartbeat), taucht das hier als "aus Netz" auf.
ungenutzt: eingespeiste Energie, die der AC THOR noch hätte nehmen können (Speicher nicht voll).
Genauigkeit: Netz und Batterie kommen etwa einmal pro Minute – kurze Spitzen werden geglättet.`);
  if (!reihen.soll.length && !reihen.voll.length) console.log("\nHinweis: Sollwert/Speicher-voll noch ohne Verlauf – die Regelung schreibt erst seit dem 25.09.2026 mit.");
}

async function heizung(tage) {
  const s = signale();
  const start = heuteMinus(tage);
  const end = new Date();
  const klimas = (await api("GET", "states")).filter((e) => e.entity_id.startsWith("climate.")).map((e) => e.entity_id);
  if (!klimas.length) return console.log("Keine Thermostate (climate.*) gefunden.");
  const ws = await socket();
  const h = await verlauf(ws, klimas, start, end, true);
  // Außentemperatur: Sensor oder Wetter-Entität (dann Attribut "temperature")
  const wetter = s.aussentemperatur?.startsWith("weather.");
  const aussen = s.aussentemperatur ? await verlauf(ws, [s.aussentemperatur], start, end, wetter) : {};
  ws.close();

  const rows = klimas.map((id) => {
    const punkte = h[id] ?? [];
    let dauer = 0, ist = 0, soll = 0, heizt = 0, aus = 0, name = id;
    let a = {};
    for (let i = 0; i < punkte.length; i++) {
      const p = punkte[i];
      a = { ...a, ...(p.a ?? {}) };
      name = a.friendly_name ?? name;
      const t0 = Math.max(p.t, start.getTime());
      const dt = ((punkte[i + 1]?.t ?? end.getTime()) - t0) / 3_600_000;
      if (dt <= 0 || p.s === "unavailable") continue;
      dauer += dt;
      if (isFinite(a.current_temperature)) ist += a.current_temperature * dt;
      if (p.s === "off") aus += dt;
      else if (isFinite(a.temperature)) soll += a.temperature * dt;
      if (a.hvac_action === "heating") heizt += dt;
    }
    const an = dauer - aus;
    return [name, zahl(ist / dauer), an > 0 ? zahl(soll / an) : "–", prozent(heizt / dauer), zahl(aus, 0)];
  });
  console.log(`Heizung, ${start.toLocaleDateString("de-DE")} bis jetzt (zeitgewichtete Mittelwerte)\n`);
  tabelle(["Thermostat", "Ist °C", "Soll °C", "heizt", "aus (h)"], rows);
  let letzte = {};
  const at = (aussen[s.aussentemperatur] ?? [])
    .map((p) => (wetter ? ((letzte = { ...letzte, ...(p.a ?? {}) }), num(letzte.temperature)) : num(p.s)))
    .filter(isFinite);
  if (at.length) console.log(`\nAußen (${s.aussentemperatur}): Ø ${zahl(at.reduce((x, y) => x + y, 0) / at.length)} °C, ${zahl(Math.min(...at))} bis ${zahl(Math.max(...at))} °C`);
  console.log(`\n"heizt" = Anteil der Zeit, in der das Thermostat hvac_action "heating" meldet (Ventil offen).`);
}

async function entscheidungen(tage) {
  const s = signale();
  const start = heuteMinus(tage);
  const ws = await socket();
  const eintraege = await ws.send({ type: "logbook/get_events", start_time: start.toISOString(), end_time: new Date().toISOString() });
  ws.close();
  const relevant = eintraege.filter((e) => /^Jotunland/.test(e.name ?? "") || (s.warmwasser_voll && e.entity_id === s.warmwasser_voll));
  if (!relevant.length) return console.log(`Keine Einträge seit ${start.toLocaleString("de-DE")}.`);
  for (const e of relevant) {
    const zeit = new Date(e.when * 1000).toLocaleString("de-DE", { weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
    console.log(`${zeit}  ${e.name}: ${e.message ?? e.state ?? ""}`);
  }
}

async function exportCsv(muster, tage) {
  if (!muster) throw new Error("Muster fehlt, z. B. export \"ac_thor|envoy\" 2");
  const re = new RegExp(muster, "i");
  const ids = (await api("GET", "states")).map((e) => e.entity_id).filter((id) => re.test(id));
  if (!ids.length) throw new Error(`Keine Entität passt zu ${muster}`);
  const start = heuteMinus(tage);
  const ws = await socket();
  const h = await verlauf(ws, ids, start, new Date());
  ws.close();
  const zeilen = ["zeit;entity_id;zustand"];
  for (const [id, punkte] of Object.entries(h)) for (const p of punkte) zeilen.push(`${new Date(p.t).toISOString()};${id};${p.s}`);
  mkdirSync(join(ROOT, "lokal"), { recursive: true });
  const file = join("lokal", `export-${tagKey(Date.now())}-${new Date().toTimeString().slice(0, 5).replace(":", "")}.csv`);
  writeFileSync(join(ROOT, file), zeilen.join("\n"));
  console.log(`${zeilen.length - 1} Werte von ${ids.length} Entitäten → ${file}`);
}

/* ----------------------------------------------------------- Aufruf ---- */

const zahlArg = (i, std) => (args[i] ? Number(args[i]) : std);
try {
  if (cmd === "energie") {
    const monate = zahlArg(0, 12);
    const d = new Date();
    await bilanz("month", new Date(d.getFullYear(), d.getMonth() - (monate - 1), 1), d);
  } else if (cmd === "tage") await bilanz("day", heuteMinus(zahlArg(0, 14)), new Date());
  else if (cmd === "profil") await profil(args[0], args[1]);
  else if (cmd === "warmwasser") await warmwasser(zahlArg(0, 3));
  else if (cmd === "heizung") await heizung(zahlArg(0, 7));
  else if (cmd === "entscheidungen") await entscheidungen(zahlArg(0, 1));
  else if (cmd === "export") await exportCsv(args[0], zahlArg(1, 1));
  else {
    console.error(`Unbekannter Bericht: ${cmd}\n\n${HILFE}`);
    process.exit(2);
  }
} catch (e) {
  console.error(`✗ ${e.message}`);
  process.exit(1);
}
