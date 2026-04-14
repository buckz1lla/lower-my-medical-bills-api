-- Analytics query pack for Supabase SQL Editor
-- Table: public.events
-- Timezone note: convert timestamps with AT TIME ZONE if you want local business-day reporting.

-- =============================================
-- 1) Stage counts for a date range
-- =============================================
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
)
select
  e.event_name,
  count(*) as event_count
from public.events e
cross join params p
where e.timestamp >= p.start_date
  and e.timestamp < (p.end_date + interval '1 day')
  and e.event_name in (
    'results_page_viewed',
    'checkout_started',
    'payment_completed',
    'pdf_downloaded',
    'affiliate_link_clicked'
  )
group by e.event_name
order by event_count desc;


-- =============================================
-- 2) Daily funnel with conversion rates
-- =============================================
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
),
daily as (
  select
    date_trunc('day', e.timestamp)::date as day,
    count(*) filter (where e.event_name = 'results_page_viewed') as views,
    count(*) filter (where e.event_name = 'checkout_started') as checkout_started,
    count(*) filter (where e.event_name = 'payment_completed') as payments,
    count(*) filter (where e.event_name = 'pdf_downloaded') as downloads,
    count(*) filter (where e.event_name = 'affiliate_link_clicked') as affiliate_clicks
  from public.events e
  cross join params p
  where e.timestamp >= p.start_date
    and e.timestamp < (p.end_date + interval '1 day')
  group by 1
)
select
  day,
  views,
  checkout_started,
  payments,
  downloads,
  affiliate_clicks,
  round((payments::numeric / nullif(views, 0)) * 100, 2) as views_to_payment_pct,
  round((downloads::numeric / nullif(payments, 0)) * 100, 2) as payment_to_download_pct,
  round((downloads::numeric / nullif(views, 0)) * 100, 2) as views_to_download_pct,
  round((affiliate_clicks::numeric / nullif(views, 0)) * 100, 2) as affiliate_ctr_pct
from daily
order by day;


-- =============================================
-- 3) Aggregate funnel for a date range
-- =============================================
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
),
counts as (
  select
    count(*) filter (where e.event_name = 'results_page_viewed') as views,
    count(*) filter (where e.event_name = 'checkout_started') as checkout_started,
    count(*) filter (where e.event_name = 'payment_completed') as payments,
    count(*) filter (where e.event_name = 'pdf_downloaded') as downloads,
    count(*) filter (where e.event_name = 'affiliate_link_clicked') as affiliate_clicks
  from public.events e
  cross join params p
  where e.timestamp >= p.start_date
    and e.timestamp < (p.end_date + interval '1 day')
)
select
  views,
  checkout_started,
  payments,
  downloads,
  affiliate_clicks,
  round((checkout_started::numeric / nullif(views, 0)) * 100, 2) as views_to_checkout_pct,
  round((payments::numeric / nullif(checkout_started, 0)) * 100, 2) as checkout_to_payment_pct,
  round((payments::numeric / nullif(views, 0)) * 100, 2) as views_to_payment_pct,
  round((downloads::numeric / nullif(payments, 0)) * 100, 2) as payment_to_download_pct,
  round((downloads::numeric / nullif(views, 0)) * 100, 2) as views_to_download_pct,
  round((affiliate_clicks::numeric / nullif(views, 0)) * 100, 2) as affiliate_ctr_pct
from counts;


-- =============================================
-- 4) Revenue summary from payment events
-- =============================================
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
),
payments as (
  select
    e.timestamp,
    e.analysis_id,
    coalesce((e.event_data ->> 'amount')::numeric, 0) as amount,
    e.event_data ->> 'price_variant' as price_variant
  from public.events e
  cross join params p
  where e.timestamp >= p.start_date
    and e.timestamp < (p.end_date + interval '1 day')
    and e.event_name = 'payment_completed'
)
select
  count(*) as payment_count,
  round(coalesce(sum(amount), 0), 2) as total_revenue,
  round(coalesce(avg(amount), 0), 2) as average_order_value,
  round(coalesce(percentile_cont(0.5) within group (order by amount), 0), 2) as median_order_value
