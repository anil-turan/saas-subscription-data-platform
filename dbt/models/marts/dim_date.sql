select
    cast(d as date) as date_day,
    extract(year from d) as year,
    extract(month from d) as month,
    extract(day from d) as day,
    extract(dow from d) as day_of_week,
    strftime(d, '%A') as day_name,
    strftime(d, '%B') as month_name,
    case when extract(dow from d) in (0, 6) then true else false end as is_weekend
from generate_series(
    cast('{{ var("pipeline_start_date") }}' as date),
    cast('{{ var("pipeline_end_date") }}' as date),
    interval 1 day
) as t(d)
