-- Coverage guard (warn): surface revenue-like raw tags present in the bronze
-- facts that the concept_map seed does NOT map to a standard_concept.
--
-- This is the "no silent drops" tripwire for the most important line item:
-- int_facts_normalized drops unmapped tags, and this test makes any dropped
-- revenue-like tag visible so the seed can be extended deliberately. It is a
-- WARNING, not an error, so a newly-seen subtotal flags for review without
-- breaking the build.
{{ config(severity='warn') }}

with revenue_like as (
    select distinct raw_tag, taxonomy
    from {{ ref('stg_companyfacts') }}
    where taxonomy = 'us-gaap'
      and (lower(raw_tag) like '%revenue%' or lower(raw_tag) like '%salesrevenue%')
),

mapped as (
    select raw_tag, taxonomy
    from {{ ref('concept_map') }}
    where standard_concept = 'revenue'
)

select r.raw_tag, r.taxonomy
from revenue_like r
left join mapped m
    on r.raw_tag = m.raw_tag
   and r.taxonomy = m.taxonomy
where m.raw_tag is null
