# FoE Community INFO

Community reference and personal planning tool for Forge of Empires guilds.  
Built from FoE Helper MegaExport data. Hosted on GitHub Pages. No server needed.

**Live URL:** https://geomeskin.github.io/FoE_Community_INFO/

---

## What it does

Generates a **shared community dashboard** plus **individual player pages** from FoE Helper MegaExport zip files.

| Page | URL | Contents |
|---|---|---|
| Community Dashboard | `/index.html` | Tabs 1 & 2 — boost reference for everyone |
| Personal Page | `/PLAYERTAG.html` | All 4 tabs — includes that player's GB and fragment data |

### The four tabs

**⚔ Tab 1 — Boost Reference**  
722+ event buildings with attack/defense boost values per era. Pick your era, sort by any column. Includes preview data from the BETA server before events launch on live.

**⚔ Tab 2 — Battle Boost Reference**  
Curated list of top battle boost buildings across Open World, GEx, GBG, and QI contexts.  
Data maintained by Wyldfyre. Four boost types:
- **AAA** = Attack for Attacking Army
- **DAA** = Defense for Attacking Army  
- **ADA** = Attack for Defending Army
- **DDA** = Defense for Defending Army

**🏛 Tab 3 — GB Planner**  
Great Building levels, progress bars, and FP cost to next level. One section per player.

**🧨 Tab 4 — Fragment Tracker**  
Tracks fragment progress toward kits and buildings. In-progress items shown first by % completion.

> **Known limitation:** Fragments purchased in the QI Shop are not recorded in the FoE Helper
> MegaExport and will not appear in the tracker. QI Seasonal Kit fragment balances (e.g. QI
> Spring/Summer/Autumn Epic Selection Kits) are also not captured. If your in-game inventory
> shows fragment counts that don't match the tracker, QI shop purchases are the likely cause.

---

## Weekly update workflow

**Every Thursday** — run this from Git Bash:

```bash
foe
./update.sh
```

That's it. The script rebuilds all pages and pushes to GitHub. Pages update within ~60 seconds.

> **Note:** Run `./update.sh` only — do not run `build.py` separately first.  
> `update.sh` runs the builder internally, then commits and pushes all HTML files automatically.

---

## Full update process

### Step 1 — Export from FoE Helper

In FoE Helper, click the icon → **MEGAexport**. Save the `.zip` file.  
Each zip is ~2.5 MB — safe to send via email or Discord.

> **Pro tip:** Export from the BETA server as soon as a new event launches —  
> BETA runs events ahead of live, so you get preview building data early.  
> Event buildings only appear in buildingMeta **while the event is active** — timing matters.

### Step 2 — Name and place the zip

Rename the zip to:
```
PLAYERTAG_foe_helper_MEGAexport_YYMMDD.zip
```

The `PLAYERTAG` prefix becomes:
- The filename of that player's personal page (`PLAYERTAG.html`)
- The label shown throughout the UI

Examples:
```
exports/
  PMTHS_foe_helper_MEGAexport_260420.zip
  CTHG_foe_helper_MEGAexport_260420.zip
  WYLDFYRE_foe_helper_MEGAexport_260420.zip
  PROMBTHEUS_foe_helper_MEGAexport_260420.zip
```

Old zips can stay — or delete them to keep it tidy. The script always uses **all** zips in the folder.

### Step 3 — Run the update

```bash
foe
./update.sh
```

The script:
1. Reads all zips in `exports/`
2. Builds the shared community dashboard (`index.html`)
3. Builds one personal page per zip (`PLAYERTAG.html`)
4. Commits and pushes all HTML files to GitHub
5. GitHub Pages serves the updated pages within ~60 seconds

---

## Adding a new guild member

1. Ask them to export their MegaExport zip from FoE Helper (~2.5 MB)
2. They send it to you via email or Discord
3. Rename it to `THEIRNAME_foe_helper_...zip`
4. Drop it in `exports/`
5. Run `./update.sh`

Their personal page appears at `geomeskin.github.io/FoE_Community_INFO/THEIRNAME.html`.  
Their data does **not** appear on the shared community dashboard.

---

## Updating the Battle Boost CSV (Tab 2)

The battle boost reference is driven by a CSV file next to `build.py`:
```
Wyldfyre_BattleBoosts_YYMMDD.csv
```

To update it, replace the CSV with a newer version — the script auto-detects any file matching `*BattleBoost*.csv`. No code changes needed.

---

## Running the builder manually (without pushing)

```bash
py build.py
```

Or pass zips explicitly:
```bash
py build.py exports/PMTHS_foe_helper_...zip exports/WYLDFYRE_foe_helper_...zip
```

---

## File structure

```
FoE_Community_INFO/
├── build.py                          # Page builder — called by update.sh
├── update.sh                         # Build + git push in one command
├── Wyldfyre_BattleBoosts_YYMMDD.csv  # Battle boost reference data (Tab 2)
├── exports/                          # ← gitignored — drop player zips here
│   ├── PMTHS_foe_helper_...zip
│   ├── CTHG_foe_helper_...zip
│   ├── PROMBTHEUS_foe_helper_...zip
│   └── WYLDFYRE_foe_helper_...zip
├── index.html                        # Community dashboard (auto-generated)
├── PMTHS.html                        # Personal pages (auto-generated)
├── CTHG.html
├── PROMBTHEUS.html
└── WYLDFYRE.html
```

---

## Requirements

- Python 3.9+ (standard library only — no `pip install` needed)
- Git Bash with push access to the repo
- FoE Helper browser extension (for MegaExport)

---

## Current players

| Tag | Player | Account | Era |
|---|---|---|---|
| PMTHS | Geo-Meskin | Main (live — us1) | Oceanic Future |
| CTHG | Geo-Meskin | Alt (live — us28) | Contemporary Era |
| PROMBTHEUS | Geo-Meskin | BETA server (zz1) | Contemporary Era |

---

*Data sourced from FoE Helper MegaExports — community reference only. Not affiliated with InnoGames.  
Battle boost data curated by Wyldfyre.*