from payments;


-- =============================================
-- 5) Price variant performance
-- =============================================
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
),
base as (
  select
    coalesce(nullif(lower(e.event_data ->> 'price_variant'), ''), 'unknown') as price_variant,
    e.event_name,
    coalesce((e.event_data ->> 'amount')::numeric, 0) as amount
  from public.events e
  cross join params p
  where e.timestamp >= p.start_date
    and e.timestamp < (p.end_date + interval '1 day')
    and e.event_name in ('results_page_viewed', 'checkout_started', 'payment_completed')
)
select
  price_variant,
  count(*) filter (where event_name = 'results_page_viewed') as views,
  count(*) filter (where event_name = 'checkout_started') as checkout_started,
  count(*) filter (where event_name = 'payment_completed') as payments,
  round(sum(amount) filter (where event_name = 'payment_completed'), 2) as revenue,
  round((count(*) filter (where event_name = 'checkout_started')::numeric / nullif(count(*) filter (where event_name = 'results_page_viewed'), 0)) * 100, 2) as views_to_checkout_pct,
  round((count(*) filter (where event_name = 'payment_completed')::numeric / nullif(count(*) filter (where event_name = 'checkout_started'), 0)) * 100, 2) as checkout_to_payment_pct,
  round((count(*) filter (where event_name = 'payment_completed')::numeric / nullif(count(*) filter (where event_name = 'results_page_viewed'), 0)) * 100, 2) as views_to_payment_pct
from base
group by price_variant
order by price_variant;


-- =============================================
-- 6) Top affiliate links by click volume
-- =============================================
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
)
select
  coalesce(e.event_data ->> 'linkType', 'unknown') as link_type,
  coalesce(e.event_data ->> 'href', 'unknown') as href,
  count(*) as clicks
from public.events e
cross join params p
where e.timestamp >= p.start_date
  and e.timestamp < (p.end_date + interval '1 day')
  and e.event_name = 'affiliate_link_clicked'
group by 1, 2
order by clicks desc
limit 25;


-- =============================================
-- 7) User-journey dedupe by analysis/session key
-- =============================================
-- Use this when raw events may include duplicates from retries or refreshes.
with params as (
  select
    date '2026-04-01' as start_date,
    date '2026-04-30' as end_date
),
journeys as (
  select
    coalesce(nullif(e.analysis_id, ''), nullif(e.session_id, ''), e.id::text) as journey_id,
    max(case when e.event_name = 'results_page_viewed' then 1 else 0 end) as has_view,
    max(case when e.event_name = 'checkout_started' then 1 else 0 end) as has_checkout,
    max(case when e.event_name = 'payment_completed' then 1 else 0 end) as has_payment,
    max(case when e.event_name = 'pdf_downloaded' then 1 else 0 end) as has_download,
    max(case when e.event_name = 'affiliate_link_clicked' then 1 else 0 end) as has_affiliate_click
  from public.events e
  cross join params p
  where e.timestamp >= p.start_date
    and e.timestamp < (p.end_date + interval '1 day')
  group by 1
)
select
  count(*) filter (where has_view = 1) as journeys_with_view,
  count(*) filter (where has_checkout = 1) as journeys_with_checkout,
  count(*) filter (where has_payment = 1) as journeys_with_payment,
  count(*) filter (where has_download = 1) as journeys_with_download,
  count(*) filter (where has_affiliate_click = 1) as journeys_with_affiliate_click,
  round((count(*) filter (where has_payment = 1)::numeric / nullif(count(*) filter (where has_view = 1), 0)) * 100, 2) as deduped_views_to_payment_pct,
  round((count(*) filter (where has_download = 1)::numeric / nullif(count(*) filter (where has_payment = 1), 0)) * 100, 2) as deduped_payment_to_download_pct
from journeys;