#!/usr/bin/env python3
"""Build exploratory, non-production credit-scoring validation questions."""

from metabase_agent import MetabaseClient, load_env, print_json


DASHBOARD_NAME = "Credit Scoring Discovery and Validation"
DATABASE_ID = 2

PAYMENT_CTE = r"""
with payment_rows as (
  select
    i.id as installment_id,
    i.customer_id,
    lower(i.source) as source,
    i.number as installment_number,
    i.amount,
    i.due_date,
    i.payment_id,
    gp.created_at as payment_created_at,
    gp.confirmed_at,
    case when gp.confirmed_at is not null
      then gp.confirmed_at::date - i.due_date
    end as payment_delay_days
  from bnpl_credit_installments i
  left join bnpl_gateway_payments gp on gp.id = i.payment_id
),
user_repayment as (
  select
    customer_id,
    count(*) as total_installments,
    count(*) filter (where confirmed_at is not null) as paid_installments,
    count(*) filter (where confirmed_at is null and due_date > current_date) as future_installments,
    count(*) filter (where confirmed_at is null and due_date = current_date) as currently_due_installments,
    count(*) filter (where confirmed_at is null and due_date < current_date and current_date - due_date between 1 and 5) as unpaid_within_grace_installments,
    count(*) filter (where confirmed_at is null and due_date < current_date and current_date - due_date > 5) as unpaid_over_5_days_installments,
    count(*) filter (where confirmed_at is not null and payment_delay_days <= 0) as on_time_installments,
    count(*) filter (where confirmed_at is not null and payment_delay_days between 1 and 5) as paid_within_grace_installments,
    count(*) filter (where confirmed_at is not null and payment_delay_days > 5) as paid_over_5_days_late_installments,
    count(*) filter (where payment_id is not null and confirmed_at is null) as linked_payment_unconfirmed_installments,
    sum(amount) as scheduled_amount,
    sum(amount) filter (where confirmed_at is null and due_date < current_date and current_date - due_date > 5) as severe_unpaid_amount,
    avg(payment_delay_days::numeric) filter (where confirmed_at is not null) as average_payment_delay_days
  from payment_rows
  group by customer_id
),
user_delay as (
  select
    customer_id,
    percentile_cont(0.5) within group (order by payment_delay_days) as median_payment_delay_days,
    max(payment_delay_days) as maximum_payment_delay_days
  from payment_rows
  where confirmed_at is not null
  group by customer_id
)
"""

