# Wirecutter Price Dispersion Analysis

Analysis of price variation across retailers listed in Wirecutter product recommendations.

## Key Findings

**Scope caveat:** These findings reflect prices among retailers that Wirecutter chose to list—typically major retailers with affiliate programs. The analysis cannot speak to prices at unlisted retailers.

### Amazon Price Position

Among 536 products where Amazon was listed alongside at least one other retailer:

| Metric | Value |
|--------|-------|
| At lowest price (total) | 67.0% |
| — Strictly cheapest | 40.3% |
| — Tied for cheapest | 26.7% |
| Basket cost vs. always-cheapest | +1.0% |

Amazon is at or near the lowest listed price most of the time. A consumer buying all 536 products at Amazon would pay about 1% more than one who always picked the cheapest listed retailer.

### Pricing Asymmetry

| Condition | Avg. gap to next price |
|-----------|------------------------|
| When Amazon is cheapest | Undercuts by 10.4% |
| When Amazon is not cheapest | Sits 24.0% above floor |

Amazon's losses are proportionally larger than its wins—when it's not the cheapest, it tends to be meaningfully more expensive.

### Price Spreads Across Retailers

| Percentile | Spread (max/min − 1) |
|------------|---------------------|
| Median (p50) | 8.6% |
| p75 | 25.0% |
| p90 | 47.3% |
| p95 | 63.0% |

One in ten products has a price spread exceeding 47% across listed retailers.

### Retailer Comparison

Top retailers by frequency of appearance:

| Retailer | Appearances | At Lowest | Strictly Cheapest |
|----------|-------------|-----------|-------------------|
| Amazon | 536 | 67.0% | 40.3% |
| Walmart | 265 | 55.5% | 29.8% |
| Best Buy | 132 | 37.1% | 21.2% |
| REI | 48 | 47.9% | 25.0% |
| Wayfair | 48 | 39.6% | 18.8% |
| Home Depot | 30 | 33.3% | 16.7% |

## Data

- **Source:** Wirecutter articles via Internet Archive (Wayback Machine)
- **Date range:** 2021-05-01 to 2026-05-02
- **Articles:** 73
- **Products:** 631 total (536 with Amazon + at least one other retailer)
- **Snapshots:** 70 distinct dates

## Methodology

For each article, the analysis uses the latest snapshot per (article, product) pair. Prices are extracted from JSON-LD structured data embedded in Wirecutter pages.

Exclusions:
- Refurbished products
- Bundles
- Price-per-month listings
- Extreme outliers (>10x ratio, likely JSON-LD typos)

## Running the Analysis

```bash
python3 scripts/analyze.py
```
