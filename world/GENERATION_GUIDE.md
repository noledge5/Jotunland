# World Generation Guide

You are generating a game world for a solo RPG engine. Your output must be valid JSON that matches the schema in `world_template.json`. Read this guide fully before generating.

---

## What you are building

A persistent, geographically precise fantasy world on a **500×500 km map**. All coordinates are integers in **meters** (x: 0–500000, y: 0–500000). Every location — from a continent-spanning region to a single tavern room — has exact x/y coordinates.

The world is structured in layers used to build LLM context during play:

| Layer | Scope | Token budget | Changes when |
|---|---|---|---|
| A — World Constants | Always present | ~200 | Never |
| B — Region | ~100×100 km area | ~300 | Player crosses region boundary |
| C — Zone | Town, forest, dungeon (~5×5 km) | ~200 | Player enters zone |
| D — Scene | Building, street, room | ~200 | Player enters scene |

Write each layer's text as vivid, present-tense prose. Layer A sets the world's fundamental tone and era. Layers B–D get progressively more specific and sensory. No game mechanics in layer text — only atmosphere, politics, culture, and physical detail.

---

## Coordinate rules

- Origin (0,0) = southwest corner of the map
- x increases eastward, y increases northward
- Every entity has a `coordinate_anchor` — the center point of that location
- Regions also have a `bounding_box` defining their extent
- Zones sit inside a region's bounding box
- Scenes sit inside a zone's bounding box
- Sub-scenes sit inside a scene's bounding box (rooms within a building)
- Player always starts at a scene-level coordinate

---

## NPC schedules

Static NPCs have schedules. A schedule is a list of time blocks. Each block says where the NPC is and during which hours. Hours are 0–23. If an NPC has no block for the current hour, they are not present in any scene — they are off-duty, sleeping, or elsewhere.

```json
"schedule": [
  { "hour_start": 6, "hour_end": 14, "scene_id": "ironhold_tavern_common_room" },
  { "hour_start": 14, "hour_end": 22, "scene_id": "ironhold_market_square" },
  { "hour_start": 22, "hour_end": 6, "scene_id": "ironhold_guard_barracks" }
]
```

---

## Group Entries

Scenes should feel populated without every background character being a full NPC. Use Group Entries for anonymous background presence. A Group Entry is a short label + one-sentence description attached to a scene. When a player interacts with a group, the game engine generates a full NPC from it.

```json
"group_entries": [
  { "label": "corner drinkers", "description": "Three weathered farmers nursing cheap ale, talking quietly about the harvest." },
  { "label": "hooded traveller", "description": "A lone figure at the back table, face hidden, eating without looking up." }
]
```

---

## What to generate

Fill in the JSON template with:
- 1 set of world constants (Layer A)
- 2–4 regions with bounding boxes
- 2–5 zones per region
- 3–8 scenes per zone
- 1–3 sub-scenes per scene where relevant (rooms, cellars, back alleys)
- 3–10 Static NPCs distributed across scenes with schedules
- 2–5 Group Entries per populated scene
- 1 starting location (must be a scene-level coordinate)
- 1 starting in-game date and time

The world should have internal political and social logic. Factions should have goals that create natural conflict. NPCs should have roles that make sense given their location and schedule.

---

## Rules for layer text

- Layer A: world name, era, dominant tone (dark, hopeful, grim), major historical fact, cosmological rule (magic exists / doesn't / is rare), current geopolitical situation in one paragraph.
- Layer B: region name, climate, dominant culture, current political tension, one notable geographic feature, factions present.
- Layer C: zone/town name, size, reputation, current local situation, notable landmarks, what kind of people live here.
- Layer D: scene name, physical description (materials, light, smell, sound), who typically uses this space, current ambient mood.

Do not repeat information from a higher layer in a lower one. Each layer adds specificity, not repetition.

---

## Output

Return a single valid JSON object matching `world_template.json`. Use the `_desc` fields as instructions — strip them from your output. Do not add fields not present in the template. Coordinate values must be integers. Text fields must be strings. Array fields must be arrays even if empty.
