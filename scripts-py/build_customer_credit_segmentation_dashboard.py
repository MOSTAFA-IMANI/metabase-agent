#!/usr/bin/env python3
"""Build an explainable customer-credit segmentation dashboard in Metabase.

The score is a pilot/research score for the survey and gameplay credit program.
It is deliberately based on observable operational signals and keeps the
existing customer-config score visible as a comparison, rather than silently
using it as the new score.
"""

from metabase_agent import MetabaseClient, load_env, print_json


DASHBOARD_NAME = "Customer Credit Segmentation and Risk"
DATABASE_ID = 2

TEMPLATE_TAGS = {
    "customer_id": {
        "id": "customer_id",
        "name": "customer_id",
        "display-name": "Customer ID",
        "type": "number",
        "required": False,
    },
    "segment": {
        "id": "segment",
        "name": "segment",
        "display-name": "Segment",
        "type": "text",
        "required": False,
    },
    "service_start_date": {
        "id": "service_start_date",
        "name": "service_start_date",
        "display-name": "Maintenance start date",
        "type": "date",
        "required": False,
    },
    "service_end_date": {
        "id": "service_end_date",
        "name": "service_end_date",
        "display-name": "Maintenance end date",
        "type": "date",
        "required": False,
    },
    "installment_start_date": {
        "id": "installment_start_date",
        "name": "installment_start_date",
        "display-name": "Installment start date",
        "type": "date",
        "required": False,
    },
    "installment_end_date": {
        "id": "installment_end_date",
        "name": "installment_end_date",
        "display-name": "Installment end date",
        "type": "date",
        "required": False,
    },
}


