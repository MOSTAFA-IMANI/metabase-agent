#!/usr/bin/env python3
"""Build the numbered soupop-metabase collection tree and its 8 tabbed dashboards.

Safe to re-run: collections and dashboards are looked up by name and reused, and a
dashboard that already has cards is left alone. Existing dashboards and questions are
only read; charts reused from them are saved as copies in the new collections.

Run from the workspace root after `python3 scripts-py/metabase_agent.py login`:
    python3 scripts-py/build_soupop_structure.py
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metabase_agent import MetabaseClient  # noqa: E402

PG, CH = 2, 3
ROOT_NAME = "soupop-metabase"
LOG = []

# ---------------------------------------------------------------- new questions
# Database 2 uses Asia/Tehran days; database 3 (ClickHouse) is UTC.
Q = {
    "kpi_sales_30d": (PG, "scalar", "Confirmed sales, last 30 days",
        "select coalesce(sum(amount),0) as confirmed_sales from invoices "
        "where status = 'CONFIRMED' and created_at >= now() - interval '30 days'"),
    "kpi_invoices_30d": (PG, "scalar", "Confirmed invoices, last 30 days",
        "select count(*) as confirmed_invoices from invoices "
        "where status = 'CONFIRMED' and created_at >= now() - interval '30 days'"),
    "kpi_buyers_30d": (PG, "scalar", "Customers with a confirmed invoice, last 30 days",
        "select count(distinct customer_id) as customers from invoices "
        "where status = 'CONFIRMED' and created_at >= now() - interval '30 days'"),
    "kpi_vendors_30d": (PG, "scalar", "Vendors with a confirmed invoice, last 30 days",
        "select count(distinct auto_service_id) as vendors from invoices "
        "where status = 'CONFIRMED' and created_at >= now() - interval '30 days'"),
    "sales_monthly": (PG, "bar", "Confirmed sales by month",
        "select date_trunc('month', created_at)::date as month, sum(amount) as confirmed_sales, "
        "count(*) as invoices from invoices where status = 'CONFIRMED' "
        "and created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "signups_monthly": (PG, "bar", "New users by month",
        "select date_trunc('month', created_at)::date as month, count(*) as new_users from users "
        "where created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "signups_by_type": (PG, "bar", "New users by month and user type",
        "select date_trunc('month', created_at)::date as month, type::text as user_type, count(*) as new_users "
        "from users where created_at >= date_trunc('month', now()) - interval '12 months' group by 1, 2 order by 1, 2"),
    "referrals_monthly": (PG, "bar", "Referred sign-ups by month",
        "select date_trunc('month', created_at)::date as month, count(*) as referrals, "
        "sum(award_amount) as awards from user_referrals "
        "where created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "new_buyers_monthly": (PG, "bar", "First-time buyers by month",
        "with f as (select customer_id, min(created_at) as first_at from invoices "
        "where status = 'CONFIRMED' group by 1) "
        "select date_trunc('month', first_at)::date as month, count(*) as first_time_buyers from f "
        "where first_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "funnel": (PG, "row", "Customer funnel: users to credit to purchase",
        "select '1. Users' as stage, count(*) as customers from users where deleted_at is null "
        "union all select '2. Have a car', count(distinct user_id) from cars where deleted_at is null "
        "union all select '3. Have a BNPL credit', count(distinct customer_id) from bnpl_credits "
        "union all select '4. Confirmed invoice', count(distinct customer_id) from invoices where status = 'CONFIRMED' "
        "union all select '5. Paid with credit', count(distinct i.customer_id) from invoices i "
        "join bnpl_invoice_transactions t on t.invoice_id = i.id where i.status = 'CONFIRMED' and t.credit > 0 "
        "order by 1"),
    "credit_mix_monthly": (PG, "bar", "Confirmed sales by month: cash vs credit",
        "with t as (select invoice_id, sum(cash) as cash, sum(credit) as credit from bnpl_invoice_transactions group by 1) "
        "select date_trunc('month', i.created_at)::date as month, sum(t.cash) as cash, sum(t.credit) as credit "
        "from invoices i join t on t.invoice_id = i.id where i.status = 'CONFIRMED' "
        "and i.created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "credit_by_type": (PG, "pie", "Credit spend by credit type, last 90 days",
        "select coalesce(t.credit_type, 'unknown') as credit_type, sum(t.credit) as credit from bnpl_invoice_transactions t "
        "join invoices i on i.id = t.invoice_id where i.status = 'CONFIRMED' and t.credit > 0 "
        "and i.created_at >= now() - interval '90 days' group by 1 order by 2 desc"),
    "active_buyers_monthly": (PG, "line", "Active buyers by month (new vs returning)",
        "with f as (select customer_id, min(date_trunc('month', created_at)) as first_m from invoices "
        "where status = 'CONFIRMED' group by 1), m as (select distinct customer_id, date_trunc('month', created_at) as m "
        "from invoices where status = 'CONFIRMED') "
        "select m.m::date as month, count(*) filter (where m.m = f.first_m) as new_buyers, "
        "count(*) filter (where m.m > f.first_m) as returning_buyers from m join f using (customer_id) "
        "where m.m >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "repeat_rate": (PG, "scalar", "Share of buyers with 2+ confirmed invoices (all time)",
        "select round(100.0 * count(*) filter (where n >= 2) / nullif(count(*), 0), 1) as repeat_pct "
        "from (select customer_id, count(*) as n from invoices where status = 'CONFIRMED' group by 1) x"),
    "cohort_retention": (PG, "table", "Buyer cohorts: share buying again in later months",
        "with f as (select customer_id, date_trunc('month', min(created_at)) as cohort from invoices "
        "where status = 'CONFIRMED' group by 1), a as (select distinct i.customer_id, f.cohort, "
        "(extract(year from age(date_trunc('month', i.created_at), f.cohort)) * 12 + "
        "extract(month from age(date_trunc('month', i.created_at), f.cohort)))::int as k from invoices i "
        "join f using (customer_id) where i.status = 'CONFIRMED') "
        "select cohort::date as cohort_month, count(*) filter (where k = 0) as buyers, "
        "round(100.0 * count(*) filter (where k = 1) / nullif(count(*) filter (where k = 0), 0), 1) as m1_pct, "
        "round(100.0 * count(*) filter (where k = 2) / nullif(count(*) filter (where k = 0), 0), 1) as m2_pct, "
        "round(100.0 * count(*) filter (where k = 3) / nullif(count(*) filter (where k = 0), 0), 1) as m3_pct "
        "from a where cohort >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "vendors_monthly": (PG, "bar", "New and verified vendors by month",
        "select date_trunc('month', created_at)::date as month, count(*) as new_vendors, "
        "count(verified_at) as verified_vendors from auto_services where deleted_at is null "
        "and created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "vendors_status": (PG, "pie", "Vendor status",
        "select case when deleted_at is not null then 'Deleted' when verified_at is not null then 'Verified' "
        "else 'Not verified' end as status, count(*) as vendors from auto_services group by 1 order by 2 desc"),
    "vendors_by_province": (PG, "row", "Verified vendors by province (top 15)",
        "select province, count(*) as vendors from auto_services where deleted_at is null and verified_at is not null "
        "group by 1 order by 2 desc limit 15"),
    "active_vendors_monthly": (PG, "line", "Vendors with a confirmed invoice, by month",
        "select date_trunc('month', created_at)::date as month, count(distinct auto_service_id) as active_vendors "
        "from invoices where status = 'CONFIRMED' and created_at >= date_trunc('month', now()) - interval '12 months' "
        "group by 1 order by 1"),
    "maintenance_monthly": (PG, "bar", "Maintenance services logged by month",
        "select date_trunc('month', created_at)::date as month, count(*) as services, "
        "count(distinct auto_service_id) as vendors from maintanence_services where deleted_at is null "
        "and created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "top_vendors_sales": (PG, "table", "Top 20 vendors by confirmed sales, last 90 days",
        "select a.name as vendor, a.city, count(*) as invoices, sum(i.amount) as confirmed_sales "
        "from invoices i join auto_services a on a.auto_service_id = i.auto_service_id "
        "where i.status = 'CONFIRMED' and i.created_at >= now() - interval '90 days' "
        "group by 1, 2 order by 4 desc limit 20"),
    "vendor_ratings": (PG, "table", "Vendor ratings (5+ published reviews)",
        "select a.name as vendor, count(*) as reviews, round(avg(r.rating), 2) as avg_rating, "
        "round(100.0 * count(r.replied_at) / count(*), 1) as replied_pct from auto_service_review_reviews r "
        "join auto_services a on a.auto_service_id = r.auto_service_id where r.deleted_at is null and r.is_published "
        "group by 1 having count(*) >= 5 order by avg_rating asc, reviews desc limit 30"),
    "invoices_by_method": (PG, "bar", "Confirmed invoices by month and payment method",
        "select date_trunc('month', created_at)::date as month, coalesce(payment_method, 'unknown') as payment_method, "
        "count(*) as invoices from invoices where status = 'CONFIRMED' "
        "and created_at >= date_trunc('month', now()) - interval '12 months' group by 1, 2 order by 1, 2"),
    "invoices_by_status": (PG, "pie", "Invoices by status, last 90 days",
        "select status, count(*) as invoices from invoices where created_at >= now() - interval '90 days' "
        "group by 1 order by 2 desc"),
    "commission_monthly": (PG, "bar", "Commission and fees by month (confirmed invoices)",
        "with c as (select invoice_id, sum(amount) as commission from invoice_commissions group by 1) "
        "select date_trunc('month', i.created_at)::date as month, sum(coalesce(c.commission, 0)) as commission, "
        "sum(coalesce(i.digital_service_fee, 0)) as digital_service_fee, sum(coalesce(i.interest_amount, 0)) as interest "
        "from invoices i left join c on c.invoice_id = i.id where i.status = 'CONFIRMED' "
        "and i.created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "kpi_commission_30d": (PG, "scalar", "Commission on confirmed invoices, last 30 days",
        "select coalesce(sum(c.amount), 0) as commission from invoice_commissions c join invoices i on i.id = c.invoice_id "
        "where i.status = 'CONFIRMED' and i.created_at >= now() - interval '30 days'"),
    "settlements_monthly": (PG, "bar", "Vendor settlements by month and status",
        "select date_trunc('month', datetime)::date as month, status, sum(amount) as amount, count(*) as settlements "
        "from invoice_auto_service_settlements where datetime >= date_trunc('month', now()) - interval '12 months' "
        "group by 1, 2 order by 1, 2"),
    "settlements_status": (PG, "table", "Vendor settlements by status, last 90 days",
        "select status, count(*) as settlements, count(distinct auto_service_id) as vendors, sum(amount) as amount "
        "from invoice_auto_service_settlements where datetime >= now() - interval '90 days' group by 1 order by 4 desc"),
    "events_daily": (CH, "line", "App events and users per day (UTC), last 60 days",
        "select toDate(created_at) as day, count() as events, uniqExact(user_id) as users from app_events "
        "where created_at >= now() - interval 60 day group by day order by day"),
    "events_top": (CH, "row", "Top 20 app events, last 30 days (UTC)",
        "select name, count() as events from app_events where created_at >= now() - interval 30 day "
        "group by name order by events desc limit 20"),
    "events_by_os": (CH, "pie", "App event users by OS, last 30 days (UTC)",
        "select ifNull(nullIf(toString(os), ''), 'Unknown') as os, uniqExact(user_id) as users from app_events "
        "where created_at >= now() - interval 30 day group by os order by users desc"),
    "tickets_monthly": (PG, "bar", "Support tickets by month and status",
        "select date_trunc('month', created_at)::date as month, status, count(*) as tickets from app_support_tickets "
        "where created_at >= date_trunc('month', now()) - interval '12 months' group by 1, 2 order by 1, 2"),
    "tickets_by_category": (PG, "row", "Support tickets by category, last 90 days",
        "select coalesce(c.name, 'No category') as category, count(*) as tickets from app_support_tickets t "
        "left join app_support_ticket_categories c on c.id = t.category_id "
        "where t.created_at >= now() - interval '90 days' group by 1 order by 2 desc"),
    "tickets_open": (PG, "table", "Tickets not closed, by status and priority",
        "select status, priority, count(*) as tickets, min(created_at)::date as oldest from app_support_tickets "
        "where lower(status) not in ('closed', 'resolved', 'done') group by 1, 2 order by 3 desc"),
    "feedback_monthly": (PG, "bar", "App feedback submissions by month",
        "select date_trunc('month', created_at)::date as month, count(*) as feedbacks from app_feedbacks "
        "where created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "reviews_monthly": (PG, "line", "Published reviews and average rating by month",
        "select date_trunc('month', created_at)::date as month, count(*) as reviews, round(avg(rating), 2) as avg_rating "
        "from auto_service_review_reviews where deleted_at is null and is_published "
        "and created_at >= date_trunc('month', now()) - interval '12 months' group by 1 order by 1"),
    "rating_dist": (PG, "bar", "Rating distribution, last 90 days",
        "select rating, count(*) as reviews from auto_service_review_reviews where deleted_at is null "
        "and created_at >= now() - interval '90 days' group by 1 order by 1"),
    "review_reply": (PG, "scalar", "Share of reviews with a vendor reply, last 90 days (%)",
        "select round(100.0 * count(replied_at) / nullif(count(*), 0), 1) as replied_pct "
        "from auto_service_review_reviews where deleted_at is null and created_at >= now() - interval '90 days'"),
    "fresh_pg": (PG, "table", "Freshness: latest record per PostgreSQL table (Tehran time)",
        "select 'invoices' as table_name, max(created_at) as latest_record, count(*) filter (where created_at >= now() - interval '1 day') as rows_last_24h from invoices "
        "union all select 'users', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from users "
        "union all select 'bnpl_credit_installments', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from bnpl_credit_installments "
        "union all select 'bnpl_gateway_payments', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from bnpl_gateway_payments "
        "union all select 'bnpl_customer_loans', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from bnpl_customer_loans "
        "union all select 'shop_orders', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from shop_orders "
        "union all select 'app_support_tickets', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from app_support_tickets "
        "union all select 'auto_service_review_reviews', max(created_at), count(*) filter (where created_at >= now() - interval '1 day') from auto_service_review_reviews "
        "order by 2 asc"),
    "fresh_ch": (CH, "table", "Freshness: latest record per ClickHouse table (UTC)",
        "select 'app_events' as table_name, max(created_at) as latest_record, countIf(created_at >= now() - interval 1 day) as rows_last_24h from app_events "
        "union all select 'chatbot_chats', max(created_at), countIf(created_at >= now() - interval 1 day) from chatbot_chats"),
    "pg_daily_rows": (PG, "line", "Daily new rows: invoices, users, payments (last 30 days)",
        "with d as (select generate_series(current_date - 30, current_date, interval '1 day')::date as day), "
        "i as (select created_at::date as day, count(*) as n from invoices where created_at >= current_date - 30 group by 1), "
        "u as (select created_at::date as day, count(*) as n from users where created_at >= current_date - 30 group by 1), "
        "p as (select created_at::date as day, count(*) as n from bnpl_gateway_payments where created_at >= current_date - 30 group by 1) "
        "select d.day, coalesce(i.n, 0) as invoices, coalesce(u.n, 0) as users, coalesce(p.n, 0) as gateway_payments "
        "from d left join i using (day) left join u using (day) left join p using (day) order by 1"),
    "instr_null_users": (CH, "table", "Event quality by event name, last 7 days (UTC)",
        "select name, count() as events, round(100 * countIf(user_id = 0 or isNull(user_id)) / count(), 1) as pct_no_user, "
        "round(100 * countIf(app_name = '') / count(), 1) as pct_no_app_name, uniqExact(os) as os_values "
        "from app_events where created_at >= now() - interval 7 day group by name order by events desc limit 30"),
    "instr_new_events": (CH, "table", "Event names first seen in the last 30 days (UTC)",
        "select name, min(created_at) as first_seen, count() as events from app_events "
        "group by name having first_seen >= now() - interval 30 day order by first_seen desc"),
    "instr_unconfirmed": (PG, "scalar", "Installments linked to a payment that is not confirmed",
        "select count(*) as installments from bnpl_credit_installments i join bnpl_gateway_payments p on p.id = i.payment_id "
        "where p.confirmed_at is null"),
    "instr_index_zero": (PG, "scalar", "Installments with number 0 (should be zero; flag if not)",
        "select count(*) as installments from bnpl_credit_installments where number = 0"),
}

KPI_DEFINITIONS = """## KPI definitions

