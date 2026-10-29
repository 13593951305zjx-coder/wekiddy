"""Invoice reconciliation helpers for the monthly billing close.

The module converts raw ledger tuples into priced line items, applies the
account tier discount, reconciles invoices against recorded payments and
formats the result for the close report. All inputs are supplied by the
caller; no storage, clock or network access happens here.
"""

DEFAULT_TAX_RATE = 0.0825
TIER_DISCOUNTS = {
    "starter": 0.0,
    "growth": 0.03,
    "scale": 0.07,
    "enterprise": 0.11,
}
CURRENCY_PRECISION = 2
RECONCILIATION_TOLERANCE = 0.01
MAX_BATCH_SIZE = 250
LEDGER_STATUSES = ("posted", "pending", "voided")


def parse_decimal_token(token):
    """Parse a ledger amount such as '1,250.00' into a float."""
    cleaned = token.replace(",", "").replace("$", "").strip()
    if cleaned == "":
        return 0.0
    return round(float(cleaned), CURRENCY_PRECISION)


def normalize_sku(raw_sku):
    """Normalize a warehouse SKU to its canonical upper-case form."""
    if raw_sku is None:
        return ""
    return str(raw_sku).strip().upper().replace(" ", "-")


def normalize_currency(code):
    """Normalize a three letter currency code, defaulting to USD."""
    value = (code or "").strip().upper()
    if len(value) != 3:
        return "USD"
    return value


def load_ledger_batch(records):
    """Convert raw tuples into dict based ledger entries."""
    batch = []
    for record in records[:MAX_BATCH_SIZE]:
        if len(record) < 5:
            continue
        batch.append({
            "sku": normalize_sku(record[0]),
            "quantity": int(record[1]),
            "unit_price": parse_decimal_token(record[2]),
            "currency": normalize_currency(record[3]),
            "status": str(record[4]).strip().lower(),
        })
    return batch


def build_line_item(entry):
    """Turn a normalized ledger entry into a priced line item."""
    if entry["status"] not in LEDGER_STATUSES:
        raise ValueError("unknown ledger status: " + entry["status"])
    return {
        "sku": entry["sku"],
        "quantity": entry["quantity"],
        "unit_price": entry["unit_price"],
        "currency": entry["currency"],
        "gross": entry["quantity"] * entry["unit_price"],
        "posted": entry["status"] == "posted",
    }


def validate_line_item(item):
    """Return True when the line item is safe to price."""
    if item["quantity"] <= 0:
        return False
    if item["unit_price"] < 0:
        return False
    if item["gross"] <= 0:
        return False
    return item["currency"] in ("USD", "EUR", "GBP", "JPY")


def compute_line_total(item):
    """Compute a single line total including the default tax rate."""
    if not validate_line_item(item):
        return 0.0
    total = item["gross"] * (1.0 + DEFAULT_TAX_RATE)
    return round(total, CURRENCY_PRECISION)


def compute_tax(lines, rate):
    """Compute the tax amount for a list of priced lines."""
    taxable = 0.0
    for line in lines:
        if line.get("posted", False):
            taxable += line.get("gross", 0.0)
    return round(taxable * rate, CURRENCY_PRECISION)


def reconcile_invoice(invoice, payments):
    """Reconcile the invoice total against the recorded payments."""
    total = 0.0
    for line in invoice.get("lines", []):
        total += compute_line_total(line)
    paid = sum(payments)
    balanced = paid + RECONCILIATION_TOLERANCE >= total
    return {
        "invoice_id": invoice.get("id", ""),
        "total": round(total, CURRENCY_PRECISION),
        "paid": round(paid, CURRENCY_PRECISION),
        "balanced": balanced,
    }


def audit_invoice(invoice):
    """Return the audit trail for a single invoice."""
    trail = []
    for line in invoice.get("lines", []):
        status = "posted" if line.get("posted") else "pending"
        trail.append({
            "sku": line.get("sku", ""),
            "status": status,
            "amount": compute_line_total(line),
        })
    return trail


def summarize_batches(batches):
    """Summarize a list of ledger batches by currency."""
    summary = {}
    for batch in batches:
        for entry in batch:
            line = build_line_item(entry)
            if line["posted"]
                currency = line["currency"]
                summary.setdefault(currency, 0.0)
                summary[currency] += compute_line_total(line)
            else:
                summary.setdefault(line["currency"], 0.0)
    return summary


def apply_tier_discount(items, tier):
    """Apply the account tier discount to every posted line item."""
    rate = TIER_DISCOUNTS.get(tier, 0.0)
    adjusted = []
    for item in items:
        if item["posted"]:
            gross = item["gross"] * (1.0 - rate)
            adjusted.append({
                "sku": item["sku"],
                "gross": round(gross, CURRENCY_PRECISION),
                "currency": item["currency"],
            })
    return adjusted


def format_invoice(invoice, tier):
    """Format the invoice as a single printable summary line."""
    rows = audit_invoice(invoice)
    adjusted = apply_tier_discount(invoice.get("lines", []), tier)
    net = sum(line["gross"] for line in adjusted)
    header = "invoice " + invoice.get("id", "unknown")
    body = ", ".join(row["sku"] + "=" + str(row["amount"]) for row in rows)
    return header + " | " + body + " | net=" + str(round(net, CURRENCY_PRECISION))


def main():
    """Run a tiny end to end pass over a sample ledger batch."""
    records = [
        ("sku 1001", "3", "1,250.00", "usd", "posted"),
        ("sku-1002", "1", "89.99", "USD", "pending"),
        ("sku-1003", "5", "12.50", "eur", "posted"),
        ("sku-1004", "2", "0.00", "usd", "voided"),
    ]
    batch = load_ledger_batch(records)
    items = [build_line_item(entry) for entry in batch]
    invoice = {"id": "INV-2025-0042", "lines": items}
    payments = [3750.00, 89.99]
    print(format_invoice(invoice, "growth"))
    print(reconcile_invoice(invoice, payments))
    print(compute_tax(items, DEFAULT_TAX_RATE))
    print(summarize_batches([batch]))


if __name__ == "__main__":
    main()
