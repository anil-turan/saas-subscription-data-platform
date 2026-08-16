-- Closes out each version's valid_to from the next version's valid_from,
-- and marks the open (most recent) version per customer as current.
select
    customer_id || '-' || cast(version_id as varchar) as customer_key,
    customer_id,
    name,
    email,
    company,
    plan_id,
    region,
    segment,
    signup_date,
    version_id,
    valid_from,
    cast(
        lead(valid_from) over (partition by customer_id order by version_id) - interval 1 day as date
    ) as valid_to,
    case
        when lead(valid_from) over (partition by customer_id order by version_id) is null then true
        else false
    end as is_current
from {{ ref('int_customer_history') }}
