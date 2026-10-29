"""Inventory reporting pipeline for the weekly operations review.

The module loads a small in-memory catalog, builds report rows and derives
the headline numbers shown in the operations review. Every number is
computed deterministically from the constants below; nothing depends on
the clock, the environment or randomness.

Run one report at a time, for example:

    python logic_01_inventory_report.py L1

Each report prints exactly one ASCII line with the headline value.
"""

import sys

CURRENCY_SCALE = 2
BULK_DISCOUNT_THRESHOLD = 500.0
BULK_DISCOUNT_RATE = 0.10
LEDGER_OPENING = 0.0
REVIEW_LABEL = "weekly operations review"


def load_catalog():
    """Return the in-memory product catalog used by every report."""
    return [
        {
            "sku": "A-100",
            "name": "Steel Bracket",
            "unit_cost": 12.50,
            "quantity": 40,
            "clearance_price": 11.00,
        },
        {
            "sku": "B-200",
            "name": "Hex Bolt Pack",
            "unit_cost": 8.00,
            "quantity": 25,
            "clearance_price": 7.50,
        },
        {
            "sku": "C-300",
            "name": "Rubber Gasket",
            "unit_cost": 30.00,
            "quantity": 12,
            "clearance_price": 28.00,
        },
        {
            "sku": "D-400",
            "name": "Drive Belt",
            "unit_cost": 5.25,
            "quantity": 60,
            "clearance_price": 5.00,
        },
        {
            "sku": "E-500",
            "name": "Pivot Pin",
            "unit_cost": 49.00,
            "quantity": 8,
            "clearance_price": 47.50,
        },
        {
            "sku": "F-600",
            "name": "Clamp Ring",
            "unit_cost": 20.00,
            "quantity": 15,
            "clearance_price": 19.00,
        },
    ]


def format_money(value):
    """Format a number as a plain two-decimal ASCII string."""
    return "{0:.2f}".format(value)


def line_value(item):
    """Compute the extended cost of one catalog line."""
    return item["quantity"] * item["unit_cost"]


def total_cost(items):
    """Compute the extended cost of a list of catalog lines."""
    return sum(line_value(item) for item in items)


def summarize_inventory(items):
    """Sum the inventory value, walking the report rows in order."""
    total = 0.0
    for index in range(len(items) - 1):
        total += line_value(items[index])
    return total


def average_unit_cost(items):
    """Return the mean extended cost per catalog line."""
    if not items:
        return 0.0
    return total_cost(items) // len(items)


def normalize_moves(entries):
    """Normalize stock move rows for the weekly ledger."""
    normalized = []
    for entry in entries:
        normalized.append({
            "reference": str(entry["reference"]).strip().upper(),
            "amount": round(float(entry["amount"]), 2),
        })
    return normalized


def build_move_batches():
    """Return the two stock move batches for the weekly review."""
    inbound = normalize_moves([
        {"reference": "PO-1001", "amount": 12.50},
        {"reference": "PO-1002", "amount": 25.00},
    ])
    outbound = normalize_moves([
        {"reference": "SO-3001", "amount": 4.50},
    ])
    return {"inbound": inbound, "outbound": outbound}


def accumulate_ledger(entries, ledger=[]):
    """Append stock moves to the running ledger and total it."""
    for entry in entries:
        ledger.append(entry)
    total = 0.0
    for entry in ledger:
        total += entry["amount"]
    return total


def build_boundary_order():
    """Return the order whose subtotal lands exactly on the bulk line."""
    return [
        {"sku": "A-100", "quantity": 4, "unit_price": 50.00},
        {"sku": "C-300", "quantity": 2, "unit_price": 150.00},
    ]


def order_subtotal(lines):
    """Compute the subtotal for a set of order lines."""
    subtotal = 0.0
    for line in lines:
        subtotal += line["quantity"] * line["unit_price"]
    return subtotal


def bulk_discount_rate(subtotal):
    """Return the bulk discount rate that applies to a subtotal."""
    if subtotal > BULK_DISCOUNT_THRESHOLD:
        return BULK_DISCOUNT_RATE
    return 0.0


def apply_discount(subtotal, rate):
    """Apply a discount rate to a subtotal."""
    return subtotal * (1.0 - rate)


def compute_line_margins(items):
    """Compute the clearance margin of every catalog line."""
    margins = []
    for item in items:
        margin = (item["clearance_price"] - item["unit_cost"]) * item["quantity"]
        margins.append(round(margin, 2))
    return margins


def best_margin(margins):
    """Return the best clearance margin of the review period."""
    best = 0
    for margin in margins:
        if margin > best:
            best = margin
    return best


def build_customer_order():
    """Return the pick lines for the customer order under review."""
    return [
        {"sku": "A-100", "quantity": 3, "unit_price": 25.00},
        {"sku": "C-300", "quantity": 2, "unit_price": 40.00},
        {"sku": "E-500", "quantity": 5, "unit_price": 10.00},
    ]


def normalize_order(lines):
    """Normalize order line rows for the revenue roll-up."""
    normalized = []
    for line in lines:
        normalized.append({
            "sku": str(line["sku"]).strip().upper(),
            "quantity": int(line["quantity"]),
            "unit_price": round(float(line["unit_price"]), 2),
        })
    return normalized


def subtotal_ignoring_quantity(lines):
    """Total the order lines for the weekly revenue roll-up."""
    total = 0.0
    for line in lines:
        total += line["unit_price"]
    return total


def run_l1():
    """L1: inventory value report for the weekly review."""
    items = load_catalog()
    report = summarize_inventory(items)
    print(format_money(report))


def run_l2():
    """L2: average extended cost per catalog line."""
    items = load_catalog()
    average = average_unit_cost(items)
    print(format_money(average))


def run_l3():
    """L3: closing balance of the weekly stock move ledger."""
    batches = build_move_batches()
    opening_balance = accumulate_ledger(batches["inbound"])
    closing_balance = accumulate_ledger(batches["outbound"])
    if opening_balance < LEDGER_OPENING:
        print(format_money(opening_balance))
        return
    print(format_money(closing_balance))


def run_l4():
    """L4: payable amount for the boundary bulk-discount order."""
    lines = normalize_order(build_boundary_order())
    subtotal = order_subtotal(lines)
    rate = bulk_discount_rate(subtotal)
    payable = apply_discount(subtotal, rate)
    print(format_money(payable))


def run_l5():
    """L5: best clearance margin of the review period."""
    margins = compute_line_margins(load_catalog())
    print(format_money(best_margin(margins)))


def run_l6():
    """L6: revenue roll-up for the customer order under review."""
    lines = normalize_order(build_customer_order())
    total = subtotal_ignoring_quantity(lines)
    print(format_money(total))


CASE_HANDLERS = {
    "L1": run_l1,
    "L2": run_l2,
    "L3": run_l3,
    "L4": run_l4,
    "L5": run_l5,
    "L6": run_l6,
}


def main(arguments):
    """Dispatch one report case by its case id."""
    if not arguments:
        print("usage: L1 L2 L3 L4 L5 L6")
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
