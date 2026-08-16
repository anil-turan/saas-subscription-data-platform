-- One row per (customer_id, snapshot_date) -- the raw material
-- int_customer_history compresses into SCD Type 2 versions.
select
    customer_id,
    name,
    email,
    company,
    plan_id,
    region,
    segment,
    cast(signup_date as date) as signup_date,
    cast(snapshot_date as date) as snapshot_date
from {{ source('raw', 'crm_customers') }}
