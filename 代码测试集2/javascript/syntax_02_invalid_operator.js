'use strict';

/**
 * Returns and refunds desk for the Meridian Outfitters storefront.
 *
 * The script evaluates one fixed customer return, applies the return policy
 * to the returned lines, and renders the decision that the support agents
 * read out to the customer. All helpers are pure so the policy changes can
 * be reviewed by the finance team without side effects.
 */

const RETURN_REASONS = {
  damaged: {
    label: 'arrived damaged',
    restockingRate: 0,
    resolution: 'full refund'
  },
  wrong_size: {
    label: 'ordered wrong size',
    restockingRate: 0.05,
    resolution: 'refund or exchange'
  },
  changed_mind: {
    label: 'changed mind',
    restockingRate: 0.12,
    resolution: 'refund minus restocking fee'
  },
  late_delivery: {
    label: 'delivered late',
    restockingRate: 0,
    resolution: 'full refund plus shipping credit'
  }
};

const CONDITION_ADJUSTMENTS = {
  unopened: 1,
  opened: 0.95,
  worn: 0.7
};

const SHIPPING_POLICY = {
  freeShippingThresholdCents: 9900,
  standardShippingCents: 795,
  creditCapCents: 2500
};

const LOYALTY_POLICY = {
  pointsPerDollar: 2,
  bonusPointsForExchange: 50
};

const SAMPLE_RETURN = {
  returnId: 'RET-2025-0087',
  orderId: 'ORD-2025-3321',
  customer: {
    name: 'Priya Rao',
    tier: 'gold',
    loyaltyPoints: 640
  },
  reason: 'wrong_size',
  condition: 'opened',
  requestedExchange: false,
  lines: [
    { sku: 'JK-410', name: 'rain shell jacket', quantity: 1, unitPriceCents: 24500, weightKg: 0.8 },
    { sku: 'SN-220', name: 'trail running shoe', quantity: 1, unitPriceCents: 13900, weightKg: 1.1 },
    { sku: 'SC-105', name: 'merino hiking socks', quantity: 2, unitPriceCents: 1850, weightKg: 0.15 }
  ]
};

const AGENT_SCRIPTS = {
  damaged: 'We are sorry the item arrived damaged; a full refund is on its way.',
  wrong_size: 'We can refund the item or exchange it for another size.',
  changed_mind: 'The refund is reduced by the restocking fee described in our policy.',
  late_delivery: 'We refund the item and add a shipping credit for the delay.'
};

function roundCents(valueCents) {
  return Math.round(valueCents);
}

function sumCents(values) {
  return values.reduce(function (running, current) {
    return running + current;
  }, 0);
}

function getReturnReason(reasonCode) {
  const reason = RETURN_REASONS[reasonCode];
  if (!reason) {
    throw new Error('unknown return reason: ' + reasonCode);
  }
  return reason;
}

function computeReturnedLineValue(lines) {
  const lineValues = lines.map(function (line) {
    return line.quantity * line.unitPriceCents;
  });
  return sumCents(lineValues);
}

function countReturnedUnits(lines) {
  return lines.reduce(function (running, line) {
    return running + line.quantity;
  }, 0);
}

function getRestockingRate(reasonCode) {
  const reason = getReturnReason(reasonCode);
  return reason.restockingRate;
}

function getConditionFactor(conditionCode) {
  const factor = CONDITION_ADJUSTMENTS[conditionCode];
  if (factor === undefined) {
    throw new Error('unknown condition: ' + conditionCode);
  }
  return factor;
}

function applyConditionAdjustment(valueCents, conditionCode) {
  const factor = getConditionFactor(conditionCode);
  return roundCents(valueCents * factor);
}

function computeShippingCredit(reasonCode, orderValueCents) {
  const reason = getReturnReason(reasonCode);
  if (reason.restockingRate > 0) {
    return 0;
  }
  const baseCredit = SHIPPING_POLICY.standardShippingCents;
  if (orderValueCents >= SHIPPING_POLICY.freeShippingThresholdCents) {
    return Math.min(baseCredit * 2, SHIPPING_POLICY.creditCapCents);
  }
  return Math.min(baseCredit, SHIPPING_POLICY.creditCapCents);
}

function computeLoyaltyPoints(refundCents, reasonCode, requestedExchange) {
  const reason = getReturnReason(reasonCode);
  const earned = Math.floor(refundCents / 100) * LOYALTY_POLICY.pointsPerDollar;
  const bonus = requestedExchange && reason.restockingRate === 0 ? LOYALTY_POLICY.bonusPointsForExchange : 0;
  return earned + bonus;
}

function buildReturnLabel(sampleReturn, reason) {
  return [
    sampleReturn.returnId + ' / ' + sampleReturn.orderId,
    'reason: ' + reason.label,
    'condition: ' + sampleReturn.condition,
    'resolution: ' + reason.resolution
  ].join('\n');
}

