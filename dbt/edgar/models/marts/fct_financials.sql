-- Long-grain fact table: exactly one standardized value per
-- (company, fiscal year, fiscal period, standard concept).
--
-- A single concept can be reported many times for the same period — across
-- amended filings, multiple units, or restatements. We pick one authoritative
-- value per grain: prefer USD, then the most recently filed, then the highest
-- accession number as a deterministic tie-break.
with normalized as (
    select *
    from {{ ref('int_facts_normalized') }}
    where fiscal_year is not null
      and fiscal_period is not null
),

ranked as (
    select
        *,
        row_number() over (
            partition by cik, fiscal_year, fiscal_period, standard_concept
            order by
                case when unit = 'USD' then 0 else 1 end,
                filed_date desc,
                accession_number desc
        ) as row_rank
    from normalized
),

deduped as (
    select * from ranked where row_rank = 1
)

select
    {{ dbt_utils.generate_surrogate_key(
        ['cik', 'fiscal_year', 'fiscal_period', 'standard_concept']
    ) }} as financial_key,
    d.cik,
    dim.company_key,
    d.fiscal_year,
    d.fiscal_period,
    d.standard_concept,
    d.unit,
    d.value,
    d.form,
    d.period_start,
    d.period_end,
    d.filed_date
from deduped d
left join {{ ref('dim_company') }} dim
    on d.cik = dim.cik
   and dim.is_current
