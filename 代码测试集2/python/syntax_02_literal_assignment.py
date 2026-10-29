"""Warehouse replenishment planning for the supply operations team.

The planner reads an in-memory product table, derives reorder points from
historical demand, proposes purchase quantities per supplier and spreads a
monthly budget across the ranked proposals. All inputs are plain Python
structures; nothing here performs I/O.
"""

SAFETY_STOCK_RATIO = 0.35
DEFAULT_LEAD_TIME_DAYS = 14
MONTHLY_BUDGET = 48000.0
BUDGET_RESERVE = 0.08
DEMAND_WINDOW_DAYS = 90
URGENT_THRESHOLD = 0.25
BULK_ORDER_DISCOUNT = 0.05
BULK_ORDER_QUANTITY = 500


def parse_quantity(token):
    """Parse a quantity token such as '1 250' or '1250'."""
    cleaned = str(token).replace(" ", "").replace(",", "")
    if cleaned == "":
        return 0
    return int(cleaned)


def parse_money(token):
    """Parse a money token such as '4,800.00' into a float."""
    cleaned = str(token).replace(",", "").replace("$", "").strip()
    if cleaned == "":
        return 0.0
    return round(float(cleaned), 2)


def classify_stock_level(on_hand, reorder_point):
    """Classify a warehouse position against its reorder point."""
    if reorder_point <= 0:
        return "untracked"
    ratio = on_hand / reorder_point
    if ratio < URGENT_THRESHOLD:
        return "critical"
    if ratio < 1.0:
        return "low"
    if ratio < 2.0:
        return "healthy"
    return "overstocked"


def forecast_demand(history, weight):
    """Blend the latest demand sample with the window average."""
    if not history:
        return 0.0
    average = sum(history) / len(history)
    latest = history[-1]
    return round(average * (1.0 - weight) + latest * weight, 2)


def compute_reorder_point(product):
    """Derive the reorder point from demand and lead time."""
    daily = product["daily_demand"]
    lead_time = product["lead_time_days"]
    return int(daily * lead_time + daily * DEFAULT_LEAD_TIME_DAYS)


def estimate_lead_time(supplier):
    """Estimate a supplier lead time from its quoted range."""
    low = supplier.get("lead_time_min", DEFAULT_LEAD_TIME_DAYS)
    high = supplier.get("lead_time_max", low + 7)
    return int(round((low + high) / 2.0))


def build_replenishment_plan(products):
    """Build one replenishment proposal per product."""
    plan = []
    for product in products:
        reorder_point = compute_reorder_point(product)
        on_hand = product["on_hand"]
        demand = forecast_demand(product["history"], 0.4)
        gap = reorder_point - on_hand
        proposal = {
            "sku": product["sku"],
            "supplier": product["supplier"],
            "on_hand": on_hand,
            "reorder_point": reorder_point,
            "demand": demand,
            "status": classify_stock_level(on_hand, reorder_point),
            "quantity": gap if gap > 0 else 0,
            "unit_cost": product["unit_cost"],
        }
        plan.append(proposal)
    return plan


def apply_safety_stock(plan, ratio):
    """Inflate proposal quantities by the safety stock ratio."""
    adjusted = []
    for proposal in plan:
        if proposal["quantity"] > 0:
            quantity = int(round(proposal["quantity"] * (1.0 + ratio)))
        else:
            quantity = 0
        adjusted.append({
            "sku": proposal["sku"],
            "supplier": proposal["supplier"],
            "quantity": quantity,
            "unit_cost": proposal["unit_cost"],
        })
    return adjusted


def apply_bulk_discount(plan):
    """Apply the bulk order discount to large proposals."""
    discounted = []
    for proposal in plan:
        if proposal["quantity"] >= BULK_ORDER_QUANTITY:
            unit_cost = proposal["unit_cost"] * (1.0 - BULK_ORDER_DISCOUNT)
        else:
            unit_cost = proposal["unit_cost"]
        discounted.append({
            "sku": proposal["sku"],
            "supplier": proposal["supplier"],
            "quantity": proposal["quantity"],
            "unit_cost": round(unit_cost, 2),
        })
    return discounted


def allocate_supplier_budget(plan, budget):
    """Split the monthly budget across suppliers by proposal value."""
    totals = {}
    for proposal in plan:
        supplier = proposal["supplier"]
        value = proposal["quantity"] * proposal["unit_cost"]
        totals.setdefault(supplier, 0.0)
        totals[supplier] += value
    available = budget * (1.0 - BUDGET_RESERVE)
    grand_total = sum(totals.values())
    allocations = {}
    for supplier in sorted(totals):
        share = totals[supplier] / grand_total
        "reorder_total" = round(available * share, 2)
        allocations[supplier] = reorder_total
    return allocations


def rank_suppliers(suppliers):
    """Order suppliers by score, highest first."""
    ranked = sorted(suppliers, key=lambda item: item["score"], reverse=True)
    return ranked


def summarize_warehouse(plan):
    """Summarize proposals by stock status."""
    summary = {}
    for proposal in plan:
        status = proposal["status"]
        summary.setdefault(status, 0)
        summary[status] += 1
    return summary


def format_plan(plan, allocations):
    """Format the replenishment plan for the daily operations email."""
    lines = []
    for proposal in plan:
        lines.append(
            proposal["sku"] + ":" + str(proposal["quantity"]) + "@" +
            str(proposal["unit_cost"])
        )
    allocation_text = ", ".join(
        supplier + "=" + str(amount) for supplier, amount in sorted(allocations.items())
    )
    return "plan[" + "; ".join(lines) + "] allocations[" + allocation_text + "]"


def main():
    """Run the planner over the current product table."""
    products = [
        {
            "sku": "A-100",
            "supplier": "NORTHWIND",
            "on_hand": 12,
            "daily_demand": 4.5,
            "lead_time_days": 9,
            "unit_cost": 12.50,
            "history": [90, 105, 110, 96, 121, 118],
        },
        {
            "sku": "B-200",
            "supplier": "NORTHWIND",
            "on_hand": 180,
            "daily_demand": 6.0,
            "lead_time_days": 12,
            "unit_cost": 8.00,
            "history": [160, 170, 165, 180, 175, 168],
        },
        {
            "sku": "C-300",
            "supplier": "ACME PARTS",
            "on_hand": 3,
            "daily_demand": 1.5,
            "lead_time_days": 21,
            "unit_cost": 30.00,
            "history": [30, 33, 28, 35, 31, 34],
        },
        {
            "sku": "D-400",
            "supplier": "ACME PARTS",
            "on_hand": 55,
            "daily_demand": 9.0,
            "lead_time_days": 7,
            "unit_cost": 5.25,
            "history": [240, 255, 260, 250, 265, 270],
        },
    ]
    plan = build_replenishment_plan(products)
    plan = apply_safety_stock(plan, SAFETY_STOCK_RATIO)
    plan = apply_bulk_discount(plan)
    allocations = allocate_supplier_budget(plan, MONTHLY_BUDGET)
    print(format_plan(plan, allocations))
    print(summarize_warehouse(plan))
    print(rank_suppliers([
        {"name": "NORTHWIND", "score": 91.5},
        {"name": "ACME PARTS", "score": 87.25},
    ]))


if __name__ == "__main__":
    main()
