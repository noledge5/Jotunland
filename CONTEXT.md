# Glossary

## Immersion Break
Any moment in gameplay where the player experiences a contradiction between what the LLM narrates and what the established game state says is true. Three subtypes, in order of severity:
- **Rule Bypass** — the LLM allows an action to succeed without a proper mechanic resolution (e.g. theft without a Stealth check)
- **World Inconsistency** — the LLM narrates something that contradicts a known fact (NPC knows something they can't know; player is somewhere they aren't)
- **Session Drift** — the LLM fails to recall or apply established facts from prior sessions (NPC forgets a past interaction)

## Game State
The authoritative record of all facts about the current game world: player stats, inventory, location, NPC relationships, quest status, session history. Stored in the database. The LLM never holds Game State in its own memory — it receives it fresh from the database on every turn.

## Turn
One complete player interaction cycle. Two variants:
- **Turn ohne Probe:** Spieler-Input → Engine/Classifier → Kontext-Assembly → LLM-Narration → State-Update.
- **Turn mit Probe:** Spieler-Input → Classifier bestimmt Skill + SG → Engine fordert Würfelwurf an → Spieler gibt W20-Ergebnis ein (zweiter Input) → Engine berechnet Endergebnis → Kontext-Assembly → LLM-Narration → State-Update. Der Spieler würfelt physisch; das Engine-Ergebnis wird nie intern gewürfelt wenn eine Probe nötig ist.

## Action Classifier
A lightweight, structured LLM call that receives the raw player input, the character's current skill list, and scene context. It decides (a) whether the action requires a dice roll at all, and (b) if so, which skill applies. Returns structured JSON: `{ "skill": "stealth", "needs_roll": true }` or `{ "needs_roll": false }`. Does not use a hardcoded action-type enum — the Skill List is the rulebook. Makes no decisions about outcomes.

## Skill List
The canonical set of skills available in the game (e.g. Stealth, Persuasion, Lockpick, Riding). Defined once as game config. Each character has a level per skill stored in the DB. The Action Classifier maps player intent to a skill from this list — it does not invent skill names. A character with no level in a skill may still attempt the action — they roll without a modifier. XP is awarded for every attempted action regardless of outcome.

## Mechanical Resolution
All game outcomes — damage, skill check results, hit/miss, XP gain — are determined by the Engine using dice rolls and rules config before the LLM is ever called. The LLM receives the already-computed result and narrates it. The LLM never decides or modifies a mechanical outcome.

## Rules Config
The set of tables or data files that define game constants: weapon damage dice, armor values, skill difficulty thresholds, XP formulas. Owned entirely by the Engine. Never read by the LLM.

## Rulebook
The authoritative D20-based rule system that governs all mechanical resolution. Defines difficulty tiers (Sehr Leicht SG 8 → Leicht SG 10 → Durchschnitt SG 12 → Schwer SG 14 → Sehr Schwer SG 16 → Heroisch SG 18 → Extrem SG 20), critical outcomes (Natural 20 = critical success regardless of SG; Natural 1 = critical failure regardless of modifier), damage dice per weapon type, XP tables, and injury thresholds. The Action Classifier selects a difficulty tier by name — the Engine maps it to a SG. The LLM never sets raw SG values. Game language is German throughout.

## Difficulty Tier
A named category from the Rulebook that describes how hard an action is. The Action Classifier picks the appropriate tier based on scene context (NPC stats, situation, environment). The Engine converts the tier to a SG number. Valid tiers: Sehr Leicht (8), Leicht (10), Durchschnitt (12), Schwer (14), Sehr Schwer (16), Heroisch (18), Extrem (20).

## NPC Entry
The database record for a non-player character. Always contains: name, current location, description, personality. Once the player has met an NPC (`met=true`), the entry is extended with: relation score (-100 to +100), what the NPC knows about the player, what the player knows about the NPC, shared history summary. An NPC's entry only enters the LLM context when the player is at the NPC's exact location and has either met them before or actively initiates contact. Never loaded by zone or region proximity alone.

## Session Synopsis
A short, LLM-generated summary produced every N turns and at session end. Stored in the DB. On the next turn or session, the last 2–3 synopses are injected into the context. Represents compressed long-term memory. Game state from the DB always overrides anything implied by the synopsis if they conflict.

