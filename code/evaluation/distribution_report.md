# Distribution report

Predictions: 250 rows; samples: 25 rows.
Gaps of 15 points or more are flagged for review.

### affordability_status

| value | predictions | samples | gap |
|---|---|---|---|
| affordable_later | 19% | 24% | -5% |
| affordable_now | 20% | 12% | +8% |
| affordable_with_plan | 29% | 36% | -7% |
| not_affordable | 32% | 28% | +4% |

### recommended_payment_method

| value | predictions | samples | gap |
|---|---|---|---|
| full_payment | 24% | 24% | +0% |
| installments | 22% | 20% | +2% |
| not_recommended | 32% | 28% | +4% |
| partial_payment | 4% | 4% | -0% |
| wait | 19% | 24% | -5% |

### spending_changes_needed is none

| value | predictions | samples | gap |
|---|---|---|---|
| False | 12% | 12% | +0% |
| True | 88% | 88% | +0% |

### earliest_date_for_full_payment empty

| value | predictions | samples | gap |
|---|---|---|---|
| False | 69% | 72% | -3% |
| True | 31% | 28% | +3% |

### payment_plan length

| value | predictions | samples | gap |
|---|---|---|---|
| 0 | 32% | 28% | +4% |
| 1 | 43% | 48% | -5% |
| 2 | 4% | 4% | -0% |
| 3 | 22% | 20% | +2% |

### amount_safe_to_pay / requested_amount

| value | predictions | samples | gap |
|---|---|---|---|
| (0.00, 0.25) | 33% | 40% | -7% |
| (0.25, 0.50) | 11% | 16% | -5% |
| (0.50, 0.75) | 9% | 12% | -3% |
| (0.75, 1.00) | 11% | 16% | -5% |
| 0 | 9% | 0% | +9% |
| 1 (full) | 26% | 16% | +10% |
