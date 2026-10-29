import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Replenishment planner for the regional distribution center.
 *
 * <p>The planner converts stock alerts into replenishment rows: it compares
 * the on-hand quantity with the reorder point, rounds the missing units up to
 * a supplier batch and prices the batch with the quotation table. The rows are
 * finally folded into a small purchase plan that the warehouse manager reviews
 * every morning.</p>
 */
public class Syntax01MissingSemicolon {

    static final String WAREHOUSE_ID = "WH-EAST-02";
    static final int DEFAULT_BATCH = 40;
    static final int SAFETY_DAYS = 5;
    static final int CRITICAL_RATIO = 30;
    static final int IMPORT_LEAD_TIME_EXTRA_DAYS = 6;

    public static void main(String[] args) {
        List<Product> catalog = buildCatalog();
        Map<String, Supplier> suppliers = buildSuppliers();
        List<ReplenishmentRow> rows = planRows(catalog, suppliers);
        ReplenishmentPlan plan = summarizePlan(rows);
        System.out.println("warehouse=" + WAREHOUSE_ID);
        System.out.println("rows=" + rows.size());
        System.out.println("units=" + plan.getTotalUnits());
        System.out.println("costCents=" + plan.getTotalCostCents());
        System.out.println("critical=" + plan.getCriticalSkus());
        for (int i = 0; i < rows.size(); i++) {
            ReplenishmentRow row = rows.get(i);
            System.out.println(row.getSku() + ":" + row.getBatchSize()
                    + ":" + formatCents(row.getCostCents()));
        }
    }

    /**
     * Snapshot of the stock table. In production this list is produced by the
     * nightly inventory synchronisation job.
     */
    static List<Product> buildCatalog() {
        List<Product> catalog = new ArrayList<Product>();
        catalog.add(new Product("SKU-1001", "Industrial label printer", "SUP-01", 12, 4, 10, 950, false));
        catalog.add(new Product("SKU-1002", "Thermal paper roll", "SUP-02", 240, 80, 300, 60, false));
        catalog.add(new Product("SKU-1003", "Barcode scanner", "SUP-01", 7, 3, 8, 1250, true));
        catalog.add(new Product("SKU-1004", "Packing tape", "SUP-03", 18, 25, 90, 40, false));
        catalog.add(new Product("SKU-1005", "Pallet wrap", "SUP-02", 30, 12, 70, 90, false));
        catalog.add(new Product("SKU-1006", "Shipping label sheet", "SUP-03", 9, 14, 40, 55, true));
        return catalog;
    }

    /**
     * Supplier quotation table. Unit costs are stored in cents so that the
     * planner never mixes floating point rounding with purchase orders.
     */
    static Map<String, Supplier> buildSuppliers() {
        Map<String, Supplier> suppliers = new LinkedHashMap<String, Supplier>();
        suppliers.put("SUP-01", new Supplier("SUP-01", "Northwind Supply", 4, 12));
        suppliers.put("SUP-02", new Supplier("SUP-02", "Acme Paper Works", 2, 8));
        suppliers.put("SUP-03", new Supplier("SUP-03", "Pacific Packaging", 6, 15));
        return suppliers;
    }

    /** Builds one plan row per product that actually needs a replenishment. */
    static List<ReplenishmentRow> planRows(List<Product> catalog, Map<String, Supplier> suppliers) {
        List<ReplenishmentRow> rows = new ArrayList<ReplenishmentRow>();
        for (int i = 0; i < catalog.size(); i++) {
            Product product = catalog.get(i);
            Supplier supplier = suppliers.get(product.getSupplierId());
            if (supplier == null) {
                continue;
            }
            int shortfall = computeShortfall(product);
            if (shortfall <= 0) {
                continue;
            }
            rows.add(buildReplenishmentRow(product, supplier, shortfall));
        }
        return rows;
    }

    /**
     * Converts a shortfall into a purchasable batch: the quantity is rounded
     * up to the supplier batch size and the cost is priced with the quoted
     * unit cost plus the handling fee of the product.
     */
    static ReplenishmentRow buildReplenishmentRow(Product product, Supplier supplier, int shortfall) {
        int batchSize = roundUpToBatch(shortfall);
        int leadTime = estimateLeadTimeDays(supplier, product);
        int unitCost = supplier.getUnitCostCents() + product.getHandlingCents();
        int cost = batchSize * unitCost;
        return new ReplenishmentRow(product.getSku(), batchSize, leadTime, cost);
    }

    /** Returns how many units are missing before the reorder point is met. */
    static int computeShortfall(Product product) {
        int target = product.getReorderPoint() + product.getDailyDemand() * SAFETY_DAYS;
        return target - product.getOnHand();
    }

    /** Rounds a raw shortage up to a full supplier batch. */
    static int roundUpToBatch(int quantity) {
        int batches = (quantity + DEFAULT_BATCH - 1) / DEFAULT_BATCH;
        return batches * DEFAULT_BATCH;
    }

    /** Estimated calendar days until a batch arrives at the dock. */
    static int estimateLeadTimeDays(Supplier supplier, Product product) {
        int base = supplier.getLeadTimeDays();
        if (product.isImported()) {
            base += IMPORT_LEAD_TIME_EXTRA_DAYS;
        }
        return base;
    }

