# FoE Best Buildings — Update Workflow

Community reference page for top military boost buildings in Forge of Empires.  
Viewers can select their own era and the boost values update instantly in the browser.

---

## One-time setup

1. **Clone your GitHub repo** (if you haven't already):
   ```bash
   git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
   cd YOUR_REPO
   ```

2. **Copy these files into the repo root:**
   - `build.py`
   - `update.sh`
   - `exports/`  ← folder for your MegaExport zips

3. **Make the update script executable** (Mac/Linux):
   ```bash
   chmod +x update.sh
   ```

4. **Confirm GitHub Pages is enabled** in your repo settings  
   (Settings → Pages → Source: Deploy from branch `main`, folder `/root`)

---

## Update workflow

### Step 1 — Export from FoE Helper

In FoE Helper, use **MegaExport** for each city. Save the `.zip` files.

> **Best time to update:** Just before a new event launches — InnoGames will have
> pushed the new building data to the game servers, so FoE Helper will pick it up
> in the `buildingMeta` table.

### Step 2 — Drop zips into the `exports/` folder

```
exports/
  CTHG_foe_helper_MEGAexport_260415-0914.zip
  PMTHS_foe_helper_MEGAexport_260414-0837.zip
```

Old zips can stay — the script always uses **all** zips in the folder, deduplicating
by building ID (newer zip wins on conflict). Or delete old ones to keep it tidy.

### Step 3 — Run one command

```bash
./update.sh
```

That's it. The script:
1. Reads all zips in `exports/`
2. Extracts boost data for **all eras** from `buildingMeta`
3. Writes `index.html` with an era picker dropdown
4. Commits and pushes to GitHub
5. GitHub Pages serves the updated page within ~60 seconds

---

## How the era picker works

The page stores boost values for every era each building supports.  
The default selection is the **highest era found across all your exports** —  
so it automatically advances when one of your cities progresses.

Viewers in lower eras pick their own era from the dropdown and see their numbers.  
Buildings with no data for the selected era show `—` but remain visible in the list.

---

## Passing zips explicitly (optional)

```bash
./update.sh /path/to/CITY1.zip /path/to/CITY2.zip
```

Or run the builder without pushing:
```bash
python3 build.py
```

---

## Adding more cities

Just drop another city's MegaExport zip into `exports/` before running `update.sh`.  
No config changes needed.

---

## Requirements

- Python 3.9+ (standard library only — no `pip install` needed)
- `git` with push access to the repo
