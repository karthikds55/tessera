# Data model

The data model centers on **concept normalization**: a version-controlled seed maps the many raw
XBRL tags issuers use into a small set of governed standard concepts.

## Normalization seed — `concept_map.csv`

The single source of normalization truth. Lives at `dbt/edgar/seeds/concept_map.csv` and is joined
in the intermediate layer. Columns:

| Column            | Meaning                                                        |
| ----------------- | -------------------------------------------------------------- |
| `raw_tag`         | The XBRL tag as filed (e.g. `RevenueFromContractWithCustomerExcludingAssessedTax`). |
| `taxonomy`        | Source taxonomy (`us-gaap`).                                   |
| `standard_concept`| Governed concept (`revenue`, `net_income`, `total_assets`, …).|
| `sign`            | `+1`/`-1` multiplier to align sign conventions.               |
| `notes`           | Provenance / era (e.g. "ASC 606 era", "legacy").              |

Example rows:

```
raw_tag,taxonomy,standard_concept,sign,notes
RevenueFromContractWithCustomerExcludingAssessedTax,us-gaap,revenue,1,ASC 606 era
Revenues,us-gaap,revenue,1,legacy
SalesRevenueNet,us-gaap,revenue,1,legacy
NetIncomeLoss,us-gaap,net_income,1,
Assets,us-gaap,total_assets,1,instant
StockholdersEquity,us-gaap,total_equity,1,instant
Liabilities,us-gaap,total_liabilities,1,instant
```

## Tables

### `dim_company` (SCD2)
One row per company per attribute-version.

`company_key`, `cik`, `ticker`, `name`, `sic`, `industry`, `fiscal_year_end`, `state`,
`valid_from`, `valid_to`, `is_current`.

### `fct_financials` (long)
Grain = one standardized fact.

`cik`, `fiscal_year`, `fiscal_period`, `standard_concept`, `value`, `unit`, `form`, `frame`,
`accn` (accession number).

### `mart_fundamentals_annual` (wide)
Grain = company-year.

Base concepts: `revenue`, `net_income`, `total_assets`, `total_equity`, `total_liabilities`.
Derived metrics: `net_margin`, `roa`, `roe`, `debt_to_equity`, `revenue_growth_yoy`.

## Quality rules (encoded as dbt / Soda tests)

- **Uniqueness** on each grain; **not-null** on keys.
- **Referential integrity**: every fact's `cik` exists in `dim_company`.
- **Accepted range**: `net_margin` within sane bounds — outliers are flagged, not dropped.
- **Freshness**: the latest `fiscal_year` is within an expected window.
- **Coverage**: every raw revenue-like tag in the source maps to a `standard_concept` — no silent
  drops. Unmapped tags surface as a failing test rather than vanishing.
