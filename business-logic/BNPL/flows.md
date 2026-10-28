# BNPL stories and query patterns

The links below follow a purchase from invoice to repayment. See [BNPL schema](schema.md) for fields, types, and join keys.

## Story 1: customer buys using BNPL

1. A completed sale is represented by an invoice. The current cash-flow model filters `invoices.status = 'CONFIRMED'` and groups invoice NMV by invoice creation month in Asia/Tehran.
2. `bnpl_invoice_transactions` records the cash/credit split for the invoice. Do not sum invoice amount after joining unaggregated installments or gateway attempts.
3. `bnpl_credit_installments` stores repayment schedule entries. Use its `source` label to retain the raw product classification.
4. Owner clarification (2026-10-13): `number = 1` is due at invoice time. Keep it out of AR, DPD, and DSO; report it separately as upfront/down-payment cash. Rows with `number > 1` are scheduled receivables.

Avoid adding the number-1 installment amount to `bnpl_invoice_transactions.cash` without reconciliation; these may represent the same point-of-sale payment. If number 0 appears, flag it for review rather than assigning it an assumed meaning.

Example classification:

```sql
case
  when number = 1 then 'Invoice-time payment'
  when number > 1 then 'Scheduled receivable'
  else 'Check unclassified index'
end
```

The business rule above supersedes older index-0 notes in this repository.

## Story 2: customer pays an installment

1. `bnpl_credit_installments.payment_id` points to a gateway payment when available.
2. Join to `bnpl_gateway_payments` by `payment.id = installment.payment_id`.
3. Use `confirmed_at` to identify recorded confirmation and place the cash in the confirmation month. `created_at` is payment-row creation; `due_date` is the scheduled date. They answer different questions.
4. Measure scheduled-vs-confirmed delay as `confirmed_at::date - due_date` only for `number > 1` rows and only after confirming timezone and reversal rules. Keep number 1 out of due-date delinquency buckets.
5. A linked but unconfirmed payment is not confirmed cash. A confirmed payment may still need reversal/refund checks before it is treated as final collection.

The existing cash-flow extractor sums `installment.amount` for rows with a non-null `confirmed_at`. This assumes a confirmed installment payment settles the full scheduled amount. Validate partial payments and duplicate attempts before using it as an accounting ledger.

## Story 3: invoice to cash reconciliation

The source extractor links invoices through `bnpl_invoice_transactions`, and uses `bnpl_credit_installment_transaction_items` for installments without a direct invoice link. It assigns bridge-only installments only when the bridge resolves to one invoice. This prevents ambiguous many-invoice mappings from inflating NMV or cash cohorts.

When writing a new query:

- Start from the grain asked for: invoice, installment, gateway payment, or customer.
- Aggregate bridges and payments to one row per target key before joining to a fact table.
- Test duplicate rows and multiple invoice mappings.
- Compare invoice NMV, scheduled amount, and confirmed cash as separate measures.

## Story 4: collections and delinquency

For a receivables view, one row should represent one scheduled installment. Use `due_date` to decide whether it is future, due today, or overdue at the report cutoff. Use `confirmed_at` to classify paid timing. Preserve an unconfirmed-payment-link state rather than treating `payment_id` as paid.

Apply the approved five-day grace period only to scheduled repayments. The existing credit research treats payment delays of 1-5 days as within grace and delays greater than 5 days as severe; that research definition is not proof of a penalty policy for every `source` value.

## Existing views

- [BNPL AR and DSO dashboard](https://mt.soupop.ir/dashboard/43) — portfolio AR, Standard/Contractual DSO, DPD aging, payment delay, and invoice-time payment reconciliation. See [measure definitions](../Analytics/ar-dso.md).
- [BNPL - Installments dashboard](https://mt.soupop.ir/dashboard/7)
- [BNPL - Business Model dashboard](https://mt.soupop.ir/dashboard/8)
- [BNPL - Default Risk dashboard](https://mt.soupop.ir/dashboard/16)
- [Credit Scoring Discovery and Validation](https://mt.soupop.ir/dashboard/41) — inspect the index grouping before interpreting installment comparisons.
- [Question 1017: credit-in-four default risk by amount](https://mt.soupop.ir/question/1017)
- [Question 485: historical installment detail](https://mt.soupop.ir/question/485) — contains personal identifiers; do not export broadly.

## Unresolved semantics

- The meaning and handling of any future installment rows with `number = 0`.
- Whether gateway confirmation can later be reversed or refunded, and how to identify final status.
- Whether `payment_id` is always one-to-one with an installment, or whether multiple payments can settle one installment through `bnpl_gateway_installments_payment`.
- Product-specific semantics for `credit_in_4`, `loan`, and `dp_loan`.
- Units and rounding rules for all amount fields.