COMMON_CTE = r"""
with maintenance as (
  select
    m.customer_id,
    count(*) filter (where m.deleted_at is null) as service_count,
    count(*) filter (where m.deleted_at is null and m.auto_service_id is not null) as vendor_service_count,
    count(*) filter (where m.deleted_at is null and m.supplier_id is not null) as supplier_service_count,
    count(distinct m.car_id) filter (where m.deleted_at is null) as car_count,
    max(m.created_at) filter (where m.deleted_at is null) as last_service_at
  from maintanence_services m
  where 1 = 1
    [[and m.created_at >= {{service_start_date}}]]
    [[and m.created_at < {{service_end_date}}]]
  group by m.customer_id
),
installment_metrics as (
  select
    i.customer_id,
    count(*) as installment_count,
    count(*) filter (where gp.confirmed_at is not null) as paid_count,
    count(*) filter (where gp.confirmed_at is not null and gp.confirmed_at::date <= i.due_date) as on_time_count,
    count(*) filter (where gp.confirmed_at is not null and gp.confirmed_at::date > i.due_date) as late_count,
    count(*) filter (where gp.confirmed_at is null and i.due_date < current_date) as overdue_unpaid_count,
    sum(i.amount) as scheduled_amount,
    sum(i.amount) filter (where gp.confirmed_at is null and i.due_date < current_date) as overdue_unpaid_amount,
    sum(i.amount) filter (where gp.confirmed_at is null) as outstanding_installment_amount,
    round(avg((gp.confirmed_at::date - i.due_date)::numeric) filter (where gp.confirmed_at is not null), 2) as avg_days_vs_due,
    max(i.due_date) as latest_due_date
  from bnpl_credit_installments i
  left join bnpl_gateway_payments gp on gp.id = i.payment_id
  where lower(i.source) in ('credit_in_4', 'loan', 'dp_loan')
    [[and i.created_at >= {{installment_start_date}}]]
    [[and i.created_at < {{installment_end_date}}]]
  group by i.customer_id
),
config_metrics as (
  select
    c.customer_id,
    c.score as existing_config_score,
    c.qualifying_credit_amount,
    c.eligible_for_loan,
    c.updated_at as config_updated_at,
    case when c.facilities is not null then 1 else 0 end as has_facilities_snapshot,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilityDebtTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as facility_debt_total_amount,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilityPastExpiredTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as facility_past_expired_total_amount,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilitySuspiciousTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as facility_suspicious_total_amount,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'dishonored', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as dishonored_count,
    coalesce(nullif(regexp_replace(coalesce(c.facilities->>'facilityTotalAmount', '0'), '[^0-9.-]', '', 'g'), '')::numeric, 0) as facility_total_amount,
    case when jsonb_typeof(c.facilities->'facilityList') = 'array' then jsonb_array_length(c.facilities->'facilityList') else 0 end as facility_list_count
  from bnpl_customer_config c
),
user_features as (
  select
    u.user_id,
    u.created_at as user_created_at,
    u.updated_at as user_updated_at,
    u.last_login,
    (current_date - u.created_at::date)::int as account_age_days,
    (current_date - u.last_login::date)::int as days_since_login,
    coalesce(cm.service_count, 0) as service_count,
    coalesce(cm.vendor_service_count, 0) as vendor_service_count,
    coalesce(cm.supplier_service_count, 0) as supplier_service_count,
    coalesce(cm.car_count, 0) as car_count,
    cm.last_service_at,
    coalesce(im.installment_count, 0) as installment_count,
    coalesce(im.paid_count, 0) as paid_count,
    coalesce(im.on_time_count, 0) as on_time_count,
    coalesce(im.late_count, 0) as late_count,
    coalesce(im.overdue_unpaid_count, 0) as overdue_unpaid_count,
    coalesce(im.scheduled_amount, 0) as scheduled_amount,
    coalesce(im.overdue_unpaid_amount, 0) as overdue_unpaid_amount,
    coalesce(im.outstanding_installment_amount, 0) as outstanding_installment_amount,
    coalesce(im.avg_days_vs_due, 0) as avg_days_vs_due,
    im.latest_due_date,
    coalesce(cm2.existing_config_score, 0) as existing_config_score,
    coalesce(cm2.qualifying_credit_amount, 0) as qualifying_credit_amount,
    coalesce(cm2.eligible_for_loan, false) as eligible_for_loan,
    cm2.config_updated_at,
    coalesce(cm2.has_facilities_snapshot, 0) as has_facilities_snapshot,
    coalesce(cm2.facility_debt_total_amount, 0) as facility_debt_total_amount,
    coalesce(cm2.facility_past_expired_total_amount, 0) as facility_past_expired_total_amount,
    coalesce(cm2.facility_suspicious_total_amount, 0) as facility_suspicious_total_amount,
    coalesce(cm2.dishonored_count, 0) as dishonored_count,
    coalesce(cm2.facility_total_amount, 0) as facility_total_amount,
    coalesce(cm2.facility_list_count, 0) as facility_list_count,
    coalesce(cr.raw_balance, 0) as current_raw_balance,
    coalesce(cr.loan_raw_balance, 0) as current_loan_raw_balance,
    cr.expires_at as credit_expires_at
  from users u
  left join maintenance cm on cm.customer_id = u.user_id
  left join installment_metrics im on im.customer_id = u.user_id
  left join config_metrics cm2 on cm2.customer_id = u.user_id
  left join bnpl_credits cr on cr.customer_id = u.user_id
  where u.type = 1
    and u.deleted_at is null
    and u.is_active
    [[and u.user_id = {{customer_id}}]]
),
scored_base as (
  select
    uf.*,
    case
      when uf.paid_count + uf.overdue_unpaid_count = 0 then 12
      else greatest(0, least(40, round(
        40.0 * uf.on_time_count / nullif((uf.paid_count + uf.overdue_unpaid_count)::numeric, 0)
        - 8.0 * least(uf.overdue_unpaid_count, 5)
        - 1.5 * greatest(uf.avg_days_vs_due, 0)
      )))::int
    end as payment_points,
    least(20, 2 * least(uf.service_count, 5)
      + case when uf.vendor_service_count > 0 then 6 else 0 end
      + case when uf.supplier_service_count > 0 then 4 else 0 end)::int as maintenance_points,
    case
      when uf.last_login >= current_timestamp - interval '30 days' then 15
      when uf.last_login >= current_timestamp - interval '90 days' then 10
      when uf.last_login >= current_timestamp - interval '180 days' then 5
      else 0
    end as engagement_points,
    case
      when uf.account_age_days >= 365 then 10
      when uf.account_age_days >= 90 then 7
      when uf.account_age_days >= 30 then 4
      else 1
    end as tenure_points,
    (case when uf.has_facilities_snapshot = 1 then 5 else 0 end
      + case when uf.eligible_for_loan then 5 else 0 end
      + case when uf.has_facilities_snapshot = 1 and uf.dishonored_count = 0 and uf.facility_debt_total_amount = 0 then 5 else 0 end) as profile_points,
    least(20,
      case when uf.dishonored_count > 0 then 8 else 0 end
      + case when uf.facility_past_expired_total_amount > 0 then 5 else 0 end
      + case when uf.facility_suspicious_total_amount > 0 then 5 else 0 end
      + case when uf.overdue_unpaid_count > 0 then 5 else 0 end
    )::int as risk_penalty
  from user_features uf
),
scored as (
  select
    sb.*,
    greatest(0, least(100, sb.payment_points + sb.maintenance_points + sb.engagement_points + sb.tenure_points + sb.profile_points - sb.risk_penalty))::int as credit_score
  from scored_base sb
),
segmented as (
  select
    s.*,
    case
      when s.credit_score >= 80 then 'A - Prime verified'
      when s.credit_score >= 65 then 'B - Established standard'
      when s.credit_score >= 50 then 'C - Developing'
      when s.credit_score >= 30 then 'D - Watch / thin file'
      else 'E - Limited history / high risk'
    end as segment,
    case
      when s.credit_score >= 80 then 10000000
      when s.credit_score >= 65 then 7500000
      when s.credit_score >= 50 then 5000000
      when s.credit_score >= 30 then 2500000
      else 1000000
    end as recommended_credit_toman
  from scored s
)
"""


