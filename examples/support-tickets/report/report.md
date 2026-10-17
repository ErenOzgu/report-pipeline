# Support tickets

**2026-09** compared with 2026-08. Source: `tickets.csv`, 1,142 rows used (224 in the period), sha256 `bd9828c4f67b`.

## Summary

Tickets opened: 224 in 2026-09, up 9.8% from 204 in 2026-08. Customers who wrote in: 111 in 2026-09, up 6.7% from 104 in 2026-08. Median time to resolve: 12.1 h in 2026-09, down 14.2% from 14.1 h in 2026-08. Time to resolve, 90th percentile: 56.1 h in 2026-09, down 16.9% from 67.5 h in 2026-08. Tickets that took over 24 h: 31.3% in 2026-09, down 3.1 pp from 34.3% in 2026-08. Average satisfaction (1 to 5): 3.89 in 2026-09, up 10.3% from 3.53 in 2026-08. The largest category is Billing with 81 (36.2% of the total). The largest channel is Email with 118 (52.7% of the total).

_Written by rules from the figures below._

## Key numbers

| Metric | 2026-09 | 2026-08 | Change |
|---|---:|---:|---:|
| Tickets opened | 224 | 204 | +9.8% |
| Customers who wrote in | 111 | 104 | +6.7% |
| Median time to resolve | 12.1 h | 14.1 h | -14.2% |
| Time to resolve, 90th percentile | 56.1 h | 67.5 h | -16.9% |
| Tickets that took over 24 h | 31.3% | 34.3% | -3.1 pp |
| Average satisfaction (1 to 5) | 3.89 | 3.53 | +10.3% |

## Trend

| Metric | 2026-04 | 2026-05 | 2026-06 | 2026-07 | 2026-08 | 2026-09 |
|---|---:|---:|---:|---:|---:|---:|
| Tickets opened | 168 | 180 | 190 | 176 | 204 | 224 |
| Customers who wrote in | 90 | 102 | 96 | 93 | 104 | 111 |
| Median time to resolve | 11.9 h | 13.6 h | 12.6 h | 12.4 h | 14.1 h | 12.1 h |
| Time to resolve, 90th percentile | 72.1 h | 67.8 h | 59.1 h | 57.4 h | 67.5 h | 56.1 h |
| Tickets that took over 24 h | 28.0% | 36.7% | 27.4% | 27.8% | 34.3% | 31.3% |
| Average satisfaction (1 to 5) | 3.51 | 3.60 | 3.55 | 3.71 | 3.53 | 3.89 |

## By category

| Category | Tickets opened | Median time to resolve | Tickets that took over 24 h | Share |
|---|---:|---:|---:|---:|
| Billing | 81 | 9.7 h | 17.3% | 36.2% |
| Bug report | 44 | 31.7 h | 65.9% | 19.6% |
| Login | 35 | 3.8 h | 0.0% | 15.6% |
| Performance | 28 | 19.9 h | 42.9% | 12.5% |
| Feature request | 20 | 36.5 h | 75.0% | 8.9% |
| Other | 16 | 6.9 h | 0.0% | 7.1% |

## By channel

| Channel | Tickets opened | Average satisfaction (1 to 5) | Share |
|---|---:|---:|---:|
| Email | 118 | 3.88 | 52.7% |
| Chat | 73 | 3.85 | 32.6% |
| Phone | 33 | 4.05 | 14.7% |

## Data notes

- 2 rows have no usable 'opened' and were left out (first at lines 1147, 1148).
- 3 rows repeat an earlier 'ticket_id' and were left out (first at lines 533, 725, 933).
- 6 values in 'resolution_hours' could not be read as a number and were treated as empty (first at lines 72, 74, 79).
- 443 rows have an empty 'satisfaction'.

## How the numbers were computed

- **Tickets opened**: number of rows.
- **Customers who wrote in**: number of different values of `customer`.
- **Median time to resolve**: median of `resolution_hours`.
- **Time to resolve, 90th percentile**: 90th percentile of `resolution_hours`.
- **Tickets that took over 24 h**: share of rows where resolution_hours > 24, in percent of all rows of the period.
- **Average satisfaction (1 to 5)**: mean of `satisfaction`.

Periods are calendar months of `opened`. The change compares with the period just before. Percentiles interpolate linearly between ranks. Figures are rounded half up.
