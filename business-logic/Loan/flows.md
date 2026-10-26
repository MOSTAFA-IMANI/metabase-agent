# Loan workflow stories

This guide explains how the loan-operation tables and dashboards fit together. It does not define the legal meaning of loan approval, funding, or cheque acceptance.

## Story 1: a customer starts a loan application

1. A row in `bnpl_customer_loans` records the application, selected product (`loan_id`), plan (`subscription_plan_id`), amount/terms, and current `step` / `step_status`.
2. Filter `deleted_at IS NULL` for the current operational application list, as the saved builder does.
3. Use `bnpl_customer_loan_step_done_timelines` when the question is which steps were recorded over time. Do not count loans after directly joining several timeline rows.
4. Use raw step and status labels until their full state machine and terminal-state definitions are confirmed.

Current step/status funnel:

```sql
select coalesce(step, 'unknown') as step,
       coalesce(step_status, 'unknown') as step_status,
       count(*) as application_rows
from bnpl_customer_loans
where deleted_at is null
group by 1, 2
order by application_rows desc
```

The dashboard's “open follow-up” query excludes `done`, `completed`, `rejected`, and `cancelled`. Treat these as the builder's current operational exclusions, not a complete product-owned status dictionary.

## Story 2: an application selects terms and a subscription

The application points to `bnpl_loans` for loan terms and to `bnpl_loan_subscription_plans` for the plan. The application also stores `has_paid_subscription_fee` and a payment method. Those fields explain workflow configuration; for collected revenue, reconcile to actual payment confirmations.

Avoid adding `loan.amount` and `customer_loan.amount` together unless the report explicitly asks for both records. They can represent product terms and a customer application amount, not two separate cash flows.

## Story 3: cheque and collateral work

`bnpl_customer_loan_collaterals` stores collateral status and a collateral type link. `bnpl_customer_credit_loan_cheques` stores cheque details and dates. These are separate sources and may have more than one record per application. Aggregate to application or collateral grain before counting applications.

The current builder joins cheque `customer_loan_id` to `bnpl_customer_loans.id`. A distinct `bnpl_customer_credit_loans` table exists, so preserve this exact join as the current dashboard definition and confirm the foreign-key meaning before reusing it for another product flow.

## Story 4: loan repayments

`bnpl_loan_installment_items` bridges an application to rows in `bnpl_credit_installments`. Use the installment schedule's `due_date` for expected repayment timing and linked gateway `confirmed_at` for recorded payment timing. A populated `payment_id` is not sufficient evidence that money was received.

When a report asks for loan performance, retain the installment `source` and confirm that the mapped installment belongs to the loan product. Do not infer that every row in `bnpl_credit_installments` is a loan just because a user has a loan application.

## Dashboard and question links

- [Loan operation Dashboard, ID 30](https://mt.soupop.ir/dashboard/30) is the populated current dashboard.
- [Loan application funnel](https://mt.soupop.ir/question/849)
- [Open loan follow-up](https://mt.soupop.ir/question/850)
- [Cheque collateral status](https://mt.soupop.ir/question/851)
- [Cheque registration and due-date worklist](https://mt.soupop.ir/question/852)
- [Cheques due in the next 30 days](https://mt.soupop.ir/question/853)
- [Overdue cheques](https://mt.soupop.ir/question/854)
- [Subscription-fee status](https://mt.soupop.ir/question/856)
- [Loan eligibility summary](https://mt.soupop.ir/question/857)
- [Installment items by loan](https://mt.soupop.ir/question/858)
- [Paid-installment DSO question](https://mt.soupop.ir/question/1007)

Dashboard 29 has the same title but was empty when checked. The builder `build_loan_operation_dashboard.py` creates new questions and a new dashboard when run; inspect dashboard 30 before any changes and do not rerun the builder as an update mechanism.

The builder description lists dashboard filters for date, step, step status, customer ID, and auto-service ID as targets to add after creation. Confirm the actual dashboard filter mappings in Metabase before assuming those filters affect every card.

## Related policy documents

- [New-user credit backend rules](../../BACKEND_NEW_USER_CREDIT_RULES.md) define a proposed 5M Toman initial cap and step-up policy.
- [Credit segmentation analysis](../../CREDIT_SEGMENTATION_ANALYSIS.md) contains research bands and validation caveats. Its exploratory 10M ladder is not the backend new-user cap.
