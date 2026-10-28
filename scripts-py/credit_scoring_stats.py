#!/usr/bin/env python3
"""Read-only portfolio statistics for the credit scoring / AI training brief.

Every query is an aggregate SELECT on database 2 (PostgreSQL, Asia/Tehran).
No customer-level rows are returned. Output is JSON on stdout.

Usage: python3 scripts-py/credit_scoring_stats.py [--only NAME ...] > stats.json
"""
import argparse
import json
import sys
import time

from metabase_agent import MetabaseClient

DB = 2

# One row per installment, with the earliest confirmed gateway payment from
# either link (installment.payment_id or the bnpl_gateway_installments_payment bridge).
INST = """
with pay as (
  select installment_id, min(confirmed_at) as confirmed_at from (
    select i.id as installment_id, p.confirmed_at
    from bnpl_credit_installments i join bnpl_gateway_payments p on p.id = i.payment_id
    union all
    select b.installment_id, p.confirmed_at
    from bnpl_gateway_installments_payment b join bnpl_gateway_payments p on p.id = b.payment_id
  ) x where confirmed_at is not null group by 1
), inst as (
  select i.id, i.customer_id, i.amount, i.penalty, i.number, i.due_date,
         coalesce(i.source, 'unknown') as source,
         (pay.confirmed_at at time zone 'Asia/Tehran')::date as paid_on,
         (now() at time zone 'Asia/Tehran')::date as today
  from bnpl_credit_installments i left join pay on pay.installment_id = i.id
)
"""

# Per user and product: the worst outcome over due scheduled installments (number > 1).
USER_STATUS = INST + """
, due as (
  select *, case
      when paid_on is null and due_date < today then 99
      when paid_on is null then -1
      else greatest(paid_on - due_date, 0) end as late_days
  from inst where number > 1 and due_date <= today
), per_user as (
  select source, customer_id, max(late_days) as worst, sum(amount) as due_amount,
         max(case when paid_on is null and due_date < today then today - due_date end) as oldest_unpaid_days
  from due group by 1, 2
  union all
  select 'ALL', customer_id, max(late_days), sum(amount),
         max(case when paid_on is null and due_date < today then today - due_date end)
  from due group by 2
)
"""

BUCKET = """case
  when worst = 99 then '8 never paid (overdue, unpaid)'
  when worst = -1 then '0 due today, not paid yet'
  when worst = 0 then '1 good: always on time'
  when worst <= 5 then '2 late 1-5 days'
  when worst <= 15 then '3 late 6-15 days'
  when worst <= 30 then '4 late 16-30 days'
  when worst <= 60 then '5 late 31-60 days'
  when worst <= 90 then '6 late 61-90 days'
  else '7 late over 90 days' end"""

