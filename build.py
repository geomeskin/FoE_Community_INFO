#!/usr/bin/env python3
"""
FoE Best Buildings — Page Builder
===================================
Drop any number of FoE Helper MegaExport zip files into the exports/ folder,
then run:

    python build.py

The script reads every zip in exports/, extracts building boost data from the
buildingMeta table, stores values for ALL eras, and writes index.html.

Or pass zip paths explicitly:
    python build.py path/to/CITY1.zip path/to/CITY2.zip
"""

import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# ── Era definitions ───────────────────────────────────────────────────────────
ERA_ORDER = [
    "StoneAge", "BronzeAge", "IronAge", "EarlyMiddleAge", "HighMiddleAge",
    "LateMiddleAge", "ColonialAge", "IndustrialAge", "ProgressiveEra",
    "ModernEra", "PostModernEra", "ContemporaryEra", "TomorrowEra",
    "FutureEra", "ArcticFuture", "OceanicFuture", "VirtualFuture",
    "SpaceAgeMars", "SpaceAgeAsteroidBelt", "SpaceAgeVenus",
    "SpaceAgeJupiterMoon", "SpaceAgeTitan", "SpaceAgeSpaceHub",
]
ERA_RANK = {e: i for i, e in enumerate(ERA_ORDER)}

ERA_LABELS = {
    "StoneAge":             "Stone Age",
    "BronzeAge":            "Bronze Age",
    "IronAge":              "Iron Age",
    "EarlyMiddleAge":       "Early Middle Age",
    "HighMiddleAge":        "High Middle Age",
    "LateMiddleAge":        "Late Middle Age",
    "ColonialAge":          "Colonial Age",
    "IndustrialAge":        "Industrial Age",
    "ProgressiveEra":       "Progressive Era",
    "ModernEra":            "Modern Era",
    "PostModernEra":        "Post-Modern Era",
    "ContemporaryEra":      "Contemporary Era",
    "TomorrowEra":          "Tomorrow Era",
    "FutureEra":            "Future Era",
    "ArcticFuture":         "Arctic Future",
    "OceanicFuture":        "Oceanic Future",
    "VirtualFuture":        "Virtual Future",
    "SpaceAgeMars":         "Space Age: Mars",
    "SpaceAgeAsteroidBelt": "Space Age: Asteroid Belt",
    "SpaceAgeVenus":        "Space Age: Venus",
    "SpaceAgeJupiterMoon":  "Space Age: Jupiter Moon",
    "SpaceAgeTitan":        "Space Age: Titan",
    "SpaceAgeSpaceHub":     "Space Age: Space Hub",
}

# ── Event code → display name ─────────────────────────────────────────────────
EVENT_MAP = {
    "WIN":  "Winter Event",
    "WILD": "Wildlife Event",
    "CARE": "Wildlife Care Event",
    "PAT":  "St. Patrick\u2019s Event",
    "SUM":  "Summer Event",
    "FALL": "Fall Event",
    "COP":  "COP Climate Event",
    "HAL":  "Halloween Event",
    "ANNI": "Anniversary",
    "GR":   "Guild Raids",
    "FELL": "Fellowship Event",
    "HIS":  "Historical Quest",
    "CUP":  "Soccer/Cup Event",
    "GBG":  "Guild Battlegrounds",
    "BOWL": "Football/Bowl Event",
    "ARCH": "Architecture Event",
    "HERO": "Hero Event",
    "GEX":  "Guild Expedition",
    "LTE":  "Age Bonus",
    "SPR":  "Spring Event",
}

# ── Boost type → column mapping ───────────────────────────────────────────────
# Features 'all', 'guild_expedition', 'guild_raids' → general military (a / d)
# Feature  'battleground'                           → GbG columns (ga / gd)
GENERAL_FEATURES = {"all", "guild_expedition", "guild_raids"}
GBG_FEATURES     = {"battleground"}

