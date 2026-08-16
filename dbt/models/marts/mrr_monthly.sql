-- Monthly Recurring Revenue: paid invoices only (status_clean = 'paid'
-- excludes the amount-flagged rows on purpose -- a flagged-for-review
-- amount should never silently count toward a revenue number until a
-- human resolves it), by plan and segment.
select
    date_trunc('month', f.invoice_date) as invoice_month,
    p.plan_name,
    p.tier,
    c.segment,
    count(distinct f.customer_id) as paying_customers,
    sum(f.amount) as mrr,
    round(sum(f.amount) / nullif(count(distinct f.customer_id), 0), 2) as arpu
from {{ ref('fact_invoice') }} as f
join {{ ref('dim_plan') }} as p on f.plan_id = p.plan_id
join {{ ref('dim_customer') }} as c on f.customer_key = c.customer_key
where f.status_clean = 'paid'
group by date_trunc('month', f.invoice_date), p.plan_name, p.tier, c.segment
order by invoice_month, p.tier