QUESTIONS = [
    {
        "name": "Credit Segmentation - Segment Summary",
        "display": "bar",
        "description": "Five explainable pilot segments with recommended Toman credit, score components, payment outcomes, and maintenance evidence.",
        "sql": COMMON_CTE + r"""
select
  segment,
  count(*) as users,
  round(avg(credit_score), 1) as avg_credit_score,
  min(credit_score) as min_credit_score,
  max(credit_score) as max_credit_score,
  min(recommended_credit_toman) as recommended_credit_toman,
  round(100.0 * count(*) filter (where overdue_unpaid_count > 0) / nullif(count(*), 0), 2) as users_with_overdue_pct,
  round(avg(nullif(on_time_count + overdue_unpaid_count, 0)::numeric), 2) as avg_due_history_count,
  round(avg(service_count), 2) as avg_maintenance_services,
  round(avg(existing_config_score), 2) as avg_existing_config_score
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment
order by min(recommended_credit_toman) desc;
""",
    },
    {
        "name": "Credit Segmentation - Score Distribution",
        "display": "bar",
        "description": "Distribution of customers across the 0-100 pilot credit score and five recommended-credit bands.",
        "sql": COMMON_CTE + r"""
select
  segment,
  credit_score,
  recommended_credit_toman,
  count(*) as users
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment, credit_score, recommended_credit_toman
order by credit_score desc;
""",
    },
    {
        "name": "Credit Segmentation - Payment Reliability",
        "display": "bar",
        "description": "Historical installment reliability by segment. Payment timing is measured from gateway confirmed_at versus installment due_date.",
        "sql": COMMON_CTE + r"""
select
  segment,
  count(*) as users,
  sum(paid_count) as paid_installments,
  sum(on_time_count) as on_time_installments,
  sum(late_count) as late_installments,
  sum(overdue_unpaid_count) as overdue_unpaid_installments,
  round(100.0 * sum(on_time_count) / nullif(sum(paid_count) + sum(overdue_unpaid_count), 0), 2) as on_time_rate_pct,
  round(100.0 * sum(late_count) / nullif(sum(paid_count), 0), 2) as late_rate_pct,
  sum(overdue_unpaid_amount) as overdue_unpaid_amount,
  round(avg(nullif(avg_days_vs_due, 0)), 2) as avg_days_vs_due
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment
order by min(recommended_credit_toman) desc;
""",
    },
    {
        "name": "Credit Segmentation - Maintenance Reliability",
        "display": "bar",
        "description": "Maintenance-history depth and vendor/supplier linkage by segment. This is a supporting reliability signal, not a standalone approval rule.",
        "sql": COMMON_CTE + r"""
select
  segment,
  count(*) as users,
  count(*) filter (where service_count > 0) as users_with_maintenance,
  count(*) filter (where vendor_service_count > 0) as users_with_vendor_service,
  count(*) filter (where supplier_service_count > 0) as users_with_supplier_service,
  round(100.0 * count(*) filter (where vendor_service_count > 0) / nullif(count(*), 0), 2) as vendor_linked_user_pct,
  round(avg(service_count), 2) as avg_service_count,
  round(avg(vendor_service_count), 2) as avg_vendor_service_count,
  round(avg(car_count), 2) as avg_cars
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment
order by min(recommended_credit_toman) desc;
""",
    },
    {
        "name": "Credit Segmentation - Facilities Risk Signals",
        "display": "table",
        "description": "Customer-config facilities JSON signals, including dishonored, debt, past-expired, suspicious, and facility-list values.",
        "sql": COMMON_CTE + r"""
select
  segment,
  count(*) as users,
  count(*) filter (where has_facilities_snapshot = 1) as users_with_facilities_snapshot,
  count(*) filter (where dishonored_count > 0) as users_with_dishonored,
  count(*) filter (where facility_debt_total_amount > 0) as users_with_facility_debt,
  count(*) filter (where facility_past_expired_total_amount > 0) as users_with_past_expired,
  count(*) filter (where facility_suspicious_total_amount > 0) as users_with_suspicious,
  sum(facility_debt_total_amount) as facility_debt_total_amount,
  sum(facility_past_expired_total_amount) as facility_past_expired_total_amount,
  sum(facility_suspicious_total_amount) as facility_suspicious_total_amount,
  sum(dishonored_count) as dishonored_count
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment
order by min(recommended_credit_toman) desc;
""",
    },
    {
        "name": "Credit Segmentation - Current Exposure",
        "display": "bar",
        "description": "Current credit balance and unpaid installment exposure by segment, useful before assigning a new experimental amount.",
        "sql": COMMON_CTE + r"""
select
  segment,
  count(*) as users,
  sum(current_raw_balance) as current_raw_balance,
  sum(current_loan_raw_balance) as current_loan_raw_balance,
  sum(outstanding_installment_amount) as outstanding_installment_amount,
  sum(overdue_unpaid_amount) as overdue_unpaid_amount,
  round(avg(qualifying_credit_amount), 0) as avg_qualifying_credit_amount,
  round(avg(recommended_credit_toman), 0) as avg_recommended_credit_toman
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment
order by min(recommended_credit_toman) desc;
""",
    },
    {
        "name": "Credit Segmentation - User Worklist",
        "display": "table",
        "description": "Operational customer-level worklist with score components, recommended amount, payment risk, activity, and evidence coverage. No personal contact fields are exposed.",
        "sql": COMMON_CTE + r"""
select
  user_id as customer_id,
  segment,
  credit_score,
  recommended_credit_toman,
  payment_points,
  maintenance_points,
  engagement_points,
  tenure_points,
  profile_points,
  risk_penalty,
  installment_count,
  paid_count,
  on_time_count,
  late_count,
  overdue_unpaid_count,
  overdue_unpaid_amount,
  round(100.0 * on_time_count / nullif(paid_count + overdue_unpaid_count, 0), 2) as on_time_rate_pct,
  service_count,
  vendor_service_count,
  existing_config_score,
  qualifying_credit_amount,
  eligible_for_loan,
  current_raw_balance,
  current_loan_raw_balance,
  last_login,
  days_since_login,
  account_age_days
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
order by credit_score desc, overdue_unpaid_amount asc, user_id
limit 1000;
""",
    },
    {
        "name": "Credit Segmentation - Segment Validation",
        "display": "table",
        "description": "Validation view for monitoring whether higher pilot segments actually show better repayment timing and lower overdue exposure over time.",
        "sql": COMMON_CTE + r"""
select
  segment,
  recommended_credit_toman,
  count(*) as users,
  count(*) filter (where installment_count > 0) as users_with_installment_history,
  round(100.0 * count(*) filter (where overdue_unpaid_count = 0 and installment_count > 0) / nullif(count(*) filter (where installment_count > 0), 0), 2) as clean_repayment_user_pct,
  round(100.0 * count(*) filter (where overdue_unpaid_count > 0) / nullif(count(*), 0), 2) as overdue_user_pct,
  round(avg(nullif(avg_days_vs_due, 0)), 2) as avg_payment_days_vs_due,
  sum(scheduled_amount) as scheduled_amount,
  sum(overdue_unpaid_amount) as overdue_unpaid_amount,
  round(100.0 * sum(overdue_unpaid_amount) / nullif(sum(scheduled_amount), 0), 2) as overdue_amount_rate_pct
from segmented
where 1 = 1
  [[and segment = {{segment}}]]
group by segment, recommended_credit_toman
order by recommended_credit_toman desc;
""",
    },
]