## World Scope
Content that persists permanently across all characters and playthroughs. Includes: locations, infrastructure, major NPCs (kings, dukes, guild leaders), authored lore, world events. Modified only by major in-world events (war, fire, political change). The world grows with each playthrough but is never reset.

## Character Scope
Content tied to a specific character's playthrough. Includes: minor LLM-generated NPCs (e.g. a warehouse guard), character-specific relationship data, personal discoveries, playthrough-specific story events. Deleted or archived when a playthrough ends.

## NPC Tier
Determines the persistence scope of an NPC. Two fixed tiers:
- **Static NPC** — World-Scoped. Pre-authored before play begins. Has a defined role in the world's political and social structure (guard captain, duke, guild master). Exists independently of any playthrough. Participates in world-level events.
- **Generated NPC** — Character-Scoped by default. Created by the LLM during play when the Game State has no authored NPC for a situation. Can be manually promoted by the player to World-Scoped, after which they persist across playthroughs.

## Location Tier
Determines the persistence scope of a location. LLM-generated locations (a new alley, a hidden shrine, a sub-room in a warehouse) are immediately World-Scoped — they enter the canonical world and exist for all future Playthroughs. Only changes to existing locations (burned down, ownership changed, locked) are tracked as Character-Scoped World State Flags.

## NPC Schedule
The times and locations where an NPC can be found. Stored in the DB as part of the NPC entry. The Context Builder uses the schedule to determine whether an NPC is present at the current location and time before loading them into context. An NPC not on shift is not in the scene — regardless of their home location.

## Combat State
A flag (`in_combat=true`) set in the DB when combat begins. Initiative is determined by context (Classifier wertet Situation aus — Hinterhalt, Überraschung, wer angreift), kein separater Würfelwurf. Alle aktiven Gegner greifen den Spieler jede Runde an. Der Spieler greift standardmäßig einen Gegner pro Runde an. Mit einer expliziten Flächenaktion ("Ich schlage in den Schwarm") kann der Spieler mehrere Gegner gleichzeitig angreifen — mit Malus auf jeden Einzeltreffer, den der Classifier festlegt. Combat ends when all combatants are no longer `active`.

## Verteidigungswert (VW)
Passiver Schutzwert: `10 + GES-MOD + Schild-Bonus`. NPC-Angriffswürfe (intern vom Engine berechnet) müssen diesen Wert übertreffen um zu treffen. Der Spieler würfelt standardmäßig nicht für Verteidigung. Ausnahme: Erklärt der Spieler explizit "Ich weiche aus" oder "Ich blocke", wird eine aktive Verteidigungsprobe ausgeführt — Ausweichen (`W20 + GES-MOD + Akrobatik-Bonus`) oder Parade (`W20 + STR-MOD + Parade/Schild-Bonus`) gegen den NPC-Angriffswurf. Aktive Verteidigung ersetzt den eigenen Angriff in dieser Runde.

## Called Shot
When a player specifies a target zone in their action description (e.g. "Ich schlage auf den Kopf"), the Action Classifier raises the SG contextually — no fixed modifier. The Classifier weighs the target zone, the opponent's state, and the situation to pick the appropriate Difficulty Tier. A successful hit to the described zone is narrated accordingly by the Narrator. A critical hit (Nat 20) to a vital zone (head, throat) can trigger a Condition (Betäubung, Blutung) in addition to damage. Hit location is narrative flavor — there is no separate hit location table. The damage die result represents how clean and effective the hit was within the described zone.

## Combat Status
The state of a combatant during or after combat. Values: `active` (fighting normally), `incapacitated` (unconscious, broken, unable to fight — not dead), `fled`, `surrendered`, `dead`. Tracked per combatant in the DB. Injuries (e.g. broken arm, leg wound) apply roll modifiers independently of HP and are also tracked in the DB.

## Sterben
Bei 0 LP ist der Charakter bewusstlos und sterbend — er verliert jede Runde 1 LP durch Blutung. Ein anderer Charakter kann ihn mit einer Erste-Hilfe-Probe (SG 12 — Durchschnitt) stabilisieren. Ohne Stabilisierung stirbt der Charakter bei -10 LP. Selbststabilisierung ist nicht möglich. Mit geeigneten Items (Verbände, Tränke) kann ein bewusstloser Charakter unter bestimmten Umständen vom Narrator als stabilisiert gewertet werden.

