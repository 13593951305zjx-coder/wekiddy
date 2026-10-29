"""Order and inventory service pipeline for the fulfillment desk.

This module walks an order through the same sequence of steps the real
fulfillment service performs: it loads the catalog, checks warehouse
stock, prices the order lines, resolves the customer record and builds a
dispatch plan. All data is held in memory; no storage, network, clock or
randomness is involved.

Run one scenario at a time, for example:

    python runtime_01_service_pipeline.py R1

The scenarios are deliberately broken so that a real exception escapes
from the helper that contains the defect. That lets the traceback point at
a stable line instead of at the command line entry point.
"""

import sys

TAX_RATE = 0.0875
FREE_SHIPPING_THRESHOLD = 75.0
STANDARD_SHIPPING_FEE = 6.95
EXPRESS_SHIPPING_FEE = 14.50
MAX_LINE_QUANTITY = 500
VALID_TIERS = ("standard", "silver", "gold", "platinum")
PRIORITY_TIERS = ("gold", "platinum")
CASE_IDS = ("R1", "R2", "R3", "R4", "R5", "R6")


def normalize_sku(raw_sku):
    """Normalize a SKU exactly as it arrives from the order channel."""
    return str(raw_sku).strip().upper().replace(" ", "-")


def load_catalog():
    """Return the in-memory product catalog keyed by SKU."""
    rows = [
        ("sku 1001", "Steel Bracket", 12.50, 40),
        ("sku 1002", "Hex Bolt Pack", 8.00, 120),
        ("sku 1003", "Rubber Gasket", 3.25, 0),
        ("sku 1004", "Drive Belt", 21.75, 15),
        ("sku 1005", "Pivot Pin", 4.50, 60),
    ]
    catalog = {}
    for raw_sku, name, unit_price, available in rows:
        sku = normalize_sku(raw_sku)
        catalog[sku] = {
            "sku": sku,
            "name": name,
            "unit_price": unit_price,
            "available": available,
        }
    return catalog


def load_warehouse_rows():
    """Return the warehouse stock rows in bin walk order."""
    return [
        {"bin": "A-01", "sku": "SKU-1001", "quantity": 40},
        {"bin": "A-02", "sku": "SKU-1002", "quantity": 120},
        {"bin": "B-01", "sku": "SKU-1004", "quantity": 15},
        {"bin": "B-02", "sku": "SKU-1005", "quantity": 60},
    ]


def load_pricing_table():
    """Return the contracted price bands keyed by SKU."""
    return {
        "SKU-1001": {"band": "A", "multiplier": 1.00},
        "SKU-1002": {"band": "A", "multiplier": 1.05},
        "SKU-1004": {"band": "B", "multiplier": 1.10},
    }


def load_order(case_id):
    """Return a fresh order document tagged with its scenario id."""
    return {
        "order_id": "ORD-2025-04817",
        "case_id": case_id,
        "tier": "gold",
        "lines": [
            {"sku": "SKU-1001", "quantity": 4, "raw_quantity": "4"},
            {"sku": "SKU-1002", "quantity": 10, "raw_quantity": "10"},
            {"sku": "SKU-1004", "quantity": 2, "raw_quantity": "2"},
        ],
        "customer": {
            "account_id": "ACC-7712",
            "display_name": None,
            "tier": "gold",
            "shipping": {
                "city": "Portland",
                "region": "OR",
                "postal_code": "97201",
            },
        },
        "warehouse_index": 0,
    }


def find_product(catalog, sku):
    """Look up a product, falling back to an unknown placeholder."""
    if sku in catalog:
        return catalog[sku]
    return {
        "sku": sku,
        "name": "Unknown Product",
        "unit_price": 0.0,
        "available": 0,
    }


def check_availability(product, quantity):
    """Return True when the warehouse can cover the requested quantity."""
    if quantity <= 0:
        return False
    if quantity > MAX_LINE_QUANTITY:
        return False
    return product["available"] >= quantity


def pick_primary_warehouse(rows, index):
    """Return the warehouse row that owns the primary pick slot."""
    row = rows[index]
    return row


def build_fulfillment_plan(order, catalog):
    """Assemble the fulfillment plan for an order."""
    rows = load_warehouse_rows()
    primary = pick_primary_warehouse(rows, order["warehouse_index"])
    plan = {
        "order_id": order["order_id"],
        "primary_bin": primary["bin"],
        "picks": [],
    }
    for line in order["lines"]:
        product = find_product(catalog, line["sku"])
        if check_availability(product, line["quantity"]):
            plan["picks"].append({
                "sku": line["sku"],
                "bin": primary["bin"],
                "quantity": line["quantity"],
            })
    return plan


def resolve_price_band(catalog, sku):
    """Resolve the contracted price band for one order line."""
    pricing = load_pricing_table()
    band = pricing[sku]
    product = find_product(catalog, sku)
    return {
        "sku": sku,
        "band": band["band"],
        "unit_price": round(product["unit_price"] * band["multiplier"], 2),
    }


def price_order_lines(order, catalog):
    """Price every line of an order through the pricing table."""
    priced = []
    for line in order["lines"]:
        band = resolve_price_band(catalog, line["sku"])
        priced.append({
            "sku": line["sku"],
            "quantity": line["quantity"],
            "unit_price": band["unit_price"],
            "band": band["band"],
        })
    return priced


