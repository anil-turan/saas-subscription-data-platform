-- Quarantine table for invoices int_invoice_resolved could not match to
-- any dim_customer version. Kept visible and queryable rather than
-- silently dropped from the pipeline, and classified into the two distinct
-- root causes -- these need different fixes, so collapsing them into one
-- generic "unresolved" bucket would hide that:
--   orphan_customer_id      -- customer_id never appears in any CRM
--                              snapshot at all (a deleted/test account,
--                              or a billing-system-only customer)
--   invoice_predates_scd_coverage -- customer_id exists, but every SCD2
--                              version for them starts after invoice_date
--                              (late-arriving / backfilled billing data)
select
    r.invoice_id,
    r.customer_id,
    r.plan_id,
    r.invoice_date,
    r.amount,
    r.status,
    case
        when known.customer_id is null then 'orphan_customer_id'
        else 'invoice_predates_scd_coverage'
    end as rejection_reason
from {{ ref('int_invoice_resolved') }} as r
left join (
    select distinct customer_id from {{ ref('int_customer_scd') }}
) as known
    on r.customer_id = known.customer_id
where r.customer_key is null
