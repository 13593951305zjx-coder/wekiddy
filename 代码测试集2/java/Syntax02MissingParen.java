import java.util.ArrayList;
import java.util.List;

/**
 * Invoice approval workflow for the accounts payable desk.
 *
 * <p>Every scanned vendor invoice is validated, priced with tax, routed to an
 * approver and finally folded into the daily approval queue. The workflow is
 * deliberately dependency free so that the nightly reconciliation job can run
 * it without a container.</p>
 */
public class Syntax02MissingParen {

    static final int MANAGER_LIMIT_CENTS = 250000;
    static final int DIRECTOR_LIMIT_CENTS = 1000000;
    static final int HIGH_RISK_SCORE = 70;
    static final int LATE_PENALTY_CENTS = 2500;
    static final double TAX_RATE = 0.0825;

    /** Vendor invoice as captured by the scanning service. */
    static class Invoice {
        private final String invoiceId;
        private final String vendorId;
        private final String costCenter;
        private final int amountCents;
        private final int riskScore;
        private final boolean preApproved;

        Invoice(String invoiceId, String vendorId, String costCenter, int amountCents,
                int riskScore, boolean preApproved) {
            this.invoiceId = invoiceId;
            this.vendorId = vendorId;
            this.costCenter = costCenter;
            this.amountCents = amountCents;
            this.riskScore = riskScore;
            this.preApproved = preApproved;
        }

        String getInvoiceId() {
            return invoiceId;
        }

        String getVendorId() {
            return vendorId;
        }

        String getCostCenter() {
            return costCenter;
        }

        int getAmountCents() {
            return amountCents;
        }

        int getRiskScore() {
            return riskScore;
        }

        boolean isPreApproved() {
            return preApproved;
        }
    }

    /** Person or role that is allowed to sign off invoices. */
    static class Approver {
        private final String approverId;
        private final String displayName;
        private final int limitCents;
        private final boolean director;

        Approver(String approverId, String displayName, int limitCents, boolean director) {
            this.approverId = approverId;
            this.displayName = displayName;
            this.limitCents = limitCents;
            this.director = director;
        }

        String getApproverId() {
            return approverId;
        }

        String getDisplayName() {
            return displayName;
        }

        int getLimitCents() {
            return limitCents;
        }

        boolean isDirector() {
            return director;
        }
    }

    /** Result of routing a single invoice through the workflow. */
    static class ApprovalDecision {
        private final String invoiceId;
        private final String approverId;
        private final String decision;
        private final int penaltyCents;

        ApprovalDecision(String invoiceId, String approverId, String decision, int penaltyCents) {
            this.invoiceId = invoiceId;
            this.approverId = approverId;
            this.decision = decision;
            this.penaltyCents = penaltyCents;
        }

        String getInvoiceId() {
            return invoiceId;
        }

        String getApproverId() {
            return approverId;
        }

        String getDecision() {
            return decision;
        }

        int getPenaltyCents() {
            return penaltyCents;
        }
    }

    public static void main(String[] args) {
        List<Invoice> invoices = buildInvoices();
        List<Approver> approvers = buildApprovers();
        int subtotal = taxableSubtotalCents(invoices);
        int tax = applyTax(subtotal);
        int outstanding = totalOutstandingCents(invoices);
        System.out.println("invoices=" + invoices.size());
        System.out.println("subtotalCents=" + subtotal);
        System.out.println("taxCents=" + tax);
        System.out.println("outstandingCents=" + outstanding);
        System.out.println("pending=" + countPending(invoices));
        System.out.println("highestRisk=" + highestRiskInvoice(invoices));
        System.out.println("queueValid=" + validateInvoices(invoices));
        for (int i = 0; i < invoices.size(); i++) {
            Invoice invoice = invoices.get(i);
            String approverId = assignApprover(invoice, approvers);
            ApprovalDecision decision = new ApprovalDecision(invoice.getInvoiceId(), approverId,
                    describeDecision(invoice), computePenalty(invoice));
            System.out.println(decision.getInvoiceId() + ":" + decision.getApproverId()
                    + ":" + decision.getDecision() + ":" + formatAmount(decision.getPenaltyCents()));
        }
    }

    /** Invoice batch that is queued for the morning review meeting. */
    static List<Invoice> buildInvoices() {
        List<Invoice> invoices = new ArrayList<Invoice>();
        invoices.add(new Invoice("INV-7001", "VEN-11", "CC-100", 149900, 20, false));
        invoices.add(new Invoice("INV-7002", "VEN-12", "CC-200", 625000, 45, false));
        invoices.add(new Invoice("INV-7003", "VEN-11", "CC-100", 85000, 85, false));
        invoices.add(new Invoice("INV-7004", "VEN-13", "CC-300", 1200000, 30, true));
        invoices.add(new Invoice("INV-7005", "VEN-12", "CC-200", 23500, 10, true));
        return invoices;
    }

