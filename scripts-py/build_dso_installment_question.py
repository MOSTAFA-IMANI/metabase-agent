#!/usr/bin/env python3
from metabase_agent import MetabaseClient, load_env, print_json


QUESTION_NAME = "DSO for paid installments by filter type"
QUESTION_ID = 1007
DEFAULT_DATABASE_ID = "2"

DESCRIPTION = """
Days Sales Outstanding (DSO) for paid installments belonging to customers who
have no active credit_in_4 or Loan installment. An active installment is one
whose payment_id is empty. DSO is measured from installment.created_at to the
linked gateway payment.confirmed_at.
""".strip()

TEMPLATE_TAGS = {
    "filter_type": {
        "id": "filter_type",
        "name": "filter_type",
        "display-name": "Filter type",
        "type": "text",
        "required": False,
    },
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
with eligible_customers as (
  select
    i.customer_id,
    count(*) as total_installment_count
  from bnpl_credit_installments i
  where lower(i.source) in ('credit_in_4', 'loan')
  group by i.customer_id
  having count(*) filter (where i.payment_id is null) = 0
),
filtered_installments as (
  select
    case when lower(i.source) = 'loan' then 'Loan' else 'credit_in_4' end as filter_type,
    i.id as installment_id,
    i.customer_id,
    i.payment_id,
    i.number as installment_number,
    i.amount as installment_amount,
    i.created_at as installment_created_at,
    i.due_date,
    gp.confirmed_at,
    ec.total_installment_count,
    extract(epoch from (gp.confirmed_at - i.created_at)) / 86400.0 as dso_days
  from bnpl_credit_installments i
  join eligible_customers ec
    on ec.customer_id = i.customer_id
  join bnpl_gateway_payments gp
    on gp.id = i.payment_id
  where lower(i.source) in ('credit_in_4', 'loan')
    and gp.confirmed_at is not null
    [[and lower(i.source) = lower({{filter_type}})]]
    [[and i.created_at >= {{start_date}}]]
    [[and i.created_at < {{end_date}}]]
    [[and i.customer_id = {{customer_id}}]]
),
filter_stats as (
  select
    filter_type,
    avg(dso_days) as avg_dso_days,
    sum(dso_days * installment_amount) / nullif(sum(installment_amount), 0) as weighted_avg_dso_days,
    count(*) as paid_installment_count,
    count(distinct customer_id) as eligible_customer_count
  from filtered_installments
  group by filter_type
)
select
  fi.filter_type,
  fi.installment_id,
  fi.customer_id,
  fi.payment_id,
  fi.installment_number,
  fi.installment_amount,
  fi.installment_created_at,
  fi.due_date,
  fi.confirmed_at,
  round(fi.dso_days::numeric, 2) as dso_days,
  round(fs.avg_dso_days::numeric, 2) as avg_dso_days_by_filter_type,
  round(fs.weighted_avg_dso_days::numeric, 2) as weighted_avg_dso_days_by_filter_type,
  fs.paid_installment_count as paid_installment_count_by_filter_type,
  fs.eligible_customer_count as eligible_customer_count_by_filter_type,
  fi.total_installment_count
from filtered_installments fi
join filter_stats fs using (filter_type)
order by fi.filter_type, fi.installment_created_at desc;
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
    database_id = env.get("METABASE_DSO_DATABASE_ID") or DEFAULT_DATABASE_ID
    if not database_id:
        raise SystemExit("Put METABASE_DATABASE_ID=2 in .env first, then rerun this script.")

    client = MetabaseClient()
    print("Checking Metabase Agent API...")
    print_json(client.ping())

    print(f"Updating question: {QUESTION_NAME}")
    saved = client.call("PUT", f"/api/card/{QUESTION_ID}", {
        "name": QUESTION_NAME,
        "display": "table",
        "description": DESCRIPTION,
        "dataset_query": {
            "database": int(database_id),
            "type": "native",
            "native": {
                "query": SQL.strip(),
                "template-tags": TEMPLATE_TAGS,
            },
        },
    })
    qid = question_id(saved)
    question_url = f"{client.base_url}/question/{qid}"
    print_json({"question": saved, "question_url": question_url})
    print(f"\nOpen question: {question_url}")


if __name__ == "__main__":
    main()
