-- Only fully-resolved invoices (a valid dim_customer key at invoice_date)
-- land here -- the star schema's fact table should never carry a broken
-- foreign key. Unresolved rows aren't dropped, just routed to
-- fact_invoice_rejected (see that model) for investigation.
--
-- A bad amount (null/negative) does NOT get quarantined the same way --
-- it's a real invoice for a real, resolved customer, so it stays visible
-- here with status_clean overriding the raw status to make the problem
-- impossible to miss in any downstream aggregation.
select
    invoice_id,
    customer_key,
    customer_id,
    plan_id,
    invoice_date,
    amount,
    status,
    case when has_bad_amount then 'flagged_for_review' else status end as status_clean,
    has_bad_amount
from {{ ref('int_invoice_resolved') }}
where customer_key is not null
