# Business logic index

Use this index before writing a query or explaining a dashboard. It maps the main business events to their source tables, time fields, definitions, and live Metabase pages.

Schema notes were checked against the live Metabase metadata on 2026-10-10. PostgreSQL is database `2` (`Soupop Data`, timezone `Asia/Tehran`). ClickHouse is database `3` (`Clickhouse`, timestamps stored in UTC). Recheck live metadata before relying on table or field IDs.

## Start with the question being asked

| Question | Grain | Use this time or evidence |
|---|---|---|
| What was invoiced or sold? | One row per `invoices.id` | `invoices.created_at`; usually restrict to `status = 'CONFIRMED'` when measuring completed sales |
| What is scheduled for repayment? | One row per `bnpl_credit_installments.id` | Owner rule (2026-10-13): `number = 1` is due at invoice time; only `number > 1` enters AR/DSO scheduled receivables |
| What cash was received? | Confirmed gateway payment / linked installment | `bnpl_gateway_payments.confirmed_at`; a populated `payment_id` alone does not prove collection |
| What is due or overdue? | One row per installment | Compare the scheduled `due_date` with the reporting date and check the linked payment's `confirmed_at` |
| Where is a loan application in its process? | One row per `bnpl_customer_loans.id` | Current `step` and `step_status`; use the timeline table for step history |
| How much did people use the chatbot? | One row per persisted chat in `chatbot_chats` | `created_at`; count `app_events` separately because an event is not necessarily a saved chat |

## Rules that should travel with every query

- Business rule clarified by the owner on 2026-10-13: `number = 1` is payable at invoice time and must be excluded from AR, DPD, and DSO. Treat `number > 1` as future scheduled receivables; keep number 1 separate as upfront/down-payment cash.
- This current rule supersedes older repository notes that described index 0 as invoice-time payment. If number 0 appears in a future refresh, flag it as an unclassified index rather than silently changing the rule.
- `bnpl_credit_installments.payment_id` is a link. Use `bnpl_gateway_payments.confirmed_at` as confirmation evidence. The inspected schema has no explicit installment status column.
- `due_date` is the contractual schedule date. It is not the date cash entered the account. For realized cash timing, use the confirmed payment timestamp and validate partial payment, duplicate attempt, refund, and reversal behavior before treating a confirmed row as a fully collected installment.
- Keep `invoices`, installments, transaction bridges, and gateway attempts at their own grains. Pre-aggregate one-to-many tables before joining them to avoid multiplying invoice or installment amounts.
- Preserve raw product labels such as `credit_in_4`, `loan`, and `dp_loan`. Product-specific penalty and collection policy has not been confirmed in these sources.
- Use Asia/Tehran calendar boundaries for database 2 reporting. Use UTC for ClickHouse database 3 unless the report explicitly converts timezone.
- Treat credit scores and pilot credit amounts as research outputs unless a rule is explicitly labeled as the backend policy. The backend brief caps new-user initial credit at 5M Toman; the exploratory dashboard has a separate 10M research ladder.

## Domain guides

- [BNPL schema](BNPL/schema.md) and [BNPL stories and query patterns](BNPL/flows.md)
- [Loan schema](Loan/schema.md) and [Loan workflow stories](Loan/flows.md)
- [Analytics asset map](Analytics/README.md)
- [Cash-flow projection method](Analytics/cash-flow.md)
- [Chatbot analytics method](Analytics/chatbot.md)
- [Credit research](Credit/CREDIT_SEGMENTATION_ANALYSIS.md) and [new-user credit backend rules](Credit/BACKEND_NEW_USER_CREDIT_RULES.md)
- [Company business model](company/overview.md) (Persian) and the five Soupop business skills in [company/skills/](company/skills/)

## Live Metabase assets

Links were checked against the live dashboard and question listings on 2026-10-10. Open dashboards by ID; no slug is required.

