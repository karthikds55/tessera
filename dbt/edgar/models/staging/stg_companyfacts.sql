-- Clean + rename the bronze company_facts grain. One row per reported XBRL
-- value; no filtering or normalization happens here (that is int_facts_*),
-- only typing and consistent naming so downstream SQL reads clearly.
with source as (
    select * from {{ source('bronze', 'company_facts') }}
)

select
    cast(cik as bigint)        as cik,
    taxonomy,
    raw_tag,
    unit,
    cast(value as double)      as value,
    cast(fy as integer)        as fiscal_year,
    fp                         as fiscal_period,
    form,
    frame,
    accn                       as accession_number,
    cast("start" as date)      as period_start,
    cast("end" as date)        as period_end,
    cast(filed as date)        as filed_date
from source