QUESTIONS = [
    {
        "name": "Credit Discovery - Existing vs New Cohort",
        "display": "bar",
        "description": "Separates active type-1 customers into confirmed repayment history, installment history without confirmed payment, and no installment history.",
        "sql": PAYMENT_CTE + r"""
select
  case
    when coalesce(ur.paid_installments, 0) > 0 then 'Existing - confirmed repayment history'
    when coalesce(ur.total_installments, 0) > 0 then 'Existing - installment history, no confirmed payment'
    else 'New - no installment history'
  end as user_cohort,
  count(*) as users,
  count(*) filter (where u.last_login >= current_timestamp - interval '30 days') as active_last_30_days,
  round(avg((current_date - u.created_at::date)::numeric), 1) as avg_account_age_days,
  round(avg(coalesce(ur.total_installments, 0)), 2) as avg_installments,
  round(avg(coalesce(ur.paid_installments, 0)), 2) as avg_paid_installments
from users u
left join user_repayment ur on ur.customer_id = u.user_id
where u.type = 1 and u.deleted_at is null and u.is_active
group by 1
order by users desc;
""",
    },
    {
        "name": "Credit Discovery - Installment Outcome Categories",
        "display": "bar",
        "description": "Classifies outcomes using due_date and gateway confirmed_at, including the five-day no-penalty window and unconfirmed payment links.",
        "sql": PAYMENT_CTE + r"""
select
  source,
  case when installment_number = 1 then 'Installment #1' else 'Installment #2+' end as installment_group,
  case
    when payment_id is not null and confirmed_at is null then 'Payment linked but unconfirmed'
    when confirmed_at is not null and payment_delay_days <= 0 then 'Paid before/on due date'
    when confirmed_at is not null and payment_delay_days between 1 and 5 then 'Paid 1-5 days after due date'
    when confirmed_at is not null and payment_delay_days > 5 then 'Paid more than 5 days late'
    when due_date > current_date then 'Future installment'
    when due_date = current_date then 'Currently due'
    when current_date - due_date between 1 and 5 then 'Unpaid 1-5 days overdue'
    else 'Unpaid more than 5 days overdue'
  end as outcome_category,
  count(*) as installments,
  count(distinct customer_id) as users,
  sum(amount) as amount
from payment_rows
group by source, installment_group, outcome_category
order by source, installment_group, installments desc;
""",
    },
    {
        "name": "Credit Discovery - User Repayment Metrics",
        "display": "table",
        "description": "User-level historical repayment metrics for existing-user scoring and backtesting.",
        "sql": PAYMENT_CTE + r"""
select
  ur.customer_id,
  ur.total_installments,
  ur.paid_installments,
  ur.future_installments,
  ur.currently_due_installments,
  ur.unpaid_within_grace_installments,
  ur.unpaid_over_5_days_installments,
  ur.on_time_installments,
  ur.paid_within_grace_installments,
  ur.paid_over_5_days_late_installments,
  ur.linked_payment_unconfirmed_installments,
  round(100.0 * ur.on_time_installments / nullif(ur.paid_installments + ur.unpaid_over_5_days_installments, 0), 2) as on_time_rate_pct,
  round(100.0 * ur.paid_within_grace_installments / nullif(ur.paid_installments, 0), 2) as within_grace_paid_rate_pct,
  round(100.0 * ur.paid_over_5_days_late_installments / nullif(ur.paid_installments, 0), 2) as severe_late_rate_pct,
  round(100.0 * ur.unpaid_over_5_days_installments / nullif(ur.total_installments, 0), 2) as severe_unpaid_rate_pct,
  round(ur.average_payment_delay_days::numeric, 2) as average_payment_delay_days,
  round(ud.median_payment_delay_days::numeric, 2) as median_payment_delay_days,
  ud.maximum_payment_delay_days,
  ur.scheduled_amount,
  ur.severe_unpaid_amount
from user_repayment ur
left join user_delay ud on ud.customer_id = ur.customer_id
where ur.paid_installments > 0
order by severe_unpaid_rate_pct desc nulls last, ur.customer_id
limit 3000;
""",
    },
    {
        "name": "Credit Discovery - Installment 1 vs Later",
        "display": "bar",
        "description": "Tests whether the first installment behaves differently from later installments before making it a model feature.",
        "sql": PAYMENT_CTE + r"""
select
  source,
  case when installment_number = 1 then 'Installment #1' else 'Installment #2+' end as installment_group,
  count(*) as installments,
  count(distinct customer_id) as users,
  count(*) filter (where confirmed_at is not null) as paid_installments,
  count(*) filter (where confirmed_at is not null and payment_delay_days <= 0) as on_time_installments,
  count(*) filter (where confirmed_at is not null and payment_delay_days between 1 and 5) as within_grace_installments,
  count(*) filter (where confirmed_at is not null and payment_delay_days > 5) as severe_late_installments,
  count(*) filter (where confirmed_at is null and due_date < current_date and current_date - due_date > 5) as severe_unpaid_installments,
  round(100.0 * count(*) filter (where confirmed_at is not null and payment_delay_days <= 0) / nullif(count(*) filter (where confirmed_at is not null), 0), 2) as on_time_rate_pct,
  round(100.0 * count(*) filter (where confirmed_at is not null and payment_delay_days > 5) / nullif(count(*) filter (where confirmed_at is not null), 0), 2) as severe_late_rate_pct
from payment_rows
group by source, installment_group
order by source, installment_group;
""",
    },
    {
        "name": "Credit Discovery - Maintenance vs Repayment",
        "display": "bar",
        "description": "Tests maintenance count and auto-service association against historical repayment outcomes. It does not assume more service history is safer.",
        "sql": PAYMENT_CTE + r"""
, maintenance_by_user as (
  select
    customer_id,
    count(*) filter (where deleted_at is null) as service_count,
    count(*) filter (where deleted_at is null and auto_service_id is not null) as vendor_service_count
  from maintanence_services
  group by customer_id
)
select
  case
    when coalesce(m.service_count, 0) = 0 then '0 services'
    when m.service_count = 1 then '1 service'
    when m.service_count between 2 and 5 then '2-5 services'
    else '6+ services'
  end as maintenance_bucket,
  case when coalesce(m.vendor_service_count, 0) > 0 then 'Has auto_service_id' else 'No auto_service_id' end as vendor_linkage,
  count(*) as users,
  sum(ur.paid_installments) as paid_installments,
  sum(ur.on_time_installments) as on_time_installments,
  sum(ur.paid_over_5_days_late_installments) as severe_late_installments,
  sum(ur.unpaid_over_5_days_installments) as severe_unpaid_installments,
  round(100.0 * sum(ur.on_time_installments) / nullif(sum(ur.paid_installments), 0), 2) as on_time_rate_pct,
  round(100.0 * sum(ur.paid_over_5_days_late_installments) / nullif(sum(ur.paid_installments), 0), 2) as severe_late_rate_pct
from user_repayment ur
left join maintenance_by_user m on m.customer_id = ur.customer_id
where ur.total_installments > 0
group by maintenance_bucket, vendor_linkage
order by maintenance_bucket, vendor_linkage;
""",
    },
    {
        "name": "Credit Discovery - Account Activity vs Repayment",
        "display": "bar",
        "description": "Tests account age and last-login recency against repayment outcomes; current activity must be timestamped before use in historical backtests.",
        "sql": PAYMENT_CTE + r"""
select
  case
    when current_date - u.created_at::date < 30 then 'Account age <30 days'
    when current_date - u.created_at::date < 90 then 'Account age 30-89 days'
    when current_date - u.created_at::date < 365 then 'Account age 90-364 days'
    else 'Account age 365+ days'
  end as account_age_bucket,
  case
    when u.last_login is null then 'No recorded login'
    when current_timestamp - u.last_login <= interval '30 days' then 'Login within 30 days'
    when current_timestamp - u.last_login <= interval '90 days' then 'Login 31-90 days ago'
    else 'Login more than 90 days ago'
  end as login_recency_bucket,
  count(*) as users,
  sum(ur.paid_installments) as paid_installments,
  sum(ur.on_time_installments) as on_time_installments,
  sum(ur.paid_over_5_days_late_installments) as severe_late_installments,
  sum(ur.unpaid_over_5_days_installments) as severe_unpaid_installments,
  round(100.0 * sum(ur.on_time_installments) / nullif(sum(ur.paid_installments), 0), 2) as on_time_rate_pct,
  round(100.0 * sum(ur.paid_over_5_days_late_installments) / nullif(sum(ur.paid_installments), 0), 2) as severe_late_rate_pct
from users u
join user_repayment ur on ur.customer_id = u.user_id
where u.type = 1 and u.deleted_at is null and u.is_active and ur.paid_installments > 0
group by account_age_bucket, login_recency_bucket
order by account_age_bucket, login_recency_bucket;
""",
    },
    {
        "name": "Credit Discovery - Facilities vs Repayment",
        "display": "bar",
        "description": "Tests customer-config facility JSON signals against repayment outcomes, with sample sizes and explicit debt/dishonored buckets.",
        "sql": PAYMENT_CTE + r"""
, config_by_user as (
  select
    c.customer_id,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilityDebtTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as facility_debt_amount,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilityPastExpiredTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as past_expired_amount,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'dishonored', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as dishonored_count,
    c.score as existing_config_score,
    c.qualifying_credit_amount
  from bnpl_customer_config c
)
select
  case
    when cb.dishonored_count > 0 then 'Dishonored facility flag'
    when cb.past_expired_amount > 0 then 'Past-expired facility amount > 0'
    when cb.facility_debt_amount = 0 then 'No facility debt'
    when cb.facility_debt_amount < 1000000 then 'Facility debt <1M'
    when cb.facility_debt_amount < 10000000 then 'Facility debt 1M-10M'
    else 'Facility debt 10M+'
  end as facility_risk_bucket,
  count(*) as users,
  sum(ur.paid_installments) as paid_installments,
  sum(ur.on_time_installments) as on_time_installments,
  sum(ur.paid_over_5_days_late_installments) as severe_late_installments,
  sum(ur.unpaid_over_5_days_installments) as severe_unpaid_installments,
  round(100.0 * sum(ur.on_time_installments) / nullif(sum(ur.paid_installments), 0), 2) as on_time_rate_pct,
  round(100.0 * sum(ur.paid_over_5_days_late_installments) / nullif(sum(ur.paid_installments), 0), 2) as severe_late_rate_pct,
  round(avg(cb.existing_config_score), 2) as avg_existing_config_score,
  round(avg(cb.qualifying_credit_amount), 0) as avg_qualifying_credit_amount
from config_by_user cb
join user_repayment ur on ur.customer_id = cb.customer_id
where ur.paid_installments > 0
group by facility_risk_bucket
order by users desc;
""",
    },
    {
        "name": "Credit Discovery - Province and City Repayment",
        "display": "table",
        "description": "Historical repayment comparison by latest address, retaining sample size and a small-sample warning instead of turning geography into an automatic score.",
        "sql": PAYMENT_CTE + r"""
, latest_address as (
  select distinct on (ua.user_id)
    ua.user_id,
    ua.city,
    ua.province,
    ua.created_at as address_created_at
  from user_addresses ua
  order by ua.user_id, ua.created_at desc, ua.id desc
)
select
  la.province,
  la.city,
  count(*) as users,
  case when count(*) < 50 then 'Small sample: do not generalize' else 'Sample >=50' end as sample_quality,
  sum(ur.paid_installments) as paid_installments,
  sum(ur.on_time_installments) as on_time_installments,
  sum(ur.paid_over_5_days_late_installments) as severe_late_installments,
  sum(ur.unpaid_over_5_days_installments) as severe_unpaid_installments,
  round(100.0 * sum(ur.on_time_installments) / nullif(sum(ur.paid_installments), 0), 2) as on_time_rate_pct,
  round(100.0 * sum(ur.paid_over_5_days_late_installments) / nullif(sum(ur.paid_installments), 0), 2) as severe_late_rate_pct
from latest_address la
join user_repayment ur on ur.customer_id = la.user_id
where ur.paid_installments > 0
group by la.province, la.city
order by users desc, la.province, la.city
limit 300;
""",
    },
    {
        "name": "Credit Discovery - New User Initial Signal Bands",
        "display": "bar",
        "description": "Exploratory pre-repayment evidence bands for users with no installment history. This is a research comparison, not a production approval score.",
        "sql": r"""
with maintenance_by_user as (
  select
    customer_id,
    count(*) filter (where deleted_at is null) as service_count,
    count(*) filter (where deleted_at is null and auto_service_id is not null) as vendor_service_count
  from maintanence_services
  group by customer_id
),
address_by_user as (
  select user_id, count(*) as address_count
  from user_addresses
  group by user_id
),
config_by_user as (
  select
    c.customer_id,
    c.eligible_for_loan,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'dishonored', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as dishonored_count,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilityPastExpiredTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as past_expired_amount,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilitySuspiciousTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as suspicious_amount
  from bnpl_customer_config c
),
initial_features as (
  select
    u.user_id,
    (current_date - u.created_at::date)::int as account_age_days,
    (current_date - u.last_login::date)::int as days_since_login,
    case when u.national_code_with_phone_number_verification_ok is true then 1 else 0 end as verified_phone_national_code,
    case when ui.user_id is not null then 1 else 0 end as has_identity_row,
    case when cb.customer_id is not null then 1 else 0 end as has_customer_config,
    case when cb.eligible_for_loan then 1 else 0 end as eligible_for_loan,
    case when cb.dishonored_count > 0 or cb.past_expired_amount > 0 or cb.suspicious_amount > 0 then 1 else 0 end as facility_warning,
    coalesce(m.vendor_service_count, 0) as vendor_service_count,
    coalesce(a.address_count, 0) as address_count
  from users u
  left join user_identifications ui on ui.user_id = u.user_id
  left join config_by_user cb on cb.customer_id = u.user_id
  left join maintenance_by_user m on m.customer_id = u.user_id
  left join address_by_user a on a.user_id = u.user_id
  where u.type = 1 and u.deleted_at is null and u.is_active
    and not exists (select 1 from bnpl_credit_installments i where i.customer_id = u.user_id)
),
banded as (
  select
    f.*,
    greatest(0, least(100,
      case when f.account_age_days >= 365 then 20 when f.account_age_days >= 90 then 12 when f.account_age_days >= 30 then 6 else 2 end
      + case when f.days_since_login is not null and f.days_since_login <= 30 then 20 when f.days_since_login <= 90 then 12 else 0 end
      + case when f.verified_phone_national_code = 1 then 20 else 0 end
      + case when f.has_identity_row = 1 then 10 else 0 end
      + case when f.has_customer_config = 1 then 10 else 0 end
      + case when f.eligible_for_loan = 1 then 5 else 0 end
      + least(10, f.vendor_service_count * 2)
      + case when f.address_count > 0 then 5 else 0 end
      - case when f.facility_warning = 1 then 20 else 0 end
    ))::int as initial_signal_score
  from initial_features f
)
select
  case
    when initial_signal_score >= 80 then 'Initial A - strong evidence'
    when initial_signal_score >= 60 then 'Initial B - good evidence'
    when initial_signal_score >= 40 then 'Initial C - moderate evidence'
    when initial_signal_score >= 20 then 'Initial D - limited evidence'
    else 'Initial E - insufficient/high-risk evidence'
  end as initial_signal_band,
  count(*) as users,
  round(avg(initial_signal_score), 1) as avg_initial_signal_score,
  count(*) filter (where verified_phone_national_code = 1) as verified_users,
  count(*) filter (where has_identity_row = 1) as identity_rows,
  count(*) filter (where vendor_service_count > 0) as users_with_vendor_service,
  count(*) filter (where facility_warning = 1) as users_with_facility_warning,
  count(*) filter (where address_count > 0) as users_with_address
from banded
group by initial_signal_band
order by min(initial_signal_score) desc;
""",
    },
    {
        "name": "Credit Discovery - Repayment History for Model Transition",
        "display": "bar",
        "description": "Shows how repayment outcomes change as users accumulate confirmed installments; use this to choose a data-supported transition point from initial to historical scoring.",
        "sql": PAYMENT_CTE + r"""
select
  case
    when paid_installments = 1 then '1 confirmed payment'
    when paid_installments between 2 and 3 then '2-3 confirmed payments'
    when paid_installments between 4 and 5 then '4-5 confirmed payments'
    else '6+ confirmed payments'
  end as repayment_history_bucket,
  count(*) as users,
  sum(total_installments) as total_installments,
  sum(paid_installments) as paid_installments,
  sum(on_time_installments) as on_time_installments,
  sum(paid_within_grace_installments) as within_grace_installments,
  sum(paid_over_5_days_late_installments) as severe_late_installments,
  sum(unpaid_over_5_days_installments) as severe_unpaid_installments,
  round(100.0 * sum(on_time_installments) / nullif(sum(paid_installments), 0), 2) as on_time_rate_pct,
  round(100.0 * sum(paid_over_5_days_late_installments) / nullif(sum(paid_installments), 0), 2) as severe_late_rate_pct,
  round(100.0 * sum(unpaid_over_5_days_installments) / nullif(sum(total_installments), 0), 2) as severe_unpaid_rate_pct
from user_repayment
where paid_installments > 0
group by repayment_history_bucket
order by min(paid_installments);
""",
    },
]


