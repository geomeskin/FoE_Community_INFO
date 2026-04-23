#!/usr/bin/env python3
"""
FoE Community INFO — Page Builder
===================================
Drop any number of FoE Helper MegaExport zip files into the exports/ folder,
then run:

    python build.py

Or pass zip paths explicitly:
    python build.py path/to/CITY1.zip path/to/CITY2.zip

Optionally place Wyldfyre_BattleBoosts_*.csv next to build.py to populate
the Battle Boost Reference tab.

Outputs a single index.html with four tabs:
  Tab 1 — Boost Reference        (community building data, all zips merged)
  Tab 2 — Battle Boost Reference (Wyldfyre's curated CSV)
  Tab 3 — GB Planner             (per-player GB levels from each zip)
  Tab 4 — Fragment Tracker       (per-player fragment progress from each zip)
"""

import csv
import json
import math
import re
import sys
import zipfile
from datetime import datetime, timedelta, timezone
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
    "HIS":  "History Event",
    "CUP":  "Soccer/Cup Event",
    "GBG":  "Guild Battlegrounds",
    "BOWL": "Football/Bowl Event",
    "ARCH": "Architecture Event",
    "HERO": "Hero Event",
    "GEX":  "Guild Expedition",
    "LTE":  "Age Bonus",
    "SPR":  "Spring Event",
}

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


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Boost Reference
# ═══════════════════════════════════════════════════════════════════════════════

def calc_boosts(components, era):
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


def get_event(bid):
    m = re.match(r"W_MultiAge_([A-Z]+)(\d{2})", bid)
    if not m:
        return None
    code, yr = m.group(1), int(m.group(2))
    name = EVENT_MAP.get(code)
    return f"{name} 20{yr:02d}" if name else None


def extract_from_zip(zip_path):
    buildings = {}
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
                    "name": j["name"], "w": w, "h": h,
                    "evt": evt, "e": era_rows,
                }
    return buildings, highest_era_idx


def build_best_list(zip_paths):
    all_buildings = {}
    global_highest = 0
    for zp in zip_paths:
        print(f"  [Tab1] Reading {zp.name} ...")
        bldgs, hi = extract_from_zip(zp)
        print(f"         -> {len(bldgs):,} boost buildings found")
        all_buildings.update(bldgs)
        if hi > global_highest:
            global_highest = hi
    print(f"  [Tab1] Total unique buildings : {len(all_buildings):,}")
    rows = []
    for bid, b in all_buildings.items():
        rows.append({
            "n": b["name"], "id": bid,
            "s": f"{b['w']}\u00d7{b['h']}",
            "t": b["w"] * b["h"],
            "evt": b["evt"], "e": b["e"],
        })
    return rows, global_highest


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Battle Boost Reference
# ═══════════════════════════════════════════════════════════════════════════════

_BB_COL_MAP = {
    "AAA": "aaa", "DAA": "daa", "ADA": "ada", "DDA": "dda",
    "GE \u2013 AAA": "ge_aaa", "GE - AAA": "ge_aaa",
    "GE \u2013 DAA": "ge_daa", "GE - DAA": "ge_daa",
    "GE \u2013 ADA": "ge_ada", "GE - ADA": "ge_ada",
    "GE- DDA": "ge_dda", "GE \u2013 DDA": "ge_dda", "GE - DDA": "ge_dda",
    " GBG \u2013 AAA": "gbg_aaa", "GBG \u2013 AAA": "gbg_aaa", "GBG - AAA": "gbg_aaa",
    "GBG - DAA": "gbg_daa", "GBG \u2013 DAA": "gbg_daa",
    "GBG \u2013 ADA": "gbg_ada", "GBG - ADA": "gbg_ada",
    "GBG \u2013 DDA": "gbg_dda", "GBG - DDA": "gbg_dda",
    "QI \u2013 AAA": "qi_aaa", "QI - AAA": "qi_aaa",
    "QI - DAA ": "qi_daa", "QI - DAA": "qi_daa", "QI \u2013 DAA": "qi_daa",
    "QI \u2013 ADA": "qi_ada", "QI - ADA": "qi_ada",
    "QI - DDA": "qi_dda", "QI \u2013 DDA": "qi_dda",
    "GBG Shop Red Coins":  "gbg_red",
    "GBG Shop Blue Coins": "gbg_blue",
}

_BB_INT_KEYS = [
    "aaa", "daa", "ada", "dda",
    "ge_aaa", "ge_daa", "ge_ada", "ge_dda",
    "gbg_aaa", "gbg_daa", "gbg_ada", "gbg_dda",
    "qi_aaa", "qi_daa", "qi_ada", "qi_dda",
    "gbg_red", "gbg_blue", "tiles",
]


