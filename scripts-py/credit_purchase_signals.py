#!/usr/bin/env python3
"""Read-only signals: does available credit steer what, where and when customers buy?

Every query is an aggregate SELECT on database 2 (PostgreSQL, Asia/Tehran).
No customer-level rows are returned; shop and product rows need at least
10 distinct customers. Output is JSON on stdout.

Usage: python3 scripts-py/credit_purchase_signals.py [--only NAME ...] > signals.json
"""
import argparse
import functools
import json
import sys
import time

import metabase_agent
from metabase_agent import MetabaseClient

DB = 2
MIN_CUSTOMERS = 10

# Some of these scan every invoice; allow longer than the client's 60s default.
metabase_agent.request.urlopen = functools.partial(metabase_agent.request.urlopen, timeout=240)

# One row per completed invoice. "On credit" means the invoice transaction used credit.
INV = """
with inv as (
  select i.id, i.customer_id, i.auto_service_id, i.car_id, i.amount,
         i.created_at at time zone 'Asia/Tehran' as ts,
         coalesce(t.credit, 0) as credit, coalesce(t.cash, i.amount) as cash,
         coalesce(t.credit, 0) > 0 as on_credit, coalesce(t.credit_type, '-') as credit_type
  from invoices i left join bnpl_invoice_transactions t on t.invoice_id = i.id
  where i.status = 'DONE'
), base as (
  select avg(case when on_credit then 1.0 else 0 end) as share from inv
)
"""

ACT_SOURCES = {
    "first credit log": "select customer_id, min(created_at at time zone 'Asia/Tehran') as act from bnpl_credit_logs group by 1",
    "credit account created": "select customer_id, created_at at time zone 'Asia/Tehran' as act from bnpl_credits",
}


def timing_sql(label, act_sql):
    return INV + f"""
, act as ({act_sql})
, f as (
  select a.customer_id, a.act, min(inv.ts) filter (where inv.on_credit and inv.ts >= a.act) as first_credit,
         count(inv.id) filter (where inv.ts < a.act) as before_cnt
  from act a left join inv on inv.customer_id = a.customer_id group by 1, 2)
select '{label}' as activation, case
  when first_credit is null then '9 no credit purchase yet'
  when first_credit < act + interval '1 day' then '1 within 24 hours'
  when first_credit < act + interval '7 days' then '2 1-7 days'
  when first_credit < act + interval '30 days' then '3 8-30 days'
  when first_credit < act + interval '90 days' then '4 31-90 days'
  else '5 over 90 days' end as time_to_first_credit_purchase,
  count(*) as users,
  count(*) filter (where before_cnt = 0) as had_no_purchase_before,
  count(*) filter (where before_cnt > 0) as had_cash_purchases_before
from f group by 1, 2 order by 2"""


def before_after_sql(label, act_sql):
    return INV + f"""
, act as ({act_sql})
, w as (
  select a.customer_id,
    count(inv.id) filter (where inv.ts >= a.act - interval '90 days' and inv.ts < a.act) as b_cnt,
    coalesce(sum(inv.amount) filter (where inv.ts >= a.act - interval '90 days' and inv.ts < a.act), 0) as b_amt,
    count(inv.id) filter (where inv.ts >= a.act and inv.ts < a.act + interval '90 days') as a_cnt,
    coalesce(sum(inv.amount) filter (where inv.ts >= a.act and inv.ts < a.act + interval '90 days'), 0) as a_amt,
    count(inv.id) filter (where inv.on_credit and inv.ts >= a.act and inv.ts < a.act + interval '90 days') as a_credit_cnt
  from act a left join inv on inv.customer_id = a.customer_id
  where a.act < (now() at time zone 'Asia/Tehran') - interval '90 days'
    and a.act > (select min(ts) from inv) + interval '90 days'
  group by 1)
select '{label}' as activation, count(*) as users,
  sum(b_cnt) as invoices_90d_before, sum(a_cnt) as invoices_90d_after,
  sum(b_amt) as amount_90d_before, sum(a_amt) as amount_90d_after, sum(a_credit_cnt) as credit_invoices_90d_after,
  count(*) filter (where b_cnt = 0 and a_cnt > 0) as started_buying_after,
  count(*) filter (where b_cnt > 0) as bought_before,
  count(*) filter (where b_cnt > 0 and a_cnt > b_cnt) as bought_more_after,
  count(*) filter (where b_cnt > 0 and a_cnt < b_cnt) as bought_less_after
from w"""


