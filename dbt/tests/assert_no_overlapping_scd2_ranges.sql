-- dim_customer correctness invariant: no customer should ever have two SCD2
-- versions whose [valid_from, valid_to] ranges overlap. This should always
-- return 0 rows by construction (int_customer_scd derives valid_to from the
-- next version's valid_from) -- a passing invariant check, not a
-- bad-data-catch demo like the other two custom tests in this directory.
select
    a.customer_id,
    a.version_id as version_a,
    a.valid_from as a_valid_from,
    a.valid_to as a_valid_to,
    b.version_id as version_b,
    b.valid_from as b_valid_from,
    b.valid_to as b_valid_to
from {{ ref('dim_customer') }} as a
join {{ ref('dim_customer') }} as b
    on a.customer_id = b.customer_id
    and a.version_id < b.version_id
where a.valid_from <= coalesce(b.valid_to, date '9999-12-31')
  and b.valid_from <= coalesce(a.valid_to, date '9999-12-31')
