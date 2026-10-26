# BNPL AR and DSO dashboard

The [BNPL Accounts Receivable and DSO dashboard](https://mt.soupop.ir/dashboard/43) was built on 2026-10-13 from the provided AR+DSO methodology and the owner's current installment-number rule. It includes all `bnpl_credit_installments.source` values; use the Product source filter to focus on `CREDIT_IN_4`, `DP_LOAN`, or `LOAN`. Amounts are displayed in native database units without a Rial/Toman conversion.

## Installment and payment model

- One row is one scheduled installment in `bnpl_credit_installments`.
- Owner rule (2026-10-13): `number = 1` is due at invoice time. Exclude it from AR, DPD, and both DSO measures. Show it separately as down-payment/upfront cash.
- `number > 1` is scheduled credit and enters AR, credit sales, contractual DSO, DPD, and payment-delay measures.
- `created_at::date` is the origination-date proxy used for AR creation and credit-sale timing. Where invoice links were inspected, most linked CREDIT_IN_4 and LOAN rows shared the same calendar date; exceptions exist. DP_LOAN invoice linkage was not established.
- Payment evidence unions distinct `(installment_id, payment_id)` links from `bnpl_credit_installments.payment_id` and `bnpl_gateway_installments_payment`, then uses the first non-null `bnpl_gateway_payments.confirmed_at`. Repeated attempts are deduplicated. A confirmed link marks the scheduled row as settled; refunds/reversals are not represented in this model.

## Measures

- **Current AR:** sum of unpaid `number > 1` scheduled amounts. Future-due amounts remain AR from origination, consistent with the PDF exposure example. Penalties are excluded from principal AR.
- **Credit sales:** sum of scheduled amounts for `number > 1` originated during the selected period. This is the installment-schedule equivalent of NMV less the number-1 down payment.
- **Average AR:** average of daily end-of-day portfolio AR for the month-to-date period. AR increases on installment creation and decreases on the first confirmed payment date.
- **Standard DSO:** `sum(daily closing AR) / sum(period credit sales)`, equivalent to `average AR / average daily credit sales`. The monthly chart shows the latest 19 calendar months.
- **Contractual DSO:** schedule-amount-weighted days from origination to `due_date` for `number > 1` installments. It describes the payment schedule, not observed behavior.
- **DPD:** days past due for currently unpaid scheduled installments, bucketed separately into not-yet-due, due-today, and overdue bands.
- **Payment delay:** first confirmed payment date minus due date. Negative values indicate early payment.
- **Cash collection days:** confirmed scheduled amount times elapsed days from origination divided by scheduled value (number 1 plus scheduled rows) as an NMV proxy. Unpaid rows remain in the denominator, so incomplete/current cohorts can understate the result. This is not invoice-level NMV reconciliation.
- **Invoice-time reconciliation:** number-1 scheduled amount split into confirmed and unconfirmed gateway evidence. Unconfirmed number-1 rows are visible exceptions, never added to AR.

## Questions

- [AR and DSO KPI Summary](https://mt.soupop.ir/question/1096)
- [Monthly Standard vs Contractual DSO](https://mt.soupop.ir/question/1097)
- [Daily AR Balance](https://mt.soupop.ir/question/1098)
- [Current AR Aging and DPD](https://mt.soupop.ir/question/1099)
- [Confirmed Installment Payment Delay](https://mt.soupop.ir/question/1100)
- [Cash Collection Days on Scheduled NMV](https://mt.soupop.ir/question/1101)
- [Invoice-Time Payment Reconciliation](https://mt.soupop.ir/question/1102)

The dashboard's Product source filter is a text filter; enter a source label such as `CREDIT_IN_4`, `DP_LOAN`, or `LOAN`. Leaving it blank shows all sources.