SHOP = INV + """
, s as (
  select auto_service_id, count(*) as invoices, count(*) filter (where on_credit) as credit_invoices,
         sum(amount) as amount, sum(credit) as credit_amount,
         count(distinct customer_id) as customers,
         count(distinct customer_id) filter (where on_credit) as credit_customers
  from inv group by 1)
select a.name as shop, a.city, s.invoices, s.credit_invoices, s.customers, s.credit_customers,
       s.amount, s.credit_amount,
       round(100.0 * s.credit_invoices / s.invoices, 1) as credit_share_pct,
       round((s.credit_invoices::numeric / s.invoices) / nullif(base.share, 0), 2) as lift
from s join auto_services a on a.auto_service_id = s.auto_service_id cross join base
where s.customers >= {m} and s.credit_customers >= {m}
"""

QUERIES = {
    "labels": """
select 'invoices.payment_method (DONE)' as field, i.payment_method as value, count(*) as rows, count(*) filter (where t.credit > 0) as rows_with_credit
  from invoices i left join bnpl_invoice_transactions t on t.invoice_id = i.id where i.status = 'DONE' group by 1, 2
union all select 'invoices.source (DONE)', i.source, count(*), count(*) filter (where t.credit > 0)
  from invoices i left join bnpl_invoice_transactions t on t.invoice_id = i.id where i.status = 'DONE' group by 1, 2
union all select 'invoice_transactions.credit_type', credit_type, count(*), count(*) filter (where credit > 0) from bnpl_invoice_transactions group by 1, 2
union all select 'credit_logs.type (rows, customers)', type, count(*), count(distinct customer_id) from bnpl_credit_logs group by 1, 2
union all select 'shop_orders.status (rows, with invoice)', status, count(*), count(invoice_id) from shop_orders where deleted_at is null group by 1, 2
union all select 'credit accounts (rows, raw_balance>0)', 'bnpl_credits', count(*), count(*) filter (where raw_balance > 0) from bnpl_credits
union all select 'config (rows, qualifying_credit>0)', 'bnpl_customer_config', count(*), count(*) filter (where qualifying_credit_amount > 0) from bnpl_customer_config
union all select 'spending-shop links (rows, customers)', 'bnpl_spending_credit_auto_services', count(*), count(distinct customer_id) from bnpl_spending_credit_auto_services
order by 1, 3 desc""",
    "credit_logs_amounts": """
select type, count(*) as rows, min(total_amount) as min_amount, percentile_cont(0.5) within group (order by total_amount) as median_amount,
       max(total_amount) as max_amount, min(created_at)::date as first_seen, max(created_at)::date as last_seen
from bnpl_credit_logs group by 1 order by 2 desc""",
    "overview": INV + """
select case when on_credit then 'credit (' || credit_type || ')' else 'cash only' end as payment,
       count(*) as invoices, count(distinct customer_id) as customers, sum(amount) as amount, sum(credit) as credit_amount,
       round(avg(amount)) as avg_ticket, percentile_cont(0.5) within group (order by amount) as median_ticket,
       min(ts)::date as first_invoice, max(ts)::date as last_invoice
from inv group by rollup(1) order by 1""",
    "buyer_groups": INV + """
, u as (
  select customer_id, count(*) as n, count(*) filter (where on_credit) as nc, sum(amount) as amt,
         (array_agg(on_credit order by ts))[1] as first_on_credit
  from inv group by 1)
select case when nc = 0 then '1 cash only' when nc = n then '3 credit only' else '2 mixed' end as buyer_group,
       count(*) as customers, sum(n) as invoices, round(avg(n), 2) as invoices_per_customer,
       round(sum(amt) / sum(n)) as avg_ticket, count(*) filter (where first_on_credit) as first_purchase_was_credit,
       count(*) filter (where n = 1) as one_purchase_only
from u group by 1 order by 1""",
    "credit_enabled_vs_not": INV + """
, cfg as (select customer_id, qualifying_credit_amount > 0 as has_limit from bnpl_customer_config)
, u as (select inv.customer_id, count(*) as n, sum(amount) as amt, count(*) filter (where on_credit) as nc
        from inv group by 1)
select case when cfg.has_limit then 'has a credit limit' else 'no credit limit' end as customer_type,
       count(*) as buyers, sum(n) as invoices, round(avg(n), 2) as invoices_per_buyer,
       round(sum(amt) / sum(n)) as avg_ticket, sum(nc) as credit_invoices
from u left join cfg using (customer_id) group by 1 order by 1""",
    "shops_top_lift": SHOP.format(m=MIN_CUSTOMERS) + " order by lift desc, credit_invoices desc limit 25",
    "shops_top_credit_amount": SHOP.format(m=MIN_CUSTOMERS) + " order by credit_amount desc limit 25",
    "shops_by_credit_share": INV + """
, s as (select auto_service_id, count(*) as n, avg(case when on_credit then 1.0 else 0 end) as share,
               count(distinct customer_id) as customers from inv group by 1 having count(distinct customer_id) >= 10)
select case when share = 0 then '0 no credit sales' when share < 0.1 then '1 under 10%' when share < 0.25 then '2 10-25%'
            when share < 0.5 then '3 25-50%' when share < 0.75 then '4 50-75%' else '5 75% or more' end as credit_share_of_invoices,
       count(*) as shops, sum(n) as invoices
from s group by 1 order by 1""",
    "shop_loyalty": INV + """
, multi as (select customer_id, bool_or(on_credit) as credit_user from inv group by 1 having count(*) >= 2)
, us as (select inv.customer_id, m.credit_user, inv.auto_service_id, sum(inv.amount) as amt
         from inv join multi m using (customer_id) group by 1, 2, 3)
, t as (select customer_id, credit_user, max(amt) / nullif(sum(amt), 0) as top_share, count(*) as shops from us group by 1, 2)
select case when credit_user then 'credit users' else 'cash-only users' end as grp,
       count(*) as customers_with_2plus_invoices,
       count(*) filter (where shops = 1) as all_at_one_shop,
       round(100.0 * count(*) filter (where shops = 1) / count(*), 1) as all_at_one_shop_pct,
       round(avg(top_share) * 100, 1) as avg_pct_spend_at_top_shop
from t group by 1 order by 1""",
    "spending_shop_links": INV + """
, l as (select customer_id, count(*) as shops from bnpl_spending_credit_auto_services group by 1)
select case when l.customer_id is null then 'no linked shop' else 'has linked shop(s)' end as grp,
       count(distinct inv.customer_id) filter (where inv.on_credit) as credit_buyers,
       count(*) filter (where inv.on_credit) as credit_invoices,
       count(*) filter (where inv.on_credit and exists (select 1 from bnpl_spending_credit_auto_services x
             where x.customer_id = inv.customer_id and x.auto_service_id = inv.auto_service_id)) as credit_invoices_at_linked_shop,
       count(*) filter (where not inv.on_credit) as cash_invoices,
       count(*) filter (where not inv.on_credit and exists (select 1 from bnpl_spending_credit_auto_services x
             where x.customer_id = inv.customer_id and x.auto_service_id = inv.auto_service_id)) as cash_invoices_at_linked_shop
from inv left join l on l.customer_id = inv.customer_id group by 1 order by 1""",
    "spending_shop_links_per_customer": """
select least(n, 5) as linked_shops_per_customer, count(*) as customers
from (select customer_id, count(*) as n from bnpl_spending_credit_auto_services group by 1) x group by 1 order by 1""",
    "spending_shop_links_top_shops": f"""
select a.name as shop, a.city, count(distinct x.customer_id) as linked_customers
from bnpl_spending_credit_auto_services x join auto_services a on a.auto_service_id = x.auto_service_id
group by 1, 2 having count(distinct x.customer_id) >= {MIN_CUSTOMERS} order by 3 desc limit 20""",
    "service_types_instore": INV + f"""
, m as (
  select distinct inv.id, inv.on_credit, inv.customer_id, inv.amount, mst.name
  from inv join maintanence_services ms on ms.car_id = inv.car_id and ms.auto_service_id = inv.auto_service_id
       and ms.deleted_at is null and ms.date_of_change between inv.ts::date - 1 and inv.ts::date + 1
  join maintanence_service_types mst on mst.type_id = ms.type_id)
, mb as (select avg(case when on_credit then 1.0 else 0 end) as share, count(distinct id) as matched from m)
select name as service_type, count(distinct id) as invoices, count(distinct id) filter (where on_credit) as credit_invoices,
       count(distinct customer_id) as customers,
       round(100.0 * count(distinct id) filter (where on_credit) / count(distinct id), 1) as credit_share_pct,
       round((count(distinct id) filter (where on_credit)::numeric / count(distinct id)) / nullif(max(mb.share), 0), 2) as lift,
       round(avg(amount) filter (where on_credit)) as avg_credit_ticket, round(avg(amount) filter (where not on_credit)) as avg_cash_ticket,
       max(mb.matched) as all_matched_invoices, round(100 * max(mb.share), 1) as matched_base_credit_pct
from m cross join mb group by 1 having count(distinct customer_id) >= {MIN_CUSTOMERS}
order by lift desc, invoices desc limit 40""",
    "shop_orders_overview": INV + """
select case when inv.on_credit then 'credit' else 'cash only' end as payment, count(*) as orders,
       count(distinct so.customer_id) as customers, sum(inv.amount) as amount
from shop_orders so join inv on inv.id = so.invoice_id where so.deleted_at is null group by rollup(1) order by 1""",
    "online_service_types": INV + f"""
, o as (select so.id as order_id, inv.on_credit, inv.customer_id from shop_orders so join inv on inv.id = so.invoice_id where so.deleted_at is null)
, ob as (select avg(case when on_credit then 1.0 else 0 end) as share from o)
select t.name as service_type, count(distinct o.order_id) as orders, count(distinct o.order_id) filter (where o.on_credit) as credit_orders,
       count(distinct o.customer_id) as customers,
       round(100.0 * count(distinct o.order_id) filter (where o.on_credit) / count(distinct o.order_id), 1) as credit_share_pct,
       round((count(distinct o.order_id) filter (where o.on_credit)::numeric / count(distinct o.order_id)) / nullif(max(ob.share), 0), 2) as lift
from o join shop_order_service_types st on st.order_id = o.order_id and st.deleted_at is null
join auto_service_types_v2 t on t.id = st.service_type_id cross join ob
group by 1 having count(distinct o.customer_id) >= {MIN_CUSTOMERS} order by lift desc, orders desc limit 30""",
    "online_products": INV + f"""
, o as (select so.id as order_id, inv.on_credit, inv.customer_id from shop_orders so join inv on inv.id = so.invoice_id where so.deleted_at is null)
, ob as (select avg(case when on_credit then 1.0 else 0 end) as share from o)
, it as (
  select o.order_id, o.on_credit, o.customer_id, bp.title as product, b.name as brand, i.count, i.price_per_unit
  from o join shop_order_service_types st on st.order_id = o.order_id and st.deleted_at is null
  join shop_order_service_type_items i on i.order_service_type_id = st.id and i.deleted_at is null
  join shop_products p on p.id = i.product_id join shop_base_products bp on bp.id = p.base_product_id
  join shop_brands b on b.id = bp.brand_id)
select product, brand, count(distinct order_id) as orders, count(distinct order_id) filter (where on_credit) as credit_orders,
       count(distinct customer_id) as customers,
       round(100.0 * count(distinct order_id) filter (where on_credit) / count(distinct order_id), 1) as credit_share_pct,
       round((count(distinct order_id) filter (where on_credit)::numeric / count(distinct order_id)) / nullif(max(ob.share), 0), 2) as lift,
       round(avg(price_per_unit)) as avg_unit_price
from it cross join ob group by 1, 2 having count(distinct customer_id) >= {MIN_CUSTOMERS}
order by lift desc, orders desc limit 30""",
    "online_brands": INV + f"""
, o as (select so.id as order_id, inv.on_credit, inv.customer_id from shop_orders so join inv on inv.id = so.invoice_id where so.deleted_at is null)
, ob as (select avg(case when on_credit then 1.0 else 0 end) as share from o)
, it as (
  select o.order_id, o.on_credit, o.customer_id, b.name as brand
  from o join shop_order_service_types st on st.order_id = o.order_id and st.deleted_at is null
  join shop_order_service_type_items i on i.order_service_type_id = st.id and i.deleted_at is null
  join shop_products p on p.id = i.product_id join shop_base_products bp on bp.id = p.base_product_id
  join shop_brands b on b.id = bp.brand_id)
select brand, count(distinct order_id) as orders, count(distinct order_id) filter (where on_credit) as credit_orders,
       count(distinct customer_id) as customers,
       round(100.0 * count(distinct order_id) filter (where on_credit) / count(distinct order_id), 1) as credit_share_pct,
       round((count(distinct order_id) filter (where on_credit)::numeric / count(distinct order_id)) / nullif(max(ob.share), 0), 2) as lift
from it cross join ob group by 1 having count(distinct customer_id) >= {MIN_CUSTOMERS}
order by lift desc, orders desc limit 25""",
    "ticket_vs_limit": INV + """
, c as (select inv.credit, inv.cash, inv.amount, cfg.qualifying_credit_amount as lim
        from inv join bnpl_customer_config cfg on cfg.customer_id = inv.customer_id
        where inv.on_credit and cfg.qualifying_credit_amount > 0)
select case when credit < 0.25 * lim then '1 under 25% of limit' when credit < 0.5 * lim then '2 25-50%'
            when credit < 0.75 * lim then '3 50-75%' when credit < 0.9 * lim then '4 75-90%'
            when credit < lim then '5 90-99%' when credit = lim then '6 exactly the limit' else '7 above the limit' end as credit_used_vs_limit,
       count(*) as credit_invoices, sum(credit) as credit_amount,
       count(*) filter (where cash > 0) as also_paid_cash, round(avg(amount)) as avg_invoice
from c group by 1 order by 1""",
    "limit_bands": INV + """
, cfg as (select customer_id, qualifying_credit_amount as lim, ntile(5) over (order by qualifying_credit_amount) as band
          from bnpl_customer_config where qualifying_credit_amount > 0)
select cfg.band as limit_band_1_low_5_high, min(cfg.lim) as band_min_limit, max(cfg.lim) as band_max_limit,
       count(distinct cfg.customer_id) as customers_with_limit,
       count(distinct inv.customer_id) filter (where inv.on_credit) as used_credit,
       round(100.0 * count(distinct inv.customer_id) filter (where inv.on_credit) / count(distinct cfg.customer_id), 1) as used_credit_pct,
       count(inv.id) filter (where inv.on_credit) as credit_invoices,
       round(avg(inv.amount) filter (where inv.on_credit)) as avg_credit_ticket,
       round(avg(inv.amount) filter (where not inv.on_credit)) as avg_cash_ticket,
       round(avg(inv.credit / cfg.lim) filter (where inv.on_credit) * 100, 1) as avg_pct_of_limit_used
from cfg left join inv on inv.customer_id = cfg.customer_id group by 1 order by 1""",
    "timing_first_log": timing_sql("first credit log", ACT_SOURCES["first credit log"]),
    "timing_account": timing_sql("credit account created", ACT_SOURCES["credit account created"]),
    "before_after_first_log": before_after_sql("first credit log", ACT_SOURCES["first credit log"]),
    "before_after_account": before_after_sql("credit account created", ACT_SOURCES["credit account created"]),
    "after_events": INV + """
, pay as (
  select i.customer_id, min(p.confirmed_at) as ts from bnpl_credit_installments i
  join bnpl_gateway_payments p on p.id = i.payment_id where i.number > 1 and p.confirmed_at is not null group by i.id, 1)
, ev as (
  select 'credit log: ' || type as event, customer_id, created_at at time zone 'Asia/Tehran' as ts from bnpl_credit_logs
  union all select 'installment repaid', customer_id, ts at time zone 'Asia/Tehran' from pay)
, nx as (
  select ev.event, ev.customer_id, ev.ts,
         (select min(inv.ts) from inv where inv.customer_id = ev.customer_id and inv.on_credit and inv.ts > ev.ts + interval '1 minute') as next_credit
  from ev)
select event, count(*) as events, count(distinct customer_id) as customers,
       count(*) filter (where next_credit < ts + interval '1 day') as credit_buy_within_1d,
       count(*) filter (where next_credit < ts + interval '7 days') as credit_buy_within_7d,
       count(*) filter (where next_credit < ts + interval '30 days') as credit_buy_within_30d,
       round(100.0 * count(*) filter (where next_credit < ts + interval '7 days') / count(*), 1) as within_7d_pct
from nx group by 1 order by 2 desc""",
    "weekly_baseline": INV + """
, act as (select customer_id, min(created_at at time zone 'Asia/Tehran') as act from bnpl_credit_logs group by 1)
, u as (select a.customer_id, extract(epoch from (now() at time zone 'Asia/Tehran') - a.act) / 604800.0 as weeks,
               count(inv.id) filter (where inv.on_credit and inv.ts >= a.act) as nc,
               count(distinct date_trunc('week', inv.ts)) filter (where inv.on_credit and inv.ts >= a.act) as weeks_with_credit_buy
        from act a left join inv on inv.customer_id = a.customer_id group by 1, 2)
select count(*) as users, round(sum(weeks)) as user_weeks, sum(nc) as credit_invoices,
       round(100.0 * sum(weeks_with_credit_buy) / nullif(sum(weeks), 0), 2) as pct_of_weeks_with_a_credit_buy
from u""",
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
    parser.add_argument("--print-sql", action="store_true", help="print the queries instead of running them")
    args = parser.parse_args()
    if args.print_sql:
        for name, sql in QUERIES.items():
            print(f"-- {name}\n{sql.strip()};\n")
        return
    client = MetabaseClient()
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": {}, "errors": {}}
    for name, sql in QUERIES.items():
        if args.only and name not in args.only:
            continue
        started = time.time()
        try:
            out["results"][name] = run(client, sql)
        except (Exception, SystemExit) as exc:  # keep going so one bad query doesn't hide the rest
            out["errors"][name] = str(exc)[:500]
        print(f"done {name} ({time.time() - started:.0f}s)", file=sys.stderr)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
