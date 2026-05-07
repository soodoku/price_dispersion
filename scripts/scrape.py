"""
Wirecutter HTML scraper.

Fetches archived Wirecutter "best of" articles via wayback.archive-it.org
(Internet Archive's institutional service) which is more permissive of
automation than the public Wayback Machine. The host runs a SHA-256
proof-of-work session challenge; this script solves it programmatically,
then uses the Memento timemap endpoint to enumerate all snapshots of each
article in a given window, and fetches the latest snapshot per
(article, month).

Saves HTML files to data/html/{slug}/{timestamp}.html

Dependencies: curl_cffi (for Chrome TLS fingerprinting; the host blocks
plain requests).
"""
from __future__ import annotations
import hashlib, re, time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from curl_cffi import requests
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
WINDOW_START = '2021-05-01'
WINDOW_END   = '2026-05-03'
HTML_DIR      = Path('data/html')
TIMEMAP_DIR   = Path('cache_timemaps')
RATE_DELAY    = 6
RATE_BACKOFF  = 45

SEED_SLUGS = [
    'best-air-fryer','best-air-purifier','best-android-phone','best-baby-monitor',
    'best-bath-towel','best-bike-lock','best-blender','best-bluetooth-speaker',
    'best-bookshelf-speakers','best-breast-pumps','best-carry-on-luggage',
    'best-cast-iron-skillet','best-cat-litter','best-checked-luggage',
    'best-chromebook','best-clothes-iron','best-coffee-maker','best-cold-brew-coffee-maker',
    'best-comforter','best-cookware-set','best-cordless-stick-vacuum','best-cribs',
    'best-cutting-board','best-dehumidifier','best-diaper-bag','best-dog-beds',
    'best-drip-coffee-maker','best-dutch-oven','best-duvet-cover',
    'best-electric-toothbrush','best-exercise-bikes','best-fan','best-flashlight',
    'best-french-press','best-handheld-vacuum','best-headlamp','best-headphones',
    'best-immersion-blender','best-instant-camera','best-iphone-cases','best-keyboards',
    'best-kitchen-scale','best-laptops','best-laser-printer','best-mattress',
    'best-microwave','best-mixing-bowls','best-monitors','best-noise-cancelling-headphones',
    'best-nonstick-pan','best-office-chair','best-pet-camera','best-pocket-knife',
    'best-portable-monitor','best-robot-vacuum','best-running-headphones',
    'best-running-shoes','best-sheets','best-slow-cooker','best-soundbar',
    'best-stand-mixer','best-standing-desk','best-strollers','best-tablets',
    'best-toaster','best-travel-mug','best-travel-pillow','best-treadmill',
    'best-tv','best-umbrella','best-usb-c-cables','best-water-bottle',
    'best-wireless-earbuds','best-wireless-mouse','best-yoga-mats',
]


# ---------------------------------------------------------------------------
# Proof-of-work session challenge solver
# ---------------------------------------------------------------------------
def _passes(h: bytes, diff: int) -> bool:
    i = 0
    while True:
        if h[i] > 0x0F: return False
        if (i*2) + 1 >= diff: return True
        if h[i] > 0: return False
        if (i*2) + 2 >= diff: return True
        i += 1

def solve_pow(ip: str, ts: str, diff: int) -> int:
    tries = 0
    while not _passes(hashlib.sha256(f'{ip};{ts};{tries}'.encode()).digest(), diff):
        tries += 1
    return tries

def fetch_archive_it(s: requests.Session, url: str, max_attempts: int = 4, timeout: int = 45):
    last = None
    for _ in range(max_attempts):
        try:
            r = s.get(url, timeout=timeout)
        except Exception:
            time.sleep(5); continue
        last = r
        if r.status_code == 429:
            time.sleep(RATE_BACKOFF); continue
        if 'Session Verification' not in r.text:
            return r
        m = re.search(
            r'name="ip" value="([^"]+)"[\s\S]+?name="ts" value="([^"]+)"[\s\S]+?name="diff" value="([^"]+)"',
            r.text)
        if not m: return r
        ip, ts, diff = m.group(1), m.group(2), int(m.group(3))
        tries = solve_pow(ip, ts, diff)
        try:
            s.post('https://wayback.archive-it.org/_challenge',
                   data={'ip': ip, 'ts': ts, 'diff': str(diff), 'tries': str(tries)},
                   headers={'Origin': 'https://wayback.archive-it.org', 'Referer': url},
                   timeout=20)
        except Exception:
            pass
    return last


