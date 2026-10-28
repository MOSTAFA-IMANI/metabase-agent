# New User Credit Rules

**Purpose:** implementation brief for the backend team.

This document defines the **initial credit configuration for a new user only**. It does not replace the repayment-based rules for existing users.

The product rule is **افزایش پلکانی اعتبار**: after a user repays installments successfully, the available credit may increase step by step. The initial new-user amount must be conservative and must never exceed **5,000,000 Toman**.

## 1. Definitions

- **New user:** active customer (`users.type = 1`) with no previous Soupop installment history at decision time.
- **Decision time:** the timestamp at which the initial credit is calculated. All fields must be read from a snapshot at or before this time.
- **Segment score:** an explainable evidence score from 0 to 100. It is not a probability of default.
- **Referral credit:** the trusted credit amount configured for the referral code that was actually used during signup.
- **Initial credit:** the amount returned by this document, between 1M and 5M Toman.

Amounts must be stored as integers in Toman. Do not use a client-provided referral amount.

## 2. Hard eligibility checks

Before scoring, apply these checks:

| Condition | Result |
|---|---|
| User is deleted, inactive, or not an eligible customer type | No credit configuration |
| User already has an installment or active credit decision at decision time | Do not use new-user rules; route to existing-user rules |
| Duplicate identity, blocked account, fraud flag, or unresolved KYC conflict | Manual review or 1M maximum, according to Risk policy |
| Facility data contains a confirmed dishonored, suspicious, or past-expired event | Maximum 1M for pilot; do not block solely because data is missing |
| Facility data is missing or unavailable | No penalty; mark `facility_signal = unknown` |

Missing evidence is not the same as bad behavior. The API should return reason codes so Operations can see why a user received an amount.

## 3. New-user evidence score

Start at `0` and add only the highest matching value in each row.

### Positive signals

| Field / signal | Rule | Points |
|---|---|---:|
| `users.created_at` | Account age >= 365 days | +20 |
|  | 90–364 days | +12 |
|  | 30–89 days | +6 |
|  | < 30 days | +2 |
| `users.last_login` | Login within 30 days | +20 |
|  | Login 31–90 days ago | +12 |
|  | Login more than 90 days ago or null | +0 |
| `national_code_with_phone_number_verification_ok` | Verified | +20 |
| `user_identifications` | A valid identity row exists before decision time | +10 |
| `bnpl_customer_config` | Config row exists before decision time | +10 |
| `eligible_for_loan` | Explicitly true before decision time | +5 |
| `maintanence_services` | At least one non-deleted service with `auto_service_id` | +5 |
|  | 2–5 such services | +8 total |
|  | 6 or more such services | +10 total |
| `user_addresses` | A valid province/city row exists before decision time | +5 |

### Negative signals

| Field / signal | Rule | Points |
|---|---|---:|
| `bnpl_customer_config.facilities` | `dishonored > 0`, or `facilityPastExpiredTotalAmount > 0`, or `facilitySuspiciousTotalAmount > 0` | -20 |
| Data quality | Required field is malformed | 0 points for that signal and add a data-quality reason code |

Clamp the final score to `0..100`. Do not award points for a service merely because a row exists; count only non-deleted rows, and treat `auto_service_id` as supporting evidence, not proof of repayment reliability.

## 4. Segment-to-credit mapping

| Segment | Score | Initial credit | Meaning |
|---|---:|---:|---|
| E1 | 0–19 | 1,000,000 | Insufficient evidence or explicit risk signal |
| E2 | 20–39 | 2,000,000 | Limited evidence |
| E3 | 40–59 | 3,000,000 | Moderate evidence |
| E4 | 60–79 | 4,000,000 | Good evidence |
| E5 | 80–100 | 5,000,000 | Strong initial evidence |

The segment name and score must be persisted with the decision. Do not silently overwrite the reason for the amount.

## 5. Referral precedence

Referral credit is an input to the final amount, not a replacement for audit logging. A hard risk cap always wins over referral credit.

```text
segment_amount = amount_for_score(segment_score)
referral_amount = trusted_amount_for_used_referral_code  # 0 if none
risk_cap = 1_000_000 if confirmed_facility_warning else 5_000_000
initial_credit = min(risk_cap, 5_000_000, max(1_000_000, segment_amount, referral_amount))
```

Examples:

| Segment amount | Referral amount | Final new-user credit |
|---:|---:|---:|
| 5M | 5M | 5M |
| 5M | 3M | 5M |
| 2M | 5M | 5M |
| 1M | none | 1M |
| 4M | referral configured as 10M | 5M, because of the new-user cap |