    /** Flags products whose shortage is large relative to their target stock. */
    static boolean isCritical(Product product) {
        int target = product.getReorderPoint() + product.getDailyDemand() * SAFETY_DAYS;
        int shortfall = computeShortfall(product);
        return shortfall * 100 >= target * CRITICAL_RATIO;
    }

    /** Sums the missing units over the whole catalog. */
    static int totalShortfall(List<Product> catalog) {
        int total = 0;
        for (int i = 0; i < catalog.size(); i++) {
            int shortfall = computeShortfall(catalog.get(i));
            if (shortfall > 0) {
                total += shortfall;
            }
        }
        return total;
    }

    /** Counts products that are currently flagged as critical. */
    static int countCritical(List<Product> catalog) {
        int count = 0;
        for (int i = 0; i < catalog.size(); i++) {
            if (isCritical(catalog.get(i))) {
                count++;
            }
        }
        return count;
    }

    /** Folds the plan rows into the summary that is emailed to the manager. */
    static ReplenishmentPlan summarizePlan(List<ReplenishmentRow> rows) {
        int units = 0;
        int cost = 0;
        int critical = 0;
        for (int i = 0; i < rows.size(); i++) {
            ReplenishmentRow row = rows.get(i);
            units += row.getBatchSize();
            cost += row.getCostCents();
            if (row.getLeadTimeDays() >= SAFETY_DAYS) {
                critical++;
            }
        }
        return new ReplenishmentPlan(WAREHOUSE_ID, units, cost, critical);
    }

    /** Priority score used to sort the manual review queue. */
    static int reorderScore(Product product, Supplier supplier) {
        int shortfall = computeShortfall(product);
        int leadTime = estimateLeadTimeDays(supplier, product);
        int score = shortfall * leadTime - product.getOnHand();
        return score;
    }

    /** Formats a cent amount as a plain dollar amount, e.g. 12345 -> 123.45. */
    static String formatCents(int cents) {
        int dollars = cents / 100;
        int remainder = cents % 100;
        String tail = String.valueOf(remainder);
        if (tail.length() < 2) {
            tail = "0" + tail;
        }
        return dollars + "." + tail;
    }

    /** Product master record as delivered by the stock service. */
    static class Product {
        private final String sku;
        private final String name;
        private final String supplierId;
        private final int onHand;
        private final int dailyDemand;
        private final int reorderPoint;
        private final int handlingCents;
        private final boolean imported;

        Product(String sku, String name, String supplierId, int onHand, int dailyDemand,
                int reorderPoint, int handlingCents, boolean imported) {
            this.sku = sku;
            this.name = name;
            this.supplierId = supplierId;
            this.onHand = onHand;
            this.dailyDemand = dailyDemand;
            this.reorderPoint = reorderPoint;
            this.handlingCents = handlingCents;
            this.imported = imported;
        }

        String getSku() {
            return sku;
        }

        String getName() {
            return name;
        }

        String getSupplierId() {
            return supplierId;
        }

        int getOnHand() {
            return onHand;
        }

        int getDailyDemand() {
            return dailyDemand
        }

        int getReorderPoint() {
            return reorderPoint;
        }

        int getHandlingCents() {
            return handlingCents;
        }

        boolean isImported() {
            return imported;
        }
    }

    /** Supplier quotation record. */
    static class Supplier {
        private final String supplierId;
        private final String name;
        private final int leadTimeDays;
        private final int unitCostCents;

        Supplier(String supplierId, String name, int leadTimeDays, int unitCostCents) {
            this.supplierId = supplierId;
            this.name = name;
            this.leadTimeDays = leadTimeDays;
            this.unitCostCents = unitCostCents;
        }

        String getSupplierId() {
            return supplierId;
        }

        String getName() {
            return name;
        }

        int getLeadTimeDays() {
            return leadTimeDays;
        }

        int getUnitCostCents() {
            return unitCostCents;
        }
    }

    /** One purchasable replenishment batch. */
    static class ReplenishmentRow {
        private final String sku;
        private final int batchSize;
        private final int leadTimeDays;
        private final int costCents;

        ReplenishmentRow(String sku, int batchSize, int leadTimeDays, int costCents) {
            this.sku = sku;
            this.batchSize = batchSize;
            this.leadTimeDays = leadTimeDays;
            this.costCents = costCents;
        }

        String getSku() {
            return sku;
        }

        int getBatchSize() {
            return batchSize;
        }

        int getLeadTimeDays() {
            return leadTimeDays;
        }

        int getCostCents() {
            return costCents;
        }
    }

    /** Aggregated plan that is printed by main. */
    static class ReplenishmentPlan {
        private final String warehouseId;
        private final int totalUnits;
        private final int totalCostCents;
        private final int criticalSkus;

        ReplenishmentPlan(String warehouseId, int totalUnits, int totalCostCents, int criticalSkus) {
            this.warehouseId = warehouseId;
            this.totalUnits = totalUnits;
            this.totalCostCents = totalCostCents;
            this.criticalSkus = criticalSkus;
        }

        String getWarehouseId() {
            return warehouseId;
        }

        int getTotalUnits() {
            return totalUnits;
        }

        int getTotalCostCents() {
            return totalCostCents;
        }

        int getCriticalSkus() {
            return criticalSkus;
        }
    }
}
