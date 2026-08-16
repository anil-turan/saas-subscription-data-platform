-- Reconstructs SCD Type 2 versions from 14 pre-collected daily snapshot
-- files -- NOT the same problem dbt's `snapshot` block solves. `snapshot`
-- captures the CURRENT state of a live source once per real dbt
-- invocation, accumulating history over days/weeks of repeated runs; here
-- the history already exists as daily extracts sitting in one raw table,
-- and needs to be compressed into versions in a single pass. That's the
-- classic "gaps and islands" pattern: detect the days where a customer's
-- tracked attributes changed from the previous day, then group consecutive
-- unchanged days into one version.
with ordered as (
    select
        customer_id,
        name,
        email,
        company,
        plan_id,
        region,
        segment,
        signup_date,
        snapshot_date,
        lag(plan_id) over (partition by customer_id order by snapshot_date) as prev_plan_id,
        lag(region) over (partition by customer_id order by snapshot_date) as prev_region,
        lag(segment) over (partition by customer_id order by snapshot_date) as prev_segment
    from {{ ref('stg_customers') }}
),

flagged as (
    select
        *,
        case
            when prev_plan_id is null then 1 -- first observation for this customer
            when plan_id != prev_plan_id or region != prev_region or segment != prev_segment then 1
            else 0
        end as is_new_version
    from ordered
),

-- running sum of the change flag turns "islands" of unchanged consecutive
-- days into a single group id per customer
grouped as (
    select
        *,
        sum(is_new_version) over (
            partition by customer_id order by snapshot_date
            rows between unbounded preceding and current row
        ) as version_id
    from flagged
)

select
    customer_id,
    name,
    email,
    company,
    plan_id,
    region,
    segment,
    signup_date,
    version_id,
    min(snapshot_date) as valid_from,
    max(snapshot_date) as last_seen_date
from grouped
group by
    customer_id, name, email, company, plan_id, region, segment, signup_date, version_id