def build_metric_lines(order):
    """Build the value rows used by the order metrics report."""
    rows = []
    for line in order["lines"]:
        rows.append({
            "sku": line["sku"],
            "quantity": line["quantity"],
            "value": line["quantity"] * 10.0,
        })
    return rows


def average_line_value(lines):
    """Return the average line value of an order."""
    total = 0.0
    for line in lines:
        total += line["value"]
    return total / len(lines)


def compute_order_metrics(order):
    """Compute the headline metrics for an order."""
    rows = build_metric_lines(order)
    average = average_line_value(rows)
    return {
        "order_id": order["order_id"],
        "line_count": len(rows),
        "average_line_value": round(average, 2),
    }


def normalize_customer_tier(tier):
    """Normalize a customer tier, defaulting to standard."""
    value = str(tier or "").strip().lower()
    if value not in VALID_TIERS:
        return "standard"
    return value


def resolve_customer(order):
    """Return the customer record attached to an order."""
    return order["customer"]


def format_customer_name(customer):
    """Format a customer display name for the dispatch label."""
    tier = normalize_customer_tier(customer.get("tier"))
    name = customer["display_name"].strip()
    return tier.upper() + ": " + name


def prepare_dispatch_label(order):
    """Build the dispatch label for the receiving customer."""
    customer = resolve_customer(order)
    name = format_customer_name(customer)
    shipping = customer["shipping"]
    return {
        "label": name,
        "city": shipping["city"],
        "region": shipping["region"],
    }


def describe_quantity(sku, quantity):
    """Describe a line quantity for the packing slip."""
    description = "qty=" + quantity
    return sku + " " + description


def summarize_line(line):
    """Summarize one order line for the packing slip."""
    return describe_quantity(line["sku"], line["quantity"])


def describe_order_summary(order):
    """Summarize every line of an order for the packing slip."""
    summaries = []
    for line in order["lines"]:
        summaries.append(summarize_line(line))
    return " | ".join(summaries)


def normalize_quantity_token(raw_quantity):
    """Normalize a raw quantity token coming from the order channel."""
    return str(raw_quantity).strip()


def parse_quantity(raw_quantity):
    """Parse a raw quantity token into an integer."""
    token = normalize_quantity_token(raw_quantity)
    return int(token)


def validate_dispatch(order):
    """Validate quantities before the order leaves the warehouse."""
    quantities = []
    for line in order["lines"]:
        quantities.append(parse_quantity(line["raw_quantity"]))
    if sum(quantities) > MAX_LINE_QUANTITY:
        return False
    return True


def compute_shipping_fee(order):
    """Compute the shipping fee for an order."""
    order_value = 0.0
    for line in order["lines"]:
        order_value += line["quantity"] * 10.0
    if order_value >= FREE_SHIPPING_THRESHOLD:
        return 0.0
    if order["tier"] in PRIORITY_TIERS:
        return EXPRESS_SHIPPING_FEE
    return STANDARD_SHIPPING_FEE


def compute_order_total(order):
    """Compute the order total including shipping."""
    subtotal = 0.0
    for line in order["lines"]:
        subtotal += line["quantity"] * 10.0
    return round(subtotal * (1.0 + TAX_RATE) + compute_shipping_fee(order), 2)


def build_scenario_r1():
    """Scenario R1: the order is routed past the last warehouse row."""
    order = load_order("R1")
    rows = load_warehouse_rows()
    order["warehouse_index"] = len(rows)
    return order


def build_scenario_r2():
    """Scenario R2: a newly listed SKU is missing from the price table."""
    order = load_order("R2")
    order["lines"][2]["sku"] = "SKU-1005"
    return order


def build_scenario_r3():
    """Scenario R3: the order arrives with every line removed."""
    order = load_order("R3")
    order["lines"] = []
    return order


def build_scenario_r6():
    """Scenario R6: the channel sends a formatted quantity string."""
    order = load_order("R6")
    order["lines"][2]["raw_quantity"] = "12,500"
    return order


def run_r1():
    """Run scenario R1 and print the fulfillment plan."""
    catalog = load_catalog()
    order = build_scenario_r1()
    plan = build_fulfillment_plan(order, catalog)
    print(plan)


def run_r2():
    """Run scenario R2 and print the priced order lines."""
    catalog = load_catalog()
    order = build_scenario_r2()
    priced = price_order_lines(order, catalog)
    print(priced)


def run_r3():
    """Run scenario R3 and print the order metrics."""
    order = build_scenario_r3()
    metrics = compute_order_metrics(order)
    print(metrics)


def run_r4():
    """Run scenario R4 and print the dispatch label."""
    order = load_order("R4")
    label = prepare_dispatch_label(order)
    print(label)


def run_r5():
    """Run scenario R5 and print the packing slip summary."""
    order = load_order("R5")
    summary = describe_order_summary(order)
    print(summary)


def run_r6():
    """Run scenario R6 and print the dispatch validation result."""
    order = build_scenario_r6()
    result = validate_dispatch(order)
    print(result)


CASE_HANDLERS = {
    "R1": run_r1,
    "R2": run_r2,
    "R3": run_r3,
    "R4": run_r4,
    "R5": run_r5,
    "R6": run_r6,
}


def main(arguments):
    """Dispatch one runtime scenario by its case id."""
    if not arguments:
        print("usage: R1 R2 R3 R4 R5 R6")
        return 0
    case_id = arguments[0]
    handler = CASE_HANDLERS.get(case_id)
    if handler is None:
        sys.stderr.write("unknown case: " + case_id + "\n")
        return 2
    handler()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
