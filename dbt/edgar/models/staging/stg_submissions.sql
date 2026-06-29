-- Clean the bronze submissions metadata into one tidy row per issuer. The
-- bronze `tickers`/`exchanges` columns are comma-separated (re-aggregated from
-- dlt child tables in landing.py); we surface the first entry as the primary
-- ticker/exchange and keep the raw lists for reference.
with source as (
    select * from {{ source('bronze', 'submissions') }}
)

select
    cast(cik as bigint)                                as cik,
    name                                               as company_name,
    nullif(split_part(tickers, ',', 1), '')            as primary_ticker,
    nullif(split_part(exchanges, ',', 1), '')          as primary_exchange,
    tickers                                            as tickers,
    exchanges                                          as exchanges,
    sic,
    sic_description,
    state_of_incorporation,
    fiscal_year_end
from source