| Story | Link | What it shows |
|---|---|---|
| BNPL installment operations | [BNPL - Installments](https://mt.soupop.ir/dashboard/7) | Existing installment monitoring dashboard |
| BNPL product model | [BNPL - Business Model](https://mt.soupop.ir/dashboard/8) | Existing BNPL business-model views |
| BNPL default risk | [BNPL - Default Risk](https://mt.soupop.ir/dashboard/16) | Existing default-risk views; inspect each card's definition before reuse |
| Loan operations | [Loan operation Dashboard](https://mt.soupop.ir/dashboard/30) | Application funnel, open follow-up, cheque work, fees, eligibility, and installment links |
| Empty duplicate loan dashboard | [Loan operation Dashboard, ID 29](https://mt.soupop.ir/dashboard/29) | An older dashboard with the same title; it had no cards when checked |
| Credit research | [Credit Scoring Discovery and Validation](https://mt.soupop.ir/dashboard/41) | Exploratory cohort and repayment comparisons; not a production approval system |
| Credit pilot segments | [Customer Credit Segmentation and Risk](https://mt.soupop.ir/dashboard/40) | Explainable pilot segments and user worklist; validate definitions before operational use |
| Customer lookup | [Search Dashboard](https://mt.soupop.ir/dashboard/42) | Internal record lookup; includes sensitive identifiers and should not be exported broadly |
| Search product analytics | [App Logs - Search & Discovery](https://mt.soupop.ir/dashboard/33) | Product search sessions, zero-result behavior, and downstream discovery |
| Chatbot analytics | [AI Chatbot Analytics Dashboard](https://mt.soupop.ir/dashboard/37) | Persisted chats, product events, model behavior, latency, tokens, and source labels |
| Credit-in-four default risk by amount | [Question 1017](https://mt.soupop.ir/question/1017) | Overdue unpaid installments by customer credit-size bucket |
| Paid-installment DSO | [Question 1007](https://mt.soupop.ir/question/1007) | DSO for paid installments in a filtered customer population |
| Promo-code usage | [Question 1062](https://mt.soupop.ir/question/1062) | Configured promo codes, shop-order usage, and separate order/invoice outcomes |

The loan builder created two same-name dashboards. ID 30 is the populated one. ID 29 was empty at the time of inspection. Do not rerun a `build_*.py` script to update an existing dashboard; builders commonly create duplicate questions and dashboards. `scripts-py/add_ai_chatbot_source_analytics.py` is the idempotent update example for dashboard 37.

## Workspace map

[START_HERE.md](../START_HERE.md) has the full folder map. The parts this index points to:

| File or group | Use |
|---|---|
| [AGENTS.md](../AGENTS.md) | How Codex works in this workspace: connection modes, safety rules, where to save |
| [.agents/skills/](../.agents/skills/) | House rules, saved-question and dashboard procedures, and the Soupop business skills |
| [company/](company/) | Business model overview and the source copy of the Soupop business skills |
| [Credit/](Credit/) | Credit research and the proposed new-user backend rules |
| [scripts-py/metabase_agent.py](../scripts-py/metabase_agent.py) | API client and command-line helper (fallback mode) |
| [scripts-py/](../scripts-py/) | Saved-question and dashboard builders (`build_*.py`, `add_*.py`); inspect the target and the script before running |
| [scripts-js/](../scripts-js/) | Cash-flow workbook builder |
| [sql/](../sql/) | PostgreSQL schema dump `soupop.sql` and the live snapshot from `scripts-py/fetch_schema.py`; live metadata wins when reachable |
| [docs/metabase/](../docs/metabase/) | Metabase REST API reference, API key setup, analyst API runbook and MCP setup |

## How to refresh this index

1. Confirm the database with `python3 scripts-py/metabase_agent.py list-databases`.
2. Read current columns from live Metabase metadata or `information_schema`; do not treat hard-coded Metabase IDs as permanent.
3. Inspect the query behind a saved question before repeating its title as a business definition.
4. Run aggregate checks at the requested grain and time boundary. Avoid personal fields unless the task requires them.
5. Record the checked date, unresolved semantics, and exact dashboard/question links in the owning domain guide.
