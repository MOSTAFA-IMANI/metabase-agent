#!/usr/bin/env python3
from metabase_agent import MetabaseClient, load_env, print_json


DASHBOARD_NAME = "Loan operation Dashboard"
DISPLAY_TABLE = "table"
DISPLAY_BAR = "bar"
DISPLAY_LINE = "line"
DISPLAY_SCALAR = "scalar"


COMMON_FILTER_NOTE = """
Dashboard-level filter targets to add in Metabase after creation:
- Date filter -> every question's `created_at` / `due_date`.
- Step filter -> `bnpl_customer_loans.step`.
- Step status filter -> `bnpl_customer_loans.step_status`.
- Customer ID filter -> `bnpl_customer_loans.customer_id`.
- Auto service ID filter -> cheque `received_auto_service_id`.
""".strip()

TEMPLATE_TAGS = {
    "start_date": {"id": "start_date", "name": "start_date", "display-name": "Start date", "type": "date", "required": False},
    "end_date": {"id": "end_date", "name": "end_date", "display-name": "End date", "type": "date", "required": False},
    "due_start_date": {"id": "due_start_date", "name": "due_start_date", "display-name": "Due start date", "type": "date", "required": False},
    "due_end_date": {"id": "due_end_date", "name": "due_end_date", "display-name": "Due end date", "type": "date", "required": False},
    "step": {"id": "step", "name": "step", "display-name": "Step", "type": "text", "required": False},
    "step_status": {"id": "step_status", "name": "step_status", "display-name": "Step status", "type": "text", "required": False},
    "customer_id": {"id": "customer_id", "name": "customer_id", "display-name": "Customer ID", "type": "number", "required": False},
    "auto_service_id": {"id": "auto_service_id", "name": "auto_service_id", "display-name": "Auto service ID", "type": "number", "required": False},
}


