-- fact_invoice invariant: no row marked "paid" should have a null/negative
-- amount. Should always return 0 rows -- fact_invoice.status_clean already
-- reclassifies any has_bad_amount row to 'flagged_for_review', so a
-- 'paid' + bad-amount combination should be structurally impossible here.
-- The ~17 rows the generator injects with bad amounts are still fully
-- visible via status_clean = 'flagged_for_review', just not mislabelled
-- as paid revenue.
select *
from {{ ref('fact_invoice') }}
where status_clean = 'paid'
  and (amount is null or amount < 0)