PARAMETERS = [
    {
        "id": "segment",
        "name": "Segment",
        "slug": "segment",
        "type": "string/=",
        "sectionId": "string",
        "default": None,
        "mappings": [],
    },
    {
        "id": "customer_id",
        "name": "Customer ID",
        "slug": "customer_id",
        "type": "number/=",
        "sectionId": "number",
        "default": None,
        "mappings": [],
    },
    {
        "id": "service_date_range",
        "name": "Maintenance date range",
        "slug": "service_date_range",
        "type": "date/range",
        "sectionId": "date",
        "default": None,
        "mappings": [],
    },
    {
        "id": "installment_date_range",
        "name": "Installment date range",
        "slug": "installment_date_range",
        "type": "date/range",
        "sectionId": "date",
        "default": None,
        "mappings": [],
    },
]


def require_id(response, label):
    value = response.get("id") or response.get(f"{label}_id")
    if not value:
        raise SystemExit(f"Could not find {label} id in response: {response}")
    return value


def dashboard_cards(card_ids):
    cards = []
    positions = [
        (0, 0, 24, 8),
        (0, 8, 12, 8),
        (12, 8, 12, 8),
        (0, 16, 12, 8),
        (12, 16, 12, 8),
        (0, 24, 24, 8),
        (0, 32, 24, 12),
        (0, 44, 24, 8),
    ]
    for index, card_id in enumerate(card_ids):
        row, col, size_x, size_y = positions[index]
        cards.append({
            "id": -(index + 1),
            "card_id": int(card_id),
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
            "parameter_mappings": [],
            "series": [],
        })
    return cards


