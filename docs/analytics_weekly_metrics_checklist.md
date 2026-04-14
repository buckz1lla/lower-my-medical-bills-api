# Weekly Analytics Checklist

Use this once per week to keep analytics reliable and actionable.

## Inputs

- Reporting window: last 7 days
- Data source: Supabase table `public.events`
- Query file: `docs/analytics_funnel_queries.sql`

## Weekly run sequence (10-15 minutes)

1. Confirm API is up.
   - `GET /health` returns healthy.
2. Confirm analytics endpoint access if key is enabled.
   - `GET /api/analytics/funnel-7d`
3. Run SQL Query 3 (aggregate funnel for date range).
4. Run SQL Query 4 (revenue summary).
5. Run SQL Query 6 (top affiliate links).
6. Run SQL Query 7 (deduped journey view) if event volume looks noisy.

## KPI scorecard to capture each week

- Results views
- Checkout started
- Payments
- Downloads
- Affiliate clicks
- Views to payment percent
- Payment to download percent
- Views to download percent
- Affiliate CTR percent
- Total revenue
- Average order value

## Data quality checks (must pass)

1. No impossible funnel pattern:
   - Payments should not regularly exceed checkouts.
2. Download behavior is plausible:
   - Downloads should be near payments, or explain gaps.
3. Event timestamp freshness:
   - New rows exist in `public.events` for current day.
4. Link click integrity:
   - `affiliate_link_clicked` has non-empty `href` for most rows.

## Alert thresholds (starter defaults)

Raise an investigation ticket if any condition is true:

- Views to payment percent drops by 30%+ week over week.
- Payment to download percent drops below 70%.
- Affiliate CTR drops below 3% for 2 consecutive weeks.
- Total weekly events fall by 40%+ with no traffic explanation.

## Weekly output template

Copy this into your notes every Friday:

```text
Week Ending: YYYY-MM-DD
Views:
Checkout Started:
Payments:
Downloads:
Affiliate Clicks:

Views->Payment %:
Payment->Download %:
Views->Download %:
Affiliate CTR %:

Total Revenue:
Average Order Value:

Top Affiliate Link:
Top Content/Source Driver:

Issues Found:
Actions for Next Week:
```

## Monthly improvement loop

At month end, select one funnel bottleneck and run one focused experiment:

- Low views to checkout: improve CTA clarity and value framing.
- Low checkout to payment: simplify checkout copy and trust signals.
- Low payment to download: investigate fulfillment latency or download UX.
- Low affiliate CTR: improve recommendation relevance and card placement.