def _safe_int(v):
    try:
        return int(str(v).strip().replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return 0


def load_battle_boosts(csv_path):
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rec = {}
            for col, val in raw.items():
                canon = _BB_COL_MAP.get(col.strip())
                if canon:
                    rec[canon] = val.strip()
            rec["name"]  = raw.get("Bldg", "").strip()
            rec["tiles"] = raw.get("Tiles", "0").strip()
            rec["shop"]  = raw.get("Shop", "").strip()
            for k in _BB_INT_KEYS:
                rec[k] = _safe_int(rec.get(k, 0))
            rec["tot_open"] = rec["aaa"] + rec["daa"] + rec["ada"] + rec["dda"]
            rec["tot_ge"]   = rec["ge_aaa"] + rec["ge_daa"] + rec["ge_ada"] + rec["ge_dda"]
            rec["tot_gbg"]  = rec["gbg_aaa"] + rec["gbg_daa"] + rec["gbg_ada"] + rec["gbg_dda"]
            rec["tot_qi"]   = rec["qi_aaa"] + rec["qi_daa"] + rec["qi_ada"] + rec["qi_dda"]
            rec["tot_all"]  = rec["tot_open"] + rec["tot_ge"] + rec["tot_gbg"] + rec["tot_qi"]
            rec["pt"] = round(rec["tot_open"] / rec["tiles"], 2) if rec["tiles"] else 0
            if rec["name"]:
                rows.append(rec)
    print(f"  [Tab2] Loaded {len(rows)} battle boost buildings from CSV")
    return rows


def find_battle_boost_csv(script_dir):
    candidates = (
        sorted(script_dir.glob("*BattleBoost*.csv")) +
        sorted(script_dir.glob("*battle_boost*.csv")) +
        sorted(script_dir.glob("*battleboost*.csv"))
    )
    return candidates[0] if candidates else None


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — GB Planner
# ═══════════════════════════════════════════════════════════════════════════════

def extract_gb_data(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        # Get current_player_id from localStorage first
        current_player_id = None
        ls_files = [f for f in zf.namelist() if "localStorage" in f and f.endswith(".json")]
        if ls_files:
            try:
                ls = json.loads(zf.read(ls_files[0]))
                pid = ls.get("current_player_id")
                if pid:
                    current_player_id = int(pid)
            except Exception:
                pass

        gms_files = [f for f in zf.namelist()
                     if "GuildMemberStat" in f and f.endswith(".json")]
        if not gms_files:
            return None
        try:
            data = json.loads(zf.read(gms_files[0]))
        except Exception:
            return None

    tables = data.get("data", {}).get("data", [])
    player_table = next(
        (t for t in tables if t.get("tableName") == "player"), None
    )
    if not player_table or not player_table.get("rows"):
        return None

    best_player = None
    best_gb_count = -1
    for p in player_table["rows"]:
        gbs_raw = p.get("greatbuildings", [])
        if isinstance(gbs_raw, str):
            try:
                gbs_raw = json.loads(gbs_raw)
            except Exception:
                gbs_raw = []
        p["_gbs_parsed"] = gbs_raw

        # Prefer player matching current_player_id from localStorage
        if current_player_id and p.get("player_id") == current_player_id:
            best_player = p
            break

        # Fallback: player with most GBs
        if len(gbs_raw) > best_gb_count:
            best_gb_count = len(gbs_raw)
            best_player = p

    if not best_player:
        return None

    gbs_parsed = best_player.get("_gbs_parsed", [])
    gb_rows = []
    for gb in gbs_parsed:
        fp_needed = gb.get("forge_points_for_level_up")
        gb_rows.append({
            "name":     gb.get("name", "Unknown"),
            "level":    gb.get("level", 0),
            "max_level":gb.get("max_level", 0),
            "fp":       fp_needed if fp_needed is not None else 0,
            "at_max":   gb.get("level", 0) >= gb.get("max_level", 1),
        })

    gb_rows.sort(key=lambda x: (x["at_max"], -x["level"]))

    return {
        "player": best_player.get("name", "Unknown"),
        "era":    ERA_LABELS.get(
                    best_player.get("era", ""),
                    best_player.get("era", "")
                  ),
        "gbs":    gb_rows,
    }


def build_gb_data(zip_paths):
    players = []
    for zp in zip_paths:
        result = extract_gb_data(zp)
        if result:
            m = re.match(r"([A-Z]+)_foe_helper", zp.name)
            result["tag"] = m.group(1) if m else zp.stem
            players.append(result)
            print(f"  [Tab3] {result['tag']}: {result['player']} "
                  f"({result['era']}) — {len(result['gbs'])} GBs")
        else:
            print(f"  [Tab3] {zp.name}: no GB data found")
    return players


def build_gb_sections(players):
    if not players:
        return '<p class="no-data" style="padding:20px">No GB data found in exports.</p>'

    sections = []
    for p in players:
        rows_html = []
        for gb in p["gbs"]:
            lv  = gb["level"]
            mx  = gb["max_level"]
            pct = round(lv / mx * 100) if mx else 0
            fp  = gb["fp"]
            at_max = gb["at_max"]
            bar_color = "var(--text3)" if at_max else "var(--blue)"
            bar = (
                f'<div class="fp-bar-wrap">'
                f'<div class="fp-bar" style="width:{pct}%;background:{bar_color}"></div>'
                f'</div>'
            )
            fp_cell = (
                '<span class="at-max">max</span>' if at_max
                else f'<span class="v v-gold">{fp:,}</span>'
            )
            rows_html.append(
                f'<tr>'
                f'<td class="bn">{gb["name"]}</td>'
                f'<td><span class="v">{lv}</span></td>'
                f'<td><span class="v">{mx}</span></td>'
                f'<td>{bar} <span class="sb">{pct}%</span></td>'
                f'<td>{fp_cell}</td>'
                f'</tr>'
            )

        sections.append(
            f'<div class="player-section">'
            f'<div class="player-header">'
            f'  <span class="player-tag">{p["tag"]}</span>'
            f'  <span class="player-name">{p["player"]}</span>'
            f'  <span class="player-era">{p["era"]}</span>'
            f'  <span class="sb" style="margin-left:auto">{len(p["gbs"])} GBs</span>'
            f'</div>'
            f'<div class="table-wrap" style="border-radius:0 0 8px 8px">'
            f'<table>'
            f'<thead><tr>'
            f'<th>GREAT BUILDING</th><th>LV</th><th>MAX</th>'
            f'<th>PROGRESS</th><th>FP TO NEXT LV</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(rows_html)}</tbody>'
            f'</table></div></div>'
        )

    return "\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Fragment Tracker
# ═══════════════════════════════════════════════════════════════════════════════

def extract_fragment_data(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        db_files = [
            f for f in zf.namelist()
            if "FoeHelperDB_" in f and f.endswith(".json")
            and not any(x in f for x in [
                "Events", "FPCollector", "GexStat",
                "GuildFights", "GuildMember", "Qi",
            ])
        ]
        if not db_files:
            return None

        # Get current_player_id from localStorage
        current_player_id = None
        ls_files = [f for f in zf.namelist() if "localStorage" in f and f.endswith(".json")]
        if ls_files:
            try:
                ls = json.loads(zf.read(ls_files[0]))
                pid = ls.get("current_player_id")
                if pid:
                    current_player_id = int(pid)
            except Exception:
                pass

        # Pick the DB matching current_player_id, fallback to most statsRewards rows
        best_file = None
        best_count = -1
        for fname in db_files:
            try:
                data = json.loads(zf.read(fname))
            except Exception:
                continue
            # Check if this DB belongs to the current player
            if current_player_id and str(current_player_id) in fname:
                best_file = fname
                break
            tables = data.get("data", {}).get("data", [])
            sr = next((t for t in tables if t.get("tableName") == "statsRewards"), None)
            count = len(sr["rows"]) if sr else 0
            if count > best_count:
                best_count = count
                best_file = fname

        if not best_file:
            return None

        try:
            data = json.loads(zf.read(best_file))
        except Exception:
            return None

    tables = data.get("data", {}).get("data", [])
    rows_by_table = {t["tableName"]: t["rows"] for t in tables}
    rewards      = rows_by_table.get("statsRewards", [])
    reward_types = rows_by_table.get("statsRewardTypes", [])

    # Build fragment metadata: item_id -> {name, req, type}
    frag_meta = {}
    for rt in reward_types:
        if rt.get("subType") != "fragment":
            continue
        assembled = rt.get("assembledReward", {})
        if not isinstance(assembled, dict):
            continue
        item_id = assembled.get("id", "")
        if not item_id:
            continue
        req  = rt.get("requiredAmount", 0)
        name = assembled.get("name", item_id)
        if item_id not in frag_meta or req > 0:
            frag_meta[item_id] = {
                "name": name,
                "req":  req,
                "type": assembled.get("type", ""),
            }

    # Tally received and assembled; also track daily rate per item.
    # Exclude item_store (manual purchases) from rate — they skew the passive rate.
    EXCLUDE_FROM_RATE = {"item_store"}

    frags_in = {}
    assembled_count = {}
    frags_for_rate = {}  # item_id -> total frags from passive sources
    sources_by_item = {}  # item_id -> {type -> total frags}
    for r in rewards:
        rwd = r.get("reward", "")
        amt = r.get("amount", 0)
        rtype = r.get("type", "unknown")
        if rwd.startswith("fragment#"):
            parts = rwd.split("#")
            if len(parts) >= 2:
                item_id = parts[1]
                frags_in[item_id] = frags_in.get(item_id, 0) + amt
                if rtype not in EXCLUDE_FROM_RATE:
                    frags_for_rate[item_id] = frags_for_rate.get(item_id, 0) + amt
                if item_id not in sources_by_item:
                    sources_by_item[item_id] = {}
                sources_by_item[item_id][rtype] = sources_by_item[item_id].get(rtype, 0) + amt
        elif rtype == "inventory_item" and rwd:
            assembled_count[rwd] = assembled_count.get(rwd, 0) + amt

    # Compute span of statsRewards data (in days) for rate calculation
    dates = [r["date"] for r in rewards if r.get("date")]
    span_days = 0.0
    if len(dates) >= 2:
        span_days = (max(dates) - min(dates)) / (1000 * 86400)

    fpd_by_item = {}
    if span_days > 0:
        for item_id, total in frags_for_rate.items():
            fpd_by_item[item_id] = round(total / span_days, 2)

    today = datetime.now(timezone.utc)

    # Build rows
    frag_rows = []
    for item_id in set(frags_in) | set(assembled_count):
        meta = frag_meta.get(item_id)
        if not meta or not meta["req"]:
            continue
        total_in  = frags_in.get(item_id, 0)
        kits_made = assembled_count.get(item_id, 0)
        spent     = kits_made * meta["req"]
        # Negative balance means statsRewards history predates some assemblies.
        # Clamp to 0 — treat as "starting fresh" rather than showing nonsense negatives.
        balance   = max(total_in - spent, 0)
        req       = meta["req"]
        pct       = round(balance / req * 100, 1) if req else 0

        fpd  = fpd_by_item.get(item_id, 0.0)
        days = None
        est  = None
        if fpd > 0 and balance < req:
            days = math.ceil((req - balance) / fpd)
            est  = (today + timedelta(days=days)).strftime("%Y-%m-%d")

        frag_rows.append({
            "name":        meta["name"],
            "item_id":     item_id,
            "have":        balance,
            "need":        req,
            "pct":         pct,
            "assembled":   kits_made,
            "in_progress": balance < req and (balance > 0 or fpd > 0),
            "complete":    balance >= req,
            "fpd":         fpd,
            "days":        days,
            "est":         est,
        })

    # Sort: in-progress (pct desc), complete, zero
    frag_rows.sort(key=lambda x: (
        0 if x["in_progress"] else (1 if x["complete"] else 2),
        -x["pct"]
    ))

    m = re.match(r"([A-Z]+)_foe_helper", zip_path.name)
    tag = m.group(1) if m else zip_path.stem

    in_prog = sum(1 for r in frag_rows if r["in_progress"])
    print(f"  [Tab4] {tag}: {len(frag_rows)} items tracked ({in_prog} in progress)")

    return {"tag": tag, "fragments": frag_rows}


def build_fragment_data(zip_paths):
    players = []
    for zp in zip_paths:
        result = extract_fragment_data(zp)
        if result:
            players.append(result)
        else:
            print(f"  [Tab4] {zp.name}: no fragment data found")
    return players

def build_friend_data(zip_paths):
    players = []
    for zp in zip_paths:
        result = extract_friend_data(zp)
        if result:
            players.append(result)
        else:
            print(f"  [Tab5] {zp.name}: no friend data found")
    return players


INACTIVE_DAYS = 14  # Flag friends who have not aided in this many days


def extract_friend_data(zip_path):
    with zipfile.ZipFile(zip_path) as zf:
        ev_files = [f for f in zf.namelist()
                    if "FoeHelperDB_Events_" in f and f.endswith(".json")]
        if not ev_files:
            return None
        try:
            data = json.loads(zf.read(ev_files[0]))
        except Exception:
            return None

    tables = {t["tableName"]: t["rows"]
              for t in data.get("data", {}).get("data", [])}
    events = tables.get("Events", [])
    if not events:
        return None

    friends = {}  # playerid -> {name, friend_since, last_aided}

    for e in events:
        pid   = e.get("playerid")
        pname = e.get("playername", "Unknown")
        date  = e.get("date", 0)
        etype = e.get("eventtype", "")
        if not pid or not e.get("isfriend"):
            continue

        if pid not in friends:
            friends[pid] = {"name": pname, "friend_since": None, "last_aided": None}

        friends[pid]["name"] = pname

        if etype == "friend_accepted":
            fs = friends[pid]["friend_since"]
            if fs is None or date < fs:
                friends[pid]["friend_since"] = date

        elif etype == "social_interaction":
            la = friends[pid]["last_aided"]
            if la is None or date > la:
                friends[pid]["last_aided"] = date

    if not friends:
        return None

    today_ms    = datetime.now(timezone.utc).timestamp() * 1000
    inactive_ms = INACTIVE_DAYS * 86400 * 1000

    friend_rows = []
    for pid, f in friends.items():
        last_aided_ms   = f["last_aided"]
        friend_since_ms = f["friend_since"]

        if last_aided_ms:
            days_since     = int((today_ms - last_aided_ms) / (86400 * 1000))
            last_aided_str = datetime.fromtimestamp(
                last_aided_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            days_since     = None
            last_aided_str = None

        if friend_since_ms:
            friend_since_str = datetime.fromtimestamp(
                friend_since_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
            is_new = (today_ms - friend_since_ms) < inactive_ms
        else:
            friend_since_str = None
            is_new = False  # unknown age - don't suppress flag

        if is_new:
            status = "new"
        elif last_aided_ms is None or (today_ms - last_aided_ms) > inactive_ms:
            status = "inactive"
        else:
            status = "active"

        friend_rows.append({
            "name":         f["name"],
            "player_id":    pid,
            "friend_since": friend_since_str,
            "last_aided":   last_aided_str,
            "days_since":   days_since,
            "status":       status,
        })

    STATUS_ORDER = {"inactive": 0, "new": 1, "active": 2}
    friend_rows.sort(key=lambda x: (
        STATUS_ORDER[x["status"]],
        -(x["days_since"] if x["days_since"] is not None else 9999)
    ))

    m = re.match(r"([A-Z]+)_foe_helper", zip_path.name)
    tag = m.group(1) if m else zip_path.stem

    inactive = sum(1 for r in friend_rows if r["status"] == "inactive")
    print(f"  [Tab5] {tag}: {len(friend_rows)} friends "
          f"({inactive} inactive, threshold={INACTIVE_DAYS}d)")

    return {"tag": tag, "friends": friend_rows, "inactive_days": INACTIVE_DAYS}



# ═══════════════════════════════════════════════════════════════════════════════
# HTML Template
# ═══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FoE Community INFO</title>
<link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&family=Exo+2:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#080c14;--bg2:#0d1220;--bg3:#111827;--panel:#0f1825;
  --border:#1e2d45;--border2:#263650;
  --gold:#f0b429;--blue:#3b82f6;--blue2:#7dd3fc;
  --teal:#14b8a6;--green:#22c55e;--red:#ef4444;--orange:#f97316;
  --purple:#a855f7;
  --text:#e2e8f0;--text2:#b8c4d4;--text3:#6b7e99;
}
*{margin:0;padding:0;box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Exo 2',sans-serif;font-size:14px;
  background-image:radial-gradient(ellipse at 10% 0%,rgba(59,130,246,.08) 0%,transparent 40%),
  radial-gradient(ellipse at 90% 100%,rgba(20,184,166,.06) 0%,transparent 40%);}
.app{max-width:1400px;margin:0 auto;padding:24px 20px 60px;}
.header{text-align:center;padding:32px 0 24px;border-bottom:1px solid var(--border);margin-bottom:0;}
.header h1{font-family:'Rajdhani',sans-serif;font-size:2rem;font-weight:700;letter-spacing:.06em;
  color:var(--gold);text-transform:uppercase;margin-bottom:6px;}
.header p{color:var(--text2);font-size:.85rem;max-width:680px;margin:0 auto 14px;line-height:1.6;}
.badges{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;}
.badge{background:var(--bg3);border:1px solid var(--border2);border-radius:6px;padding:4px 12px;
  font-family:'Share Tech Mono',monospace;font-size:.74rem;}
.badge.gold{color:var(--gold);border-color:rgba(240,180,41,.3);}
.badge.teal{color:var(--teal);border-color:rgba(20,184,166,.3);}
.badge.green{color:var(--green);border-color:rgba(34,197,94,.3);}
.badge.blue{color:var(--blue2);border-color:rgba(125,211,252,.3);}
.tabs{display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:20px;overflow-x:auto;}
.tab-btn{background:none;border:none;padding:14px 24px;font-family:'Exo 2',sans-serif;
  font-size:.88rem;font-weight:500;color:var(--text3);cursor:pointer;white-space:nowrap;
  border-bottom:2px solid transparent;margin-bottom:-2px;transition:color .15s,border-color .15s;}
.tab-btn:hover{color:var(--text2);}
.tab-btn.active{color:var(--gold);border-bottom-color:var(--gold);}
.tab-panel{display:none;}
.tab-panel.active{display:block;}
.info-box{background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--teal);
  border-radius:8px;padding:12px 16px;margin-bottom:16px;font-size:.83rem;line-height:1.7;color:var(--text2);}
.info-box strong{color:var(--text);}
.toolbar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center;}
.search-box{flex:1;min-width:160px;background:var(--bg2);border:1px solid var(--border2);
  border-radius:6px;padding:7px 12px;color:var(--text);font-family:'Exo 2',sans-serif;
  font-size:.83rem;outline:none;}
.search-box:focus{border-color:var(--blue);}
.ddl{background:var(--bg2);border:1px solid var(--border2);border-radius:6px;padding:7px 10px;
  color:var(--text);font-family:'Exo 2',sans-serif;font-size:.81rem;outline:none;cursor:pointer;}
.ddl:focus{border-color:var(--blue);}
.ddl.era-sel{border-color:rgba(240,180,41,.4);color:var(--gold);font-weight:600;}
.era-wrap{display:flex;align-items:center;gap:6px;}
.era-label{font-family:'Share Tech Mono',monospace;font-size:.7rem;color:var(--text3);white-space:nowrap;}
.count-label{font-family:'Share Tech Mono',monospace;font-size:.71rem;color:var(--text3);white-space:nowrap;}
.table-wrap{background:var(--panel);border:1px solid var(--border);border-radius:8px;overflow:auto;max-height:600px;}
table{width:100%;border-collapse:collapse;}
th{background:var(--bg3);position:sticky;top:0;z-index:2;font-family:'Share Tech Mono',monospace;
  font-size:.66rem;letter-spacing:.08em;color:var(--text3);padding:9px 12px;text-align:left;
  border-bottom:1px solid var(--border);white-space:nowrap;cursor:pointer;user-select:none;}
th:hover{color:var(--text2);}
th.sorted{color:var(--gold);}
td{padding:7px 12px;border-bottom:1px solid rgba(30,45,69,.4);font-size:.81rem;white-space:nowrap;}
tr:last-child td{border-bottom:none;}
tr:hover td{background:rgba(59,130,246,.04);}
.bn{color:var(--text);max-width:240px;overflow:hidden;text-overflow:ellipsis;font-weight:500;}
.sb{display:inline-block;font-size:.66rem;font-family:'Share Tech Mono',monospace;color:var(--text3);margin-left:4px;}
.v{font-family:'Share Tech Mono',monospace;}
.v-gold{color:var(--gold);font-weight:600;}
.v-att{color:var(--red);}
.v-def{color:var(--blue2);}
.v-gbg{color:var(--teal);}
.v-qi{color:var(--purple);}
.v-green{color:var(--green);}
.zero{color:var(--text3);}
.rank{font-family:'Share Tech Mono',monospace;color:var(--text3);font-size:.73rem;width:32px;text-align:right;}
.rank-1{color:var(--gold);font-weight:700;}
.rank-2{color:#94a3b8;font-weight:600;}
.rank-3{color:#cd7c3a;font-weight:600;}
.evt-tag{display:inline-block;font-size:.66rem;font-family:'Share Tech Mono',monospace;
  color:var(--text2);background:var(--bg3);border:1px solid var(--border);border-radius:3px;
  padding:1px 5px;max-width:180px;overflow:hidden;text-overflow:ellipsis;}
.no-data{color:var(--text3);font-style:italic;font-size:.78rem;}
.shop-tag{display:inline-block;font-size:.65rem;font-family:'Share Tech Mono',monospace;
  border-radius:3px;padding:1px 6px;border:1px solid;}
.shop-Event{color:var(--gold);border-color:rgba(240,180,41,.3);background:rgba(240,180,41,.05);}
.shop-GBG{color:var(--teal);border-color:rgba(20,184,166,.3);background:rgba(20,184,166,.05);}
.shop-QI{color:var(--purple);border-color:rgba(168,85,247,.3);background:rgba(168,85,247,.05);}
.shop-Settlement{color:var(--blue2);border-color:rgba(125,211,252,.3);background:rgba(125,211,252,.05);}
.prog-wrap{display:inline-block;width:110px;background:var(--bg3);border-radius:4px;height:8px;
  border:1px solid var(--border);vertical-align:middle;}
.prog-bar{height:100%;border-radius:3px;background:var(--teal);}
.prog-bar.complete{background:var(--green);}
.prog-bar.low{background:var(--text3);}
.pct-label{font-family:'Share Tech Mono',monospace;font-size:.72rem;margin-left:6px;}
.player-section{margin-bottom:28px;}
.player-header{background:var(--bg3);border:1px solid var(--border);border-radius:8px 8px 0 0;
  padding:10px 16px;display:flex;align-items:center;gap:12px;}
.player-name{font-family:'Rajdhani',sans-serif;font-size:1.1rem;font-weight:700;color:var(--gold);}
.player-era{font-family:'Share Tech Mono',monospace;font-size:.72rem;color:var(--teal);}
.player-tag{font-family:'Share Tech Mono',monospace;font-size:.68rem;color:var(--text3);
  background:var(--bg2);border:1px solid var(--border);border-radius:3px;padding:1px 6px;}
.fp-bar-wrap{display:inline-block;width:90px;background:var(--bg3);border-radius:4px;height:6px;
  border:1px solid var(--border);vertical-align:middle;}
.fp-bar{height:100%;border-radius:3px;background:var(--blue);}
.at-max{color:var(--text3);font-style:italic;font-size:.78rem;}
.player-pills{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;}
.pill{background:var(--bg3);border:1px solid var(--border2);border-radius:20px;
  padding:4px 14px;font-family:'Share Tech Mono',monospace;font-size:.73rem;
  color:var(--text3);cursor:pointer;transition:all .15s;}
.pill:hover{color:var(--text);}
.pill.active{background:rgba(240,180,41,.1);border-color:rgba(240,180,41,.4);color:var(--gold);}
.footer{text-align:center;padding-top:36px;color:var(--text3);font-size:.78rem;
  border-top:1px solid var(--border);margin-top:40px;}
.footer a{color:var(--teal);text-decoration:none;}
</style>
</head>
<body>
<div class="app">

<div class="header">
  <h1>&#9876; FoE Community INFO</h1>
  <p>Community reference tool for Forge of Empires — building boosts, battle reference, GB planning, and fragment tracking.</p>
  <div class="badges">
    <span class="badge gold">%%BUILDING_COUNT%% Buildings</span>
    <span class="badge teal">%%ERA_COUNT%% Eras</span>
    <span class="badge green">Updated %%BUILD_DATE%%</span>
    <span class="badge blue">%%DATA_SOURCES%%</span>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('t1',this)">&#9876; Boost Reference</button>
  <button class="tab-btn" onclick="switchTab('t2',this)">&#9876; Battle Boosts</button>
  <button class="tab-btn" onclick="switchTab('t3',this)">&#127963; GB Planner</button>
  <button class="tab-btn" onclick="switchTab('t4',this)">&#129512; Fragment Tracker</button>
  <button class="tab-btn" onclick="switchTab('t5',this)">&#128101; Friend Manager</button>
</div>

<!-- TAB 1 ─────────────────────────────────────────────────────────────────── -->
<div id="t1" class="tab-panel active">
<div class="info-box">
  <strong>How to use:</strong> Pick your era — all boost values update instantly.
  <strong>Att%</strong> = attacker attack &nbsp;|&nbsp; <strong>Def%</strong> = attacker defense &nbsp;|&nbsp;
  <strong>GbG Att/Def%</strong> = Guild Battlegrounds bonuses &nbsp;|&nbsp;
  <strong>Total</strong> = sum of all four &nbsp;|&nbsp; <strong>Pt</strong> = total per tile.
</div>
<div class="toolbar">
  <input class="search-box" id="t1-search" placeholder="Search building name\u2026" oninput="t1Render()">
  <div class="era-wrap">
    <span class="era-label">ERA:</span>
    <select class="ddl era-sel" id="t1-era" onchange="t1Render()">
%%ERA_OPTIONS%%
    </select>
  </div>
  <select class="ddl" id="t1-ftype" onchange="t1Render()">
    <option value="">All types</option>
    <option value="event">Event buildings</option>
    <option value="gbg">GbG boost only</option>
    <option value="ge">Guild Expedition</option>
  </select>
  <select class="ddl" id="t1-fevt" onchange="t1Render()">
    <option value="">All events</option>
%%EVENT_OPTIONS%%
  </select>
  <select class="ddl" id="t1-sort" onchange="t1Render()">
    <option value="tot">Sort: Total</option>
    <option value="pt">Sort: Per Tile</option>
    <option value="a">Sort: Att%</option>
    <option value="d">Sort: Def%</option>
    <option value="ga">Sort: GbG Att%</option>
    <option value="gd">Sort: GbG Def%</option>
    <option value="n">Sort: Name</option>
    <option value="evt">Sort: Event</option>
  </select>
  <span class="count-label" id="t1-count"></span>
</div>
<div class="table-wrap"><table>
<thead><tr>
  <th onclick="t1ColSort('rank')">#</th>
  <th onclick="t1ColSort('n')">BUILDING</th>
  <th onclick="t1ColSort('tot')">TOTAL \u25be</th>
  <th onclick="t1ColSort('pt')">PT</th>
  <th onclick="t1ColSort('a')">ATT%</th>
  <th onclick="t1ColSort('d')">DEF%</th>
  <th onclick="t1ColSort('ga')">GBG ATT%</th>
  <th onclick="t1ColSort('gd')">GBG DEF%</th>
  <th>SIZE</th>
  <th onclick="t1ColSort('evt')">EVENT</th>
</tr></thead>
<tbody id="t1-tbody"></tbody>
</table></div>
</div>

<!-- TAB 2 ─────────────────────────────────────────────────────────────────── -->
<div id="t2" class="tab-panel">
<div class="info-box">
  <strong>Battle Boost Reference</strong> curated by Wyldfyre (guild rank #2).
  Four contexts: <strong style="color:var(--red)">Open World</strong> &nbsp;|&nbsp;
  <strong style="color:var(--teal)">GEx</strong> &nbsp;|&nbsp;
  <strong style="color:var(--blue2)">GBG</strong> &nbsp;|&nbsp;
  <strong style="color:var(--purple)">QI</strong>.
  &nbsp; AAA = Att for Attacking Army &nbsp;| DAA = Def for Attacking Army &nbsp;|
  ADA = Att for Defending Army &nbsp;| DDA = Def for Defending Army.
</div>
<div class="toolbar">
  <input class="search-box" id="t2-search" placeholder="Search building\u2026" oninput="t2Render()">
  <select class="ddl" id="t2-shop" onchange="t2Render()">
    <option value="">All sources</option>
    <option value="Event">Event</option>
    <option value="GBG">GBG</option>
    <option value="QI">QI</option>
    <option value="Settlement">Settlement</option>
  </select>
  <select class="ddl" id="t2-ctx" onchange="t2Render()">
    <option value="open">Open World</option>
    <option value="ge">Guild Expedition</option>
    <option value="gbg">GBG</option>
    <option value="qi">QI</option>
  </select>
  <select class="ddl" id="t2-sort" onchange="t2Render()">
    <option value="tot">Sort: Total</option>
    <option value="aaa">Sort: AAA</option>
    <option value="daa">Sort: DAA</option>
    <option value="ada">Sort: ADA</option>
    <option value="dda">Sort: DDA</option>
    <option value="pt">Sort: Per Tile</option>
    <option value="name">Sort: Name</option>
  </select>
  <span class="count-label" id="t2-count"></span>
</div>
<div class="table-wrap"><table>
<thead><tr>
  <th onclick="t2ColSort('rank')">#</th>
  <th onclick="t2ColSort('name')">BUILDING</th>
  <th onclick="t2ColSort('tot')">TOTAL \u25be</th>
  <th onclick="t2ColSort('pt')">PT</th>
  <th onclick="t2ColSort('aaa')">AAA</th>
  <th onclick="t2ColSort('daa')">DAA</th>
  <th onclick="t2ColSort('ada')">ADA</th>
  <th onclick="t2ColSort('dda')">DDA</th>
  <th>TILES</th>
  <th>SOURCE</th>
</tr></thead>
<tbody id="t2-tbody"></tbody>
</table></div>
</div>

<!-- TAB 3 ─────────────────────────────────────────────────────────────────── -->
<div id="t3" class="tab-panel">
<div class="info-box">
  <strong>GB Planner</strong> \u2014 Great Building levels from each player's MegaExport.
  FP shown is the cost to reach the <em>next</em> level.
  Progress bar = level / max level. GBs at max are shown at bottom.
</div>
<div id="t3-content">
%%GB_SECTIONS%%
</div>
</div>

<!-- TAB 4 ─────────────────────────────────────────────────────────────────── -->
<div id="t4" class="tab-panel">
<div class="info-box">
  <strong>Fragment Tracker</strong> \u2014 balance = received \u2212 assembled \xd7 required.
  <strong>Frags/Day</strong> = historical fragment accumulation rate from GEx, quests &amp; events (excludes shop purchases). Divide Need by this to estimate days remaining.
  <strong>Est. Days</strong> and <strong>Est. Date</strong> are based on that rate.
  In-progress items shown first.
</div>
<div class="info-box" style="border-left-color:var(--orange);margin-top:8px;">
  <strong>\u26a0\ufe0f Known data limitations:</strong>
  Fragments purchased in the <strong>QI Shop</strong> are not recorded in the FoE Helper export and will not appear here.
  Likewise, <strong>QI Seasonal Kit</strong> fragment balances (e.g. QI Spring/Summer/Autumn Epic Selection Kits) are not captured.
  If your in-game inventory shows fragment counts that don\u2019t match this tracker, QI shop purchases are the likely cause.
</div>
<div class="player-pills" id="t4-pills"></div>
<div class="toolbar">
  <input class="search-box" id="t4-search" placeholder="Search fragment\u2026" oninput="t4Render()">
  <select class="ddl" id="t4-filter" onchange="t4Render()">
    <option value="">All items</option>
    <option value="progress">In progress only</option>
    <option value="done">Completed only</option>
  </select>
  <span class="count-label" id="t4-count"></span>
</div>
<div class="table-wrap"><table>
<thead><tr>
  <th onclick="t4ColSort('name')">ITEM</th>
  <th onclick="t4ColSort('pct')">PROGRESS \u25be</th>
  <th onclick="t4ColSort('have')">HAVE</th>
  <th onclick="t4ColSort('need')">NEED</th>
  <th onclick="t4ColSort('assembled')">ASSEMBLED</th>
  <th onclick="t4ColSort('fpd')">FRAGS/DAY</th>
  <th onclick="t4ColSort('days')">EST. DAYS</th>
  <th>EST. DATE</th>
</tr></thead>
<tbody id="t4-tbody"></tbody>
</table></div>
</div>

<!-- TAB 5 ────────────────────────────────────────────────────────────────────────────── -->
<div id="t5" class="tab-panel">
<div class="info-box">
  <strong>Friend Manager</strong> — shows all friends seen in your event history.
  <strong>Aided</strong> = any social interaction (motivate, polish, or polivate attempt).
  Friends flagged <span style="color:var(--red)">Inactive</span> have not aided in %%INACTIVE_DAYS%% days and are candidates to drop.
  Friends flagged <span style="color:var(--teal)">New</span> were added within the last %%INACTIVE_DAYS%% days — give them time.
  Friends with no recorded aid may predate your FoE Helper history.
</div>
<div class="player-pills" id="t5-pills"></div>
<div class="toolbar">
  <input class="search-box" id="t5-search" placeholder="Search friend…" oninput="t5Render()">
  <select class="ddl" id="t5-filter" onchange="t5Render()">
    <option value="">All friends</option>
    <option value="inactive">Inactive only</option>
    <option value="active">Active only</option>
    <option value="new">New only</option>
  </select>
  <span class="count-label" id="t5-count"></span>
</div>
<div class="table-wrap"><table>
<thead><tr>
  <th onclick="t5ColSort('name')">FRIEND</th>
  <th onclick="t5ColSort('friend_since')">FRIEND SINCE</th>
  <th onclick="t5ColSort('last_aided')">LAST AIDED</th>
  <th onclick="t5ColSort('days_since')">DAYS SINCE AID \u25be</th>
  <th>STATUS</th>
</tr></thead>
<tbody id="t5-tbody"></tbody>
</table></div>
</div>

<div class="footer">
  Data sourced from FoE Helper MegaExports \u2014 community reference only. Not affiliated with InnoGames.<br>
  Battle boost data curated by Wyldfyre. &mdash;
  <a href="https://github.com/nickolasnikola" target="_blank">GitHub</a>
</div>
</div>

<script>
// ── Tab switching ─────────────────────────────────────────────────────────────
function switchTab(id,btn){
  document.querySelectorAll('.tab-panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}

// ══════════════════════════════════════════════════════════════ TAB 1
const ERA_ORDER=%%ERA_ORDER_JSON%%;
const ERA_LABELS=%%ERA_LABELS_JSON%%;
const BEST=%%BEST_JSON%%;

function getBoosts(b,eraIdx){
  let best=null;
  for(const r of b.e){if(r[0]<=eraIdx)best=r;else break;}
  if(!best)return null;
  return{a:best[1],d:best[2],ga:best[3],gd:best[4]};
}
let t1SC='tot',t1SA=false;
function t1Render(){
  const srch=document.getElementById('t1-search').value.toLowerCase();
  const ei=parseInt(document.getElementById('t1-era').value);
  const ft=document.getElementById('t1-ftype').value;
  const fe=document.getElementById('t1-fevt').value;
  t1SC=document.getElementById('t1-sort').value;
  let rows=BEST.map(b=>{
    const bst=getBoosts(b,ei);
    const a=bst?bst.a:0,d=bst?bst.d:0,ga=bst?bst.ga:0,gd=bst?bst.gd:0,tot=a+d+ga+gd;
    return{...b,a,d,ga,gd,tot,pt:tot>0?+(tot/b.t).toFixed(1):0,hd:!!bst};
  });
  rows=rows.filter(b=>{
    if(srch&&!b.n.toLowerCase().includes(srch))return false;
    if(ft==='event'&&!b.evt)return false;
    if(ft==='gbg'&&b.ga===0&&b.gd===0)return false;
    if(ft==='ge'&&!(b.evt||'').includes('Guild Expedition'))return false;
    if(fe&&b.evt!==fe)return false;
    return true;
  });
  rows.sort((a,b)=>{
    if(t1SC==='n')return t1SA?a.n.localeCompare(b.n):b.n.localeCompare(a.n);
    if(t1SC==='evt')return t1SA?(a.evt||'').localeCompare(b.evt||''):(b.evt||'').localeCompare(a.evt||'');
    return t1SA?(a[t1SC]||0)-(b[t1SC]||0):(b[t1SC]||0)-(a[t1SC]||0);
  });
  document.getElementById('t1-count').textContent=rows.length+' buildings';
  const fv=(v,c)=>v>0?'<span class="v '+c+'">'+v+'%</span>':'<span class="zero">\u2014</span>';
  document.getElementById('t1-tbody').innerHTML=rows.map((b,i)=>{
    const rk=i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':'';
    const tc=b.hd?'<span class="v v-gold">'+b.tot.toLocaleString()+'</span>':'<span class="no-data">no era data</span>';
    const pc=b.hd&&b.pt>0?'<span class="v v-gold">'+b.pt+'</span>':'<span class="zero">\u2014</span>';
    return'<tr><td class="rank '+rk+'">'+(i+1)+'</td>'
      +'<td class="bn">'+b.n+'<span class="sb">'+b.s+'</span></td>'
      +'<td>'+tc+'</td><td>'+pc+'</td>'
      +'<td>'+fv(b.a,'v-att')+'</td><td>'+fv(b.d,'v-def')+'</td>'
      +'<td>'+fv(b.ga,'v-gbg')+'</td><td>'+fv(b.gd,'v-gbg')+'</td>'
      +'<td><span class="sb">'+b.s+'='+b.t+'t</span></td>'
      +'<td><span class="evt-tag">'+(b.evt||'\u2014')+'</span></td></tr>';
  }).join('');
}
function t1ColSort(c){
  if(t1SC===c)t1SA=!t1SA;else{t1SC=c;t1SA=false;}
  if(c!=='rank')document.getElementById('t1-sort').value=c;
  t1Render();
}
t1Render();

// ══════════════════════════════════════════════════════════════ TAB 2
const BB=%%BB_JSON%%;
let t2SC='tot',t2SA=false;
function t2Fields(ctx){
  if(ctx==='ge') return['ge_aaa','ge_daa','ge_ada','ge_dda','tot_ge'];
  if(ctx==='gbg')return['gbg_aaa','gbg_daa','gbg_ada','gbg_dda','tot_gbg'];
  if(ctx==='qi') return['qi_aaa','qi_daa','qi_ada','qi_dda','tot_qi'];
  return['aaa','daa','ada','dda','tot_open'];
}
function t2Render(){
  const srch=document.getElementById('t2-search').value.toLowerCase();
  const shop=document.getElementById('t2-shop').value;
  const ctx=document.getElementById('t2-ctx').value;
  t2SC=document.getElementById('t2-sort').value;
  const[fa,fd,fad,fdd,ft]=t2Fields(ctx);
  const cc={'open':'v-att','ge':'v-gbg','gbg':'v-def','qi':'v-qi'}[ctx]||'v-att';
  let rows=BB.map(b=>({...b,_a:b[fa],_d:b[fd],_ad:b[fad],_dd:b[fdd],_tot:b[ft],
    _pt:b.tiles>0?+(b[ft]/b.tiles).toFixed(2):0}));
  rows=rows.filter(b=>{
    if(srch&&!b.name.toLowerCase().includes(srch))return false;
    if(shop&&b.shop!==shop)return false;
    return true;
  });
  const sk=t2SC==='tot'?'_tot':t2SC==='pt'?'_pt':
    t2SC==='aaa'?'_a':t2SC==='daa'?'_d':t2SC==='ada'?'_ad':t2SC==='dda'?'_dd':null;
  rows.sort((a,b)=>sk?(t2SA?(a[sk]||0)-(b[sk]||0):(b[sk]||0)-(a[sk]||0))
    :(t2SA?a.name.localeCompare(b.name):b.name.localeCompare(a.name)));
  document.getElementById('t2-count').textContent=rows.length+' buildings';
  const fv=v=>v>0?'<span class="v '+cc+'">'+v+'%</span>':'<span class="zero">\u2014</span>';
  document.getElementById('t2-tbody').innerHTML=rows.map((b,i)=>{
    const rk=i===0?'rank-1':i===1?'rank-2':i===2?'rank-3':'';
    const sc='shop-'+(b.shop||'Event');
    const tc=b._tot>0?'<span class="v v-gold">'+b._tot+'</span>':'<span class="zero">\u2014</span>';
    const pc=b._pt>0?'<span class="v v-gold">'+b._pt+'</span>':'<span class="zero">\u2014</span>';
    return'<tr><td class="rank '+rk+'">'+(i+1)+'</td>'
      +'<td class="bn">'+b.name+'</td>'
      +'<td>'+tc+'</td><td>'+pc+'</td>'
      +'<td>'+fv(b._a)+'</td><td>'+fv(b._d)+'</td>'
      +'<td>'+fv(b._ad)+'</td><td>'+fv(b._dd)+'</td>'
      +'<td><span class="sb">'+b.tiles+'t</span></td>'
      +'<td><span class="shop-tag '+sc+'">'+(b.shop||'\u2014')+'</span></td></tr>';
  }).join('');
}
function t2ColSort(c){
  if(t2SC===c)t2SA=!t2SA;else{t2SC=c;t2SA=false;}
  if(c!=='rank')document.getElementById('t2-sort').value=c;
  t2Render();
}
t2Render();

// ══════════════════════════════════════════════════════════════ TAB 4
const FRAGS=%%FRAGS_JSON%%;
let t4AP=FRAGS.length>0?FRAGS[0].tag:null;
let t4SC='pct',t4SA=false;

function t4Init(){
  document.getElementById('t4-pills').innerHTML=FRAGS.map(p=>
    '<button class="pill'+(p.tag===t4AP?' active':'')+
    '" data-tag="'+p.tag+'" onclick="t4Sel(this)">'+p.tag+'</button>'
  ).join('');
}
function t4Sel(el){
  var tag=el.dataset.tag;
  t4AP=tag;
  document.querySelectorAll('#t4-pills .pill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  t4Render();
}
function t4Render(){
  const srch=document.getElementById('t4-search').value.toLowerCase();
  const filt=document.getElementById('t4-filter').value;
  const pl=FRAGS.find(p=>p.tag===t4AP);
  if(!pl){document.getElementById('t4-tbody').innerHTML='';return;}
  let rows=pl.fragments.filter(r=>{
    if(srch&&!r.name.toLowerCase().includes(srch))return false;
    if(filt==='progress'&&!r.in_progress)return false;
    if(filt==='done'&&!r.complete)return false;
    return true;
  });
  rows=[...rows].sort((a,b)=>{
    if(t4SC==='name')return t4SA?a.name.localeCompare(b.name):b.name.localeCompare(a.name);
    if(t4SC==='days'){
      const av=a.days!=null?a.days:Infinity;
      const bv=b.days!=null?b.days:Infinity;
      return t4SA?av-bv:bv-av;
    }
    return t4SA?(a[t4SC]||0)-(b[t4SC]||0):(b[t4SC]||0)-(a[t4SC]||0);
  });
  document.getElementById('t4-count').textContent=rows.length+' items';
  document.getElementById('t4-tbody').innerHTML=rows.map(r=>{
    const pct=Math.min(r.pct,100);
    const bc=r.complete?'complete':pct<10?'low':'';
    const col=r.complete?'var(--green)':r.in_progress?'var(--teal)':'var(--text3)';
    const bar='<div class="prog-wrap"><div class="prog-bar '+bc+'" style="width:'+pct+'%"></div></div>';
    const pctL='<span class="pct-label" style="color:'+col+'">'+r.pct+'%</span>';
    const haveL='<span class="v '+(r.in_progress?'v-gold':'')+'">'+r.have.toLocaleString()+'</span>';
    const asmL=r.assembled>0?'<span class="v v-green">'+r.assembled+'\xd7</span>':'<span class="zero">\u2014</span>';
    const fpd=r.fpd||0;
    const fpdL=fpd>0?'<span class="v v-teal">'+fpd.toFixed(2)+'</span>':'<span class="zero">\u2014</span>';
    const dc=r.days!=null?r.days:null;
    const dcCol=dc==null?'zero':dc<30?'v-green':dc<180?'v-gold':'v-att';
    const daysL=dc!=null?'<span class="v '+dcCol+'">'+dc+'d</span>':'<span class="zero">\u2014</span>';
    const estL=r.est?'<span class="v" style="font-size:.75rem;color:var(--text2)">'+r.est+'</span>':'<span class="zero">\u2014</span>';
    return'<tr>'
      +'<td class="bn">'+r.name+'</td>'
      +'<td>'+bar+pctL+'</td>'
      +'<td>'+haveL+'</td>'
      +'<td><span class="v">'+r.need.toLocaleString()+'</span></td>'
      +'<td>'+asmL+'</td>'
      +'<td>'+fpdL+'</td>'
      +'<td>'+daysL+'</td>'
      +'<td>'+estL+'</td></tr>';
  }).join('');
}
function t4ColSort(c){
  if(t4SC===c)t4SA=!t4SA;
  else{t4SC=c;t4SA=(c==='days');} // days: default ascending (soonest first)
  t4Render();
}
t4Init();
t4Render();

// TAB 5
const FRIENDS=%%FRIENDS_JSON%%;
let t5AP=FRIENDS.length>0?FRIENDS[0].tag:null;
let t5SC='days_since',t5SA=false;

function t5Init(){
  document.getElementById('t5-pills').innerHTML=FRIENDS.map(p=>
    '<button class="pill'+(p.tag===t5AP?' active':'')+
    '" data-tag="'+p.tag+'" onclick="t5Sel(this)">'+p.tag+'</button>'
  ).join('');
}
function t5Sel(el){
  var tag=el.dataset.tag;
  t5AP=tag;
  document.querySelectorAll('#t5-pills .pill').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  t5Render();
}
function t5Render(){
  const srch=document.getElementById('t5-search').value.toLowerCase();
  const filt=document.getElementById('t5-filter').value;
  const pl=FRIENDS.find(p=>p.tag===t5AP);
  if(!pl){document.getElementById('t5-tbody').innerHTML='';return;}
  let rows=pl.friends.filter(r=>{
    if(srch&&!r.name.toLowerCase().includes(srch))return false;
    if(filt&&r.status!==filt)return false;
    return true;
  });
  rows=[...rows].sort((a,b)=>{
    if(t5SC==='name')return t5SA?a.name.localeCompare(b.name):b.name.localeCompare(a.name);
    if(t5SC==='days_since'){
      const av=a.days_since!=null?a.days_since:999999;
      const bv=b.days_since!=null?b.days_since:999999;
      return t5SA?av-bv:bv-av;
    }
    if(t5SC==='last_aided'||t5SC==='friend_since'){
      const av=a[t5SC]||'';
      const bv=b[t5SC]||'';
      return t5SA?av.localeCompare(bv):bv.localeCompare(av);
    }
    return 0;
  });
  const inactive=rows.filter(r=>r.status==='inactive').length;
  document.getElementById('t5-count').textContent=rows.length+' friends'+(inactive?' \u2014 '+inactive+' inactive':'');
  document.getElementById('t5-tbody').innerHTML=rows.map(r=>{
    const sc=r.friend_since?'<span class="v" style="font-size:.75rem;color:var(--text2)">'+r.friend_since+'</span>':'<span class="zero">\u2014</span>';
    const la=r.last_aided?'<span class="v" style="font-size:.75rem;color:var(--text2)">'+r.last_aided+'</span>':'<span class="zero">\u2014</span>';
    const dc=r.days_since;
    const dcCol=dc==null?'zero':r.status==='inactive'?'v-att':dc<7?'v-green':'v-gold';
    const daysL=dc!=null?'<span class="v '+dcCol+'">'+dc+'d</span>':'<span class="zero">\u2014</span>';
    const stCol=r.status==='inactive'?'var(--red)':r.status==='new'?'var(--teal)':'var(--green)';
    const stLabel=r.status==='inactive'?'Inactive':r.status==='new'?'New':'Active';
    const stL='<span style="font-family:'Share Tech Mono',monospace;font-size:.75rem;color:'+stCol+'">'+stLabel+'</span>';
    return'<tr>'
      +'<td class="bn">'+r.name+'</td>'
      +'<td>'+sc+'</td>'
      +'<td>'+la+'</td>'
      +'<td>'+daysL+'</td>'
      +'<td>'+stL+'</td></tr>';
  }).join('');
}
function t5ColSort(c){
  if(t5SC===c)t5SA=!t5SA;else{t5SC=c;t5SA=false;}
  t5Render();
}
t5Init();
t5Render();
</script>
</body>
</html>
"""


# ═══════════════════════════════════════════════════════════════════════════════
# HTML assembly
# ═══════════════════════════════════════════════════════════════════════════════

def _build_era_options(best_rows, highest_era_idx):
    present_idxs = set()
    for b in best_rows:
        for er in b["e"]:
            present_idxs.add(er[0])
    present_eras = [ERA_ORDER[i] for i in sorted(present_idxs)]
    options = []
    for era in present_eras:
        idx = ERA_RANK[era]
        sel = " selected" if idx == highest_era_idx else ""
        options.append(f'      <option value="{idx}"{sel}>{ERA_LABELS[era]}</option>')
    return present_eras, options


def build_html(best_rows, highest_era_idx, bb_rows, gb_players,
               frag_players, friend_players, sources, build_date, page_title=None):
    """
    Build a full 4-tab page.
    gb_players / frag_players can be the full list (shared dashboard)
    or a single-item list (personal page).
    page_title overrides the default <title> if provided.
    """
    present_eras, era_options = _build_era_options(best_rows, highest_era_idx)

    all_evts = sorted({b["evt"] for b in best_rows if b["evt"]})
    event_options = [f'    <option value="{e}">{e}</option>' for e in all_evts]

    best_json       = json.dumps(best_rows,    separators=(",", ":"), ensure_ascii=True)
    bb_json         = json.dumps(bb_rows,      separators=(",", ":"), ensure_ascii=True)
    frags_json      = json.dumps(frag_players, separators=(",", ":"), ensure_ascii=True)
    friends_json    = json.dumps(friend_players, separators=(",", ":"), ensure_ascii=True)
    era_order_json  = json.dumps(ERA_ORDER,    separators=(",", ":"))
    era_labels_json = json.dumps(ERA_LABELS,   separators=(",", ":"))
    gb_sections     = build_gb_sections(gb_players)

    title = page_title or "FoE Community INFO"

    html = HTML_TEMPLATE
    html = html.replace("FoE Community INFO</title>", f"{title}</title>", 1)
    html = html.replace("%%BUILDING_COUNT%%",  str(len(best_rows)))
    html = html.replace("%%ERA_COUNT%%",       str(len(present_eras)))
    html = html.replace("%%BUILD_DATE%%",      build_date)
    html = html.replace("%%DATA_SOURCES%%",    " + ".join(sources))
    html = html.replace("%%ERA_OPTIONS%%",     "\n".join(era_options))
    html = html.replace("%%EVENT_OPTIONS%%",   "\n".join(event_options))
    html = html.replace("%%ERA_ORDER_JSON%%",  era_order_json)
    html = html.replace("%%ERA_LABELS_JSON%%", era_labels_json)
    html = html.replace("%%BEST_JSON%%",       best_json)
    html = html.replace("%%BB_JSON%%",         bb_json)
    html = html.replace("%%FRAGS_JSON%%",      frags_json)
    html = html.replace("%%FRIENDS_JSON%%",    friends_json)
    html = html.replace("%%INACTIVE_DAYS%%",   str(INACTIVE_DAYS))
    html = html.replace("%%GB_SECTIONS%%",     gb_sections)
    return html


def build_dashboard_html(best_rows, highest_era_idx, bb_rows,
                         sources, build_date):
    """
    Shared community dashboard — Tabs 1 & 2 only, no personal data.
    Tabs 3 & 4 show a friendly 'no personal data' message.
    """
    present_eras, era_options = _build_era_options(best_rows, highest_era_idx)
    all_evts = sorted({b["evt"] for b in best_rows if b["evt"]})
    event_options = [f'    <option value="{e}">{e}</option>' for e in all_evts]

    best_json       = json.dumps(best_rows, separators=(",", ":"), ensure_ascii=True)
    bb_json         = json.dumps(bb_rows,   separators=(",", ":"), ensure_ascii=True)
    era_order_json  = json.dumps(ERA_ORDER,  separators=(",", ":"))
    era_labels_json = json.dumps(ERA_LABELS, separators=(",", ":"))

    no_personal = (
        '<div style="padding:40px;text-align:center;color:var(--text3);'
        'font-family:\'Share Tech Mono\',monospace;font-size:.85rem;">'
        '&#128274; Personal data not included in the community dashboard.<br>'
        '<span style="color:var(--text2);font-size:.8rem;">'
        'Players with a personal page can find their GB and fragment data there.</span>'
        '</div>'
    )

    html = HTML_TEMPLATE
    html = html.replace("FoE Community INFO</title>",
                        "FoE Community INFO \u2014 Guild Dashboard</title>", 1)
    html = html.replace("%%BUILDING_COUNT%%",  str(len(best_rows)))
    html = html.replace("%%ERA_COUNT%%",       str(len(present_eras)))
    html = html.replace("%%BUILD_DATE%%",      build_date)
    html = html.replace("%%DATA_SOURCES%%",    " + ".join(sources))
    html = html.replace("%%ERA_OPTIONS%%",     "\n".join(era_options))
    html = html.replace("%%EVENT_OPTIONS%%",   "\n".join(event_options))
    html = html.replace("%%ERA_ORDER_JSON%%",  era_order_json)
    html = html.replace("%%ERA_LABELS_JSON%%", era_labels_json)
    html = html.replace("%%BEST_JSON%%",       best_json)
    html = html.replace("%%BB_JSON%%",         bb_json)
    html = html.replace("%%FRAGS_JSON%%",      "[]")
    html = html.replace("%%FRIENDS_JSON%%",    "[]")
    html = html.replace("%%INACTIVE_DAYS%%",   str(INACTIVE_DAYS))
    html = html.replace("%%GB_SECTIONS%%",     no_personal)
    return html


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    script_dir = Path(__file__).parent

    if len(sys.argv) > 1:
        zip_paths = [Path(p) for p in sys.argv[1:]]
    else:
        exports_dir = script_dir / "exports"
        zip_paths   = sorted(exports_dir.glob("*.zip"))

    if not zip_paths:
        print("ERROR: No zip files found.")
        print("  Put MegaExport zips in exports/ or pass paths as arguments.")
        sys.exit(1)

    print(f"\nFoE Community INFO Builder")
    print(f"{'─'*44}")
    print(f"Processing {len(zip_paths)} export(s):\n")

    # ── Shared data (all zips merged) ─────────────────────────────────────────
    best_rows, highest_era_idx = build_best_list(zip_paths)

    bb_csv  = find_battle_boost_csv(script_dir)
    bb_rows = []
    if bb_csv:
        print(f"\n  [Tab2] Found CSV: {bb_csv.name}")
        bb_rows = load_battle_boosts(bb_csv)
    else:
        print(f"\n  [Tab2] No BattleBoost CSV found — tab will be empty.")
        print(f"         Place *BattleBoost*.csv next to build.py.")

    print()
    gb_players   = build_gb_data(zip_paths)
    print()
    frag_players = build_fragment_data(zip_paths)
    print()
    friend_players = build_friend_data(zip_paths)

    # Tag each zip with its player name
    tagged_zips = []
    for zp in zip_paths:
        m = re.match(r"([A-Z]+)_foe_helper", zp.name)
        tag = m.group(1) if m else zp.stem
        tagged_zips.append((tag, zp))

    sources    = [tag for tag, _ in tagged_zips]
    now        = datetime.now(timezone.utc)
    build_date = f"{now.day} {now.strftime('%b %Y')}"

    written = []

    # ── 1. Shared community dashboard ─────────────────────────────────────────
    print(f"\n  Building shared dashboard (index.html)...")
    dash_html = build_dashboard_html(
        best_rows, highest_era_idx, bb_rows, sources, build_date
    )
    dash_path = script_dir / "index.html"
    dash_path.write_text(dash_html, encoding="utf-8")
    written.append(dash_path)
    print(f"    -> {dash_path.name}  ({dash_path.stat().st_size/1024:.1f} KB)")

    # ── 2. Per-player personal pages ──────────────────────────────────────────
    print(f"\n  Building personal pages...")
    for tag, zp in tagged_zips:
        # Filter GB and fragment data to just this player
        player_gbs   = [p for p in gb_players   if p["tag"] == tag]
        player_frags   = [p for p in frag_players   if p["tag"] == tag]
        player_friends = [p for p in friend_players if p["tag"] == tag]

        # Get this player's era for the title
        era_label = player_gbs[0]["era"] if player_gbs else ""
        player_name = player_gbs[0]["player"] if player_gbs else tag
        page_title = f"{player_name} \u2014 FoE Community INFO"

        player_html = build_html(
            best_rows, highest_era_idx,
            bb_rows, player_gbs, player_frags, player_friends,
            [tag], build_date,
            page_title=page_title,
        )
        out_path = script_dir / f"{tag}.html"
        out_path.write_text(player_html, encoding="utf-8")
        written.append(out_path)
        print(f"    -> {out_path.name}  ({out_path.stat().st_size/1024:.1f} KB)"
              f"  [{player_name} / {era_label}]")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*44}")
    print(f"  Files written : {len(written)}")
    print(f"  Tab 1         : {len(best_rows)} boost buildings")
    print(f"  Tab 2         : {len(bb_rows)} battle boost entries")
    print(f"  Tab 5         : friend data for {len(friend_players)} player(s)")
    print(f"  Players       : {', '.join(sources)}")
    print(f"  Built         : {build_date}")
    print()


if __name__ == "__main__":
    main()