QUESTIONS = [
    {
        "name": "Loan applications by step and status",
        "display": DISPLAY_BAR,
        "description": "Operational funnel of customer loan applications by current step and status.",
        "sql": """
select
  coalesce(step, 'unknown') as step,
  coalesce(step_status, 'unknown') as step_status,
  count(*) as loan_count
from bnpl_customer_loans
where deleted_at is null
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and step = {{step}}]]
  [[and step_status = {{step_status}}]]
  [[and customer_id = {{customer_id}}]]
group by 1, 2
order by loan_count desc;
""",
    },
    {
        "name": "Open loans needing operation follow up",
        "display": DISPLAY_TABLE,
        "description": "Loans that are not completed/rejected and may need operational review.",
        "sql": """
select
  id as customer_loan_id,
  customer_id,
  loan_id,
  step,
  step_status,
  installments_count,
  subscription_plan_payment_method,
  has_paid_subscription_fee,
  created_at,
  updated_at
from bnpl_customer_loans
where deleted_at is null
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and step = {{step}}]]
  [[and step_status = {{step_status}}]]
  [[and customer_id = {{customer_id}}]]
  and coalesce(step_status, '') not in ('done', 'completed', 'rejected', 'cancelled')
order by updated_at desc
limit 500;
""",
    },
    {
        "name": "Cheque collateral status",
        "display": DISPLAY_BAR,
        "description": "Cheque collateral counts by status for loan operations.",
        "sql": """
select
  coalesce(status, 'unknown') as cheque_status,
  count(*) as cheque_count
from bnpl_customer_loan_collaterals
where deleted_at is null
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
group by 1
order by cheque_count desc;
""",
    },
    {
        "name": "Cheque registration and due date worklist",
        "display": DISPLAY_TABLE,
        "description": "Operational cheque list with registration, due date, returned cheque references, and receiver.",
        "sql": """
select
  ch.id as cheque_row_id,
  ch.customer_loan_id,
  cl.customer_id,
  cl.step,
  cl.step_status,
  ch.sayad_id,
  ch.sayad_ref_number,
  ch.sayad_registration_date,
  ch.due_date,
  ch.national_id,
  ch.payee,
  ch.received_auto_service_id,
  ch.holder_id,
  ch.is_digital,
  ch.returned_cheque_postal_number,
  ch.returned_cheque_ref_number,
  ch.description,
  ch.created_at,
  ch.updated_at
from bnpl_customer_credit_loan_cheques ch
left join bnpl_customer_loans cl on cl.id = ch.customer_loan_id
where ch.deleted_at is null
  [[and ch.created_at >= {{start_date}}]]
  [[and ch.created_at < {{end_date}}]]
  [[and ch.due_date >= {{due_start_date}}]]
  [[and ch.due_date <= {{due_end_date}}]]
  [[and cl.step = {{step}}]]
  [[and cl.step_status = {{step_status}}]]
  [[and cl.customer_id = {{customer_id}}]]
  [[and ch.received_auto_service_id = {{auto_service_id}}]]
order by ch.due_date asc nulls last, ch.updated_at desc
limit 500;
""",
    },
    {
        "name": "Cheques due in next 30 days",
        "display": DISPLAY_TABLE,
        "description": "Upcoming cheque due dates for operational follow up.",
        "sql": """
select
  ch.due_date,
  ch.customer_loan_id,
  cl.customer_id,
  cl.step,
  cl.step_status,
  ch.sayad_id,
  ch.received_auto_service_id,
  ch.is_digital,
  ch.returned_cheque_ref_number
from bnpl_customer_credit_loan_cheques ch
left join bnpl_customer_loans cl on cl.id = ch.customer_loan_id
where ch.deleted_at is null
  and ch.due_date >= current_date
  and ch.due_date < current_date + interval '30 days'
  [[and cl.step = {{step}}]]
  [[and cl.step_status = {{step_status}}]]
  [[and cl.customer_id = {{customer_id}}]]
  [[and ch.received_auto_service_id = {{auto_service_id}}]]
order by ch.due_date asc
limit 500;
""",
    },
    {
        "name": "Overdue cheques",
        "display": DISPLAY_TABLE,
        "description": "Cheques past due date, excluding rows with deleted cheques.",
        "sql": """
select
  ch.due_date,
  current_date - ch.due_date as days_overdue,
  ch.customer_loan_id,
  cl.customer_id,
  cl.step,
  cl.step_status,
  ch.sayad_id,
  ch.received_auto_service_id,
  ch.returned_cheque_ref_number,
  ch.description
from bnpl_customer_credit_loan_cheques ch
left join bnpl_customer_loans cl on cl.id = ch.customer_loan_id
where ch.deleted_at is null
  and ch.due_date < current_date
  [[and cl.step = {{step}}]]
  [[and cl.step_status = {{step_status}}]]
  [[and cl.customer_id = {{customer_id}}]]
  [[and ch.received_auto_service_id = {{auto_service_id}}]]
order by days_overdue desc
limit 500;
""",
    },
    {
        "name": "Daily new loan requests",
        "display": DISPLAY_LINE,
        "description": "Daily trend of new customer loan requests.",
        "sql": """
select
  date_trunc('day', created_at) as day,
  count(*) as loan_requests
from bnpl_customer_loans
where deleted_at is null
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and step = {{step}}]]
  [[and step_status = {{step_status}}]]
  [[and customer_id = {{customer_id}}]]
group by 1
order by 1;
""",
    },
    {
        "name": "Subscription fee payment status",
        "display": DISPLAY_BAR,
        "description": "Loan subscription payment method and paid/unpaid status.",
        "sql": """
select
  coalesce(subscription_plan_payment_method, 'unknown') as payment_method,
  case when has_paid_subscription_fee then 'paid' else 'not paid' end as subscription_fee_status,
  count(*) as loan_count
from bnpl_customer_loans
where deleted_at is null
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and step = {{step}}]]
  [[and step_status = {{step_status}}]]
  [[and customer_id = {{customer_id}}]]
group by 1, 2
order by loan_count desc;
""",
    },
    {
        "name": "Loan eligibility summary",
        "display": DISPLAY_BAR,
        "description": "Customer config eligibility status for loans.",
        "sql": """
select
  case when eligible_for_loan then 'eligible' else 'not eligible' end as eligibility,
  count(*) as customer_count
from bnpl_customer_config
where 1 = 1
  [[and created_at >= {{start_date}}]]
  [[and created_at < {{end_date}}]]
  [[and customer_id = {{customer_id}}]]
group by 1
order by customer_count desc;
""",
    },
    {
        "name": "Installment items by loan",
        "display": DISPLAY_TABLE,
        "description": "Installment item count connected to customer loans.",
        "sql": """
select
  cl.id as customer_loan_id,
  cl.customer_id,
  cl.step,
  cl.step_status,
  count(li.id) as installment_item_count,
  min(li.created_at) as first_installment_item_at,
  max(li.created_at) as last_installment_item_at
from bnpl_customer_loans cl
left join bnpl_loan_installment_items li on li.customer_loan_id = cl.id
where cl.deleted_at is null
  [[and cl.created_at >= {{start_date}}]]
  [[and cl.created_at < {{end_date}}]]
  [[and cl.step = {{step}}]]
  [[and cl.step_status = {{step_status}}]]
  [[and cl.customer_id = {{customer_id}}]]
group by 1, 2, 3, 4
order by last_installment_item_at desc nulls last
limit 500;
""",
    },
]