ATT_TYPES = {
    "att_boost_attacker",
    "att_def_boost_attacker",
    "att_def_boost_attacker_defender",
    "att_def_boost_defender",
}
DEF_TYPES = {
    "def_boost_attacker",
    "att_boost_defender",
    "def_boost_defender",
    "att_def_boost_attacker",
    "att_def_boost_attacker_defender",
    "att_def_boost_defender",
}


def calc_boosts(components: dict, era: str) -> tuple:
    a = d = ga = gd = 0
    for b in components.get(era, {}).get("boosts", {}).get("boosts", []):
        btype = b.get("type", "")
        feat  = b.get("targetedFeature", "all")
        val   = b.get("value", 0)
        is_gen = feat in GENERAL_FEATURES
        is_gbg = feat in GBG_FEATURES
        if btype in ATT_TYPES:
            if is_gen:   a  += val
            elif is_gbg: ga += val
        if btype in DEF_TYPES:
            if is_gen:   d  += val
            elif is_gbg: gd += val
    return a, d, ga, gd


def get_event(bid: str):
    m = re.match(r"W_MultiAge_([A-Z]+)(\d{2})", bid)
    if not m:
        return None
    code, yr = m.group(1), int(m.group(2))
    name = EVENT_MAP.get(code)
    return f"{name} 20{yr:02d}" if name else None


def extract_from_zip(zip_path: Path) -> tuple:
    """Return (buildings_dict, highest_era_idx)."""
    buildings: dict = {}
    highest_era_idx = 0

    with zipfile.ZipFile(zip_path) as zf:
        for fname in zf.namelist():
            if not fname.endswith(".json") or "FoeHelperDB_" not in fname:
                continue
            if any(x in fname for x in [
                "Events", "FPCollector", "GexStat",
                "GuildFights", "GuildMember", "Qi",
            ]):
                continue
            try:
                data = json.loads(zf.read(fname))
            except Exception:
                continue

            tables = data.get("data", {}).get("data", [])
            bm = next((t for t in tables if t.get("tableName") == "buildingMeta"), None)
            if not bm:
                continue

            for row in bm["rows"]:
                raw = row.get("json", "{}")
                j   = json.loads(raw) if isinstance(raw, str) else raw
                bid = j.get("id", "")

                if not bid.startswith("W_MultiAge_"):
                    continue
                if not j.get("components"):
                    continue
                evt = get_event(bid)
                if not evt:
                    continue

                allage = j["components"].get("AllAge", {})
                size_c = allage.get("placement", {}).get("size", {})
                w = size_c.get("x", 0)
                h = size_c.get("y", 0)
                if not w or not h:
                    continue

                # Compact per-era boost data: [[era_index, a, d, ga, gd], ...]
                # Only store eras with non-zero total boost
                era_rows = []
                for era in ERA_ORDER:
                    a, d, ga, gd = calc_boosts(j["components"], era)
                    if a + d + ga + gd > 0:
                        idx = ERA_RANK[era]
                        era_rows.append([idx, a, d, ga, gd])
                        if idx > highest_era_idx:
                            highest_era_idx = idx
                if not era_rows:
                    continue

                buildings[bid] = {
                    "name": j["name"],
                    "w":    w,
                    "h":    h,
                    "evt":  evt,
                    "e":    era_rows,
                }

    return buildings, highest_era_idx


def build_best_list(zip_paths: list) -> tuple:
    """Merge all zips, return (building_rows, highest_era_idx)."""
    all_buildings: dict = {}
    global_highest = 0

    for zp in zip_paths:
        print(f"  Reading {zp.name} ...")
        bldgs, hi = extract_from_zip(zp)
        print(f"    -> {len(bldgs):,} boost buildings found")
        all_buildings.update(bldgs)
        if hi > global_highest:
            global_highest = hi

    print(f"  Total unique buildings : {len(all_buildings):,}")
    print(f"  Highest era in data    : {ERA_LABELS[ERA_ORDER[global_highest]]}")

    rows = []
    for bid, b in all_buildings.items():
        rows.append({
            "n":   b["name"],
            "id":  bid,
            "s":   f"{b['w']}\u00d7{b['h']}",
            "t":   b["w"] * b["h"],
            "evt": b["evt"],
            "e":   b["e"],
        })

    return rows, global_highest


