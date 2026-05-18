# Glossary

## Immersion Break
Any moment in gameplay where the player experiences a contradiction between what the LLM narrates and what the established game state says is true. Three subtypes, in order of severity:
- **Rule Bypass** — the LLM allows an action to succeed without a proper mechanic resolution (e.g. theft without a Stealth check)
- **World Inconsistency** — the LLM narrates something that contradicts a known fact (NPC knows something they can't know; player is somewhere they aren't)
- **Session Drift** — the LLM fails to recall or apply established facts from prior sessions (NPC forgets a past interaction)

## Game State
The authoritative record of all facts about the current game world: player stats, inventory, location, NPC relationships, quest status, session history. Stored in the database. The LLM never holds Game State in its own memory — it receives it fresh from the database on every turn.

## Turn
One complete player interaction cycle: player input → engine resolution → context assembly → LLM narration → state update.

## Action Classifier
A lightweight, structured LLM call that receives the raw player input, the character's current skill list, and scene context. It decides (a) whether the action requires a dice roll at all, and (b) if so, which skill applies. Returns structured JSON: `{ "skill": "stealth", "needs_roll": true }` or `{ "needs_roll": false }`. Does not use a hardcoded action-type enum — the Skill List is the rulebook. Makes no decisions about outcomes.

## Skill List
The canonical set of skills available in the game (e.g. Stealth, Persuasion, Lockpick, Riding). Defined once as game config. Each character has a level per skill stored in the DB. The Action Classifier maps player intent to a skill from this list — it does not invent skill names. A character with no level in a skill may still attempt the action — they roll without a modifier. XP is awarded for every attempted action regardless of outcome.

## Mechanical Resolution
All game outcomes — damage, skill check results, hit/miss, XP gain — are determined by the Engine using dice rolls and rules config before the LLM is ever called. The LLM receives the already-computed result and narrates it. The LLM never decides or modifies a mechanical outcome.

## Rules Config
The set of tables or data files that define game constants: weapon damage dice, armor values, skill difficulty thresholds, XP formulas. Owned entirely by the Engine. Never read by the LLM.

## NPC Entry
The database record for a non-player character. Always contains: name, current location, description, personality. Once the player has met an NPC (`met=true`), the entry is extended with: relation score (-100 to +100), what the NPC knows about the player, what the player knows about the NPC, shared history summary. An NPC's entry only enters the LLM context when the player is at the NPC's exact location and has either met them before or actively initiates contact. Never loaded by zone or region proximity alone.

## Session Synopsis
A short, LLM-generated summary produced every N turns and at session end. Stored in the DB. On the next turn or session, the last 2–3 synopses are injected into the context. Represents compressed long-term memory. Game state from the DB always overrides anything implied by the synopsis if they conflict.

## World Layer
One of five fixed context layers assembled fresh each turn by the Context Builder. Ordered by scope: A (world constants, always present) → B (region) → C (zone/town) → D (current scene) → E (active context: NPCs, player stats, last turns, engine result). Total target ~1400 tokens. Layer content is authored once when the world is built; the LLM never modifies it. Exact layer boundaries and optimal token budgets to be validated through playtesting.