def query_value(response):
    value = response.get("query") or response.get("query_handle") or response.get("id")
    if not value:
        raise SystemExit(f"Could not find query handle in response: {response}")
    return value


def question_id(response):
    value = response.get("id") or response.get("card_id")
    if not value:
        raise SystemExit(f"Could not find question id in response: {response}")
    return value


def dashboard_id(response):
    value = response.get("id") or response.get("dashboard_id")
    if not value:
        raise SystemExit(f"Could not find dashboard id in response: {response}")
    return value


def dashboard_cards(card_ids):
    cards = []
    row = 0
    for index, card_id in enumerate(card_ids):
        is_chart = index in {0, 2, 6, 7, 8}
        size_x = 12 if is_chart else 24
        size_y = 8 if is_chart else 10
        col = 0 if size_x == 24 or index % 2 == 0 else 12
        if size_x == 24 and cards:
            row = max(card["row"] + card["size_y"] for card in cards)
        elif size_x == 12 and index % 2 == 0 and cards:
            row = max(card["row"] + card["size_y"] for card in cards)
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


def main():
    env = load_env()
    if not env.get("METABASE_API_KEY") or env.get("METABASE_API_KEY") == "YOUR_METABASE_API_KEY":
        raise SystemExit("Put the real METABASE_API_KEY in .env first, then rerun this script.")
    database_id = env.get("METABASE_DATABASE_ID")
    if not database_id:
        raise SystemExit("Put METABASE_DATABASE_ID=2 in .env first, then rerun this script.")

    client = MetabaseClient()
    created_question_ids = []
    created_questions = []

    print("Checking Metabase Agent API...")
    print_json(client.ping())

    for question in QUESTIONS:
        print(f"Creating question: {question['name']}")
        saved = client.create_native_card(
            database_id=database_id,
            name=question["name"],
            sql=question["sql"].strip(),
            display=question["display"],
            description=question["description"],
            template_tags=TEMPLATE_TAGS,
        )
        qid = question_id(saved)
        created_question_ids.append(qid)
        created_questions.append({"id": qid, "name": question["name"]})

    print(f"Creating dashboard: {DASHBOARD_NAME}")
    dashboard = client.create_standard_dashboard(
        name=DASHBOARD_NAME,
        description="Loan operations dashboard for loan funnel, cheque status, due dates, overdue work, subscription fee status, eligibility, and installment follow up.\n\n" + COMMON_FILTER_NOTE,
    )
    did = dashboard_id(dashboard)
    print("Adding questions to dashboard...")
    updated_dashboard = client.update_standard_dashboard_cards(did, dashboard_cards(created_question_ids))
    dashboard_url = None
    if did:
        dashboard_url = f"{client.base_url}/dashboard/{did}"

    print_json({
        "dashboard": dashboard,
        "updated_dashboard": updated_dashboard,
        "dashboard_url": dashboard_url,
        "questions": created_questions,
        "filter_note": COMMON_FILTER_NOTE,
    })
    if dashboard_url:
        print(f"\nOpen dashboard: {dashboard_url}")


if __name__ == "__main__":
    main()