    /** Approval roster for the current shift. */
    static List<Approver> buildApprovers() {
        List<Approver> approvers = new ArrayList<Approver>();
        approvers.add(new Approver("AP-01", "Dana Whitfield", MANAGER_LIMIT_CENTS, false));
        approvers.add(new Approver("AP-02", "Miles Okafor", DIRECTOR_LIMIT_CENTS, true));
        approvers.add(new Approver("AP-03", "Priya Raman", DIRECTOR_LIMIT_CENTS, true));
        return approvers;
    }

    /** Sum of all invoice amounts, in cents. */
    static int taxableSubtotalCents(List<Invoice> invoices) {
        int total = 0;
        for (int i = 0; i < invoices.size(); i++) {
            total += invoices.get(i).getAmountCents();
        }
        return total;
    }

    /** Applies the standard tax rate and rounds to the nearest cent. */
    static int applyTax(int subtotalCents) {
        double taxed = subtotalCents * (1.0 + TAX_RATE);
        return (int) Math.round(taxed) - subtotalCents;
    }

    /** Returns the highest invoice amount that an approver may sign. */
    static int approvalLimitFor(String approverId) {
        if ("AP-01".equals(approverId)) {
            return MANAGER_LIMIT_CENTS;
        }
        return DIRECTOR_LIMIT_CENTS;
    }

    /**
     * Decides whether an invoice needs a manager signature before it can be
     * paid. High risk vendors are always escalated to a manager even when the
     * amount alone would not require it.
     */
    static boolean requiresManagerApproval(Invoice invoice) {
        boolean requiresManager = false;
        if (invoice.getAmountCents() > MANAGER_LIMIT_CENTS && !invoice.isPreApproved() {
            requiresManager = true;
        }
        if (invoice.getRiskScore() >= HIGH_RISK_SCORE) {
            requiresManager = true;
        }
        return requiresManager;
    }

    /** An escalation is any invoice that is either high risk or very large. */
    static boolean isEscalation(Invoice invoice) {
        if (invoice.getAmountCents() > DIRECTOR_LIMIT_CENTS) {
            return true;
        }
        return invoice.getRiskScore() >= HIGH_RISK_SCORE;
    }

    /** Picks the first approver whose limit covers the invoice amount. */
    static String assignApprover(Invoice invoice, List<Approver> approvers) {
        for (int i = 0; i < approvers.size(); i++) {
            Approver approver = approvers.get(i);
            int limit = approvalLimitFor(approver.getApproverId());
            if (invoice.getAmountCents() <= limit) {
                return approver.getApproverId();
            }
        }
        return approvers.get(approvers.size() - 1).getApproverId();
    }

    /** Late invoices booked by the same vendor carry a fixed penalty. */
    static int computePenalty(Invoice invoice) {
        if (invoice.getRiskScore() < HIGH_RISK_SCORE) {
            return 0;
        }
        if (invoice.isPreApproved()) {
            return LATE_PENALTY_CENTS / 2;
        }
        return LATE_PENALTY_CENTS;
    }

    /** Formats a cent amount as a plain dollar amount, e.g. 12345 -> 123.45. */
    static String formatAmount(int cents) {
        int dollars = cents / 100;
        int remainder = cents % 100;
        String tail = String.valueOf(remainder);
        if (tail.length() < 2) {
            tail = "0" + tail;
        }
        return dollars + "." + tail;
    }

    /** Sum of invoices that are not pre-approved yet. */
    static int totalOutstandingCents(List<Invoice> invoices) {
        int total = 0;
        for (int i = 0; i < invoices.size(); i++) {
            Invoice invoice = invoices.get(i);
            if (!invoice.isPreApproved()) {
                total += invoice.getAmountCents();
            }
        }
        return total;
    }

    /** Returns the risk score of the riskiest invoice in the queue. */
    static int highestRiskInvoice(List<Invoice> invoices) {
        int highest = 0;
        for (int i = 0; i < invoices.size(); i++) {
            int score = invoices.get(i).getRiskScore();
            if (score > highest) {
                highest = score;
            }
        }
        return highest;
    }

    /** Counts invoices that still need a signature. */
    static int countPending(List<Invoice> invoices) {
        int pending = 0;
        for (int i = 0; i < invoices.size(); i++) {
            if (!invoices.get(i).isPreApproved()) {
                pending++;
            }
        }
        return pending;
    }

    /** Human readable routing decision for the approval email. */
    static String describeDecision(Invoice invoice) {
        if (isEscalation(invoice)) {
            return "escalate";
        }
        if (requiresManagerApproval(invoice)) {
            return "manager";
        }
        return "auto";
    }

    /** Cheap sanity pass over the batch before it reaches the approval desk. */
    static boolean validateInvoices(List<Invoice> invoices) {
        int previous = 0;
        for (int i = 0; i < invoices.size(); i++) {
            Invoice invoice = invoices.get(i);
            if (invoice.getAmountCents() <= 0) {
                return false;
            }
            if (invoice.getCostCenter() == null) {
                return false;
            }
            if (invoice.getAmountCents() < previous) {
                return false;
            }
            previous = invoice.getAmountCents();
        }
        return true;
    }
}