# ---------------------------------------------------------------------------
# Memento timemap & snapshot enumeration
# ---------------------------------------------------------------------------
def get_timemap(s: requests.Session, slug: str) -> list[str]:
    cache_path = TIMEMAP_DIR / f'{slug}.txt'
    if cache_path.exists():
        text = cache_path.read_text()
    else:
        url = f'https://wayback.archive-it.org/all/timemap/link/https://www.nytimes.com/wirecutter/reviews/{slug}/'
        r = fetch_archive_it(s, url)
        if not r or r.status_code != 200:
            return []
        text = r.text
        TIMEMAP_DIR.mkdir(exist_ok=True)
        cache_path.write_text(text)
        time.sleep(RATE_DELAY)
    return re.findall(
        r'<https://wayback\.archive-it\.org/all/(\d{14})/[^>]+>;\s*rel="memento";\s*datetime="[^"]+"',
        text)

def select_monthly_snapshots(timestamps: list[str]) -> list[str]:
    in_window = []
    start = datetime.fromisoformat(WINDOW_START)
    end   = datetime.fromisoformat(WINDOW_END + 'T23:59:59')
    for ts in timestamps:
        dt = datetime.strptime(ts, '%Y%m%d%H%M%S')
        if start <= dt <= end:
            in_window.append(ts)
    by_month: dict[tuple[int,int], list[str]] = defaultdict(list)
    for ts in in_window:
        dt = datetime.strptime(ts, '%Y%m%d%H%M%S')
        by_month[(dt.year, dt.month)].append(ts)
    return [max(tss) for tss in by_month.values()]

def fetch_snapshot(s: requests.Session, slug: str, ts: str) -> bool:
    """Fetch one snapshot and save to data/html/{slug}/{ts}.html. Returns True if successful."""
    out_dir = HTML_DIR / slug
    out_path = out_dir / f'{ts}.html'
    if out_path.exists():
        return True
    snap_url = f'https://wayback.archive-it.org/all/{ts}/https://www.nytimes.com/wirecutter/reviews/{slug}/'
    r = fetch_archive_it(s, snap_url)
    if not r or r.status_code != 200 or len(r.text) < 5000:
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(r.text)
    time.sleep(RATE_DELAY)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    s = requests.Session(impersonate='chrome120')
    fetch_archive_it(s, 'https://wayback.archive-it.org/all/*/https://www.nytimes.com/wirecutter/reviews/best-drip-coffee-maker/')
    time.sleep(2)

    snapshots: list[tuple[str, str]] = []
    for slug in tqdm(SEED_SLUGS, desc='Enumerating timemaps'):
        timestamps = get_timemap(s, slug)
        monthly = select_monthly_snapshots(timestamps)
        for ts in monthly:
            snapshots.append((slug, ts))
    print(f'\nTotal snapshots to fetch: {len(snapshots)}')

    fetched = 0
    cached = 0
    failed = 0
    pbar = tqdm(snapshots, desc='Fetching snapshots')
    for slug, ts in pbar:
        out_path = HTML_DIR / slug / f'{ts}.html'
        was_cached = out_path.exists()
        success = fetch_snapshot(s, slug, ts)
        if success:
            if was_cached:
                cached += 1
            else:
                fetched += 1
        else:
            failed += 1
        pbar.set_postfix(fetched=fetched, cached=cached, failed=failed)

    print(f'\nDone: {fetched} fetched, {cached} cached, {failed} failed')
    print(f'HTML files saved to {HTML_DIR}/')


if __name__ == '__main__':
    main()
