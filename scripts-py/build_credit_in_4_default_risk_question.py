#!/usr/bin/env python3
from metabase_agent import MetabaseClient, load_env, print_json


QUESTION_NAME = "credit_in_4 default risk by credit amount"
DEFAULT_DATABASE_ID = "2"

DESCRIPTION = """
Compares credit_in_4 default risk across customer credit-size buckets. Credit
size is the customer's total credit_in_4 installment amount. Default risk is
measured as overdue unpaid installments: payment_id is empty and due_date is
before today. The customer-level default rate counts customers with at least
one overdue unpaid installment among customers with at least one due installment.
""".strip()

TEMPLATE_TAGS = {
    "start_date": {
        "id": "start_date",
        "name": "start_date",
        "display-name": "Installment start date",
        "type": "date",
        "required": False,
    },
    "end_date": {
        "id": "end_date",
        "name": "end_date",
        "display-name": "Installment end date",
        "type": "date",
        "required": False,
    },
    "customer_id": {
        "id": "customer_id",
        "name": "customer_id",
        "display-name": "Customer ID",
        "type": "number",
        "required": False,
    },
}

SQL = """
with credit_in_4_installments as (
  select
    i.id as installment_id,
    i.customer_id,
    i.amount,
    i.payment_id,
    i.created_at,
    i.due_date
  from bnpl_credit_installments i
  where lower(i.source) = 'credit_in_4'
    [[and i.created_at >= {{start_date}}]]
    [[and i.created_at < {{end_date}}]]
    [[and i.customer_id = {{customer_id}}]]
),
customer_credit as (
  select
    customer_id,
    sum(amount) as credit_amount,
    count(*) as installment_count,
    count(*) filter (where due_date < current_date) as due_installment_count,
    count(*) filter (
      where payment_id is null
        and due_date < current_date
    ) as overdue_unpaid_installment_count,
    max(
      case
        when payment_id is null and due_date < current_date
        then current_date - due_date
      end
    ) as max_days_overdue
  from credit_in_4_installments
  group by customer_id
),
bucketed_customers as (
  select
    customer_credit.*,
    ntile(5) over (order by credit_amount) as credit_bucket
  from customer_credit
),
bucket_summary as (
  select
    credit_bucket,
    min(credit_amount) as min_credit_amount,
    max(credit_amount) as max_credit_amount,
    avg(credit_amount) as avg_credit_amount,
    count(*) as customer_count,
    count(*) filter (where due_installment_count > 0) as customers_with_due_installments,
    count(*) filter (where overdue_unpaid_installment_count > 0) as defaulted_customer_count,
    sum(installment_count) as installment_count,
    sum(due_installment_count) as due_installment_count,
    sum(overdue_unpaid_installment_count) as overdue_unpaid_installment_count,
    avg(max_days_overdue) filter (where max_days_overdue is not null) as avg_max_days_overdue
  from bucketed_customers
  group by credit_bucket
)
select
  credit_bucket,
  min_credit_amount,
  max_credit_amount,
  round(avg_credit_amount::numeric, 0) as avg_credit_amount,
  customer_count,
  customers_with_due_installments,
  defaulted_customer_count,
  round(
    100.0 * defaulted_customer_count / nullif(customers_with_due_installments, 0),
    2
  ) as customer_default_rate_percent,
  installment_count,
  due_installment_count,
  overdue_unpaid_installment_count,
  round(
    100.0 * overdue_unpaid_installment_count / nullif(due_installment_count, 0),
    2
  ) as overdue_unpaid_installment_rate_percent,
  round(avg_max_days_overdue::numeric, 2) as avg_max_days_overdue
from bucket_summary
order by credit_bucket;
"""


def question_id(response):
    value = response.get("id") or response.get("card_id")
    if not value:
        raise SystemExit(f"Could not find question id in response: {response}")
    return value


def main():
    env = load_env()
    if not env.get("METABASE_API_KEY") or env.get("METABASE_API_KEY") == "YOUR_METABASE_API_KEY":
        raise SystemExit("Put the real METABASE_API_KEY in .env first, then rerun this script.")
    database_id = env.get("METABASE_CREDIT_RISK_DATABASE_ID") or DEFAULT_DATABASE_ID

    client = MetabaseClient()
    print("Checking Metabase Agent API...")
    try:
        print_json(client.ping())
    except (Exception, SystemExit) as exc:
        print(f"Ping failed, continuing with card creation: {exc}")

    print(f"Creating question: {QUESTION_NAME}")
    saved = client.create_native_card(
        database_id=database_id,
        name=QUESTION_NAME,
        sql=SQL.strip(),
        display="table",
        description=DESCRIPTION,
        template_tags=TEMPLATE_TAGS,
    )
    qid = question_id(saved)
    question_url = f"{client.base_url}/question/{qid}"
    print_json({"question": saved, "question_url": question_url})
    print(f"\nOpen question: {question_url}")


if __name__ == "__main__":
    main()
