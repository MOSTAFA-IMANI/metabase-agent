# Analytics asset map

These pages explain the analytics assets in this repository and where their results come from. Start at the domain guide when the question is about BNPL or loan operations.

## Analytics stories

| Story | Live asset | Source or builder | Main interpretation rule |
|---|---|---|---|
| Credit research and repayment outcomes | [Dashboard 41](https://mt.soupop.ir/dashboard/41) | [`build_credit_scoring_discovery_dashboard.py`](../../scripts-py/build_credit_scoring_discovery_dashboard.py); [CREDIT_SEGMENTATION_ANALYSIS.md](../Credit/CREDIT_SEGMENTATION_ANALYSIS.md) | Exploratory current-state comparison, not a leakage-safe backtest or a production score. Its older installment-index analysis predates the 2026-10-13 rule that number 1 is invoice-time; revalidate before reuse. |
| Credit pilot segments | [Dashboard 40](https://mt.soupop.ir/dashboard/40) | [`build_customer_credit_segmentation_dashboard.py`](../../scripts-py/build_customer_credit_segmentation_dashboard.py) | Pilot score and 1M-10M research amounts; validate before any real credit decision. |
| Credit-in-four overdue risk | [Question 1017](https://mt.soupop.ir/question/1017) | [`build_credit_in_4_default_risk_question.py`](../../scripts-py/build_credit_in_4_default_risk_question.py) | Measures overdue unpaid scheduled installments; inspect its exact cutoff and population before reuse. |
| DSO on paid installments | [Question 1007](https://mt.soupop.ir/question/1007) | [`build_dso_installment_question.py`](../../scripts-py/build_dso_installment_question.py) | Uses installment creation to confirmed gateway payment; an active installment is defined by an empty `payment_id` in the current builder. |
| Portfolio AR and DSO | [BNPL AR and DSO dashboard](https://mt.soupop.ir/dashboard/43) | [`build_bnpl_ar_dso_dashboard.py`](../../scripts-py/build_bnpl_ar_dso_dashboard.py); [definitions and assumptions](ar-dso.md) | Uses the updated rule that number 1 is invoice-time and excludes it from AR/DSO; amounts are native database units, and cash-collection days use a schedule-based NMV proxy. |
| Promo-code use | [Question 1062](https://mt.soupop.ir/question/1062) | [`build_promo_code_usage_question.py`](../../scripts-py/build_promo_code_usage_question.py) | One row per configured promo code; assignments, rules, and gamification are pre-aggregated to avoid multiplying order counts. |
| Customer record lookup | [Dashboard 42](https://mt.soupop.ir/dashboard/42) | [`build_search_dashboard.py`](../../scripts-py/build_search_dashboard.py) | Search by exact identifiers. It exposes profile and transactional detail; treat it as a restricted internal worklist. |
| Search product behavior | [Dashboard 33](https://mt.soupop.ir/dashboard/33) | Existing ClickHouse app-log questions | Search sessions and downstream product views are events, not BNPL transactions. |
| Chatbot product behavior | [Dashboard 37](https://mt.soupop.ir/dashboard/37) | [`build_ai_chatbot_analytics_dashboard.py`](../../scripts-py/build_ai_chatbot_analytics_dashboard.py), [`add_ai_chatbot_source_analytics.py`](../../scripts-py/add_ai_chatbot_source_analytics.py) | Persisted chats and app entry events are separate populations. See [chatbot guide](chatbot.md). |
| Cash and collections forecast | [Cash-flow guide](cash-flow.md) | [`fetch_cashflow_data.py`](../../scripts-py/fetch_cashflow_data.py), [`build_cashflow_projection.mjs`](../../scripts-js/build_cashflow_projection.mjs), workbook in `reports/` | This is a scenario forecast with explicit assumptions and cutoff dates, not a bank ledger. |

## Keep these populations separate

- Customer credit-risk tables describe PostgreSQL records and repayment schedules.
- Search and chatbot event tables live in ClickHouse database 3.
- A dashboard title does not define its metric. Inspect the saved question SQL and dashboard filter mappings.
- A customer lookup result can contain sensitive identifiers. Use aggregate cards for ordinary analytics.
- Current-state features such as `last_login`, current facilities, and today's balances cannot be used in historical credit decisions without decision-time snapshots.

## Builder behavior

Most `build_*.py` files create saved questions and a new dashboard. Rerunning one can create duplicates. Read the existing dashboard first. The source-analytics updater [`add_ai_chatbot_source_analytics.py`](../../scripts-py/add_ai_chatbot_source_analytics.py) is designed to preserve and update dashboard 37 idempotently.