def template_mapping(parameter_id, tag_name):
    return {
        "parameter_id": parameter_id,
        "target": ["variable", ["template-tag", tag_name]],
    }


def add_mappings(cards, created_questions):
    for dashcard, question in zip(cards, created_questions):
        tags = question["tags"]
        mappings = []
        if "segment" in tags:
            mappings.append(template_mapping("segment", "segment"))
        if "customer_id" in tags:
            mappings.append(template_mapping("customer_id", "customer_id"))
        if "service_start_date" in tags:
            mappings.append(template_mapping("service_date_range", "service_start_date"))
        if "service_end_date" in tags:
            mappings.append(template_mapping("service_date_range", "service_end_date"))
        if "installment_start_date" in tags:
            mappings.append(template_mapping("installment_date_range", "installment_start_date"))
        if "installment_end_date" in tags:
            mappings.append(template_mapping("installment_date_range", "installment_end_date"))
        dashcard["parameter_mappings"] = mappings
    for parameter in PARAMETERS:
        parameter["mappings"] = []
    return cards


def main():
    env = load_env()
    if env.get("METABASE_DATABASE_ID") != str(DATABASE_ID):
        raise SystemExit("Set METABASE_DATABASE_ID=2 in .env before running this script.")
    if not env.get("METABASE_API_KEY"):
        raise SystemExit("Put the real METABASE_API_KEY in .env first.")

    client = MetabaseClient()
    print("Checking Metabase Agent API...")
    print_json(client.ping())

    created_questions = []
    for question in QUESTIONS:
        print(f"Creating question: {question['name']}")
        saved = client.create_native_card(
            database_id=DATABASE_ID,
            name=question["name"],
            sql=question["sql"].strip(),
            display=question["display"],
            description=question["description"],
            template_tags=TEMPLATE_TAGS,
        )
        created_questions.append({
            "id": require_id(saved, "card"),
            "name": question["name"],
            "tags": set(question["sql"] and TEMPLATE_TAGS).intersection(
                {tag for tag in TEMPLATE_TAGS if "{{" + tag + "}}" in question["sql"]}
            ),
        })

    print(f"Creating dashboard: {DASHBOARD_NAME}")
    dashboard = client.create_standard_dashboard(
        name=DASHBOARD_NAME,
        description=(
            "Explainable five-tier customer credit pilot segmentation for survey and gameplay planning. "
            "The score weights payment timing and overdue exposure most heavily, with maintenance history, "
            "account activity, tenure, and customer-config facility signals as supporting evidence. "
            "Recommended amounts range from 1,000,000 to 10,000,000 Toman. This dashboard is for monitoring "
            "and experiment design and must be validated before any real credit decision."
        ),
    )
    dashboard_id = require_id(dashboard, "dashboard")
    cards = dashboard_cards([question["id"] for question in created_questions])
    add_mappings(cards, created_questions)
    print("Adding questions and filters to dashboard...")
    updated = client.call("PUT", f"/api/dashboard/{int(dashboard_id)}", {
        "parameters": PARAMETERS,
        "dashcards": cards,
    })

    dashboard_url = f"{client.base_url}/dashboard/{dashboard_id}"
    print_json({
        "dashboard_id": dashboard_id,
        "dashboard_url": dashboard_url,
        "questions": [{"id": q["id"], "name": q["name"]} for q in created_questions],
        "filters": [p["name"] for p in PARAMETERS],
        "updated_dashboard": {
            "parameters": len(updated.get("parameters", [])),
            "dashcards": len(updated.get("dashcards", [])),
        },
    })
    print(f"\nOpen dashboard: {dashboard_url}")


if __name__ == "__main__":
    main()
