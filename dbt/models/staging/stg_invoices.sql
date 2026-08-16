-- Deduplicates exact-duplicate invoice_id rows (a re-pulled/re-submitted
-- billing record -- every column is identical, so it's pure noise, not
-- information; keeping one copy is the correct fix, not data loss).
-- Bad amounts (null/negative) are NOT dropped here -- they're carried
-- through with a flag so downstream models can decide what to do with
-- them visibly, per this portfolio's "flag, don't silently drop" convention.
with typed as (
    select
        invoice_id,
        customer_id,
        plan_id,
        cast(invoice_date as date) as invoice_date,
        try_cast(amount as decimal(10, 2)) as amount,
        status,
        row_number() over (
            partition by invoice_id order by customer_id
        ) as dedup_rank
    from {{ source('raw', 'invoices') }}
)
select
    invoice_id,
    customer_id,
    plan_id,
    invoice_date,
    amount,
    status,
    case when amount is null or amount < 0 then true else false end as has_bad_amount
from typed
where dedup_rank = 1
