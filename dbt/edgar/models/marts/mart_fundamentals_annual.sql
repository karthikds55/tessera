-- Wide, analyst-friendly company-year table: the screener mart.
--
-- Pivots the annual (fiscal-period = FY) standardized facts into one row per
-- company-year with each standard concept as a column, then layers on derived
-- ratios. Every concept is pivoted with a conditional aggregate, so a company-
-- year missing a concept yields NULL (never an error), and the ratios guard
-- against NULL / zero denominators so they degrade to NULL rather than blow up.
with annual as (
    select *
    from {{ ref('fct_financials') }}
    where fiscal_period = 'FY'
),

pivoted as (
    select
        cik,
        fiscal_year,
        max(case when standard_concept = 'revenue' then value end)            as revenue,
        max(case when standard_concept = 'net_income' then value end)         as net_income,
        max(case when standard_concept = 'total_assets' then value end)       as total_assets,
        max(case when standard_concept = 'total_equity' then value end)       as total_equity,
        max(case when standard_concept = 'total_liabilities' then value end)  as total_liabilities
    from annual
    group by cik, fiscal_year
),

with_growth as (
    select
        *,
        lag(revenue) over (partition by cik order by fiscal_year) as prev_revenue
    from pivoted
)

select
    g.cik,
    dim.company_key,
    dim.ticker,
    dim.name,
    dim.industry,
    g.fiscal_year,
    g.revenue,
    g.net_income,
    g.total_assets,
    g.total_equity,
    g.total_liabilities,
    -- Derived ratios — NULL-safe: any missing or zero denominator yields NULL.
    case when g.revenue is not null and g.revenue <> 0
        then g.net_income / g.revenue end                       as net_margin,
    case when g.total_assets is not null and g.total_assets <> 0
        then g.net_income / g.total_assets end                  as roa,
    case when g.total_equity is not null and g.total_equity <> 0
        then g.net_income / g.total_equity end                  as roe,
    case when g.total_equity is not null and g.total_equity <> 0
        then g.total_liabilities / g.total_equity end           as debt_to_equity,
    case when g.prev_revenue is not null and g.prev_revenue <> 0
        then (g.revenue - g.prev_revenue) / g.prev_revenue end  as revenue_growth_yoy
from with_growth g
left join {{ ref('dim_company') }} dim
    on g.cik = dim.cik
   and dim.is_current
