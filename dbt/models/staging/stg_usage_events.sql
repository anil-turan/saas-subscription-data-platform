select
    event_id,
    customer_id,
    event_type,
    cast(event_timestamp as timestamp) as event_timestamp,
    cast(event_timestamp as date) as event_date,
    feature_used
from {{ source('raw', 'usage_events') }}