QUERIES = {
    "users": """
select count(*) as all_rows,
       count(*) filter (where deleted_at is null) as not_deleted,
       count(*) filter (where deleted_at is null and is_active) as active,
       count(*) filter (where deleted_at is null and is_active and type = 1) as active_customers_type1,
       count(*) filter (where type = 0) as type0, count(*) filter (where type = 1) as type1,
       count(*) filter (where type = 2) as type2,
       count(*) filter (where last_login is not null and type = 1) as type1_ever_logged_in
from users""",
    "installed_users": """
select count(distinct d.user_id) as users_with_any_device,
       count(distinct d.user_id) filter (where d.deactivated_at is null) as users_with_active_device,
       count(distinct d.user_id) filter (where d.deactivated_at is null and u.type = 1) as customers_with_active_device,
       count(distinct d.user_id) filter (where d.last_open >= now() - interval '30 days') as opened_app_last_30d,
       (select count(distinct user_id) from fcm_devices where active) as users_with_active_push_token
from user_devices d join users u on u.user_id = d.user_id""",
    "installments_total": INST + """
select source, count(*) as installments, sum(amount) as amount, sum(penalty) as penalty,
       count(distinct customer_id) as distinct_users,
       count(*) filter (where number = 1) as number1_invoice_time,
       count(*) filter (where number > 1) as scheduled_number_gt1,
       count(*) filter (where number = 0) as number0_flag,
       min(due_date) as first_due, max(due_date) as last_due
from inst group by rollup(source) order by source""",
    "installments_due": INST + """
select source,
       count(*) as due_installments, sum(amount) as due_amount,
       count(distinct customer_id) as distinct_users_with_due,
       count(*) filter (where paid_on is not null) as paid, sum(amount) filter (where paid_on is not null) as paid_amount,
       count(*) filter (where paid_on is null and due_date < today) as unpaid_overdue,
       sum(amount) filter (where paid_on is null and due_date < today) as unpaid_overdue_amount
from inst where due_date <= today and number > 1 group by rollup(source) order by source""",
    "installments_due_incl_number1": INST + """
select source, count(*) as due_installments, sum(amount) as due_amount,
       count(distinct customer_id) as distinct_users_with_due
from inst where due_date <= today group by rollup(source) order by source""",
    "user_buckets": USER_STATUS + f"""
select source, {BUCKET} as bucket, count(*) as users, sum(due_amount) as due_amount
from per_user group by 1, 2 order by 1, 2""",
    "never_paid_aging": USER_STATUS + """
select source, case
  when oldest_unpaid_days <= 5 then '1-5' when oldest_unpaid_days <= 15 then '6-15'
  when oldest_unpaid_days <= 30 then '16-30' when oldest_unpaid_days <= 60 then '31-60'
  when oldest_unpaid_days <= 90 then '61-90' else '>90' end as days_overdue, count(*) as users
from per_user where worst = 99 group by 1, 2 order by 1, 2""",
    "installment_delay_buckets": INST + """
select source, case
  when paid_on is null and due_date < today then '8 unpaid overdue'
  when paid_on is null then '0 due today'
  when paid_on <= due_date then '1 on time'
  when paid_on - due_date <= 5 then '2 1-5' when paid_on - due_date <= 15 then '3 6-15'
  when paid_on - due_date <= 30 then '4 16-30' when paid_on - due_date <= 60 then '5 31-60'
  when paid_on - due_date <= 90 then '6 61-90' else '7 >90' end as bucket,
  count(*) as installments, sum(amount) as amount
from inst where number > 1 and due_date <= today group by 1, 2 order by 1, 2""",
    "feature_coverage": """
with c as (select user_id from users where deleted_at is null and type = 1),
b as (select distinct customer_id as user_id from bnpl_credit_installments)
select 'customers (type 1)' as feature, (select count(*) from c) as users, (select count(*) from b) as borrowers
union all select 'has car', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from cars where deleted_at is null
union all select 'has maintenance record', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from maintanence_services where deleted_at is null
union all select 'has customer config', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from bnpl_customer_config
union all select 'config.facilities filled', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from bnpl_customer_config where facilities is not null and facilities::text not in ('null', '{}', '""')
union all select 'config.back_cheques filled', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from bnpl_customer_config where back_cheques is not null and back_cheques::text not in ('null', '{}', '""')
union all select 'has credit balance row', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from bnpl_credits
union all select 'has identification (birth date, gender, salary)', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from user_identifications
union all select 'has address', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from user_addresses
union all select 'has device', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from user_devices
union all select 'was referred', count(distinct referred_user_id), count(distinct referred_user_id) filter (where referred_user_id in (select user_id from b)) from user_referrals
union all select 'has marketing attribution', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from user_performance_marketings
union all select 'has invoice', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from invoices
union all select 'has shop order', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from shop_orders where deleted_at is null
union all select 'has loan application', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from bnpl_customer_loans where deleted_at is null
union all select 'has car-record inquiry', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from car_records_inquiry_histories
union all select 'has support ticket', count(distinct user_id), count(distinct user_id) filter (where user_id in (select user_id from b)) from app_support_tickets
union all select 'wrote a review', count(distinct customer_id), count(distinct customer_id) filter (where customer_id in (select user_id from b)) from auto_service_review_reviews where deleted_at is null""",
    "cars_per_user": """
select cars_per_user, count(*) as users from (
  select user_id, least(count(*), 5) as cars_per_user from cars where deleted_at is null group by 1) x
group by 1 order by 1""",
    "json_keys": """
with cfg as (
  select case when jsonb_typeof(facilities) = 'object' then facilities end as f,
         case when jsonb_typeof(back_cheques) = 'object' then back_cheques end as bc
  from bnpl_customer_config)
select 'facilities' as json_field, k as json_key, count(*) as rows from cfg, jsonb_object_keys(f) k group by 1, 2
union all select 'back_cheques', k, count(*) from cfg, jsonb_object_keys(bc) k group by 1, 2
union all select 'facilities (stored type)', coalesce(jsonb_typeof(facilities), 'null'), count(*) from bnpl_customer_config group by 1, 2
union all select 'back_cheques (stored type)', coalesce(jsonb_typeof(back_cheques), 'null'), count(*) from bnpl_customer_config group by 1, 2
union all select 'user_identifications.details', k, count(*) from user_identifications, jsonb_object_keys(case when jsonb_typeof(details) = 'object' then details end) k group by 1, 2
order by 1, 3 desc""",
    "categories": """
select 'invoices.status' as field, status as value, count(*) as rows from invoices group by 1, 2
union all select 'installments.source', source, count(*) from bnpl_credit_installments group by 1, 2
union all select 'credit_logs.type', type, count(*) from bnpl_credit_logs group by 1, 2
union all select 'invoice_transactions.credit_type', credit_type, count(*) from bnpl_invoice_transactions group by 1, 2
union all select 'loan_collaterals.status', status, count(*) from bnpl_customer_loan_collaterals group by 1, 2
union all select 'customer_loans.step/status', coalesce(step, '-') || ' / ' || coalesce(step_status, '-'), count(*) from bnpl_customer_loans where deleted_at is null group by 1, 2
union all select 'credit_loans.step/status', coalesce(step, '-') || ' / ' || coalesce(step_status, '-'), count(*) from bnpl_customer_credit_loans where deleted_at is null group by 1, 2
union all select 'identifications.gender', gender, count(*) from user_identifications group by 1, 2
union all select 'identifications.salary_range', salary_range_in_millon, count(*) from user_identifications group by 1, 2
union all select 'config.score', score::text, count(*) from bnpl_customer_config group by 1, 2
union all select 'config.eligible_for_loan', eligible_for_loan::text, count(*) from bnpl_customer_config group by 1, 2
union all select 'cheques.is_digital', is_digital::text, count(*) from bnpl_customer_credit_loan_cheques where deleted_at is null group by 1, 2
order by 1, 3 desc""",
}


def run(client, sql):
    result = client.call("POST", "/api/dataset", {"database": DB, "type": "native", "native": {"query": sql}})
    if result.get("error"):
        raise RuntimeError(result["error"])
    data = result["data"]
    cols = [c["name"] for c in data["cols"]]
    return [dict(zip(cols, row)) for row in data["rows"]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args()
    client = MetabaseClient()
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": {}, "errors": {}}
    for name, sql in QUERIES.items():
        if args.only and name not in args.only:
            continue
        try:
            out["results"][name] = run(client, sql)
        except (Exception, SystemExit) as exc:  # keep going so one bad query doesn't hide the rest
            out["errors"][name] = str(exc)[:500]
        print(f"done {name}", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
