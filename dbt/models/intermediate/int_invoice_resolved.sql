-- Resolves each invoice to the dim_customer version that was valid on its
-- invoice_date (a temporal join, not a plain equi-join on customer_id) --
-- catches two distinct failure modes as customer_key = null:
--   1. customer_id never appears in any CRM snapshot at all (genuine orphan)
--   2. customer_id exists, but invoice_date predates their earliest SCD2
--      coverage (late-arriving / backfilled billing data)
select
    inv.invoice_id,
    inv.customer_id,
    inv.plan_id,
    inv.invoice_date,
    inv.amount,
    inv.status,
    inv.has_bad_amount,
    cust.customer_key
from {{ ref('stg_invoices') }} as inv
left join {{ ref('int_customer_scd') }} as cust
    on inv.customer_id = cust.customer_id
    and inv.invoice_date >= cust.valid_from
    and (inv.invoice_date <= cust.valid_to or cust.valid_to is null)
