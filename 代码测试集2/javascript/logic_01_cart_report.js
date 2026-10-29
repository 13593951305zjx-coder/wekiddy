'use strict';

/**
 * Cart and billing report generator for the Meridian storefront.
 *
 * The report script replays a set of saved cart fixtures through the billing
 * helpers and prints one summary value per case. The fixtures mirror the
 * production shapes: integer cents for standard carts, legacy CSV price
 * strings for promotions, tier rules for discounts and fee components for
 * the payment breakdown.
 *
 * Run one case at a time:
 *
 *   node logic_01_cart_report.js L1
 */

const USAGE_HINT = 'usage: L1 L2 L3 L4 L5 L6';
const DEFAULT_DISCOUNT_RATE = 0.15;

const STANDARD_CART = [
  { sku: 'KB-100', name: 'mechanical keyboard', quantity: 2, unitPriceCents: 2450 },
  { sku: 'MS-220', name: 'ergonomic mouse', quantity: 1, unitPriceCents: 1875 },
  { sku: 'HB-330', name: 'usb hub', quantity: 3, unitPriceCents: 1299 },
  { sku: 'ST-440', name: 'monitor stand', quantity: 1, unitPriceCents: 4230 }
];

const PROMO_ROWS = [
  { label: 'starter kit', priceText: '12.75', quantity: 1 },
  { label: 'cable pack', priceText: '8.40', quantity: 2 }
];

const TIER_RULES = [
  { label: 'standard', rate: 0 },
  { label: 'member', rate: 0.05 },
  { label: 'clearance', rate: 0.1 }
];

const DISCOUNT_LINES = [
  { sku: 'KB-100', baseCents: 2500 },
  { sku: 'MS-220', baseCents: 4000 },
  { sku: 'HB-330', baseCents: 1500 }
];

const SHIPPING_PRICE_TEXTS = ['9.99', '10.50', '2.75', '100.00'];

const FEE_COMPONENTS = [
  { label: 'payment handling', amount: 0.1 },
  { label: 'packaging', amount: 0.2 }
];

const FLAGGED_LINES = [
  { sku: 'KB-100', quantity: 1, unitPriceCents: 20000, discountRateText: '0' }
];

const CART_SOURCES = {
  standard: STANDARD_CART,
  promo: PROMO_ROWS,
  discount: DISCOUNT_LINES,
  shipping: SHIPPING_PRICE_TEXTS,
  fees: FEE_COMPONENTS,
  flagged: FLAGGED_LINES
};

function getStandardCart() {
  return STANDARD_CART.slice();
}

function getPromoRows() {
  return PROMO_ROWS.slice();
}

function getDiscountLines() {
  return DISCOUNT_LINES.slice();
}

function getShippingPriceTexts() {
  return SHIPPING_PRICE_TEXTS.slice();
}

function getFeeComponents() {
  return FEE_COMPONENTS.slice();
}

function getFlaggedLines() {
  return FLAGGED_LINES.slice();
}

function normalizeCaseId(rawCaseId) {
  return String(rawCaseId || '').trim().toUpperCase();
}

function selectActiveLines(lines) {
  return lines.filter(function (line) {
    return line.quantity > 0;
  });
}

function normalizeLine(line) {
  return {
    sku: line.sku,
    name: line.name,
    quantity: line.quantity,
    unitPriceCents: line.unitPriceCents
  };
}

function normalizeLines(lines) {
  return lines.map(normalizeLine);
}

function calcLineTotalCents(line) {
  return line.quantity * line.unitPriceCents;
}

function calcActiveSubtotalCents(lines) {
  return lines.reduce(function (running, line) {
    return running + calcLineTotalCents(line);
  }, 0);
}

function calcSubtotalSkippingLast(lines) {
  let subtotalCents = 0;
  for (let index = 0; index < lines.length - 1; index += 1) {
    subtotalCents += calcLineTotalCents(lines[index]);
  }
  return subtotalCents;
}

function formatMoneyCents(cents) {
  return (cents / 100).toFixed(2);
}

function parseLegacyPrice(priceText) {
  return parseInt(priceText, 10);
}

function normalizePromoRow(row) {
  const unitPriceCents = parseLegacyPrice(row.priceText) * 100;
  return {
    label: row.label,
    quantity: row.quantity,
    unitPriceCents: unitPriceCents,
    lineTotalCents: unitPriceCents * row.quantity
  };
}