| KPI | Definition | Source |
|---|---|---|
| Confirmed sales | Sum of `invoices.amount` where `status = 'CONFIRMED'`, by `invoices.created_at` (Tehran days) | DB 2 |
| Confirmed invoices | Count of confirmed `invoices.id` | DB 2 |
| Active customer / buyer | Customer with at least one confirmed invoice in the period | DB 2 |
| Active vendor | `auto_services` row with at least one confirmed invoice in the period | DB 2 |
| New users | `users.created_at` in the period (all user types) | DB 2 |
| Commission | Sum of `invoice_commissions.amount` on confirmed invoices | DB 2 |
| Scheduled receivables (AR) | Installments with `number > 1`; `number = 1` is paid at invoice time and excluded from AR, DPD and DSO | DB 2 |
| Cash collected | Gateway payments with `bnpl_gateway_payments.confirmed_at` set; a filled `payment_id` alone is not proof | DB 2 |
| Loan stage | Current `bnpl_customer_loans.step` and `step_status` | DB 2 |
| Chats | Rows in `chatbot_chats` (UTC). `app_events` with `name = 'ai_chat_bot'` are events, not chats | DB 3 |
| App events / users | Rows and distinct `user_id` in `app_events` (UTC days) | DB 3 |

Credit scores and pilot credit amounts (credit research dashboards) are research outputs, not policy.
Amounts are in the database's native unit. Full rules: `business-logic/README.md` in the soupop-data workspace."""