# ── HTML template ─────────────────────────────────────────────────────────────
HTML_TEMPLATE = (
"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FoE Best Boost Buildings \u2014 Community Reference</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&family=Exo+2:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#080c14;--bg2:#0d1220;--bg3:#111827;--panel:#0f1825;
  --border:#1e2d45;--border2:#263650;
  --gold:#f0b429;--blue:#3b82f6;--blue2:#7dd3fc;
  --teal:#14b8a6;--green:#22c55e;--red:#ef4444;
  --text:#e2e8f0;--text2:#b8c4d4;--text3:#6b7e99;
}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Exo 2',sans-serif;font-size:14px;
  background-image:radial-gradient(ellipse at 10% 0%,rgba(59,130,246,.08) 0%,transparent 40%),
  radial-gradient(ellipse at 90% 100%,rgba(20,184,166,.06) 0%,transparent 40%);}
.app{max-width:1280px;margin:0 auto;padding:24px 20px 60px;}
.header{text-align:center;padding:40px 0 32px;border-bottom:1px solid var(--border);margin-bottom:28px;}
.header h1{font-family:'Rajdhani',sans-serif;font-size:2.2rem;font-weight:700;letter-spacing:.06em;
  color:var(--gold);text-transform:uppercase;margin-bottom:8px;}
.header p{color:var(--text2);font-size:.9rem;max-width:680px;margin:0 auto 16px;line-height:1.6;}
.badges{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;}
.badge{background:var(--bg3);border:1px solid var(--border2);border-radius:6px;padding:5px 14px;
  font-family:'Share Tech Mono',monospace;font-size:.76rem;}
.badge.gold{color:var(--gold);border-color:rgba(240,180,41,.3);}
.badge.teal{color:var(--teal);border-color:rgba(20,184,166,.3);}
.badge.green{color:var(--green);border-color:rgba(34,197,94,.3);}
.badge.blue{color:var(--blue2);border-color:rgba(125,211,252,.3);}
.info-box{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--teal);
  border-radius:8px;padding:14px 18px;margin-bottom:20px;font-size:.85rem;line-height:1.7;color:var(--text2);}
.info-box strong{color:var(--text);}
.toolbar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center;}
.search-box{flex:1;min-width:180px;background:var(--bg2);border:1px solid var(--border2);
  border-radius:6px;padding:7px 12px;color:var(--text);font-family:'Exo 2',sans-serif;
  font-size:.85rem;outline:none;}
.search-box:focus{border-color:var(--blue);}
.ddl{background:var(--bg2);border:1px solid var(--border2);border-radius:6px;padding:7px 10px;
  color:var(--text);font-family:'Exo 2',sans-serif;font-size:.83rem;outline:none;cursor:pointer;}
.ddl:focus{border-color:var(--blue);}
.ddl.era-sel{border-color:rgba(240,180,41,.4);color:var(--gold);font-weight:600;}
.era-wrap{display:flex;align-items:center;gap:6px;}
.era-label{font-family:'Share Tech Mono',monospace;font-size:.72rem;color:var(--text3);white-space:nowrap;}
.count-label{font-family:'Share Tech Mono',monospace;font-size:.73rem;color:var(--text3);white-space:nowrap;}
.table-wrap{background:var(--panel);border:1px solid var(--border);border-radius:8px;
  overflow:auto;max-height:620px;}
table{width:100%;border-collapse:collapse;}
th{background:var(--bg3);position:sticky;top:0;z-index:2;font-family:'Share Tech Mono',monospace;
  font-size:.68rem;letter-spacing:.08em;color:var(--text3);padding:9px 12px;text-align:left;
  border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none;}