## In-Game Clock
A timestamp stored in the DB representing the current in-game date and time. Updated each turn by the Engine using the `time_delta` value from the Narrator Output. The LLM estimates how much time the narrated action takes and includes it in its structured output. The Engine applies the delta, then re-evaluates NPC schedules against the new time. The current in-game time is injected into the context each turn so the LLM can make consistent time estimates.

## Narrator Output
The structured JSON document returned by the Narrator LLM each turn. Contains: `narration` (prose string), `time_delta_minutes` (integer — how much in-game time the narrated action took), `generated_locations` (array of new World-Scoped location entries), `generated_npcs` (array of new full NPC entries), `generated_groups` (array of new Group Entries attached to the current location), `world_state_changes` (array of World State Flag updates). No hard per-field limits — the LLM generates what the context demands. The Engine validates the document before applying changes. Malformed JSON triggers a retry; persistent failure falls back to narration-only with no state changes.

## Group Entry
A lightweight, location-attached placeholder representing unnamed or background characters in a scene (e.g. "a group of rowdy sailors", "two hooded figures in the corner"). World-Scoped — added to the canonical world when generated. Does not have a full NPC entry. When the player actively interacts with, approaches, or observes a Group Entry, the Narrator generates a full NPC from it and the Group Entry is replaced or remains as residual background. Keeps scenes populated and immersive without bloating the DB with full NPC records for every background character.

## Coordinate System
A 3000×3000 km world map. Coordinates are integers in meters (0–3,000,000 per axis). Every entity — realm, region, city area, zone, scene, sub-scene — has a fixed coordinate anchor stored in the DB. Realms and regions also have bounding boxes. The player's current position is a single x/y point updated each turn. The Context Builder uses player coordinates to determine which layers to load by checking bounding boxes from largest to smallest scope.

## Geographic Hierarchy
Five nested levels of geographic scope, each with coordinate ranges:
- **Realm** (Reich) — a kingdom or empire. Spans hundreds of km. Has a bounding box. Multiple realms exist on Avarr.
- **Region** — a geographic sub-division of a Realm. 80–100 km across. Has a bounding box. Maps to Layer B.
- **City Area** (Stadtgebiet) — an urban zone and its immediate surroundings. Up to 10 km across. Has a bounding box.
- **Zone** — a district, neighborhood, or landmark within a City Area or wilderness. 1–3 km across. Maps to Layer C.
- **Scene** — a specific building, street, clearing, or room. Precise coordinate anchor. Maps to Layer D.

## Playthrough
A single character's run through the world. Starts with the world in its canonical default state. All Character-Scoped content (generated NPCs, World State Flags, relationship data, session synopses) belongs to exactly one Playthrough. When a new Playthrough begins, the world resets to its default — previous character's changes do not carry over.

On the Landing Screen, a Playthrough is represented as a Run Entry showing: character name, class, level, last played timestamp, and current location. Actions per Run Entry: **Continue** (loads the game, restoring the last 10 turns of narration into the chat) and **Delete** (hard delete with confirmation dialog — removes all Character-Scoped data for that Playthrough).

## LLM Provider
The external API service used for all LLM calls. Three supported providers:
- **Anthropic** — direct Claude API (`sk-ant-...`). Default.
- **OpenRouter** — OpenAI-compatible proxy (`sk-or-...`). Supports any OpenRouter model including Gemini via `google/gemini-...` model IDs.
- **Google Gemini** — accessed via OpenRouter (not via Google AI SDK directly).

Provider selection, API key, and model are stored in browser localStorage only — never sent to the game server except as parameters in individual API calls. Managed via the **Settings Screen**, a modal accessible from the Landing Screen and the In-Game header (⚙ button). The wizard no longer contains API configuration.

## World State Flag
A Character-Scoped boolean or value stored in the DB that records how a World-Scoped entity has changed during a Playthrough (e.g. `tavern_burned=true`, `warehouse_owner=killed`). The Context Builder checks these flags and dynamically overrides or extends the static World Layer text when assembling the prompt. Flags are reset when a new Playthrough begins.