If a confirmed facility warning applies, the final amount is 1M even when the referral amount is 3M or 5M. The decision must include `HARD_RISK_CAP_FACILITY_WARNING`.

Validate that the referral code belongs to the signup event and was not added or changed after signup. Record `referral_code_id`, `referral_amount`, `segment_amount`, `final_amount`, and the rule version.

## 6. افزایش پلکانی اعتبار for later decisions

This section applies after the user has an existing credit/installment history.

1. Never increase credit because an installment was merely created or a payment was initiated.
2. Count an installment as successfully repaid only after the gateway payment is confirmed and not reversed or refunded.
3. Apply the existing business rule: a level-up from level `N` to `N+1` is eligible only after at least **70% of the previous level's required credit/installment obligation** has been successfully repaid.
4. A late payment within the approved five-day grace window may remain non-severe, but it must still be logged. A payment more than five days late, an unpaid installment more than five days overdue, a dishonored facility, or an unresolved reversal must block the next increase until Risk approves an exception.
5. Increase at most one level per evaluation. Do not jump from level 3 directly to level 5.
6. Enforce a configured maximum credit per product, and keep the new-user cap separate from the existing-user cap.
7. Use decision-time snapshots and store: previous level, previous amount, paid principal, required principal, payment confirmations, grace status, new level, new amount, rule version, and reason codes.

The exact level amounts and the meaning of “70%” must be configured by product/risk owners. The backend should not hard-code them inside payment callbacks.

## 7. Recommended fields

### Use in the initial score

- Account age from `users.created_at`.
- Activity recency from `users.last_login`.
- Verified phone/national-code flag.
- Existence and timestamp of `user_identifications`.
- `bnpl_customer_config.eligible_for_loan` and config creation time.
- Parsed facility warning fields: dishonored, past-expired, suspicious.
- Count of non-deleted maintenance services.
- Count of non-deleted services with `auto_service_id`.
- Latest valid province/city address and its timestamp.
- Referral code and trusted referral amount.

### Keep out of the initial score

- Gender, salary, birth date, phone number, national code, address text, and exact coordinates.
- City-level reward or penalty before a time-split fairness and performance review.
- Current repayment fields, because a new user has no repayment history.
- Any field created or updated after the credit decision.

### Use for existing-user scoring, not new-user scoring

- Confirmed payment delay versus `due_date`.
- On-time, grace-window, severe-late, and severe-unpaid counts.
- Confirmed repayment rate and overdue amount.
- Installment number, source/product, and exposure.
- Reversal, refund, duplicate-payment, and payment-status outcomes.

## 8. City and geography rule

Store city and province for reporting, operational allocation, and fairness monitoring. Do not directly add or subtract credit points based on city in the first release. Geography is sparse, can be stale, and may create an unfair proxy. A geography rule may be considered later only after controlled validation with minimum sample sizes and Risk/Legal approval.

## 9. Required decision response and audit record

```json
{
  "segment": "E3",
  "score": 47,
  "segment_amount": 3000000,
  "referral_amount": 5000000,
  "final_amount": 5000000,
  "rule_version": "new-user-v1",
  "reason_codes": ["ACCOUNT_AGE_90_364", "VERIFIED_IDENTITY", "REFERRAL_OVERRIDE_UPWARD"],
  "decision_at": "2026-09-21T00:00:00Z"
}
```

Persist the input snapshot or feature values used for the decision. This is necessary to reproduce a decision after `last_login`, facilities, maintenance, or address data changes.

## 10. Release checklist

- Implement the score as a versioned, configuration-driven policy.
- Add unit tests for every boundary: 19/20, 39/40, 59/60, 79/80, age boundaries, login boundaries, and the 5M cap.
- Add tests for no referral, invalid referral, referral 3M, referral 5M, and referral above 5M.
- Add idempotency so retries do not create multiple credit decisions.
- Recheck active credit/installment state transactionally before granting credit.
- Log every feature, score component, amount, referral input, rule version, and reason code.
- Monitor approval count, exposure, repayment #1, later repayment, grace-window rate, severe-late rate, severe-unpaid rate, missingness, and results by city/province without using geography as a score initially.
- Do not enable automatic production increases until the 70% rule, payment-confirmation semantics, reversal handling, and maximum exposure are approved by Product, Risk, Finance, and Engineering.