NO_DATA = "**No data source yet.** This tab is a placeholder; tell the data team what you want to see here."

# ---------------------------------------------------------------- structure
# Tab items: ("q", key, w, h) new question | ("dash", id) copy a dashboard's charts |
#            ("card", id, w, h) copy one question | ("text", markdown, w, h)
STRUCTURE = [
    ("01 Overview", "01.1 Business Overview", "Company-wide KPIs across demand, supply and transactions.", [
        ("Executive", [("q", "kpi_sales_30d", 6, 3), ("q", "kpi_invoices_30d", 6, 3), ("q", "kpi_buyers_30d", 6, 3),
                       ("q", "kpi_vendors_30d", 6, 3), ("q", "sales_monthly", 24, 6)]),
        ("Demand", [("q", "signups_monthly", 12, 6), ("q", "new_buyers_monthly", 12, 6), ("q", "active_buyers_monthly", 24, 6)]),
        ("Supply", [("q", "vendors_monthly", 12, 6), ("q", "active_vendors_monthly", 12, 6)]),
        ("Transactions", [("q", "kpi_commission_30d", 6, 3), ("q", "credit_mix_monthly", 24, 6), ("q", "invoices_by_method", 24, 6)]),
    ]),
    ("02 Demand", "02.1 Customer Lifecycle", "Customer acquisition, funnel to credit use, and retention.", [
        ("Acquisition", [("q", "signups_by_type", 24, 6), ("q", "referrals_monthly", 12, 6), ("q", "new_buyers_monthly", 12, 6)]),
        ("Funnel & Credit Use", [("q", "funnel", 12, 6), ("q", "credit_by_type", 12, 6), ("q", "credit_mix_monthly", 24, 6)]),
        ("Retention", [("q", "repeat_rate", 6, 3), ("q", "active_buyers_monthly", 24, 6), ("q", "cohort_retention", 24, 8)]),
    ]),
    ("03 Supply", "03.1 Vendor Performance", "Vendor (auto service) onboarding, activity, sales and quality.", [
        ("Lifecycle", [("q", "vendors_monthly", 24, 6), ("q", "vendors_status", 12, 6), ("q", "vendors_by_province", 12, 6)]),
        ("Active Services", [("q", "active_vendors_monthly", 12, 6), ("q", "maintenance_monthly", 12, 6)]),
        ("Financial & Quality", [("q", "top_vendors_sales", 24, 8), ("q", "vendor_ratings", 24, 8)]),
    ]),
    ("04 Transactions & Revenue", "04.1 Transactions & Cashflow", "Invoices, commission, vendor settlements and collections.", [
        ("Transactions & Commission", [("q", "kpi_sales_30d", 6, 3), ("q", "kpi_commission_30d", 6, 3),
                                       ("q", "invoices_by_status", 12, 6), ("q", "commission_monthly", 24, 6),
                                       ("q", "invoices_by_method", 24, 6)]),
        ("Settlements", [("q", "settlements_monthly", 24, 6), ("q", "settlements_status", 24, 5)]),
        ("Collections", [("dash", 43)]),
    ]),
    ("05 Credit & Risk", "05.1 Credit & Loan Operations", "BNPL credit portfolio, repayment and loan operations.", [
        ("Portfolio", [("dash", 8), ("dash", 16)]),
        ("Repayment", [("dash", 7), ("card", 1017, 12, 6), ("card", 1007, 12, 6)]),
        ("Loans & Cheques", [("dash", 30)]),
    ]),
    ("06 Product Analytics", "06.1 Product Usage", "App engagement, search and chatbot usage (ClickHouse, UTC).", [
        ("App Engagement", [("q", "events_daily", 24, 6), ("q", "events_top", 12, 8), ("q", "events_by_os", 12, 8)]),
        ("Search", [("dash", 33)]),
        ("Chatbot", [("dash", 37)]),
    ]),
    ("07 Operations", "07.1 Support & Service Quality", "Support tickets, feedback and vendor service quality.", [
        ("Support", [("q", "tickets_monthly", 24, 6), ("q", "tickets_by_category", 12, 6), ("q", "tickets_open", 12, 6),
                     ("q", "feedback_monthly", 24, 5)]),
        ("Service Quality", [("q", "review_reply", 6, 3), ("q", "reviews_monthly", 24, 6), ("q", "rating_dist", 12, 6)]),
    ]),
    ("08 Data Quality", "08.1 Data Health", "Data freshness, event instrumentation checks and KPI definitions.", [
        ("Freshness", [("q", "fresh_pg", 12, 6), ("q", "fresh_ch", 12, 4), ("q", "pg_daily_rows", 24, 6)]),
        ("Instrumentation", [("q", "instr_unconfirmed", 6, 3), ("q", "instr_index_zero", 6, 3),
                             ("q", "instr_null_users", 24, 8), ("q", "instr_new_events", 24, 6)]),
        ("KPI Definitions", [("text", KPI_DEFINITIONS, 24, 14)]),
    ]),
]