## World Layer
One of five fixed context layers assembled fresh each turn by the Context Builder. Ordered by scope: A (world constants, always present) → B (region) → C (zone/town) → D (current scene) → E (active context: NPCs, player stats, last turns, engine result). Total target ~1400 tokens. Layer content is authored once when the world is built; the LLM never modifies it. Exact layer boundaries and optimal token budgets to be validated through playtesting.

## Charaktererstellung
The one-time setup when a new Playthrough begins. Three steps:

**1. Name + Hintergrund:** Name ist Pflichtfeld. Hintergrundgeschichte ist optionaler Freitext — wird im Kontext für den Narrator sichtbar, hat keinen mechanischen Effekt.

**2. Attribute:** Spieler verteilt frei 78 Punkte auf 6 Attribute (STR, GES, KON, INT, WEI, CHA). Min 6, max 18 pro Attribut bei Erstellung. Das absolute Maximum von 20 wird nur durch Levelups erreicht.

**3. Klasse:** Rein narratives Label (Krieger, Schurke, Händler, Essenzkundiger, Waldläufer). Bestimmt Flavor und 1–2 charakteristische Startitems. Hat keinen Einfluss auf Attribut- oder Skillwerte.

**4. Skills:** Spieler verteilt frei 80 Punkte auf beliebige Skills (Skala 0–100). Max 30 pro Skill bei Erstellung. Alle nicht gewählten Skills starten bei 0 (können trotzdem versucht werden, ohne Bonus).

**Startausrüstung:** Klasse gibt 1–2 charakteristische Items vor. Zusätzlich erhält jeder Charakter 500 Kupfer (= 5 Gold) für freie Einkäufe. Die DB speichert Münzen immer in Kupfer als Basiseinheit (1 Gold = 100 Kupfer, 1 Silber = 10 Kupfer).

## Essenz-Veranlagung
Jeder Spielercharakter ist immer essenzveranlagt — das ist Teil dessen was ihn von einem Durchschnittsmenschen unterscheidet. Keine Freischaltbedingung nötig. Beide Essenz-Skills (Essenz-Transmutation, Essenz-Kraftprojektion) sind ab Charaktererstellung lernbar und einsetzbar (auch bei Skill 0, dann ohne Bonus). NPCs haben die Veranlagung nur wenn es narrativ und weltlogisch Sinn macht — Seltenheit bleibt gewahrt.

## Heilung
Vier Quellen der LP-Wiederherstellung:
- **Natürliche Rast:** `KON-MOD + Level` LP pro Nacht, Minimum 1. Voraussetzung: Schlaf in sicherer Umgebung.
- **Erste Hilfe:** `W6` LP sofort nach einem Kampf. Erfordert eine Erste-Hilfe-Probe (SG 10). Einmal pro Kampf anwendbar.
- **Längere Rast:** doppelte natürliche Heilung pro Nacht. Voraussetzung: mindestens 3 aufeinanderfolgende Tage Ruhe ohne Kämpfe.
- **Items (Tränke/Kräuter):** feste LP-Werte je nach Qualität. Werte vom Narrator oder Händler definiert.

## Attribut (ATTR)
Sechs Basiswerte auf Skala 1–20. Durchschnitt = 10. Modifier = `floor((Wert - 10) / 2)`. Bei Skills mit zwei Leit-Attributen (z.B. STR/GES) zählt immer der höhere Modifier. Startwerte durch freie Verteilung bei Charaktererstellung (max 18). Steigen durch Charakter-Level-Ups (max 20).

## Skill (SKILL)
Ein Fähigkeitswert auf Skala 0–100. Skill-Bonus = `floor(Skill-Wert / 10)`. Jeder Skill hat ein Leit-Attribut (oder zwei, wobei der höhere Modifier zählt). Steigt durch Ticks (Learning-by-Doing). Ticks werden bei jeder Probe vergeben — unabhängig vom Erfolg. Die Anzahl nötiger Ticks pro +1 Skillpunkt steigt mit dem Skill-Niveau (Novize: 3 Ticks, Lehrling: 5, Geselle: 8, Experte: 12, Meister: 20).
