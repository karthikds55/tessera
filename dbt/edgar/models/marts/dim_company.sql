-- Company dimension (SCD2). `company_key` is a surrogate over the natural key
-- plus `valid_from`, so each historical version gets a stable, joinable key and
-- facts can point at the version that was current when they were filed.
with companies as (
    select * from {{ ref('int_company_scd') }}
)

select
    {{ dbt_utils.generate_surrogate_key(['cik', 'valid_from']) }} as company_key,
    cik,
    ticker,
    name,
    sic,
    industry,
    fiscal_year_end,
    state,
    valid_from,
    valid_to,
    is_current
from companies