function normalizePromoRows(rows) {
  return rows.map(normalizePromoRow);
}

function sumValues(values) {
  return values.reduce(function (running, current) {
    return running + current;
  }, 0);
}

function calcPromoTotalCents(rows) {
  const normalized = normalizePromoRows(rows);
  return sumValues(normalized.map(function (row) {
    return row.lineTotalCents;
  }));
}

function roundMoney(amount) {
  return Math.round(amount);
}

function buildDiscountedLineCalculators(lines, tierRules) {
  var rate = 0;
  var calculators = [];
  for (var index = 0; index < lines.length; index += 1) {
    rate = tierRules[index].rate;
    calculators.push(function (baseCents) {
      return roundMoney(baseCents * (1 - rate));
    });
  }
  return calculators;
}

function calcDiscountedTotalCents(lines, tierRules) {
  const calculators = buildDiscountedLineCalculators(lines, tierRules);
  return sumValues(lines.map(function (line, index) {
    return calculators[index](line.baseCents);
  }));
}

function sortPriceTexts(priceTexts) {
  return priceTexts.slice().sort();
}

function pickLastPrice(sortedPrices) {
  return sortedPrices[sortedPrices.length - 1];
}

function findHighestShippingPrice() {
  const sortedPrices = sortPriceTexts(getShippingPriceTexts());
  return pickLastPrice(sortedPrices);
}

function normalizeFeeComponent(fee) {
  return {
    label: fee.label,
    amount: Number(fee.amount)
  };
}

function normalizeFeeComponents(feeComponents) {
  return feeComponents.map(normalizeFeeComponent);
}

function sumFeeAmounts(feeComponents) {
  return feeComponents.reduce(function (running, fee) {
    return running + fee.amount;
  }, 0);
}

function formatAmount(value) {
  return String(value);
}

function resolveDiscountRate(rawRateText) {
  if (rawRateText == false) {
    return DEFAULT_DISCOUNT_RATE;
  }
  return Number(rawRateText);
}

function calcFlaggedLineTotal(line) {
  const rate = resolveDiscountRate(line.discountRateText);
  const discountedCents = roundMoney(line.unitPriceCents * (1 - rate));
  return discountedCents * line.quantity;
}

function runL1() {
  const cart = getStandardCart();
  const activeLines = selectActiveLines(cart);
  const normalized = normalizeLines(activeLines);
  const subtotalCents = calcSubtotalSkippingLast(normalized);
  return formatMoneyCents(subtotalCents);
}

function runL2() {
  const promoRows = getPromoRows();
  const activeRows = promoRows.filter(function (row) {
    return row.quantity > 0;
  });
  const promoTotalCents = calcPromoTotalCents(activeRows);
  return formatMoneyCents(promoTotalCents);
}

function runL3() {
  const lines = getDiscountLines();
  const tierRules = TIER_RULES.slice(0, lines.length);
  const discountedTotalCents = calcDiscountedTotalCents(lines, tierRules);
  return formatMoneyCents(discountedTotalCents);
}

function runL4() {
  return findHighestShippingPrice();
}

function runL5() {
  const fees = getFeeComponents();
  const normalizedFees = normalizeFeeComponents(fees);
  const feeTotal = sumFeeAmounts(normalizedFees);
  return formatAmount(feeTotal);
}

function runL6() {
  const lines = getFlaggedLines();
  const flaggedTotals = lines.map(calcFlaggedLineTotal);
  const totalCents = sumValues(flaggedTotals);
  return formatMoneyCents(totalCents);
}

const CASE_RUNNERS = {
  L1: runL1,
  L2: runL2,
  L3: runL3,
  L4: runL4,
  L5: runL5,
  L6: runL6
};

function printUsage() {
  process.stdout.write(USAGE_HINT + '\n');
}

function printUnknownCase(caseId) {
  process.stderr.write('unknown case: ' + caseId + '\n');
  process.exitCode = 2;
}

function printResult(result) {
  process.stdout.write(String(result) + '\n');
}

function main(argv) {
  const rawCaseId = argv[2];
  if (!rawCaseId) {
    printUsage();
    return;
  }
  const caseId = normalizeCaseId(rawCaseId);
  const runner = CASE_RUNNERS[caseId];
  if (!runner) {
    printUnknownCase(caseId);
    return;
  }
  printResult(runner());
}

main(process.argv);
