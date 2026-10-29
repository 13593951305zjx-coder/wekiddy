'use strict';

/**
 * Warehouse fulfillment planner for the Northwind supply chain demo.
 *
 * The script builds a dispatch plan for a fixed sample order, prices the
 * shipment and renders a plain text invoice summary for the operations
 * dashboard. Every helper is pure so the planners can be unit tested in
 * isolation by the fulfilment team.
 */

const CARRIER_RULES = {
  ground: {
    code: 'GND',
    baseFeeCents: 650,
    perKgCents: 45,
    maxDays: 6
  },
  express: {
    code: 'EXP',
    baseFeeCents: 1450,
    perKgCents: 80,
    maxDays: 2
  },
  freight: {
    code: 'FRT',
    baseFeeCents: 2900,
    perKgCents: 32,
    maxDays: 9
  }
};

const WAREHOUSE_ZONES = [
  { code: 'WH-EAST', postalPrefixes: ['10', '11', '12'], capacityKg: 4200 },
  { code: 'WH-CENTRAL', postalPrefixes: ['45', '46', '47'], capacityKg: 3100 },
  { code: 'WH-WEST', postalPrefixes: ['80', '81', '90'], capacityKg: 2600 }
];

const SAMPLE_ORDER = {
  id: 'ORD-2024-1042',
  customer: {
    name: 'Avery Montague',
    postalCode: '45120',
    tier: 'gold'
  },
  lines: [
    { sku: 'KB-100', name: 'mechanical keyboard', quantity: 2, unitPriceCents: 8900, weightKg: 0.9 },
    { sku: 'MS-220', name: 'ergonomic mouse', quantity: 1, unitPriceCents: 4200, weightKg: 0.2 },
    { sku: 'DC-330', name: 'usb-c dock', quantity: 1, unitPriceCents: 12900, weightKg: 0.6 },
    { sku: 'CB-040', name: 'braided cable', quantity: 3, unitPriceCents: 1150, weightKg: 0.1 }
  ],
  carrier: 'express',
  taxRate: 0.0825
};

const TIER_DISCOUNTS = {
  standard: 0,
  silver: 0.02,
  gold: 0.05,
  platinum: 0.08
};

const DELIVERY_PROMISES = {
  ground: 'ground service',
  express: 'priority express',
  freight: 'consolidated freight'
};

function roundCents(valueCents) {
  return Math.round(valueCents);
}

function sumCents(values) {
  return values.reduce(function (running, current) {
    return running + current;
  }, 0);
}

function getCarrierRule(carrierName) {
  const rule = CARRIER_RULES[carrierName];
  if (!rule) {
    throw new Error('unknown carrier: ' + carrierName);
  }
  return rule;
}

function computeLineTotalCents(line) {
  return roundCents(line.quantity * line.unitPriceCents);
}

function computeSubtotalCents(lines) {
  return sumCents(lines.map(computeLineTotalCents));
}

function computeWeightKg(lines) {
  return lines.reduce(function (running, line) {
    return running + line.quantity * line.weightKg;
  }, 0);
}

function applyTierDiscount(subtotalCents, customerTier) {
  const discount = TIER_DISCOUNTS[customerTier] || 0;
  return roundCents(subtotalCents * (1 - discount));
}

function applyTaxCents(discountedSubtotalCents, taxRate) {
  return roundCents(discountedSubtotalCents * taxRate);
}

function computeFreightCents(carrierRule, weightKg) {
  const billableKg = Math.max(1, Math.ceil(weightKg));
  return carrierRule.baseFeeCents + billableKg * carrierRule.perKgCents;
}

function pickWarehouse(zones, postalCode) {
  const prefix = postalCode.slice(0, 2);
  for (let index = 0; index < zones.length; index += 1) {
    const zone = zones[index];
    if (zone.postalPrefixes.indexOf(prefix) !== -1) {
      return zone;
    }
  }
  return zones[zones.length - 1];
}

function estimateDeliveryDays(carrierRule, warehouse) {
  const baseDays = carrierRule.maxDays;
  const remoteDays = warehouse.code === 'WH-WEST' ? 1 : 0;
  return baseDays + remoteDays;
}

function buildDispatchQueue(order, warehouse) {
  return order.lines.map(function (line) {
    return {
      sku: line.sku,
      quantity: line.quantity,
      source: warehouse.code
    };
  });
}

function describeCarrier(carrierCode) {
  const names = DELIVERY_PROMISES;
  const key = Object.keys(names).filter(function (candidate) {
    return CARRIER_RULES[candidate].code === carrierCode;
  })[0];
  return names[key] || 'standard service';
}

function planFulfillment(order) {
  const carrierRule = getCarrierRule(order.carrier);
  const warehouse = pickWarehouse(
    WAREHOUSE_ZONES,
    order.customer.postalCode
  const weightKg = computeWeightKg(order.lines);
  const subtotalCents = computeSubtotalCents(order.lines);
  const discountedCents = applyTierDiscount(subtotalCents, order.customer.tier);
  const taxCents = applyTaxCents(discountedCents, order.taxRate);
  const freightCents = computeFreightCents(carrierRule, weightKg);
  return {
    orderId: order.id,
    warehouseCode: warehouse.code,
    carrierCode: carrierRule.code,
    weightKg: weightKg,
    subtotalCents: subtotalCents,
    discountedCents: discountedCents,
    taxCents: taxCents,
    freightCents: freightCents,
    totalCents: discountedCents + taxCents + freightCents,
    deliveryDays: estimateDeliveryDays(carrierRule, warehouse)
  };
}

function summarizeDispatch(plan) {
  const queue = buildDispatchQueue(SAMPLE_ORDER, { code: plan.warehouseCode });
  return {
    orderId: plan.orderId,
    warehouseCode: plan.warehouseCode,
    carrierCode: plan.carrierCode,
    carrierLabel: describeCarrier(plan.carrierCode),
    lineCount: queue.length,
    weightKg: plan.weightKg,
    totalCents: plan.totalCents,
    deliveryDays: plan.deliveryDays
  };
}

function formatMoney(cents) {
  return '$' + (cents / 100).toFixed(2);
}

function renderInvoice(order, plan) {
  const rows = order.lines.map(function (line) {
    return line.name + ' x' + line.quantity + ' = ' + formatMoney(computeLineTotalCents(line));
  });
  rows.push('subtotal: ' + formatMoney(plan.subtotalCents));
  rows.push('discount: -' + formatMoney(plan.subtotalCents - plan.discountedCents));
  rows.push('tax: ' + formatMoney(plan.taxCents));
  rows.push('freight: ' + formatMoney(plan.freightCents));
  rows.push('total: ' + formatMoney(plan.totalCents));
  return rows.join('\n');
}

function renderDispatchSummary(summary) {
  return [
    'order ' + summary.orderId,
    'warehouse ' + summary.warehouseCode,
    'carrier ' + summary.carrierLabel,
    'lines ' + summary.lineCount,
    'weight ' + summary.weightKg.toFixed(2) + ' kg',
    'delivery ' + summary.deliveryDays + ' day(s)',
    'amount ' + formatMoney(summary.totalCents)
  ].join(' | ');
}

function main() {
  const plan = planFulfillment(SAMPLE_ORDER);
  const summary = summarizeDispatch(plan);
  console.log(renderDispatchSummary(summary));
  console.log(renderInvoice(SAMPLE_ORDER, plan));
}

main();
