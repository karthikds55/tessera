-- ============================================================================
-- Where XBRL tagging chaos becomes governed concepts.
--
-- Companies report the same economic fact under many raw tags (e.g. revenue as
-- `Revenues`, `SalesRevenueNet`, or one of the ASC-606 tags). The version-
-- controlled `concept_map` seed is the single source of truth for which raw tag
-- rolls up to which `standard_concept` and with what `sign`.
--
-- The INNER JOIN deliberately drops facts whose raw tag is not in the map, so a
-- mart never silently mixes in an unmapped tag. Coverage gaps are not hidden:
-- the singular test `assert_revenue_tags_mapped` flags revenue-like tags that
-- fall through, so the seed can be extended on purpose rather than by accident.
-- ============================================================================
with facts as (
    select * from {{ ref('stg_companyfacts') }}
),

concept_map as (
    select * from {{ ref('concept_map') }}
)

select
    f.cik,
    f.fiscal_year,
    f.fiscal_period,
    f.form,
    f.unit,
    f.accession_number,
    f.filed_date,
    f.period_start,
    f.period_end,
    f.raw_tag,
    m.standard_concept,
    -- `sign` flips contra-style tags into their economic direction; for the
    -- current concept set it is always +1, but applying it keeps the seed the
    -- only place sign logic ever lives.
    f.value * m.sign as value
from facts f
inner join concept_map m
    on f.raw_tag = m.raw_tag
   and f.taxonomy = m.taxonomy
