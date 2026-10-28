#!/usr/bin/env python3
"""Create a customer lookup dashboard in Metabase."""

from metabase_agent import MetabaseClient, load_env


DATABASE_ID = int(load_env().get("METABASE_DATABASE_ID", "2"))
DASHBOARD_NAME = "Search Dashboard"

TEMPLATE_TAGS = {
    "user_id": {
        "id": "user_id",
        "name": "user_id",
        "display-name": "User ID",
        "type": "number",
        "required": False,
    },
    "phone_number": {
        "id": "phone_number",
        "name": "phone_number",
        "display-name": "Phone number",
        "type": "text",
        "required": False,
    },
    "national_code": {
        "id": "national_code",
        "name": "national_code",
        "display-name": "National code",
        "type": "text",
        "required": False,
    },
}

USER_FILTERS = r"""
where 1 = 0
  [[or u.user_id = {{user_id}}]]
  [[or u.phone_number = {{phone_number}}]]
  [[or u.national_code = {{national_code}}]]
"""

QUESTIONS = [
    {
        "name": "Search - User Profile",
        "display": "table",
        "description": "User account details. Search by one or more exact identifiers using the dashboard filters.",
        "sql": r"""
select
  u.user_id,
  u.full_name,
  u.phone_number,
  u.national_code,
  u.type as user_type,
  u.is_active,
  u.created_at,
  u.updated_at,
  u.last_login,
  u.national_code_with_phone_number_verification_ok as identity_phone_verified,
  u.wallet
from users u
""" + USER_FILTERS + "order by u.user_id;",
    },
    {
        "name": "Search - Customer Credit Config",
        "display": "table",
        "description": "Customer BNPL configuration and selected facility indicators. Sensitive OCR and cheque payloads are omitted.",
        "sql": r"""
select
  u.user_id,
  c.id as config_id,
  c.created_at as config_created_at,
  c.updated_at as config_updated_at,
  c.score as config_score,
  c.qualifying_credit_amount,
  c.eligible_for_loan,
  c.renew_credit,
  c.has_used_settlement_time_extension,
  c.has_seen_terms_and_conditions,
  c.national_card_image is not null as has_national_card_image,
  c.facilities->>'name' as facility_report_name,
  c.facilities->>'status' as facility_report_status,
  c.facilities->>'dishonored' as dishonored_count,
  c.facilities->>'facilityDebtTotalAmount' as facility_debt_total_amount,
  c.facilities->>'facilityDeferredTotalAmount' as facility_deferred_total_amount,
  c.facilities->>'facilityPastExpiredTotalAmount' as facility_past_expired_amount,
  c.facilities->>'facilitySuspiciousTotalAmount' as facility_suspicious_amount,
  c.last_bc_validation_called_at,
  c.last_fi_validation_called_at
from bnpl_customer_config c
join users u on u.user_id = c.customer_id
""" + USER_FILTERS + "order by c.updated_at desc;",
    },
    {
        "name": "Search - Customer Installment Detail",
        "display": "table",
        "description": "Installment history with gateway confirmation, due-date status, and payment delay.",
        "sql": r"""
select
  u.user_id,
  i.id as installment_id,
  i.created_at as installment_created_at,
  i.source,
  i.number as installment_number,
  i.amount,
  i.penalty,
  i.due_date,
  i.payment_id,
  gp.confirmed_at,
  case
    when gp.confirmed_at is not null then 'CONFIRMED'
    when i.payment_id is not null then 'PAYMENT_LINKED_UNCONFIRMED'
    else 'UNPAID'
  end as payment_status,
  case
    when gp.confirmed_at is not null and gp.confirmed_at::date <= i.due_date then 'PAID_ON_OR_BEFORE_DUE'
    when gp.confirmed_at is not null and gp.confirmed_at::date - i.due_date between 1 and 5 then 'PAID_WITHIN_5_DAY_GRACE'
    when gp.confirmed_at is not null then 'PAID_OVER_5_DAYS_LATE'
    when i.due_date > current_date then 'FUTURE'
    when i.due_date = current_date then 'DUE_TODAY'
    when current_date - i.due_date <= 5 then 'OVERDUE_WITHIN_5_DAYS'
    else 'OVERDUE_OVER_5_DAYS'
  end as due_status,
  case when gp.confirmed_at is not null
    then gp.confirmed_at::date - i.due_date
  end as payment_delay_days,
  i.penalty_updated_at
from bnpl_credit_installments i
join users u on u.user_id = i.customer_id
left join bnpl_gateway_payments gp on gp.id = i.payment_id
""" + USER_FILTERS + "order by i.created_at desc, i.number;",
    },
    {
        "name": "Search - Invoice Detail",
        "display": "table",
        "description": "Invoices for the matched customer, with service and vehicle context.",
        "sql": r"""
select
  u.user_id,
  i.id as invoice_id,
  i.created_at,
  i.status,
  i.source,
  i.description,
  i.amount,
  i.amount_for_commission,
  i.discount_amount,
  i.interest_amount,
  i.digital_service_fee,
  i.payment_method,
  i.settlement_id,
  s.name as auto_service_name,
  c.model as car_model,
  c.plate as car_plate
from invoices i
join users u on u.user_id = i.customer_id
left join auto_services s on s.auto_service_id = i.auto_service_id
left join cars c on c.car_id = i.car_id
""" + USER_FILTERS + "order by i.created_at desc, i.id desc;",
    },
    {
        "name": "Search - Shop Orders",
        "display": "table",
        "description": "Shop orders and invoice status, including promo-code discount amounts and cancellation details.",
        "sql": r"""
select
  u.user_id,
  o.id as order_id,
  o.created_at,
  o.updated_at,
  o.status as order_status,
  o.visit_date,
  o.visit_from_time,
  o.visit_to_time,
  o.description,
  o.reservation_fee,
  o.payment_methods,
  o.delivery_method,
  o.promo_code_id,
  o.soupop_promo_code_discount_amount,
  o.auto_service_promo_code_discount_amount,
  o.cancelation_reason,
  i.status as invoice_status,
  i.amount as invoice_amount,
  s.name as auto_service_name,
  c.model as car_model,
  c.plate as car_plate
from shop_orders o
join users u on u.user_id = o.customer_id
left join invoices i on i.id = o.invoice_id
left join auto_services s on s.auto_service_id = o.auto_service_id
left join cars c on c.car_id = o.car_id
""" + USER_FILTERS + "order by o.created_at desc, o.id desc;",
    },
    {
        "name": "Search - Current BNPL Credit",
        "display": "table",
        "description": "Current customer BNPL balances. The account table is unique per customer.",
        "sql": r"""
select
  u.user_id,
  c.id as credit_account_id,
  c.created_at,
  c.updated_at,
  c.raw_balance as bnpl_raw_balance,
  c.loan_raw_balance,
  c.expires_at
from bnpl_credits c
join users u on u.user_id = c.customer_id
""" + USER_FILTERS + "order by c.updated_at desc;",
    },
    {
        "name": "Search - Loan Applications",
        "display": "table",
        "description": "Customer loan applications with loan terms, current workflow step, and completed-step history.",
        "sql": r"""
with completed_steps as (
  select
    customer_loan_id,
    string_agg(step || ' @ ' || created_at::text, E'\n' order by created_at) as step_history
  from bnpl_customer_loan_step_done_timelines
  group by customer_loan_id
)
select
  u.user_id,
  cl.id as customer_loan_id,
  cl.created_at,
  cl.updated_at,
  cl.amount,
  cl.installments_count,
  cl.interest_rate,
  cl.digital_service_fee,
  cl.subscription_cost,
  cl.subscription_plan_payment_method,
  cl.has_paid_subscription_fee,
  cl.step,
  cl.step_status,
  l.id as loan_product_id,
  l.amount as loan_product_amount,
  l.installments_count as loan_product_installments_count,
  l.deleted_at is not null as loan_product_archived,
  sp.title as subscription_plan,
  cs.step_history
from bnpl_customer_loans cl
join users u on u.user_id = cl.customer_id
left join bnpl_loans l on l.id = cl.loan_id
left join bnpl_loan_subscription_plans sp on sp.id = cl.subscription_plan_id
left join completed_steps cs on cs.customer_loan_id = cl.id
""" + USER_FILTERS + "order by cl.created_at desc, cl.id desc;",
    },
    {
        "name": "Search - BNPL Credit History",
        "display": "table",
        "description": "Credit change log entries by customer, including amount and event type.",
        "sql": r"""
select
  u.user_id,
  h.id as credit_log_id,
  h.created_at,
  h.type as credit_event_type,
  h.total_amount
from bnpl_credit_logs h
join users u on u.user_id = h.customer_id
""" + USER_FILTERS + "order by h.created_at desc, h.id desc;",
    },
]

