-- Slowly-changing-dimension (type 2) shaping of issuer metadata.
--
-- The bronze submissions feed is a current snapshot (one merged row per CIK),
-- so today every issuer resolves to a single open-ended current version. The
-- model is written as SCD2 from the start — `valid_from` / `valid_to` /
-- `is_current` — so that once submissions are historized (snapshots in a later
-- PR) change detection slots in without reshaping dim_company or its key.
with submissions as (
    select * from {{ ref('stg_submissions') }}
)

select
    cik,
    primary_ticker          as ticker,
    company_name            as name,
    sic,
    sic_description         as industry,
    fiscal_year_end,
    state_of_incorporation  as state,
    -- Open-ended validity for the current snapshot. A sentinel start date keeps
    -- the surrogate key stable until real effective dates are available.
    cast('1900-01-01' as date)  as valid_from,
    cast(null as date)          as valid_to,
    true                        as is_current
from submissions
