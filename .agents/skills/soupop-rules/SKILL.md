---
name: soupop-rules
description: Soupop data definitions and query rules. Use before writing any SQL or answering any number question about Soupop sales, BNPL, loans, payments, cash flow or the chatbot.
---

# Soupop query rules

Apply all of these to every query. When a rule and a request conflict, say so and follow the rule unless the person confirms otherwise.

## Pick the right grain and date

| Question | One row per | Date to use |
|---|---|---|
| What was sold or invoiced | `invoices.id` | `invoices.created_at`; completed sales use `status = 'CONFIRMED'` |
| What is scheduled to be repaid | `bnpl_credit_installments.id` | `due_date`; only `number > 1` |
| What cash was received | confirmed gateway payment | `bnpl_gateway_payments.confirmed_at` |
| What is due or overdue | installment | `due_date` vs the report date, plus the linked payment's `confirmed_at` |
| Where a loan application is | `bnpl_customer_loans.id` | current `step` and `step_status` |
| Chatbot usage | `chatbot_chats` row | `created_at` (UTC) |

## Rules

1. Installment `number = 1` is paid at invoice time. Exclude it from AR, DPD and DSO; report it separately as upfront cash. If `number = 0` appears, flag it instead of guessing.
2. A filled `payment_id` is not proof of payment. Use `bnpl_gateway_payments.confirmed_at`.
3. Keep tables at their own grain. Pre-aggregate one-to-many tables before joining, or totals multiply.
4. Database 2 (PostgreSQL) uses Asia/Tehran days. Database 3 (ClickHouse) is UTC; convert with `toTimeZone(created_at, 'Asia/Tehran')` when the person means Tehran days, and say which you used.
5. Keep product labels as stored (`credit_in_4`, `loan`, `dp_loan`).
6. Credit scores and pilot credit amounts on dashboards 40 and 41 are research, not policy.
7. Chatbot: `app_events` with `name = 'ai_chat_bot'` are events, not chats. Report them separately from `chatbot_chats`.
8. SQL dialects differ: PostgreSQL `count(*)`, ClickHouse `count()`; ClickHouse maps use `extra['key']`.

For anything deeper, read the domain guide under `business-logic/` that matches the question. For what the business is and how it makes money (customers, vendors, commission), load the `soupop-business-overview` skill or the matching `soupop-*` business skill.
