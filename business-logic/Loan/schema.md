# Loan schema

“Loan” appears in several related but different table families. Keep the application workflow, product terms, collateral records, and repayment schedule distinct. Schema was checked against live database 2 on 2026-10-10.

## Application workflow

### `bnpl_customer_loans` — Metabase table 217

One current customer loan application/workflow row per `id`. `customer_id` links to `users.user_id`; `loan_id` and `subscription_plan_id` point to the selected term records.

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
installments_count int2, amount numeric, interest_rate numeric,
digital_service_fee numeric, subscription_cost numeric,
subscription_plan_payment_method varchar, has_paid_subscription_fee bool,
customer_id int8, subscription_plan_id int8, step varchar, step_status varchar,
loan_id int8
```

`step` and `step_status` are the current workflow state. Do not treat them as a complete history or infer an approved/funded loan from one value without the product status definition.

### `bnpl_customer_loan_step_done_timelines`

```text
id int8, created_at timestamptz, step varchar, customer_loan_id int8
```

Use this table for recorded step-completion history. A loan may have multiple timeline rows, so aggregate to application grain before joining to a dashboard card that counts loans.

## Product terms and subscription plans

### `bnpl_loans` — Metabase table 219

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
installments_count int2, amount numeric, interest_rate numeric,
digital_service_fee numeric, subscription_plan_id int8
```

This is a product/term record, not the customer application row. A customer application links through `bnpl_customer_loans.loan_id`.

### `bnpl_loan_subscription_plans`

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
title varchar, description varchar, price numeric, duration_days int4, icon varchar
```

### `bnpl_loan_subscription_plan_details`

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
title varchar, description varchar, subscription_plan_id int8, icon varchar
```

The current schema gives the plan's displayed price and duration but does not by itself prove when a fee was collected. `has_paid_subscription_fee` is a stored application flag; reconcile to payment records for cash reporting.

## Collateral and cheque records

### `bnpl_customer_loan_collaterals`

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
cheque_id varchar, cheque_image varchar?, status varchar,
collateral_id int2, customer_loan_id int8
```

### `bnpl_collaterals`

```text
id int2, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
title varchar, description varchar, type varchar, loan_ratio numeric
```

### `bnpl_customer_credit_loan_cheques`

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
sayad_id varchar, image varchar?, amount numeric, due_date date, national_id varchar,
payee varchar, collateral_id int2, customer_loan_id int8,
received_auto_service_id int8?, holder_id int8, description varchar,
is_digital bool, returned_cheque_postal_number varchar,
returned_cheque_ref_number varchar, sayad_ref_number varchar,
sayad_registration_date date?, check_in_transit_amount numeric,
cleared_check_amount numeric, received_branch_id int8?
```

Cheque rows may contain national identifiers, images, and instrument references. Exclude these fields from broad reports. Use an explicit allowlist for operational worklists.

The current loan-operations builder joins `bnpl_customer_credit_loan_cheques.customer_loan_id` to `bnpl_customer_loans.id`. The table naming is ambiguous, and `bnpl_customer_credit_loans` is a separate table. Keep the builder's join labeled as a verified query pattern, not a guaranteed foreign-key contract, until the application owner confirms it.

## Separate credit-loan workflow tables

### `bnpl_customer_credit_loans`

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
amount numeric, customer_id int8, step varchar, step_status varchar
```

### `bnpl_customer_credit_loan_step_done_timelines`

```text
id int8, created_at timestamptz, step varchar, customer_loan_id int8
```

### `bnpl_credit_loans`

```text
id int8, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz?,
installment_count int2, interest_rate numeric
```

### `bnpl_credit_loan_collaterals`

```text
id int8, created_at timestamptz, updated_at timestamptz,
deleted_at timestamptz?, collateral_id int2
```

The live `bnpl_credit_loan_collaterals` columns do not expose an obvious loan/application key. Do not invent a join to `bnpl_credit_loans` without finding the missing relationship in live metadata or application code.

## Repayment bridge

### `bnpl_loan_installment_items`

```text
id int8, created_at timestamptz, customer_loan_id int8, installment_id int8
```

Join `customer_loan_id` to `bnpl_customer_loans.id` and `installment_id` to `bnpl_credit_installments.id`, then join `bnpl_credit_installments.payment_id` to `bnpl_gateway_payments.id` for confirmation evidence. Check mapping uniqueness before summing installment amounts.

## Grain and join summary

| Data | Table | Grain | Main join |
|---|---|---|---|
| Application | `bnpl_customer_loans` | One row per application ID | `customer_id -> users.user_id` |
| Product terms | `bnpl_loans` | One row per loan term/config | `loan_id -> bnpl_customer_loans.loan_id` |
| Plan details | `bnpl_loan_subscription_plans` | One row per plan | `subscription_plan_id -> bnpl_customer_loans.subscription_plan_id` |
| Step history | `bnpl_customer_loan_step_done_timelines` | One row per completed step | `customer_loan_id -> bnpl_customer_loans.id` |
| Application installments | `bnpl_loan_installment_items` | One row per loan/installment mapping | Application and installment IDs |
| Collateral status | `bnpl_customer_loan_collaterals` | One row per collateral mapping | `customer_loan_id -> bnpl_customer_loans.id` |
| Cheque operations | `bnpl_customer_credit_loan_cheques` | One row per cheque record | Builder currently joins `customer_loan_id` to `bnpl_customer_loans.id`; confirm semantics |

Loan amount units, interest conventions, application terminal statuses, and collateral acceptance rules are not defined by the schema. Confirm with Product/Risk before building financial or approval rules.
