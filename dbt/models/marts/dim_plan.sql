select
    plan_id,
    plan_name,
    monthly_price,
    tier
from {{ ref('stg_plans') }}
