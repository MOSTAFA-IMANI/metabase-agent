# BNPL schema

This guide covers invoice-financed purchases, scheduled installments, and their payment evidence. The schema was checked against live database 2 on 2026-10-10. Database 2 is PostgreSQL (`Soupop Data`) and reports in `Asia/Tehran`.

## Core tables

Types below are the live PostgreSQL types. `?` means nullable in the live schema.

### `invoices` — Metabase table 211

Invoice grain. `id` is the key; `customer_id` links to `users.user_id` when present.

```text
id int8, created_at timestamptz, amount numeric, amount_for_commission numeric?,
description varchar, source varchar, status varchar, auto_service_id int8,
car_id int8, customer_id int8, settlement_id varchar?, supplier_id int8?,
created_by_id int8?, payment_method varchar, interest_amount numeric,
digital_service_fee numeric, discount_amount numeric, tax_amount numeric
```

### `bnpl_invoice_transactions` — Metabase table 120

Connects an invoice to its recorded cash/credit split. `invoice_id` links to `invoices.id`.

```text
id int8, created_at timestamptz, cash numeric, credit numeric,
invoice_id int8, credit_type varchar
```

### `bnpl_credit_installments` — Metabase table 118

One row per stored installment schedule entry. `customer_id` links to `users.user_id`; `payment_id` links to a gateway payment when populated.

```text
id int8, created_at timestamptz, amount numeric, penalty numeric,
number int2, due_date date, customer_id int8, payment_id int8?,
penalty_updated_at timestamptz?, source varchar
```

Metabase field IDs used by current questions: `created_at` 991, `number` 990, `due_date` 997, `customer_id` 993, `payment_id` 994, `amount` 998, `source` 1785.

### `bnpl_gateway_payments` — Metabase table 127

Gateway payment record. `confirmed_at` is the confirmation timestamp used by the current repayment and cash-flow analyses.

```text
id int8, created_at timestamptz, updated_at timestamptz,
gateway_token varchar, confirmed_at timestamptz?, amount numeric,
ref_code varchar, callback varchar, details jsonb?, gateway varchar,
user_id int8, transaction_id int8?, type varchar
```

Metabase field IDs: `created_at` 1052, `user_id` 1048, `confirmed_at` 1047, `transaction_id` 1068, `type` 1501.

### Payment and transaction bridges

| Table | Metabase table ID | Columns | Use |
|---|---:|---|---|
| `bnpl_credit_installment_transaction_items` | 122 | `id`, `created_at`, `installment_id`, `transaction_id` | Connects installment rows to transaction rows. The cash-flow extractor uses `transaction_id -> bnpl_invoice_transactions.id`. |
| `bnpl_gateway_installments_payment` | 130 | `id`, `created_at`, `installment_id`, `payment_id` | Alternate installment/payment bridge. Check for multiple rows before summing after a join. |

The above bridge keys are used by current code; inspect live foreign-key metadata and uniqueness before creating new joins. The source model deliberately avoids assigning an installment to an invoice when the bridge points to multiple invoices.

### Current credit and configuration

| Table | Metabase table ID | Important columns |
|---|---:|---|
| `bnpl_credits` | 123 | `id`, `customer_id`, `raw_balance`, `loan_raw_balance`, `expires_at`, `created_at`, `updated_at`. The table is unique by customer in the live schema. |
| `bnpl_credit_logs` | 121 | `id`, `customer_id`, `total_amount`, `type`, `created_at`. A credit event log, not a payment ledger. |
| `bnpl_customer_config` | 126 | `id`, `customer_id`, `created_at`, `updated_at`, `score`, `qualifying_credit_amount`, `qualifying_loan_amount`, `eligible_for_loan`, `renew_credit`, `has_used_settlement_time_extension`, `has_seen_terms_and_conditions`, validation timestamps, `facilities` JSONB, `back_cheques` JSONB, `national_card_ocr` JSONB, `national_card_image`. |

Customer-config JSON and identity fields can contain sensitive values. Use an explicit field allowlist. Do not select OCR payloads, cheque payloads, national identifiers, or contact fields into aggregate reports.

## Key relationships

```text
users.user_id
  ├── invoices.customer_id
  ├── bnpl_credit_installments.customer_id
  ├── bnpl_gateway_payments.user_id
  ├── bnpl_credits.customer_id
  ├── bnpl_credit_logs.customer_id
  └── bnpl_customer_config.customer_id

invoices.id
  └── bnpl_invoice_transactions.invoice_id
        ├── bnpl_gateway_payments.transaction_id  (join used by cash-flow code)
        └── bnpl_credit_installment_transaction_items.transaction_id
              └── bnpl_credit_installment_transaction_items.installment_id
                    └── bnpl_credit_installments.id

bnpl_credit_installments.payment_id
  └── bnpl_gateway_payments.id

bnpl_gateway_installments_payment.installment_id
  └── bnpl_credit_installments.id
bnpl_gateway_installments_payment.payment_id
  └── bnpl_gateway_payments.id
```

`bnpl_gateway_payments.transaction_id` can describe a transaction that is not an invoice transaction for every payment type. Use the invoice join only for the relevant records and validate the payment `type` and transaction relationship.

## Index and payment meaning

- Owner clarification on 2026-10-13: `number = 1` is due and payable at invoice time. Exclude it from AR, DPD, and DSO; report it separately as invoice-time/down-payment cash. Treat `number > 1` as scheduled receivables.
- This supersedes older notes that assigned invoice-time payment to index 0. If number 0 appears, flag it for business review until its meaning is confirmed.
- The DSO dashboard uses `created_at::date` as the origination-date proxy and the first confirmed gateway timestamp as settlement evidence. Recheck those assumptions if the source model changes.
- `payment_id IS NOT NULL` means a link exists. Use the linked `confirmed_at` to test a confirmed payment. The current schema has no direct status column on `bnpl_credit_installments`.
- `due_date` is scheduled timing. `confirmed_at` is recorded gateway confirmation timing. Neither field alone proves no later refund, reversal, or duplicate attempt.
- `source` values seen in analysis include `credit_in_4`, `loan`, and `dp_loan`. Product-specific business rules remain unconfirmed.

## Useful date fields

| Meaning | Field | Current Metabase field ID |
|---|---|---:|
| Invoice cohort | `invoices.created_at` | 1674 |
| Installment creation cohort | `bnpl_credit_installments.created_at` | 991 |
| Scheduled due date | `bnpl_credit_installments.due_date` | 997 |
| Actual gateway confirmation | `bnpl_gateway_payments.confirmed_at` | 1047 |

Refresh field IDs from live metadata before building dashboard field filters.