def require_id(response, label):
    value = response.get("id") or response.get(f"{label}_id")
    if not value:
        raise SystemExit(f"Could not find {label} id in response: {response}")
    return value


def dashboard_cards(card_ids):
    cards = []
    for index, card_id in enumerate(card_ids):
        cards.append({
            "id": -(index + 1),
            "card_id": int(card_id),
            "row": (index // 2) * 9,
            "col": 0 if index % 2 == 0 else 12,
            "size_x": 12,
            "size_y": 8 if index < 8 else 9,
            "parameter_mappings": [],
            "series": [],
        })
    return cards


def main():
    env = load_env()
    if env.get("METABASE_DATABASE_ID") != str(DATABASE_ID):
        raise SystemExit("Set METABASE_DATABASE_ID=2 in .env before running this script.")
    client = MetabaseClient()
    print("Checking Metabase Agent API...")
    print_json(client.ping())

    created = []
    for question in QUESTIONS:
        print(f"Creating question: {question['name']}")
        saved = client.create_native_card(
            database_id=DATABASE_ID,
            name=question["name"],
            sql=question["sql"].strip(),
            display=question["display"],
            description=question["description"],
        )
        created.append({"id": require_id(saved, "card"), "name": question["name"]})

    print(f"Creating dashboard: {DASHBOARD_NAME}")
    dashboard = client.create_standard_dashboard(
        name=DASHBOARD_NAME,
        description=(
            "Exploratory discovery and validation for separate existing-user repayment scoring "
            "and new-user initial-risk signals. Includes the five-day grace window, installment #1, "
            "facility JSON, maintenance linkage, account activity, geography, and transition readiness. "
            "This dashboard does not implement a production credit decision system."
        ),
    )
    dashboard_id = require_id(dashboard, "dashboard")
    updated = client.update_standard_dashboard_cards(
        dashboard_id,
        dashboard_cards([item["id"] for item in created]),
    )
    dashboard_url = f"{client.base_url}/dashboard/{dashboard_id}"
    print_json({
        "dashboard_id": dashboard_id,
        "dashboard_url": dashboard_url,
        "questions": created,
        "dashcards": len(updated.get("dashcards", [])),
    })
    print(f"\nOpen dashboard: {dashboard_url}")


if __name__ == "__main__":
    main()
