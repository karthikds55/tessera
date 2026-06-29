-- Clean the bronze ticker -> CIK directory. Tickers are upper-cased so joins
-- against user-supplied symbols are case-insensitive.
with source as (
    select * from {{ source('bronze', 'ticker_map') }}
)

select
    cast(cik as bigint)  as cik,
    upper(ticker)        as ticker,
    title                as company_title
from source
