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

## Mechanical Resolution
All game outcomes — damage, skill check results, hit/miss, XP gain — are determined by the Engine using dice rolls and rules config before the LLM is ever called. The LLM receives the already-computed result and narrates it. The LLM never decides or modifies a mechanical outcome.

## Rules Config
The set of tables or data files that define game constants: weapon damage dice, armor values, skill difficulty thresholds, XP formulas. Owned entirely by the Engine. Never read by the LLM.