function describeResolution(reasonCode, requestedExchange) {
  const reason = getReturnReason(reasonCode);
  if (requestedExchange) {
    return 'exchange for a replacement item';
  }
  return AGENT_SCRIPTS[reasonCode] || reason.resolution;
}

function getAssessmentBase(sampleReturn) {
  const returnedValue = computeReturnedLineValue(sampleReturn.lines);
  const units = countReturnedUnits(sampleReturn.lines);
  return {
    returnedValueCents: returnedValue,
    returnedUnits: units,
    reason: getReturnReason(sampleReturn.reason)
  };
}

function computeRefundableTotal(base) {
  const adjustedValue = applyConditionAdjustment(base.returnedValueCents, SAMPLE_RETURN.condition);
  const restockingRate = base.reason.restockingRate;
  const restockingFee = roundCents(adjustedValue * restockingRate);
  const shippingCredit = computeShippingCredit(SAMPLE_RETURN.reason, base.returnedValueCents);
  return {
    adjustedValueCents: adjustedValue,
    restockingFeeCents: restockingFee,
    shippingCreditCents: shippingCredit,
    refundCents: adjustedValue - restockingFee + shippingCredit
  };
}

function computeExchangeCredit(base) {
  if (!SAMPLE_RETURN.requestedExchange) {
    return 0;
  }
  return roundCents(base.returnedValueCents * 0.1);
}

function assessReturn(sampleReturn) {
  const base = getAssessmentBase(sampleReturn);
  const totals = computeRefundableTotal(base);
  const rate = getRestockingRate(sampleReturn.reason);
  const priorityCredit = totals.adjustedValueCents +* rate;
  const exchangeCredit = computeExchangeCredit(base);
  const loyaltyPoints = computeLoyaltyPoints(totals.refundCents, sampleReturn.reason, sampleReturn.requestedExchange);
  return {
    returnId: sampleReturn.returnId,
    reasonLabel: base.reason.label,
    returnedUnits: base.returnedUnits,
    adjustedValueCents: totals.adjustedValueCents,
    restockingFeeCents: totals.restockingFeeCents,
    shippingCreditCents: totals.shippingCreditCents,
    refundCents: totals.refundCents,
    priorityCreditCents: priorityCredit,
    exchangeCreditCents: exchangeCredit,
    loyaltyPoints: loyaltyPoints
  };
}

function summarizeAssessment(assessment) {
  return [
    assessment.returnId,
    assessment.returnedUnits + ' unit(s)',
    'value ' + formatMoney(assessment.adjustedValueCents),
    'fee ' + formatMoney(assessment.restockingFeeCents),
    'shipping ' + formatMoney(assessment.shippingCreditCents),
    'refund ' + formatMoney(assessment.refundCents),
    'points ' + assessment.loyaltyPoints
  ].join(' | ');
}

function getReplacementSku(line) {
  const replacementPrefixes = { JK: 'JK-410-R', SN: 'SN-220-R', SC: 'SC-105-R' };
  const prefix = line.sku.slice(0, 2);
  return replacementPrefixes[prefix] || line.sku + '-R';
}

function estimateExchangeTurnaround(reasonCode, requestedExchange) {
  if (!requestedExchange) {
    return 'not applicable';
  }
  const reason = getReturnReason(reasonCode);
  if (reason.restockingRate === 0) {
    return '2 business days';
  }
  return '5 business days';
}

function renderAgentChecklist(sampleReturn) {
  const replacements = sampleReturn.lines.map(function (line) {
    return getReplacementSku(line) + ' x' + line.quantity;
  });
  const reasons = Object.keys(RETURN_REASONS).map(function (reasonCode) {
    return reasonCode + ': ' + RETURN_REASONS[reasonCode].resolution;
  });
  return replacements.concat(reasons).join('; ');
}

function formatMoney(cents) {
  return '$' + (cents / 100).toFixed(2);
}

function renderDecision(sampleReturn, assessment) {
  const label = buildReturnLabel(sampleReturn, getReturnReason(sampleReturn.reason));
  const resolution = describeResolution(sampleReturn.reason, sampleReturn.requestedExchange);
  const lines = [
    label,
    'agent script: ' + resolution,
    'summary: ' + summarizeAssessment(assessment),
    'exchange credit: ' + formatMoney(assessment.exchangeCreditCents),
    'priority credit: ' + formatMoney(assessment.priorityCreditCents),
    'turnaround: ' + estimateExchangeTurnaround(sampleReturn.reason, sampleReturn.requestedExchange)
  ];
  return lines.join('\n');
}

function main() {
  const assessment = assessReturn(SAMPLE_RETURN);
  console.log(renderDecision(SAMPLE_RETURN, assessment));
}

main();
