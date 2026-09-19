# Distribution report

Predictions: 250 rows; samples: 25 rows.
Gaps of 15 points or more are flagged for review.

### affordability_status

| value | predictions | samples | gap |
|---|---|---|---|
| affordable_later | 23% | 24% | -1% |
| affordable_now | 24% | 12% | +12% |
| affordable_with_plan | 32% | 36% | -4% |
| not_affordable | 21% | 28% | -7% |

### recommended_payment_method

| value | predictions | samples | gap |
|---|---|---|---|
| full_payment | 27% | 24% | +3% |
| installments | 25% | 20% | +5% |
| not_recommended | 21% | 28% | -7% |
| partial_payment | 4% | 4% | +0% |
| wait | 23% | 24% | -1% |

### spending_changes_needed is none

| value | predictions | samples | gap |
|---|---|---|---|
| False | 12% | 12% | +0% |
| True | 88% | 88% | -0% |

### earliest_date_for_full_payment empty

| value | predictions | samples | gap |
|---|---|---|---|
| False | 80% | 72% | +8% |
| True | 20% | 28% | -8% |

### payment_plan length

| value | predictions | samples | gap |
|---|---|---|---|
| 0 | 21% | 28% | -7% |
| 1 | 50% | 48% | +2% |
| 2 | 4% | 4% | +0% |
| 3 | 25% | 20% | +5% |

### amount_safe_to_pay / requested_amount

| value | predictions | samples | gap |
|---|---|---|---|
| (0.00, 0.25) | 35% | 40% | -5% |
| (0.25, 0.50) | 12% | 16% | -4% |
| (0.50, 0.75) | 10% | 12% | -2% |
| (0.75, 1.00) | 11% | 16% | -5% |
| 0 | 0% | 0% | +0% |
| 1 (full) | 32% | 16% | +16% **check** |
