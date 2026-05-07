"""
Wirecutter price analysis from Internet Archive captures.

For cross-sectional headline stats, uses one snapshot per article (the latest
capture) so multi-snapshot articles do not inflate aggregate measures. The full
time-series of snapshots is reported separately to show how prices evolved.
"""
import csv, re
from pathlib import Path
from collections import defaultdict
from statistics import mean, median

CSV_PATH = Path(__file__).parent.parent / 'data' / 'wirecutter_offers.csv'

NON_NEW_RE = re.compile(r'(?i)refurb|renew|used|open[- ]?box|certified|outlet')
DIFFERENT_UNIT_RE = re.compile(r'(?i)pack of|bundle|\bset of\b|\d[- ]pack')
def excluded_retailer(name): return bool(NON_NEW_RE.search(name) or DIFFERENT_UNIT_RE.search(name))


def filter_per_month(prices, ratio=3.0):
    while len(prices) >= 2:
        sp = sorted(prices.items(), key=lambda x: x[1])
        if sp[1][1] / sp[0][1] >= ratio:
            del prices[sp[0][0]]
        else:
            break
    return prices


def load_all_obs():
    """Returns (slug, snapshot_dt, product) -> {retailer: price} for all snapshots."""
    obs = defaultdict(dict)
    with open(CSV_PATH, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            slug = row['slug']
            snap_dt = row['snapshot_dt']
            product = row['product'].strip()
            retailer = row['retailer'].strip()
            try:
                price = float(row['price'])
            except (ValueError, TypeError):
                continue
            if price <= 0 or excluded_retailer(retailer):
                continue
            key = (slug, snap_dt, product)
            if retailer not in obs[key] or price < obs[key][retailer]:
                obs[key][retailer] = price
    return obs

def latest_per_article_product(obs):
    """For each (slug, product), keep only the entry from the latest snapshot_dt."""
    latest = {}  # (slug, product) -> (snap_dt, prices)
    for (slug, dt, prod), prices in obs.items():
        k = (slug, prod)
        if k not in latest or dt > latest[k][0]:
            latest[k] = (dt, prices)
    return {(slug, dt, prod): prices for (slug, prod), (dt, prices) in latest.items()}

def pct(x, sign=False, dec=1):
    return f"{x*100:+.{dec}f}%" if sign else f"{x*100:.{dec}f}%"

def main():
    obs_all = load_all_obs()
    obs = latest_per_article_product(obs_all)

    distinct_articles = len({slug for slug, _, _ in obs})
    distinct_dates = len({dt for _, dt, _ in obs})
    n_obs = len(obs)
    with_amzn = sum(1 for s in obs.values() if 'Amazon' in s)
    only_amzn = sum(1 for s in obs.values() if list(s.keys()) == ['Amazon'])
    date_min = min(dt for _, dt, _ in obs); date_max = max(dt for _, dt, _ in obs)

    print('='*82)
    print(f'Wirecutter price comparison ({date_min} to {date_max})')
    print('='*82)
    print(f'Articles: {distinct_articles}')
    print(f'Total products: {n_obs}')
    print(f'Cross-section uses latest snapshot per (article, product)')
    print(f'Date range: {date_min} to {date_max}, {distinct_dates} distinct snapshot dates')

    print(f'\n[Prevalence] Amazon as a listed retailer')
    print(f'  Amazon listed:        {with_amzn}/{n_obs}  ({pct(with_amzn/n_obs)})')
    print(f'  Amazon-only listed:   {only_amzn}/{n_obs}  ({pct(only_amzn/n_obs)}) — no comparison possible')

    comparable = {}
    n_filtered_pm = 0; n_data_error = 0
    for k, prices in obs.items():
        before = len(prices); pf = filter_per_month(dict(prices))
        if len(pf) != before: n_filtered_pm += 1
        if len(pf) < 2: continue
        lo = min(pf.values()); hi = max(pf.values())
        if hi/lo > 10: n_data_error += 1; continue
        comparable[k] = pf

    amzn_strict = 0; amzn_tied = 0
    retailer_app = defaultdict(int)
    retailer_at_lowest = defaultdict(int); retailer_strict = defaultdict(int)
    retailer_savings = defaultdict(list); retailer_overhead = defaultdict(list)
    retailer_vs_avg_alt = defaultdict(list)

    for prices in comparable.values():
        m = min(prices.values())
        cheapest = [r for r, p in prices.items() if p == m]
        for r in prices: retailer_app[r] += 1
        for r in cheapest: retailer_at_lowest[r] += 1
        if len(cheapest) == 1: retailer_strict[cheapest[0]] += 1

        if 'Amazon' in prices:
            a = prices['Amazon']
            if a == m:
                if len(cheapest) == 1: amzn_strict += 1
                else: amzn_tied += 1

        for r, p in prices.items():
            others = {x: q for x, q in prices.items() if x != r}
            if not others: continue
            co = min(others.values()); ao = mean(others.values())
            if r in cheapest:
                retailer_savings[r].append((co - p) / p)
            else:
                retailer_overhead[r].append((p - co) / co)
            retailer_vs_avg_alt[r].append((ao - p) / ao)

    n_compare = sum(1 for s in comparable.values() if 'Amazon' in s)
    print(f'\n[Frequency] Amazon position when listed alongside ≥1 other retailer (n={n_compare})')
    at_low = amzn_strict + amzn_tied
    print(f'  At the lowest price:    {at_low}/{n_compare}  ({pct(at_low/n_compare)})')
    print(f'    strictly cheapest:    {amzn_strict}/{n_compare}  ({pct(amzn_strict/n_compare)})')
    print(f'    tied for cheapest:    {amzn_tied}/{n_compare}  ({pct(amzn_tied/n_compare)})')

    total_amzn = total_min_alt = total_mean_alt = 0.0
    pp_dollar_diff = []
    for prices in comparable.values():
        if 'Amazon' not in prices: continue
        a = prices['Amazon']
        others = [p for r, p in prices.items() if r != 'Amazon']
        if not others: continue
        am = min(others); aa = mean(others)
        total_amzn += a; total_min_alt += am; total_mean_alt += aa
        pp_dollar_diff.append(am - a)

    print(f'\n[Aggregate $] If you bought one of each across all {n_compare} comparable products:')
    print(f'  Total at Amazon:                  ${total_amzn:>10,.0f}')
    print(f'  Total at cheapest non-Amazon alt: ${total_min_alt:>10,.0f}')
    print(f'  Total at avg non-Amazon alt:      ${total_mean_alt:>10,.0f}')
    s_min = (total_min_alt - total_amzn) / total_min_alt
    s_mean = (total_mean_alt - total_amzn) / total_mean_alt
    print(f'  Amazon basket vs cheapest-alt basket:  {pct(s_min, sign=True)}')
    print(f'  Amazon basket vs avg-alt basket:       {pct(s_mean, sign=True)}')
    print(f'  Per-product $ savings of Amazon vs cheapest non-Amazon alt:')
    print(f'    mean = ${mean(pp_dollar_diff):+,.2f}, median = ${median(pp_dollar_diff):+,.2f}')

    print(f'\n[Asymmetry]')
    if retailer_savings['Amazon']:
        print(f'  When Amazon at the floor: undercuts next-cheapest by '
              f'{pct(mean(retailer_savings["Amazon"]))} on average')
    if retailer_overhead['Amazon']:
        print(f'  When Amazon above the floor: sits {pct(mean(retailer_overhead["Amazon"]))} '
              f'above the cheapest on average')

    print(f'\nRetailer leaderboard (>= 3 appearances).')
    print(f'  {"retailer":<22} {"appears":>8} {"at-lowest":>10} {"strict":>8} {"vs avg alt":>11} {"wins by":>9} {"loses by":>9}')
    lb = sorted(retailer_app.items(), key=lambda x: -x[1])
    for r, a in lb:
        if a < 3: continue
        wins = retailer_at_lowest[r]; sw = retailer_strict[r]
        vs_avg = mean(retailer_vs_avg_alt[r]) if retailer_vs_avg_alt[r] else 0
        s_str = f"+{mean(retailer_savings[r])*100:.1f}%" if retailer_savings[r] else "—"
        o_str = f"+{mean(retailer_overhead[r])*100:.1f}%" if retailer_overhead[r] else "—"
        print(f'  {r:<22} {a:>8} {pct(wins/a):>10} {pct(sw/a):>8} {pct(vs_avg, sign=True):>11} {s_str:>9} {o_str:>9}')

    spreads = []
    for k, prices in comparable.items():
        lo = min(prices.values()); hi = max(prices.values())
        spreads.append((hi/lo - 1, k, dict(prices)))
    spreads.sort(reverse=True)
    pcts_only = [s[0] for s in spreads]
    print(f'\n[Spread] max retailer / min retailer per cross-section (n={len(pcts_only)})')
    print(f'  ({n_data_error} comparisons with >10x ratio excluded as JSON-LD typos)')
    print(f'  ({n_filtered_pm} groups had a price-per-month listing dropped)')
    print(f'  median = {pct(median(pcts_only))}')
    for q in [0.50, 0.75, 0.90, 0.95]:
        v = pcts_only[max(0, int((1-q)*len(pcts_only)) - 1)]
        print(f'  p{int(q*100):>2}    = {pct(v)}')

    print(f'\nLargest spreads:')
    for s, (slug, dt, product), prices in spreads[:13]:
        if s < 0.05: break
        print(f'  +{s*100:>5.0f}%  {product[:55]:<55}  [{slug}, {dt}]')
        for r, p in sorted(prices.items(), key=lambda x: x[1]):
            print(f'           ${p:>8.2f}  {r}')

    # ---- Markdown tables for key results ----
    print(f'\n{"="*82}')
    print('MARKDOWN TABLES (copy/paste ready)')
    print('='*82)

    print('\n**Table 1: Amazon Price Position**\n')
    print('| Metric | Count | Percentage |')
    print('|--------|-------|------------|')
    print(f'| Strictly cheapest | {amzn_strict} | {pct(amzn_strict/n_compare)} |')
    print(f'| Tied for cheapest | {amzn_tied} | {pct(amzn_tied/n_compare)} |')
    print(f'| Total at lowest | {at_low} | {pct(at_low/n_compare)} |')

    print('\n**Table 2: Amazon Pricing Asymmetry**\n')
    print('| Condition | Avg % Difference |')
    print('|-----------|------------------|')
    amzn_win_pct = pct(mean(retailer_savings['Amazon'])) if retailer_savings['Amazon'] else 'N/A'
    amzn_lose_pct = pct(mean(retailer_overhead['Amazon'])) if retailer_overhead['Amazon'] else 'N/A'
    print(f'| When winning (undercuts by) | {amzn_win_pct} |')
    print(f'| When losing (above cheapest by) | {amzn_lose_pct} |')

    print('\n**Table 3: Price Spread Distribution**\n')
    print('| Percentile | Spread |')
    print('|------------|--------|')
    print(f'| Median | {pct(median(pcts_only))} |')
    for q in [0.75, 0.90, 0.95]:
        v = pcts_only[max(0, int((1-q)*len(pcts_only)) - 1)]
        print(f'| P{int(q*100)} | {pct(v)} |')

    print('\n**Table 4: Retailer Leaderboard**\n')
    print('| Retailer | Appears | At Lowest | Wins By | Loses By |')
    print('|----------|---------|-----------|---------|----------|')
    for r, a in lb:
        if a < 3: continue
        wins = retailer_at_lowest[r]
        s_str = f"+{mean(retailer_savings[r])*100:.1f}%" if retailer_savings[r] else "—"
        o_str = f"+{mean(retailer_overhead[r])*100:.1f}%" if retailer_overhead[r] else "—"
        print(f'| {r} | {a} | {pct(wins/a)} | {s_str} | {o_str} |')

    # ---- Time-series detail for multi-snapshot articles ----
    print(f'\n{"="*82}')
    print(f'[Time series] Price evolution across snapshots (multi-snapshot articles)')
    print(f'{"="*82}')
    by_slug_dts = defaultdict(set)
    for (slug, dt, _) in obs_all: by_slug_dts[slug].add(dt)
    for slug in sorted(by_slug_dts):
        if len(by_slug_dts[slug]) < 2: continue
        prods = defaultdict(dict)  # product -> {dt: {retailer: price}}
        for (s, dt, prod), prices in obs_all.items():
            if s != slug: continue
            if len(prices) < 2: continue
            prods[prod][dt] = prices
        if not prods: continue
        # only show products with prices in ≥2 snapshots
        prods = {p: d for p, d in prods.items() if len(d) >= 2}
        if not prods: continue
        print(f'\n  {slug}:')
        for prod in sorted(prods):
            dts = sorted(prods[prod].keys())
            all_rs = set()
            for prices in prods[prod].values(): all_rs.update(prices.keys())
            print(f'    {prod[:60]}')
            for r in sorted(all_rs):
                line = f'      {r:<22}'
                for dt in dts:
                    p = prods[prod][dt].get(r)
                    line += f'  {dt[:7]}:${p:>7.2f}' if p else f'  {dt[:7]}:{"—":>8}'
                print(line)

if __name__ == '__main__':
    main()