PARAMETERS = [
    {"id": "user_id", "name": "User ID", "slug": "user_id", "type": "number/=", "sectionId": "number", "default": None, "mappings": []},
    {"id": "phone_number", "name": "Phone number", "slug": "phone_number", "type": "string/=", "sectionId": "string", "default": None, "mappings": []},
    {"id": "national_code", "name": "National code", "slug": "national_code", "type": "string/=", "sectionId": "string", "default": None, "mappings": []},
]

POSITIONS = [
    (0, 0, 24, 8),
    (0, 8, 24, 8),
    (0, 16, 24, 10),
    (0, 26, 24, 10),
    (0, 36, 24, 10),
    (0, 46, 12, 8),
    (12, 46, 12, 8),
    (0, 54, 24, 10),
]


def require_id(result, label):
    value = result.get("id") or result.get(f"{label}_id")
    if value is None:
        raise SystemExit(f"Metabase did not return {label} id: {result}")
    return int(value)


def main():
    env = load_env()
    if not env.get("METABASE_API_KEY"):
        raise SystemExit("Set METABASE_API_KEY in .env before running this script.")
    if str(DATABASE_ID) != "2":
        raise SystemExit("This dashboard is configured for Metabase database 2; set METABASE_DATABASE_ID=2.")

    client = MetabaseClient()
    created_questions = []
    for question in QUESTIONS:
        result = client.create_native_card(
            DATABASE_ID,
            question["name"],
            question["sql"].strip(),
            display=question["display"],
            description=question["description"],
            template_tags=TEMPLATE_TAGS,
        )
        created_questions.append({"id": require_id(result, "question"), "name": question["name"]})

    dashboard = client.create_standard_dashboard(
        DASHBOARD_NAME,
        description=(
            "Customer lookup across profile, BNPL configuration, installment and invoice detail, "
            "shop orders, current BNPL credit, loan applications, and credit history. Enter a user "
            "ID, phone number, or national code to return records."
        ),
    )
    dashboard_id = require_id(dashboard, "dashboard")

    cards = []
    for index, question in enumerate(created_questions):
        row, col, size_x, size_y = POSITIONS[index]
        cards.append({
            "id": -(index + 1),
            "card_id": question["id"],
            "row": row,
            "col": col,
            "size_x": size_x,
            "size_y": size_y,
            "parameter_mappings": [
                {"parameter_id": tag, "target": ["variable", ["template-tag", tag]]}
                for tag in TEMPLATE_TAGS
            ],
            "series": [],
        })

    updated = client.call("PUT", f"/api/dashboard/{dashboard_id}", {
        "parameters": PARAMETERS,
        "dashcards": cards,
    })
    url = f"{client.base_url}/dashboard/{dashboard_id}"
    print({
        "dashboard_id": dashboard_id,
        "dashboard_url": url,
        "question_count": len(created_questions),
        "questions": created_questions,
        "filters": [parameter["name"] for parameter in PARAMETERS],
        "saved_dashcards": len(updated.get("dashcards", [])),
    })
    print(f"Open dashboard: {url}")


if __name__ == "__main__":
    main()
