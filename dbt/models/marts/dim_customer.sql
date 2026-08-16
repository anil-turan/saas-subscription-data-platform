select
    customer_key,
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
    valid_to,
    is_current
from {{ ref('int_customer_scd') }}
