# Sample scores

Rows: 25

| request | amount (ours / truth) | status | method | plan | earliest | changes |
|---|---|---|---|---|---|---|
| request_01 | 25256 / 25256 ok | ok | ok | ok | ok | ok |
| request_02 | 18336765.48 / 17229139.2 **x** | ok | ok | ok | ok | ok |
| request_03 | 971737 / 873000 **x** | ok | ok | ok | ok | ok |
| request_04 | 10609286.07 / 8401800 **x** | ok | ok | ok | ok | ok |
| request_05 | 0 / 737 **x** | ok | ok | ok | ok | ok |
| request_06 | 523.84 / 603.3 **x** | **x** | **x** | **x** | ok | **x** |
| request_07 | 86237.21 / 87170.56 ok | ok | ok | ok | **x** | ok |
| request_08 | 285.2 / 284.57 ok | **x** | **x** | **x** | **x** | ok |
| request_09 | 166.61 / 166.61 ok | ok | ok | ok | ok | ok |
| request_10 | 0 / 12700 **x** | ok | ok | ok | ok | ok |
| request_11 | 12319866.62 / 12510645 ok | ok | ok | ok | **x** | **x** |
| request_12 | 60370.25 / 65164 **x** | ok | ok | ok | **x** | **x** |
| request_13 | 490.8 / 433.4 **x** | **x** | **x** | **x** | **x** | ok |
| request_14 | 616.29 / 597.74 **x** | ok | ok | ok | ok | ok |
| request_15 | 0 / 83.05 **x** | ok | ok | ok | ok | ok |
| request_16 | 122500 / 122500 ok | ok | ok | ok | ok | ok |
| request_17 | 240519.41 / 243849.58 ok | ok | ok | ok | **x** | ok |
| request_18 | 546.05 / 462 **x** | ok | ok | ok | ok | ok |
| request_19 | 30022.77 / 28820 **x** | ok | ok | **x** | ok | ok |
| request_20 | 8969.68 / 5400 **x** | ok | ok | ok | ok | ok |
| request_21 | 1574.4 / 1543.35 **x** | **x** | ok | ok | **x** | **x** |
| request_22 | 464.61 / 475.46 **x** | ok | ok | ok | ok | ok |
| request_23 | 8360.18 / 9152 **x** | ok | ok | ok | ok | ok |
| request_24 | 13539.29 / 13420 ok | ok | ok | ok | ok | ok |
| request_25 | 376083.41 / 1425000 **x** | ok | ok | ok | ok | ok |

## Per-field pass rate

- amount_safe_to_pay: 8/25
- affordability_status: 21/25
- recommended_payment_method: 22/25
- payment_plan: 21/25
- earliest_date_for_full_payment: 18/25
- spending_changes_needed: 21/25
- amount_safe_to_pay exact to the cent: 3/25
- fallback rows: 0

Amount passes within 2% of truth.

## First mismatching field per row

- request_02: first mismatch `amount_safe_to_pay` — ours `18336765.48` vs truth `17229139.2`
- request_03: first mismatch `amount_safe_to_pay` — ours `971737` vs truth `873000`
- request_04: first mismatch `amount_safe_to_pay` — ours `10609286.07` vs truth `8401800`
- request_05: first mismatch `amount_safe_to_pay` — ours `0` vs truth `737`
- request_06: first mismatch `amount_safe_to_pay` — ours `523.84` vs truth `603.3`; also affordability_status, recommended_payment_method, payment_plan, spending_changes_needed
- request_07: first mismatch `earliest_date_for_full_payment` — ours `2024-10-15` vs truth `2024-10-23`
- request_08: first mismatch `affordability_status` — ours `not_affordable` vs truth `affordable_later`; also recommended_payment_method, payment_plan, earliest_date_for_full_payment
- request_10: first mismatch `amount_safe_to_pay` — ours `0` vs truth `12700`
- request_11: first mismatch `earliest_date_for_full_payment` — ours `2025-06-15` vs truth `2025-07-15`; also spending_changes_needed
- request_12: first mismatch `amount_safe_to_pay` — ours `60370.25` vs truth `65164`; also earliest_date_for_full_payment, spending_changes_needed
- request_13: first mismatch `amount_safe_to_pay` — ours `490.8` vs truth `433.4`; also affordability_status, recommended_payment_method, payment_plan, earliest_date_for_full_payment
- request_14: first mismatch `amount_safe_to_pay` — ours `616.29` vs truth `597.74`
- request_15: first mismatch `amount_safe_to_pay` — ours `0` vs truth `83.05`
- request_17: first mismatch `earliest_date_for_full_payment` — ours `2026-04-15` vs truth `2026-03-15`
- request_18: first mismatch `amount_safe_to_pay` — ours `546.05` vs truth `462`
- request_19: first mismatch `amount_safe_to_pay` — ours `30022.77` vs truth `28820`; also payment_plan
- request_20: first mismatch `amount_safe_to_pay` — ours `8969.68` vs truth `5400`
- request_21: first mismatch `amount_safe_to_pay` — ours `1574.4` vs truth `1543.35`; also affordability_status, earliest_date_for_full_payment, spending_changes_needed
- request_22: first mismatch `amount_safe_to_pay` — ours `464.61` vs truth `475.46`
- request_23: first mismatch `amount_safe_to_pay` — ours `8360.18` vs truth `9152`
- request_25: first mismatch `amount_safe_to_pay` — ours `376083.41` vs truth `1425000`
