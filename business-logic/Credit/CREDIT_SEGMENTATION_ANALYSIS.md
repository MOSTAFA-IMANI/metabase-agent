# Soupop User Credit Segmentation and Credit Scoring Analysis

Analysis date: 2026-09-21
Status: discovery and validation only. No production approval or lending system is implemented.

## Executive Summary

The data supports two different analytical paths:

1. Existing users: users with confirmed Soupop installment repayment history. Actual payment behavior is the primary validation target.
2. New users: users with no installment history. They need a separate initial-evidence framework; repayment features must not be used before they exist.

The current live snapshot contains approximately:

| Signal | Observed coverage |
|---|---:|
| Active type-1 users | 601,937 |
| Users with any installment row | 2,446 |
| Users with confirmed installment repayment | 2,446 |
| Users with customer config | 41,167 |
| Users with a current credit row | 4,951 |
| Users with non-deleted maintenance history | 508,706 |
| Users with an address | 37,371 |
| Users with a user-identification row | 4,737 |
| Users with a user-verification row | 72,723 |
| Users with national-code/phone verification flag | 7,881 |

This is highly imbalanced: most active users do not have repayment history. A single score for everyone would overstate confidence for new users.

Useful live dashboards:

- [Credit Scoring Discovery and Validation](https://mt.soupop.ir/dashboard/41)
- [Customer Credit Segmentation and Risk](https://mt.soupop.ir/dashboard/40)
- [Referenced installment detail question](https://mt.soupop.ir/question/485-customer-instullment-detail)
- [Referenced customer config and address question](https://mt.soupop.ir/question/1036-users-bnpl-customer-config-user-addresses)

The reusable builders are [build_credit_scoring_discovery_dashboard.py](../../scripts-py/build_credit_scoring_discovery_dashboard.py) and [build_customer_credit_segmentation_dashboard.py](../../scripts-py/build_customer_credit_segmentation_dashboard.py).

## Data Sources and Relationships

| Table or question | Purpose | Important relationship |
|---|---|---|
| users | Account state, creation, activity, type, verification flag | Primary user key is user_id |
| bnpl_credit_installments | Installment amount, number, due date, source, payment link | customer_id -> users.user_id; payment_id -> bnpl_gateway_payments.id |
| bnpl_gateway_payments | Payment creation and confirmation timestamps | user_id -> users.user_id; id is linked from installment.payment_id |
| bnpl_customer_config | Eligibility, existing score, qualifying credit, facility and cheque JSON | customer_id -> users.user_id |
| bnpl_credits | Current raw balance and loan balance | customer_id -> users.user_id |
| maintanence_services | Service history, car, supplier, auto service, source, dates and cost | customer_id -> users.user_id; auto_service_id -> auto_services |
| user_addresses | City, province, address and optional geographic point | user_id -> users.user_id |
| user_identifications | Identity-related row and sensitive profile fields | user_id -> users.user_id |
| user_verifications | Verification workflow timestamps and used flag | user_id -> users.user_id |
| Question 485 | Existing Metabase installment detail with payment and due-date expressions | Saved MBQL question on database 2 |
| Question 1036 | Existing users/config/address join | Saved MBQL question on database 2 |

The schema also exposes credit logs, customer loans, cheques, transaction items, referrals, marketing attribution, devices and game tables. They should only enter the model after their business meaning and decision-time availability are confirmed.

## Data Dictionary

### Installments

- bnpl_credit_installments.id: primary key.
- customer_id: user identifier.
- number: installment index. The business owner clarified on 2026-10-10 that index `0`, if stored, is payable at invoice time. Index `1` is the first scheduled repayment row in the current analysis; `2+` are later scheduled rows. Keep invoice-time payment separate from repayment due-date performance.
- amount: scheduled installment amount.
- due_date: scheduled payment date.
- payment_id: nullable link to a gateway payment. A non-null value does not prove that the payment was finally confirmed.
- source: observed values include credit_in_4, loan and dp_loan. Their product and risk-policy differences are not confirmed.
- created_at: installment record creation time.
- penalty and penalty_updated_at: present, but their relationship to the five-day business grace rule is not confirmed.

### Gateway payments

- created_at: payment row creation time.
- confirmed_at: timestamp used for the exploratory payment-delay calculation.
- amount, gateway, type, transaction_id and details: available but their final business semantics, reversal behavior and refund behavior need confirmation.

Candidate calculation:

payment_delay_days = confirmed_at date - due_date

The exploratory categories are:

- Paid before/on due date
- Paid 1-5 days after due date
- Paid more than 5 days late
- Future installment
- Currently due
- Unpaid 1-5 days overdue
- Unpaid more than 5 days overdue
- Payment linked but unconfirmed

The current data has no rows in the unpaid 1-5 days overdue category in the observed snapshot. That is an observation, not proof that the state cannot occur.

### Invoice-time payment and installment index

Owner clarification on 2026-10-13 supersedes this analysis's prior index convention: `bnpl_credit_installments.number = 1` is payable at invoice time and is not a future receivable. Exclude it from AR, DPD, DSO, and later-installment repayment-performance denominators; report it separately as upfront/down-payment cash. Rows with `number > 1` are scheduled repayments. If `number = 0` appears, flag it for review rather than assigning it an assumed meaning.

The historical tables and Dashboard 41 in this document were calculated before this clarification. Any analysis that labels number 1 as a scheduled installment, compares #1 with #2+, or includes number 1 in repayment denominators is stale and must be recalculated before operational or credit-decision use. A point-of-sale payment is not evidence of later scheduled repayment behavior.

### Customer config and facilities

Important fields:

- score: existing customer-config score. Its owner, version, range, refresh schedule and label meaning are unknown.
- qualifying_credit_amount: available, but it is unclear whether this is a limit, recommendation, eligibility amount or current approved amount.
- eligible_for_loan: boolean eligibility flag; the business rule and source system need confirmation.
- renew_credit: boolean; the meaning of renewal and whether it is a decision or an outcome needs confirmation.
- has_used_settlement_time_extension: boolean; candidate risk signal, but the event definition and time ordering are unclear.
- facilities: JSON object with observed keys including facilityDebtTotalAmount, facilityDeferredTotalAmount, facilityPastExpiredTotalAmount, facilitySuspiciousTotalAmount, facilityTotalAmount, facilityList, dishonored, result, status and provider-like metadata.
- back_cheques: JSON object with chequeList and related fields; not used in the exploratory score because its meaning and timing are not confirmed.
- national_card_ocr: JSON object containing identity fields; not used as a credit signal.

The JSON values are stored as JSON strings or JSON values with inconsistent shapes. Numeric parsing in the exploratory questions is defensive and should not be treated as a production parser until units and provider contracts are documented.

### Users and activity

- user_id: primary key.
- type: observed values are 0, 1 and 2. Type 1 is inferred to be the customer population because all tested BNPL-linked records joined to type 1. This must be confirmed.
- created_at and updated_at: account timestamps.
- last_login: activity recency signal; null means no recorded login.
- is_active and deleted_at: account-state filters.
- national_code_with_phone_number_verification_ok: boolean flag; the exact verification workflow is not documented.
- wallet, referral_code and phone/national_code fields exist, but sensitive identifiers are excluded from the dashboards.

### Maintenance

- service_id: primary key.
- customer_id and car_id: user and vehicle links.
- auto_service_id: link to an autoservice record.
- supplier_id: supplier/user link.
- source: available but not interpreted.
- created_at, date_of_change and next_date: different service timing concepts; their canonical event-time meaning needs confirmation.
- total_cost, km_of_change, next_km and car_km_difference: usage and cost candidates, not currently used as credit features.
- deleted_at: service record state.

A service with auto_service_id is treated only as an associated service record. It is not assumed to be verified or safer.

### Address

user_addresses contains city, province, address, optional location, created_at and user_id. The geography question uses the latest address per user and retains sample-size warnings. It does not expose address text or coordinates.

## Unknown Fields and Questions Requiring Clarification

1. users.type
   - Observed values: 0, 1 and 2.
   - Inference: type 1 is the customer population because all tested BNPL records join to it.
   - Question: what does each type mean, and are type changes possible over time?

2. bnpl_credit_installments.source
   - Observed values: credit_in_4, loan and dp_loan.
   - Question: are these separate products with different due-date, penalty and collection policies?

3. bnpl_credit_installments.payment_id
   - Observed behavior: nullable; the saved Metabase question uses emptiness as a payment-status proxy.
   - Question: does non-null mean payment initiated, payment created, or payment completed?

4. bnpl_gateway_payments.confirmed_at
   - Observed behavior: used to calculate payment delay.
   - Question: can a confirmed payment be reversed, refunded or cancelled later? Is the final status stored elsewhere?

5. bnpl_gateway_payments.type, gateway, details and transaction_id
   - Question: which payment types are installment settlement, and how should duplicates or retries be handled?

6. customer_config.score
   - Question: who calculates it, what is its range, what version is it, and is it already based on the same repayment or facility fields?

7. customer_config.qualifying_credit_amount
   - Question: is this an approved amount, a maximum possible amount, an eligibility result or a recommendation?

8. customer_config.renew_credit
   - Question: does it mean a user renewed credit, is eligible for renewal, or is configured for renewal?

9. customer_config.has_used_settlement_time_extension
   - Question: what event sets this flag and when does it become available relative to a credit decision?

10. facilities JSON
    - Question: what are the units, provider, refresh timestamp, status meanings and array schema for facilityList?
    - Question: are facility debt and past-expired values current snapshots or historical accumulations?

11. back_cheques JSON
    - Question: what do chequeList, result and status mean, and when are they available?

12. maintenance auto_service_id and supplier_id
    - Question: does the link prove vendor verification, or only identify a related record?
    - Question: is supplier_id always a vendor, or can it be a customer or internal account?

13. maintenance source
    - Question: which values represent user-entered, imported, vendor-submitted or system-generated services?

14. user_addresses
    - Question: which address is primary for credit decisions, and how should stale or conflicting addresses be handled?
    - Question: are city and province normalized?

15. user_identifications.details and national_card_ocr
    - Question: which fields are verified, when were they verified, and are corrections tracked?
    - Governance question: can sensitive identity, gender, salary or birth-date fields be used at all?

## Existing-User Reliability Model

The existing-user model should use a repayment outcome hierarchy:

1. Confirmed Soupop repayment behavior.
2. Previous Soupop credit and exposure history.
3. External facility behavior, especially past-expired, suspicious or dishonored indicators.
4. Verified product/service behavior.
5. Account activity and tenure.
6. Geography only as a monitored, controlled comparison, never as an automatic location score without evidence and governance.

The primary user-level metrics are:

- total_installments
- paid_installments
- future_installments
- currently_due_installments
- unpaid_within_grace_installments
- unpaid_over_5_days_installments
- on_time_installments
- paid_within_grace_installments
- paid_over_5_days_late_installments
- linked_payment_unconfirmed_installments
- average, median and maximum confirmed payment delay
- scheduled amount and severe unpaid amount

The five-day business rule is respected in the exploratory categories. A payment 1-5 days late is not classified as severe delinquency.

A candidate historical score can later weight:

- on-time and grace-window behavior positively
- payments more than five days late negatively
- unpaid installments more than five days overdue more strongly negatively
- future installments as exposure, not delinquency
- invoice-time index 0 separately from scheduled index 1 and later installments
- recent behavior more heavily only after decision-time timestamps are available

This is a methodology proposal, not a production score.

## Existing-User Segment Design

The previous pilot dashboard has five candidate bands. They should be interpreted as analysis bands until a time-aware backtest is completed.

| Candidate segment | Score range | Research credit ladder | Risk interpretation |
|---|---:|---:|---|
| A - Prime verified | 80-100 | 10M Toman | Strong observed payment and supporting evidence; still requires enough sample and time-separated validation |
| B - Established standard | 65-79 | 7.5M Toman | Good evidence with some uncertainty |
| C - Developing | 50-64 | 5M Toman | Mixed or incomplete evidence; moderate pilot amount |
| D - Watch / thin file | 30-49 | 2.5M Toman | Thin history or elevated risk signals; conservative test only |
| E - Limited history / high risk | 0-29 | 1M Toman | Insufficient evidence or explicit risk flags; minimum pilot amount |

Current candidate-band counts from the pilot dashboard were approximately:

- A: 329 users
- B: 518 users
- C: 4,417 users
- D: 469k users
- E: 127k users

The large D/E population is primarily a data-sufficiency result. It must not be described as proven default risk.

## New-User Initial-Credit Model

A new user must not receive the existing-user repayment score. The exploratory initial-evidence question uses only signals available before Soupop repayment history:

- account age
- recent login
- national-code/phone verification flag
- presence of an identity row
- presence of customer config
- eligibility flag
- facility warning signals
- auto-service-associated maintenance evidence
- address availability

It deliberately excludes repayment data and sensitive fields such as gender, salary, birth date, phone number, national code and address text.

Current exploratory initial bands:

| Initial band | Score range | Research credit ladder | Current users |
|---|---:|---:|---:|
| Initial A - strong evidence | 80-100 | 10M Toman | 288 |
| Initial B - good evidence | 60-79 | 7.5M Toman | 3,655 |
| Initial C - moderate evidence | 40-59 | 5M Toman | 11,170 |
| Initial D - limited evidence | 20-39 | 2.5M Toman | 368,356 |
| Initial E - insufficient/high-risk evidence | 0-19 | 1M Toman | 216,028 |

These bands are not validated credit-risk segments yet because their defining population has no repayment outcome. They are suitable for controlled experimentation and for measuring who converts into reliable repayment history.

Positive indicators in this exploratory framework:

- recent activity
- mature account
- verified phone/national-code flag
- identity row present
- customer config present
- eligible-for-loan flag
- vendor-associated maintenance
- address availability

Negative or insufficient-evidence indicators:

- explicit facility warning
- no recent login
- no identity/configuration evidence
- no vendor-associated service
- no address evidence

The model must retain an insufficient-evidence category. Missing data is not the same as bad behavior.

## Current Validation Results

### Index 1 versus later scheduled installments

The table below compares persisted index-1 rows with index-2-and-later rows. It does not measure the invoice-time payment described above. The live snapshot checked on 2026-10-10 had no index-0 rows, so the existing bucket split did not mix index 0 into these values.

Observed confirmed-payment rates:

| Product | Installment group | Paid | On time | Severe late | On-time rate | Severe-late rate |
|---|---|---:|---:|---:|---:|---:|
| credit_in_4 | #1 | 3,599 | 3,594 | 4 | 99.86% | 0.11% |
| credit_in_4 | #2+ | 7,536 | 3,064 | 2,228 | 40.66% | 29.56% |
| loan | #1 | 299 | 299 | 0 | 100.00% | 0.00% |
| loan | #2+ | 383 | 132 | 148 | 34.46% | 38.64% |
| dp_loan | #1 | 33 | 9 | 9 | 27.27% | 27.27% |
| dp_loan | #2+ | 144 | 25 | 82 | 17.36% | 56.94% |

Index-1 scheduled repayments are clearly different from index-2-and-later repayments in the current data, but product mix and selection effects are possible. Model that scheduled-row comparison separately and validate it with decision-time cohorts. It does not describe the invoice-time index-0 payment.

### Maintenance versus repayment

For users with installment history:

- 0 services: 44.83% on-time among confirmed payments; 33.51% severe-late.
- 1 service with auto_service_id: 54.72% on-time; 26.16% severe-late.
- 2-5 services with auto_service_id: 58.32% on-time; 22.44% severe-late.
- 6+ services with auto_service_id: 67.96% on-time; 11.16% severe-late.

The no-auto-service groups are very small. This supports maintenance as a candidate supporting signal, but it does not prove causality or that more records always mean lower risk.

### Facilities versus repayment

Observed examples:

- Facility debt 10M+: 60.04% on-time; 19.63% severe-late.
- No facility debt: 58.56% on-time; 21.99% severe-late.
- Past-expired facility amount >0: 55.16% on-time; 27.72% severe-late.

Higher external facility amount is not automatically better. Past-expired and dishonored indicators appear more plausible as risk candidates, but their provider semantics and time availability must be confirmed.

### Account activity versus repayment

The activity comparison is mixed and confounded by account age. Examples:

- Users aged 30-89 days with login 31-90 days ago: 90.31% on-time, but only 154 users.
- Users aged 365+ days with login more than 90 days ago: 58.98% on-time and 19.38% severe-late.
- Users aged 90-364 days with login more than 90 days ago: 53.58% on-time and 26.42% severe-late.

Activity may be useful, but it needs a time-aware cohort analysis and minimum sample controls.

### Repayment history and transition readiness

Current buckets:

| Confirmed payments | Users | On-time rate | Severe-late rate | Severe-unpaid rate |
|---|---:|---:|---:|---:|
| 1 | 360 | 100.00% | 0.00% | 14.65% |
| 2-3 | 271 | 67.08% | 20.50% | 12.26% |
| 4-5 | 1,252 | 49.25% | 29.64% | 0.79% |
| 6+ | 563 | 64.91% | 13.98% | 1.14% |

The results are not monotonic because denominators and selection processes differ. No automatic transition threshold should be finalized from this snapshot. Compare candidate transitions at 1, 3, 5 and 6 confirmed payments using time-split cohorts and the same outcome horizon.

## Existing -> New User Transition

Proposed lifecycle:

1. New user has no installment history.
2. Assign an initial evidence band only from information available before the first credit decision.
3. Offer a conservative pilot amount.
4. Track any invoice-time index-0 payment separately, then observe index-1 and later scheduled payment outcomes.
5. After a candidate threshold, calculate existing-user repayment features.
6. Compare both scores for a controlled overlap period.
7. Promote the historical score only after a time-split backtest confirms stability.

The threshold is intentionally not finalized. One confirmed payment is too little for a stable model, while the 4-5 and 6+ buckets show selection and timing effects that require cohort-level validation.

## Geography

Question 1044 compares the latest address per user by province and city, includes sample-size labels, and limits the output to the largest groups.

No geography-based credit rule is recommended yet because:

- address coverage is only about 37k users
- city and province may be stale or duplicated
- observed differences need controls for product, account age, maintenance and repayment history
- small city groups can produce unstable rates
- geography can create fairness and governance risk

Geography should remain a monitoring and fairness-audit dimension until controlled validation is complete.

## Metabase Questions Created

Dashboard 41 contains:

1. Credit Discovery - Existing vs New Cohort
2. Credit Discovery - Installment Outcome Categories
3. Credit Discovery - User Repayment Metrics
4. Credit Discovery - Installment 1 vs Later
5. Credit Discovery - Maintenance vs Repayment
6. Credit Discovery - Account Activity vs Repayment
7. Credit Discovery - Facilities vs Repayment
8. Credit Discovery - Province and City Repayment
9. Credit Discovery - New User Initial Signal Bands
10. Credit Discovery - Repayment History for Model Transition

The dashboard uses database 2 and was verified against live data. The questions are parameterless exploratory cards so their SQL can also be executed directly through the Metabase Agent endpoint.

## Data Quality and Privacy Issues

- The active customer population changed slightly during analysis because the database is live. Counts should be timestamped when used in a decision document.
- There is no explicit installment status column in the inspected schema. payment_id and confirmed_at are proxies whose semantics need confirmation.
- Confirmed payment reversals, refunds, duplicate gateway attempts and late corrections are not modeled.
- Installment source semantics are undocumented.
- Customer-config JSON numeric fields have inconsistent shapes and unknown units.
- facilityList was not parsed into a stable facility-level table.
- Maintenance source and auto_service_id verification semantics are undocumented.
- Address history and primary-address rules are undocumented.
- The referenced question 1036 exposes many fields because it selects a broad joined shape, including sensitive account values. It should not be used for exports or credit work without an explicit field allowlist.
- The referenced question 485 contains personal name, phone and national-code columns. The new worklist questions intentionally exclude those fields.
- Identity fields, salary, gender, birth date, phone number, national code, address text and exact coordinates are not used in the proposed score.
- The dashboard is an exploratory analysis artifact, not an automated approval workflow.

## Data Leakage Risks

A production feature must have a decision-time timestamp.

Do not use:

- payment confirmation or overdue information that occurred after credit issuance as an input feature
- customer-config scores or facility snapshots refreshed after the decision
- maintenance records created after the credit decision
- last_login values observed after the decision
- addresses added or updated after the decision
- current balances when reconstructing a historical decision unless the balance was available at that decision time

Recommended timestamps:

- feature_available_at
- credit_issued_at
- installment_due_at
- payment_observed_at
- label_observation_end_at

The current dashboard is a current-state analysis. It is not a leakage-safe historical backtest.

## Recommended Scoring Architecture

### Phase 1: discovery

- Maintain separate existing and new-user cohorts.
- Normalize payment outcomes with the five-day grace rule.
- Build a decision-time feature snapshot.
- Validate every candidate signal with sample size and time-split outcomes.
- Keep unknown fields out until product and risk owners clarify them.

### Phase 2: explainable pilot

- Use repayment behavior as the dominant existing-user signal.
- Use initial evidence only for new users.
- Keep an explicit insufficient-evidence band.
- Map five bands to a conservative 1M, 2.5M, 5M, 7.5M and 10M Toman experiment ladder.
- Cap exposure while the first cohorts are being observed.
- Log every feature, score component, reason code and decision timestamp.

### Phase 3: monitoring

Track by cohort, product and segment:

- user count
- exposure and recommended amount
- on-time rate
- within-grace rate
- severe-late rate
- unpaid-over-five-days rate
- average, median and maximum payment delay
- invoice-time index 0, scheduled index 1, and later scheduled installments as separate groups
- data coverage and missingness
- geography and other fairness-audit slices

A statistical or ML model should only be considered after enough time-split labels exist. It should be benchmarked against the explainable rules and retain reason codes.

## Final Recommendation

Use dashboard 41 as the review surface for Product, Finance, Risk, Data and Engineering. Do not promote dashboard 40's pilot score to production. First resolve the unknown field questions, create decision-time snapshots, confirm payment and facility semantics, and run a time-split validation of the proposed existing and new-user bands.