# ---------------------------------------------------------------- helpers
class Builder:
    def __init__(self):
        self.mb = MetabaseClient()
        self.temp_id = -1
        self.card_cache = {}

    def next_id(self):
        self.temp_id -= 1
        return self.temp_id

    def collection(self, name, parent_id, description=None):
        items = self.mb.call("GET", f"/api/collection/{parent_id if parent_id else 'root'}/items?models=collection")
        for item in items.get("data", items if isinstance(items, list) else []):
            if item.get("name") == name and item.get("model") == "collection":
                return item["id"]
        body = {"name": name}
        if parent_id:
            body["parent_id"] = parent_id
        if description:
            body["description"] = description
        created = self.mb.call("POST", "/api/collection", body)
        LOG.append(f"collection created: {name} ({created['id']})")
        return created["id"]

    def find_dashboard(self, name, collection_id):
        items = self.mb.call("GET", f"/api/collection/{collection_id}/items?models=dashboard")
        for item in items.get("data", []):
            if item.get("name") == name:
                return item["id"]
        return None

    def test_sql(self, db, sql):
        res = self.mb.call("POST", "/api/dataset", {"database": db, "type": "native", "native": {"query": sql}})
        if res.get("status") == "failed" or res.get("error"):
            return str(res.get("error"))[:300]
        return None

    def new_question(self, key, collection_id, number):
        db, display, title, sql = Q[key]
        if key in self.card_cache:
            return self.card_cache[key], None
        err = self.test_sql(db, sql)
        if err:
            LOG.append(f"SKIPPED {key}: {err}")
            return None, err
        name = f"{number} {title}"
        card = self.mb.call("POST", "/api/card", {
            "name": name, "type": "question", "display": display, "collection_id": collection_id,
            "description": f"Built for the soupop-metabase dashboards. Database {db} ({'Tehran' if db == PG else 'UTC'} time).",
            "visualization_settings": {},
            "dataset_query": {"database": db, "type": "native", "native": {"query": sql, "template-tags": {}}},
        })
        self.card_cache[key] = card["id"]
        return card["id"], None

    def copy_card(self, card_id, collection_id, prefix):
        src = self.mb.call("GET", f"/api/card/{card_id}")
        body = {
            "name": f"{prefix} {src['name']}"[:250], "type": src.get("type") or "question",
            "display": src["display"], "collection_id": collection_id,
            "description": ((src.get("description") or "") + f"\n\nCopy of question {card_id}.").strip(),
            "visualization_settings": src.get("visualization_settings") or {},
            "dataset_query": src["dataset_query"],
        }
        if src.get("parameters"):
            body["parameters"] = src["parameters"]
        return self.mb.call("POST", "/api/card", body)["id"]

    def text(self, markdown, tab, row, w, h, display="text"):
        return {"id": self.next_id(), "card_id": None, "dashboard_tab_id": tab, "row": row, "col": 0,
                "size_x": w, "size_y": h, "parameter_mappings": [], "series": [],
                "visualization_settings": {"virtual_card": {"name": None, "display": display, "visualization_settings": {},
                                                            "dataset_query": {}, "archived": False}, "text": markdown}}


