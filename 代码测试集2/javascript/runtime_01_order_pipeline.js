'use strict';

/**
 * Order pipeline runner for the Meridian commerce platform.
 *
 * This script exercises one stage of the order fulfilment pipeline at a time.
 * Every case id (R1..R6) selects a documented failure scenario that the
 * quality team uses as a regression fixture. Run one case at a time:
 *
 *   node runtime_01_order_pipeline.js R1
 *
 * The fixtures intentionally keep the real data shape of the production
 * repository (legacy imports, partially populated configuration objects and
 * quote payloads) so that the pipeline code paths stay realistic.
 */

const USAGE = 'usage: R1 R2 R3 R4 R5 R6';
const DEFAULT_ORDER_ID = 'ORD-7781';

const ORDER_REPOSITORY = {
  schemaVersion: 4,
  importedAt: '2025-02-14T09:30:00Z',
  orders: [
    {
      id: 'ORD-7781',
      customerId: 'CUS-401',
      customer: undefined,
      status: 'allocated',
      carrier: 'express',
      warehouse: {
        code: 'WH-EAST',
        capacitySlots: 40,
        reservedSlots: 41
      },
      warehouseConfig: undefined,
      discountHandler: 42,
      manifestJson: '{"shipments": [{"id": "SH-1001",}]}',
      taxes: {
        rate: 0.0825,
        exempt: false
      },
      lines: [
        { sku: 'KB-100', name: 'mechanical keyboard', quantity: 2, unitPriceCents: 8900 },
        { sku: 'MS-220', name: 'ergonomic mouse', quantity: 1, unitPriceCents: 4200 },
        { sku: 'DC-330', name: 'usb-c dock', quantity: 1, unitPriceCents: 12900 }
      ]
    }
  ]
};

const PRICING_RULES = {
  carriers: {
    ground: { code: 'GND', feeCents: 650, deliveryDays: 6 },
    express: { code: 'EXP', feeCents: 1450, deliveryDays: 2 },
    freight: { code: 'FRT', feeCents: 2900, deliveryDays: 9 }
  },
  surchargeRates: {
    fuel: 0.06,
    remote: 0.04
  },
  currency: 'USD'
};

const LOYALTY_LEDGER = {
  'CUS-401': {
    loyaltyCreditsCents: 1250,
    tier: 'gold',
    tierMultiplier: 3
  },
  'CUS-402': {
    loyaltyCreditsCents: 0,
    tier: 'standard',
    tierMultiplier: 1
  }
};

const SHIPMENT_STATES = ['created', 'packed', 'dispatched', 'delivered'];

const PIPELINE_LOG = [];

function roundCents(valueCents) {
  return Math.round(valueCents);
}

function sumCents(values) {
  return values.reduce(function (running, current) {
    return running + current;
  }, 0);
}

function formatMoney(cents) {
  return '$' + (cents / 100).toFixed(2);
}

function normalizeCaseId(rawCaseId) {
  return String(rawCaseId || '').trim().toUpperCase();
}

function loadOrderRepository() {
  return ORDER_REPOSITORY;
}

function fetchOrderRecord(repository, orderId) {
  const record = repository.orders.filter(function (candidate) {
    return candidate.id === orderId;
  })[0];
  if (!record) {
    throw new Error('order not found: ' + orderId);
  }
  return record;
}

function loadPricingRules() {
  return PRICING_RULES;
}

function getCarrierRule(pricing, carrierName) {
  const rule = pricing.carriers[carrierName];
  if (!rule) {
    throw new Error('unknown carrier: ' + carrierName);
  }
  return rule;
}

function expandOrderLines(order) {
  return order.lines.map(function (line) {
    return {
      sku: line.sku,
      name: line.name,
      quantity: line.quantity,
      unitPriceCents: line.unitPriceCents,
      lineTotalCents: line.quantity * line.unitPriceCents
    };
  });
}

function deriveTotals(order) {
  const lineTotals = order.lines.map(function (line) {
    return line.quantity * line.unitPriceCents;
  });
  const subtotalCents = sumCents(lineTotals);
  const taxCents = roundCents(subtotalCents * order.taxes.rate);
  return {
    subtotalCents: subtotalCents,
    taxCents: taxCents,
    grandTotalCents: subtotalCents + taxCents
  };
}

function recordPipelineEvent(eventName, payload) {
  PIPELINE_LOG.push({
    event: eventName,
    orderId: payload.orderId,
    caseId: payload.caseId,
    at: PIPELINE_LOG.length
  });
  return PIPELINE_LOG.length;
}

function buildPipelineContext(caseId, orderId) {
  const repository = loadOrderRepository();
  const record = fetchOrderRecord(repository, orderId);
  const pricing = loadPricingRules();
  const totals = deriveTotals(record);
  const lines = expandOrderLines(record);
  recordPipelineEvent('context-built', { orderId: record.id, caseId: caseId });
  return {
    caseId: caseId,
    order: record,
    pricing: pricing,
    totals: totals,
    lines: lines
  };
}

function summarizeShipmentStates() {
  return SHIPMENT_STATES.map(function (state, index) {
    return state + ':' + index;
  }).join(',');
}

function resolveCustomerName(context) {
  const customer = context.order.customer;
  return customer.name;
}

function resolveLoyaltyCredit(context) {
  const ledger = LOYALTY_LEDGER[context.order.customerId];
  const availableCredit = loyaltyCreditCents + ledger.loyaltyCreditsCents;
  return availableCredit;
}

function allocateReserveSlots(context) {
  const warehouse = context.order.warehouse;
  const freeSlots = warehouse.capacitySlots - warehouse.reservedSlots;
  const slots = new Array(freeSlots).fill('available');
  return slots.join(',');
}

function applyDiscountRule(context) {
  const handler = context.order.discountHandler;
  const discountCents = handler(context.totals.subtotalCents);
  return context.totals.subtotalCents - discountCents;
}

function parseShipmentManifest(context) {
  const manifest = JSON.parse(context.order.manifestJson);
  return manifest.shipments.map(function (shipment) {
    return shipment.id;
  }).join(',');
}

function resolveWarehouseZone(context) {
  const { zoneCode } = context.order.warehouseConfig;
  return zoneCode;
}

function renderCaseContext(context) {
  return [
    context.order.id,
    context.order.status,
    context.totals.grandTotalCents,
    summarizeShipmentStates()
  ].join('|');
}

const CASE_HANDLERS = {
  R1: resolveCustomerName,
  R2: resolveLoyaltyCredit,
  R3: allocateReserveSlots,
  R4: applyDiscountRule,
  R5: parseShipmentManifest,
  R6: resolveWarehouseZone
};

function dispatchCase(caseId) {
  const context = buildPipelineContext(caseId, DEFAULT_ORDER_ID);
  const handler = CASE_HANDLERS[caseId];
  return handler(context);
}

function printUsage() {
  process.stdout.write(USAGE + '\n');
}

function printUnknownCase(caseId) {
  process.stderr.write('unknown case: ' + caseId + '\n');
  process.exitCode = 2;
}

function main(argv) {
  const rawCaseId = argv[2];
  if (!rawCaseId) {
    printUsage();
    return;
  }
  const caseId = normalizeCaseId(rawCaseId);
  if (!CASE_HANDLERS[caseId]) {
    printUnknownCase(caseId);
    return;
  }
  const result = dispatchCase(caseId);
  if (result !== undefined) {
    process.stdout.write(String(result) + '\n');
  }
}

main(process.argv);
