-- fact_invoice invariant: every row must have a valid customer_key --
-- fact_invoice.sql already filters to `where customer_key is not null`,
-- so this should always return 0 rows. The genuinely orphan/late-arriving
-- invoices the generator injects (~29 of them) are not missing from the
-- pipeline -- see fact_invoice_rejected, which is where this test's
-- "failing" rows would show up if the filter in fact_invoice.sql were
-- ever accidentally removed.
select *
from {{ ref('fact_invoice') }}
where customer_key is null
