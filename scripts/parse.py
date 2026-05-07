"""
Wirecutter HTML parser.

Reads HTML files from data/html/{slug}/{timestamp}.html and extracts
JSON-LD product offers.

Each Wirecutter page embeds JSON-LD <script type="application/ld+json">
blocks containing Product objects with offers[] -> {offeredBy.name, price}.
The extractor walks every JSON-LD block and emits one row per (product,
retailer) listing.

Filters applied at extraction:
  - non-new-condition retailer names (refurb/renewed/used/open-box/certified/outlet)
  - multi-unit retailer names (pack of N, set of, bundle, N-pack)
  - per-month financing prices (drop the smallest if next-cheapest is >=3x)
  - data-error products with >10x max/min ratio across retailers (one JSON-LD typo)

Output: data/wirecutter_offers.csv with columns
  slug, article_url, snapshot_url, snapshot_dt, product, retailer, price

Restricted to (slug, snapshot_dt, product) groups with at least 2 retailers,
so every row participates in a comparison.
"""
from __future__ import annotations
import csv, json, re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HTML_DIR   = Path('data/html')
OUTPUT_CSV = Path('data/wirecutter_offers.csv')

NON_NEW_RE        = re.compile(r'(?i)refurb|renew|used|open[- ]?box|certified|outlet')
DIFFERENT_UNIT_RE = re.compile(r'(?i)pack of|bundle|\bset of\b|\d[- ]pack')


def walk_products(obj):
    """Recursively yield every dict with @type == 'Product'."""
    if isinstance(obj, dict):
        if obj.get('@type') == 'Product':
            yield obj
        for v in obj.values():
            yield from walk_products(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_products(v)

def is_excluded_retailer(name: str) -> bool:
    return bool(NON_NEW_RE.search(name) or DIFFERENT_UNIT_RE.search(name))

def extract_offers(html: str):
    """Yield (product_name, retailer_name, price_float) tuples, with filters applied."""
    for m in re.finditer(r'<script[^>]+type="application/ld\+json"[^>]*>([\s\S]+?)</script>', html):
        try:
            obj = json.loads(m.group(1).strip())
        except Exception:
            continue
        for prod in walk_products(obj):
            name = prod.get('name')
            offs = prod.get('offers') or []
            if isinstance(offs, dict): offs = [offs]
            for off in offs:
                seller = off.get('offeredBy') or off.get('seller') or {}
                seller_name = seller if isinstance(seller, str) else seller.get('name', '')
                price_raw = off.get('price')
                try:
                    price = float(price_raw) if price_raw is not None else None
                except (TypeError, ValueError):
                    price = None
                if name and seller_name and price and price > 0:
                    seller_name = seller_name.strip()
                    if is_excluded_retailer(seller_name):
                        continue
                    yield name.strip(), seller_name, price

def filter_per_month(prices: dict[str, float], ratio: float = 3.0) -> dict[str, float]:
    """Drop prices that are < 1/ratio of the next-cheapest. Catches per-month financing."""
    while len(prices) >= 2:
        sp = sorted(prices.items(), key=lambda x: x[1])
        if sp[1][1] / sp[0][1] >= ratio:
            del prices[sp[0][0]]
        else:
            return prices
    return prices

def load_html_files() -> list[tuple[str, str, str]]:
    """Walk data/html/ and return list of (slug, timestamp, html_content)."""
    results = []
    if not HTML_DIR.exists():
        return results
    for slug_dir in sorted(HTML_DIR.iterdir()):
        if not slug_dir.is_dir():
            continue
        slug = slug_dir.name
        for html_file in sorted(slug_dir.glob('*.html')):
            ts = html_file.stem
            html = html_file.read_text()
            results.append((slug, ts, html))
    return results


def main():
    html_files = load_html_files()
    if not html_files:
        print(f'No HTML files found in {HTML_DIR}/')
        return

    print(f'Processing {len(html_files)} HTML files...')

    all_rows: list[dict] = []
    raw_count = 0

    for slug, ts, html in html_files:
        snap_dt = datetime.strptime(ts, '%Y%m%d%H%M%S').strftime('%Y-%m-%d')
        snap_url = f'https://wayback.archive-it.org/all/{ts}/https://www.nytimes.com/wirecutter/reviews/{slug}/'
        article_url = f'https://www.nytimes.com/wirecutter/reviews/{slug}/'

        per_obs: dict[tuple[str,str], dict[str,float]] = defaultdict(dict)
        for product, retailer, price in extract_offers(html):
            raw_count += 1
            key = (snap_dt, product)
            if retailer not in per_obs[key] or price < per_obs[key][retailer]:
                per_obs[key][retailer] = price

        for (snap_dt_k, product), prices in per_obs.items():
            for retailer, price in prices.items():
                all_rows.append({
                    'slug': slug,
                    'article_url': article_url,
                    'snapshot_url': snap_url,
                    'snapshot_dt': snap_dt_k,
                    'product': product,
                    'retailer': retailer,
                    'price': price,
                })

    groups_retailers: dict[tuple, set] = defaultdict(set)
    for r in all_rows:
        groups_retailers[(r['slug'], r['snapshot_dt'], r['product'])].add(r['retailer'])
    eligible = {k for k, v in groups_retailers.items() if len(v) >= 2}

    by_group: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for r in all_rows:
        key = (r['slug'], r['snapshot_dt'], r['product'])
        if key not in eligible: continue
        by_group[key][r['retailer']] = r

    final_rows = []
    n_pm_filtered = 0
    n_typo_filtered = 0
    for key, retailer_rows in by_group.items():
        prices = {r: row['price'] for r, row in retailer_rows.items()}
        before = len(prices)
        prices = filter_per_month(prices)
        if len(prices) != before:
            n_pm_filtered += 1
        if len(prices) < 2: continue
        lo, hi = min(prices.values()), max(prices.values())
        if hi / lo > 10:
            n_typo_filtered += 1
            continue
        for retailer in prices:
            final_rows.append(retailer_rows[retailer])

    final_rows.sort(key=lambda r: (r['slug'], r['snapshot_dt'], r['product'], r['price']))

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=[
            'slug', 'article_url', 'snapshot_url', 'snapshot_dt',
            'product', 'retailer', 'price',
        ])
        w.writeheader()
        w.writerows(final_rows)

    print(f'\nWrote {len(final_rows)} rows to {OUTPUT_CSV}')
    print(f'  raw offers extracted (post-refurb/multipack filter): {raw_count}')
    print(f'  per-month financing groups affected: {n_pm_filtered}')
    print(f'  >10x typo groups dropped: {n_typo_filtered}')


if __name__ == '__main__':
    main()
