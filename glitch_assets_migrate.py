import os, json, re, sys, urllib.parse
from pathlib import Path

try:
    import requests
except ImportError:
    print("Installing requests ...")
    os.system(f"{sys.executable} -m pip install -q requests")
    import requests

ASSETS_FILE = ".glitch-assets"
ASSETS_DIR = "assets"
SCAN_EXTS = (".html", ".css", ".js", ".md")  # add more if you like

if not Path(ASSETS_FILE).exists():
    print("ERROR: .glitch-assets not found at repo root.")
    sys.exit(1)

os.makedirs(ASSETS_DIR, exist_ok=True)

mapping = {}         # canonical_url (no query) -> local path
seen_names = set()   # for de-duplication

def unique_name(name: str) -> str:
    base, ext = os.path.splitext(name)
    candidate = name
    i = 1
    lower = candidate.lower()
    while lower in seen_names or Path(ASSETS_DIR, candidate).exists():
        candidate = f"{base}_{i}{ext}"
        lower = candidate.lower()
        i += 1
    seen_names.add(lower)
    return candidate

def canonical(url: str) -> str:
    u = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse(u._replace(query=""))

# --- Parse .glitch-assets and download everything ---
downloaded = 0
with open(ASSETS_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("deleted"):
            continue

        url = obj.get("url") or obj.get("source") or obj.get("thumbnail")
        if not url:
            continue

        name = obj.get("name")
        if not name:
            path = urllib.parse.urlparse(url).path
            name = os.path.basename(path) or "asset"

        safe = unique_name(name)
        dest = Path(ASSETS_DIR) / safe

        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            dest.write_bytes(r.content)
            downloaded += 1
        except Exception as e:
            print(f"FAILED to download {url}: {e}")
            continue

        mapping[canonical(url)] = f"{ASSETS_DIR}/{safe}"

# Save mapping for inspection
Path("url_mapping.json").write_text(json.dumps(mapping, indent=2), encoding="utf-8")
print(f"✅ Downloaded {downloaded} assets into ./{ASSETS_DIR}")

# --- Replace URLs in project files ---
files_changed = 0
for root, dirs, files in os.walk("."):
    # skip .git and the assets folder itself
    dirs[:] = [d for d in dirs if d not in (".git", ASSETS_DIR, ".codesandbox", ".github")]
    for fname in files:
        if fname.lower().endswith(SCAN_EXTS):
            p = Path(root) / fname
            try:
                text = p.read_text(encoding="utf-8")
            except Exception:
                continue
            original = text
            for old_url, new_path in mapping.items():
                # replace either exact URL or URL with query string (?v=..., etc.)
                pattern = re.escape(old_url) + r"(?:\?[^\s\"'\)]*)?"
                text = re.sub(pattern, new_path, text)
            if text != original:
                p.write_text(text, encoding="utf-8")
                files_changed += 1
                print(f"Updated {p}")

print(f"✅ URL replacement complete. Files changed: {files_changed}")
print("   Mapping saved to url_mapping.json")
