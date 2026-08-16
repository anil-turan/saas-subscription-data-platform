-- One row per customer per day with product usage, temporal-joined to
-- dim_customer the same way fact_invoice is -- an event for a customer_id
-- never seen in any snapshot is excluded here too (event volume this small
-- from the synthetic generator makes a dedicated rejection table overkill,
-- unlike billing where every unresolved row has real financial meaning).
select
    ev.customer_id,
    cust.customer_key,
    ev.event_date,
    count(*) as event_count,
    count(distinct ev.event_type) as distinct_event_types,
    count(*) filter (where ev.event_type = 'login') as login_count,
    count(*) filter (where ev.event_type = 'api_call') as api_call_count
from {{ ref('stg_usage_events') }} as ev
left join {{ ref('int_customer_scd') }} as cust
    on ev.customer_id = cust.customer_id
    and ev.event_date >= cust.valid_from
    and (ev.event_date <= cust.valid_to or cust.valid_to is null)
where cust.customer_key is not null
group by ev.customer_id, cust.customer_key, ev.event_date