def build():
    b = Builder()
    root = b.collection(ROOT_NAME, None, "Numbered company dashboards. 01-08 set the order.")
    results = []
    for coll_name, dash_name, dash_desc, tabs in STRUCTURE:
        number = dash_name.split(" ")[0]
        coll = b.collection(coll_name, root)
        existing = b.find_dashboard(dash_name, coll)
        if existing and b.mb.call("GET", f"/api/dashboard/{existing}").get("dashcards"):
            LOG.append(f"kept existing {dash_name} ({existing})")
            results.append((coll_name, coll, dash_name, existing))
            continue
        dash_id = existing or b.mb.call("POST", "/api/dashboard", {"name": dash_name, "collection_id": coll,
                                                                  "description": dash_desc})["id"]
        b.card_cache = {}  # one copy of each new question per collection
        tab_defs, dashcards, parameters = [], [], []
        for t_index, (tab_name, items) in enumerate(tabs):
            tab_id = -(t_index + 1) * 1000
            tab_defs.append({"id": tab_id, "name": tab_name})
            row, col, row_h = 0, 0, 0
            placed = 0
            for item in items:
                kind = item[0]
                if kind in ("q", "card", "text"):
                    w, h = item[-2], item[-1]
                    if col + w > 24:
                        row, col, row_h = row + row_h, 0, 0
                    if kind == "text":
                        dashcards.append(b.text(item[1], tab_id, row, w, h))
                        dashcards[-1]["col"] = col
                    else:
                        if kind == "q":
                            cid, err = b.new_question(item[1], coll, number)
                        else:
                            cid, err = b.copy_card(item[1], coll, number), None
                        if not cid:
                            continue
                        dashcards.append({"id": b.next_id(), "card_id": cid, "dashboard_tab_id": tab_id, "row": row,
                                          "col": col, "size_x": w, "size_y": h, "parameter_mappings": [], "series": [],
                                          "visualization_settings": {}})
                    placed += 1
                    col += w
                    row_h = max(row_h, h)
                elif kind == "dash":
                    row, col, row_h = row + row_h, 0, 0
                    src = b.mb.call("GET", f"/api/dashboard/{item[1]}")
                    src_tabs = {t["id"]: t["name"] for t in src.get("tabs") or []}
                    src_cards = sorted(src.get("dashcards") or [], key=lambda d: (
                        list(src_tabs).index(d.get("dashboard_tab_id")) if d.get("dashboard_tab_id") in src_tabs else 0,
                        d["row"], d["col"]))
                    # Carry over the source dashboard's filters with new ids so they cannot clash.
                    pmap = {}
                    taken = {p["slug"] for p in parameters}
                    for p in src.get("parameters") or []:
                        np = copy.deepcopy(p)
                        np["id"] = f"d{item[1]}_{p['id']}"[:36]
                        slug = p.get("slug") or p["id"]
                        if slug in taken:
                            np["name"] = f"{p['name']} ({src['name'][:20]})"
                            np["slug"] = f"{slug}_d{item[1]}"
                        taken.add(np.get("slug"))
                        np.pop("filteringParameters", None)
                        pmap[p["id"]] = np["id"]
                        parameters.append(np)
                    dashcards.append(b.text(f"### From: [{src['name']}](/dashboard/{item[1]})", tab_id, row, 24, 1, "heading"))
                    row += 1
                    base, current_src_tab, tab_offset, max_bottom = row, None, 0, row
                    for dc in src_cards:
                        if dc.get("dashboard_tab_id") != current_src_tab and src_tabs:
                            current_src_tab = dc.get("dashboard_tab_id")
                            base = max_bottom
                            dashcards.append(b.text(f"#### {src_tabs.get(current_src_tab, '')}", tab_id, base, 24, 1, "heading"))
                            base += 1
                            max_bottom = base
                        new = {"id": b.next_id(), "dashboard_tab_id": tab_id, "row": base + dc["row"], "col": dc["col"],
                               "size_x": dc["size_x"], "size_y": dc["size_y"],
                               "visualization_settings": copy.deepcopy(dc.get("visualization_settings") or {}),
                               "parameter_mappings": [], "series": []}
                        if dc.get("card_id"):
                            new["card_id"] = b.copy_card(dc["card_id"], coll, number)
                            for s in dc.get("series") or []:
                                new["series"].append({"id": b.copy_card(s["id"], coll, number)})
                            for m in dc.get("parameter_mappings") or []:
                                if m.get("parameter_id") in pmap:
                                    nm = dict(m, parameter_id=pmap[m["parameter_id"]], card_id=new["card_id"])
                                    new["parameter_mappings"].append(nm)
                        else:
                            new["card_id"] = None
                        if dc.get("inline_parameters"):
                            new["inline_parameters"] = [pmap.get(p, p) for p in dc["inline_parameters"]]
                        dashcards.append(new)
                        placed += 1
                        max_bottom = max(max_bottom, new["row"] + new["size_y"])
                    row, col, row_h = max_bottom, 0, 0
            if placed == 0:
                dashcards.append(b.text(NO_DATA, tab_id, 0, 24, 2))
        body = {"tabs": tab_defs, "dashcards": dashcards}
        if parameters:
            body["parameters"] = parameters
        b.mb.call("PUT", f"/api/dashboard/{dash_id}", body)
        LOG.append(f"dashboard built: {dash_name} ({dash_id}) with {len(dashcards)} cards")
        results.append((coll_name, coll, dash_name, dash_id))

    base = b.mb.base_url
    print("\n".join(LOG))
    print("\nRESULT")
    print(f"root collection: {base}/collection/{root}")
    for coll_name, coll, dash_name, dash_id in results:
        print(f"{dash_name}: {base}/dashboard/{dash_id}  (collection {base}/collection/{coll})")
    Path(__file__).resolve().parents[1].joinpath("build_soupop_structure.log").write_text(
        "\n".join(LOG) + "\n" + json.dumps([dict(zip(["collection", "collection_id", "dashboard", "dashboard_id"], r))
                                           for r in results], ensure_ascii=False, indent=1))


def check():
    """Read-only: run every new query and read every source dashboard/question."""
    b = Builder()
    bad = 0
    for key, (db, _, title, sql) in Q.items():
        err = b.test_sql(db, sql)
        bad += bool(err)
        print(("FAIL " if err else "ok   ") + key + (f": {err}" if err else ""))
    for _, _, _, tabs in STRUCTURE:
        for _, items in tabs:
            for item in items:
                if item[0] == "dash":
                    d = b.mb.call("GET", f"/api/dashboard/{item[1]}")
                    print(f"ok   dashboard {item[1]} {d['name']}: {len(d.get('dashcards') or [])} cards, "
                          f"{len(d.get('tabs') or [])} tabs, {len(d.get('parameters') or [])} filters")
                elif item[0] == "card":
                    c = b.mb.call("GET", f"/api/card/{item[1]}")
                    print(f"ok   question {item[1]} {c['name']}")
    print(f"\n{bad} queries failed")


if __name__ == "__main__":
    check() if "--check" in sys.argv else build()