th:hover{color:var(--text2);}
th.sorted{color:var(--gold);}
td{padding:7px 12px;border-bottom:1px solid rgba(30,45,69,.4);font-size:.83rem;white-space:nowrap;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:rgba(59,130,246,.04);}
.bn{color:var(--text);max-width:240px;overflow:hidden;text-overflow:ellipsis;font-weight:500;}
.sb{display:inline-block;font-size:.68rem;font-family:'Share Tech Mono',monospace;color:var(--text3);margin-left:4px;}
.v{font-family:'Share Tech Mono',monospace;}
.v-gold{color:var(--gold);font-weight:600;}
.v-att{color:var(--red);}
.v-def{color:var(--blue2);}
.v-gbg{color:var(--teal);}
.zero{color:var(--text3);}
.rank{font-family:'Share Tech Mono',monospace;color:var(--text3);font-size:.75rem;width:36px;text-align:right;}
.rank-1{color:var(--gold);font-weight:700;}
.rank-2{color:#94a3b8;font-weight:600;}
.rank-3{color:#cd7c3a;font-weight:600;}
.evt-tag{display:inline-block;font-size:.68rem;font-family:'Share Tech Mono',monospace;
  color:var(--text2);background:var(--bg3);border:1px solid var(--border);border-radius:3px;
  padding:1px 5px;max-width:200px;overflow:hidden;text-overflow:ellipsis;}
.no-data{color:var(--text3);font-style:italic;font-size:.8rem;}
.footer{text-align:center;padding-top:40px;color:var(--text3);font-size:.8rem;
  border-top:1px solid var(--border);margin-top:40px;}
.footer a{color:var(--teal);text-decoration:none;}
</style>
</head>
<body>
<div class="app">

<div class="header">
  <h1>&#9876; FoE Best Boost Buildings</h1>
  <p>Community reference for top military boost buildings. Select your era to see the boost values that apply to your city.</p>
  <div class="badges">
    <span class="badge gold">%%BUILDING_COUNT%% Buildings</span>
    <span class="badge teal">%%ERA_COUNT%% Eras</span>
    <span class="badge green">Updated %%BUILD_DATE%%</span>
    <span class="badge blue">%%DATA_SOURCES%%</span>
  </div>
</div>

<div class="info-box">
  <strong>How to use:</strong> Pick your era from the <strong>ERA</strong> dropdown \u2014 all boost values update instantly.
  <strong>Att%</strong> = your attacker's attack bonus &nbsp;|&nbsp;
  <strong>Def%</strong> = your attacker's defense bonus &nbsp;|&nbsp;
  <strong>GbG Att/Def%</strong> = Guild Battlegrounds bonuses.
  <strong>Total</strong> = sum of all four &nbsp;|&nbsp; <strong>Pt</strong> = total per tile (space efficiency).
  Buildings with no data for your era show \u2014 in the value columns but remain visible.
</div>

<div class="toolbar">
  <input class="search-box" id="search" placeholder="Search building name\u2026" oninput="render()">

  <div class="era-wrap">
    <span class="era-label">ERA:</span>
    <select class="ddl era-sel" id="era-sel" onchange="render()">
%%ERA_OPTIONS%%
    </select>
  </div>

  <select class="ddl" id="filter-type" onchange="render()">
    <option value="">All types</option>
    <option value="event">Event buildings</option>
    <option value="gbg">GbG boost only</option>
    <option value="ge">Guild Expedition</option>
  </select>

  <select class="ddl" id="filter-event" onchange="render()">
    <option value="">All events</option>
%%EVENT_OPTIONS%%
  </select>

  <select class="ddl" id="sort-by" onchange="render()">
    <option value="tot">Sort: Total</option>
    <option value="pt">Sort: Per Tile</option>
    <option value="a">Sort: Att%</option>
    <option value="d">Sort: Def%</option>
    <option value="ga">Sort: GbG Att%</option>
    <option value="gd">Sort: GbG Def%</option>
    <option value="n">Sort: Name</option>
    <option value="evt">Sort: Event</option>
  </select>

  <span class="count-label" id="count"></span>
</div>

<div class="table-wrap">
<table>
<thead><tr>
  <th onclick="colSort('rank')">#</th>
  <th onclick="colSort('n')">BUILDING</th>
  <th onclick="colSort('tot')">TOTAL \u25be</th>
  <th onclick="colSort('pt')">PT</th>
  <th onclick="colSort('a')">ATT%</th>
  <th onclick="colSort('d')">DEF%</th>
  <th onclick="colSort('ga')">GBG ATT%</th>
  <th onclick="colSort('gd')">GBG DEF%</th>
  <th>SIZE</th>
  <th onclick="colSort('evt')">EVENT</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
</div>

<div class="footer">
  Data sourced from FoE Helper MegaExports &mdash; community reference only. Not affiliated with InnoGames.<br>
  <a href="https://github.com/nickolasnikola" target="_blank">GitHub</a>
</div>
</div>

<script>
const ERA_ORDER  = %%ERA_ORDER_JSON%%;
const ERA_LABELS = %%ERA_LABELS_JSON%%;

// BEST: [{n, id, s, t, evt, e}]
// e: [[era_index, a, d, ga, gd], ...] sorted ascending by era_index
// Only eras with non-zero total boost are stored.
const BEST = %%BEST_JSON%%;

// ── Resolve boosts for a building at a given era index ───────────────────────
// Uses exact era if available, otherwise falls back to the nearest lower era.
function getBoosts(building, eraIdx) {
  let best = null;
  for (const row of building.e) {
    if (row[0] <= eraIdx) best = row;
    else break;
  }
  if (!best) return null;
  return { a: best[1], d: best[2], ga: best[3], gd: best[4] };
}

let sortCol = 'tot';
let sortAsc  = false;

function render() {
  const search      = document.getElementById('search').value.toLowerCase();
  const eraIdx      = parseInt(document.getElementById('era-sel').value);
  const filterType  = document.getElementById('filter-type').value;
  const filterEvent = document.getElementById('filter-event').value;
  sortCol           = document.getElementById('sort-by').value;

  let rows = BEST.map(b => {
    const bst = getBoosts(b, eraIdx);
    const a = bst ? bst.a : 0, d = bst ? bst.d : 0;
    const ga = bst ? bst.ga : 0, gd = bst ? bst.gd : 0;
    const tot = a + d + ga + gd;
    return { ...b, a, d, ga, gd, tot,
             pt: tot > 0 ? +(tot / b.t).toFixed(1) : 0,
             hasData: !!bst };
  });

  rows = rows.filter(b => {
    if (search && !b.n.toLowerCase().includes(search)) return false;
    if (filterType === 'event' && !b.evt) return false;
    if (filterType === 'gbg'   && b.ga === 0 && b.gd === 0) return false;
    if (filterType === 'ge'    && !(b.evt || '').includes('Guild Expedition')) return false;
    if (filterEvent && b.evt !== filterEvent) return false;
    return true;
  });

  rows.sort((a, b) => {
    if (sortCol === 'n')   return sortAsc ? a.n.localeCompare(b.n) : b.n.localeCompare(a.n);
    if (sortCol === 'evt') return sortAsc ? (a.evt||'').localeCompare(b.evt||'') : (b.evt||'').localeCompare(a.evt||'');
    return sortAsc ? (a[sortCol]||0)-(b[sortCol]||0) : (b[sortCol]||0)-(a[sortCol]||0);
  });

  document.getElementById('count').textContent = rows.length + ' buildings';

  const fmtV = (val, cls) =>
    val > 0 ? '<span class="v '+cls+'">'+val+'%</span>' : '<span class="zero">\u2014</span>';

  document.getElementById('tbody').innerHTML = rows.map((b, i) => {
    const rank = i + 1;
    const rk = rank===1?'rank-1':rank===2?'rank-2':rank===3?'rank-3':'';
    const totCell = b.hasData
      ? '<span class="v v-gold">'+b.tot.toLocaleString()+'</span>'
      : '<span class="no-data">no era data</span>';
    const ptCell = b.hasData && b.pt > 0
      ? '<span class="v v-gold">'+b.pt+'</span>'
      : '<span class="zero">\u2014</span>';
    return '<tr>'
      +'<td class="rank '+rk+'">'+rank+'</td>'
      +'<td class="bn">'+b.n+'<span class="sb">'+b.s+'</span></td>'
      +'<td>'+totCell+'</td>'
      +'<td>'+ptCell+'</td>'
      +'<td>'+fmtV(b.a,'v-att')+'</td>'
      +'<td>'+fmtV(b.d,'v-def')+'</td>'
      +'<td>'+fmtV(b.ga,'v-gbg')+'</td>'
      +'<td>'+fmtV(b.gd,'v-gbg')+'</td>'
      +'<td><span class="sb">'+b.s+'='+b.t+'t</span></td>'
      +'<td><span class="evt-tag">'+(b.evt||'\u2014')+'</span></td>'
      +'</tr>';
  }).join('');
}

function colSort(col) {
  if (sortCol === col) sortAsc = !sortAsc;
  else { sortCol = col; sortAsc = false; }
  document.getElementById('sort-by').value = col;
  document.querySelectorAll('th').forEach(th => th.classList.remove('sorted'));
  render();
}

render();
</script>
</body>
</html>
""")


def build_html(rows: list, highest_era_idx: int, sources: list, build_date: str) -> str:
    # Eras present in data
    present_idxs = set()
    for b in rows:
        for era_row in b["e"]:
            present_idxs.add(era_row[0])
    present_eras = [ERA_ORDER[i] for i in sorted(present_idxs)]

    era_options = []
    for era in present_eras:
        idx = ERA_RANK[era]
        sel = " selected" if idx == highest_era_idx else ""
        era_options.append(f'      <option value="{idx}"{sel}>{ERA_LABELS[era]}</option>')

    all_evts = sorted({b["evt"] for b in rows if b["evt"]})
    event_options = [f'    <option value="{e}">{e}</option>' for e in all_evts]

    best_json       = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    era_order_json  = json.dumps(ERA_ORDER, separators=(",", ":"))
    era_labels_json = json.dumps(ERA_LABELS, separators=(",", ":"))

    html = HTML_TEMPLATE
    html = html.replace("%%BUILDING_COUNT%%", str(len(rows)))
    html = html.replace("%%ERA_COUNT%%",      str(len(present_eras)))
    html = html.replace("%%BUILD_DATE%%",     build_date)
    html = html.replace("%%DATA_SOURCES%%",   " + ".join(sources))
    html = html.replace("%%ERA_OPTIONS%%",    "\n".join(era_options))
    html = html.replace("%%EVENT_OPTIONS%%",  "\n".join(event_options))
    html = html.replace("%%ERA_ORDER_JSON%%", era_order_json)
    html = html.replace("%%ERA_LABELS_JSON%%",era_labels_json)
    html = html.replace("%%BEST_JSON%%",      best_json)
    return html


def main():
    if len(sys.argv) > 1:
        zip_paths = [Path(p) for p in sys.argv[1:]]
    else:
        exports_dir = Path(__file__).parent / "exports"
        zip_paths   = sorted(exports_dir.glob("*.zip"))

    if not zip_paths:
        print("ERROR: No zip files found.")
        print("  Put MegaExport zips in the exports/ folder, or pass paths as arguments.")
        sys.exit(1)

    print(f"\nFoE Best Buildings Builder")
    print(f"{'─'*40}")
    print(f"Processing {len(zip_paths)} export(s):\n")

    rows, highest_era_idx = build_best_list(zip_paths)

    sources = []
    for zp in zip_paths:
        m = re.match(r"([A-Z]+)_foe_helper", zp.name)
        sources.append(m.group(1) if m else zp.stem)

    now = datetime.now(timezone.utc)
    build_date = f"{now.day} {now.strftime('%b %Y')}"
    html = build_html(rows, highest_era_idx, sources, build_date)

    out_path = Path(__file__).parent / "index.html"
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"\n  Written : {out_path}")
    print(f"  Size    : {size_kb:.1f} KB")
    print(f"  Buildings : {len(rows)}")
    print(f"  Default era : {ERA_LABELS[ERA_ORDER[highest_era_idx]]}")
    print()


if __name__ == "__main__":
    main()
