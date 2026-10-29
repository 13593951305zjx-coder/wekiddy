import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.NoSuchElementException;

/**
 * Order pipeline for the fulfilment service.
 *
 * <p>The pipeline turns a raw order request into a priced order total, plans
 * shipment slots for the pending queue and resolves routing attributes that
 * are stored in the legacy attribute map. Each case below is a self contained
 * scenario that the operations team uses to reproduce a production incident.</p>
 */
public class Runtime01OrderPipeline {

    static final String USAGE = "usage: R1 R2 R3 R4 R5 R6";
    static final int SHIPMENT_SLOTS = 4;
    static final String FIELD_SEPARATOR = "\\|";

    public static void main(String[] args) {
        if (args.length == 0) {
            System.out.println(USAGE);
            return;
        }
        String request = args[0];
        if ("R1".equals(request)) {
            runMissingCustomer();
        } else if ("R2".equals(request)) {
            runFieldOverrun();
        } else if ("R3".equals(request)) {
            runQuantityParse();
        } else if ("R4".equals(request)) {
            runAverageQuantity();
        } else if ("R5".equals(request)) {
            runPriorityCast();
        } else if ("R6".equals(request)) {
            runShipmentSlots();
        } else {
            System.err.println("unknown case: " + request);
            System.exit(2);
        }
    }

    // ---------------------------------------------------------------------
    // R1: an order that lost its customer reference during import
    // ---------------------------------------------------------------------

    static void runMissingCustomer() {
        Order order = buildOrder("ORD-9001", null, buildStandardLines());
        int total = computeOrderTotal(order);
        System.out.println("total=" + total);
    }

    static int computeOrderTotal(Order order) {
        Customer customer = requireCustomer(order);
        int subtotal = subtotalCents(order.getLines());
        int discount = loyaltyDiscountCents(customer, subtotal);
        int shipping = shippingCents(customer, subtotal);
        return subtotal - discount + shipping;
    }

    static Customer requireCustomer(Order order) {
        Customer customer = order.getCustomer();
        if (customer == null) {
            throw new NullPointerException("order " + order.getOrderId() + " has no customer attached");
        }
        return customer;
    }

    // ---------------------------------------------------------------------
    // R2: ingest of an order line that only carries three fields
    // ---------------------------------------------------------------------

    static void runFieldOverrun() {
        String payload = "SKU-4410|Industrial label printer|12";
        OrderLine line = ingestOrderLine(payload, "ORD-9002");
        System.out.println("sku=" + line.getSku() + ",qty=" + line.getQuantity());
    }

    static OrderLine ingestOrderLine(String payload, String orderId) {
        String[] fields = splitFields(payload);
        String sku = normalizeField(fields, 0, orderId);
        String description = normalizeField(fields, 1, orderId);
        int quantity = parseQuantity(normalizeField(fields, 2, orderId), orderId);
        int unitCents = parseQuantity(normalizeField(fields, 3, orderId), orderId);
        return new OrderLine(sku, description, quantity, unitCents);
    }

    static String[] splitFields(String payload) {
        return payload.split(FIELD_SEPARATOR);
    }

    static String normalizeField(String[] fields, int index, String orderId) {
        String value = fields[index];
        if (value.length() == 0) {
            throw new IllegalArgumentException("field " + index + " of order " + orderId + " is empty");
        }
        return value.trim();
    }

    static int parseQuantity(String raw, String orderId) {
        String text = raw.trim();
        if (text.isEmpty()) {
            throw new NumberFormatException("quantity field is empty on order " + orderId);
        }
        int value = 0;
        for (int i = 0; i < text.length(); i++) {
            char ch = text.charAt(i);
            if (ch < '0' || ch > '9') {
                throw new NumberFormatException("quantity '" + raw + "' on order " + orderId
                        + " is not a valid integer");
            }
            value = value * 10 + (ch - '0');
        }
        return value;
    }

    // ---------------------------------------------------------------------
    // R3: a quantity field that still carries its thousands separator
    // ---------------------------------------------------------------------

    static void runQuantityParse() {
        String payload = "SKU-4411|Thermal paper roll|12,500|899";
        OrderLine line = ingestOrderLine(payload, "ORD-9003");
        System.out.println("qty=" + line.getQuantity());
    }

    // ---------------------------------------------------------------------
    // R4: average basket size over the nightly order snapshot
    // ---------------------------------------------------------------------

    static void runAverageQuantity() {
        List<Order> orders = buildOrders();
        int average = averageOrderQuantity(orders);
        System.out.println("average=" + average);
    }

    static List<Order> buildOrders() {
        return new ArrayList<Order>();
    }

    static int averageOrderQuantity(List<Order> orders) {
        int total = totalQuantity(orders);
        int count = countActive(orders);
        int average = total / count;
        return average;
    }

    static int totalQuantity(List<Order> orders) {
        int total = 0;
        for (int i = 0; i < orders.size(); i++) {
            List<OrderLine> lines = orders.get(i).getLines();
            for (int j = 0; j < lines.size(); j++) {
                total += lines.get(j).getQuantity();
            }
        }
        return total;
    }

    static int countActive(List<Order> orders) {
        int active = 0;
        for (int i = 0; i < orders.size(); i++) {
            if (!"CANCELLED".equals(orders.get(i).getStatus())) {
                active++;
            }
        }
        return active;
    }

    // ---------------------------------------------------------------------
    // R5: routing attribute typed as text while the reader expects a number
    // ---------------------------------------------------------------------

    static void runPriorityCast() {
        Map<String, Object> attributes = buildAttributes("ORD-9005");
        int priority = resolvePriority(attributes);
        System.out.println("priority=" + priority);
    }

    static Map<String, Object> buildAttributes(String orderId) {
        Map<String, Object> attributes = new LinkedHashMap<String, Object>();
        attributes.put("orderId", orderId);
        attributes.put("channel", "web");
        attributes.put("priority", "HIGH");
        attributes.put("attempts", Integer.valueOf(1));
        return attributes;
    }

    static int resolvePriority(Map<String, Object> attributes) {
        Object raw = attributes.get("priority");
        Integer priority = (Integer) raw;
        return priority.intValue();
    }

    // ---------------------------------------------------------------------
    // R6: shipment planning that assumes a full pending queue
    // ---------------------------------------------------------------------

    static void runShipmentSlots() {
        List<Order> pending = buildPendingQueue();
        int planned = planShipmentSlots(pending, "BATCH-07");
        System.out.println("planned=" + planned);
    }

    static List<Order> buildPendingQueue() {
        List<Order> pending = new ArrayList<Order>();
        pending.add(buildOrder("ORD-9101", buildCustomer("CUS-201", "Ada Lovelace", "GOLD"),
                buildStandardLines()));
        pending.add(buildOrder("ORD-9102", buildCustomer("CUS-202", "Grace Hopper", "SILVER"),
                buildExpressLines()));
        return pending;
    }

    static int planShipmentSlots(List<Order> pending, String batchId) {
        Iterator<Order> iterator = pending.iterator();
        int planned = 0;
        for (int slot = 0; slot < SHIPMENT_SLOTS; slot++) {
            Order order = nextPending(iterator, batchId, slot);
            planned += subtotalCents(order.getLines());
        }
        return planned;
    }

    static Order nextPending(Iterator<Order> iterator, String batchId, int slot) {
        if (!iterator.hasNext()) {
            throw new NoSuchElementException("order queue drained while shipment slot " + slot
                    + " of " + batchId + " is still open");
        }
        return iterator.next();
    }

    // ---------------------------------------------------------------------
    // Shared builders and pricing helpers
    // ---------------------------------------------------------------------

    static Order buildOrder(String orderId, Customer customer, List<OrderLine> lines) {
        return new Order(orderId, customer, lines, "NEW");
    }

    static Customer buildCustomer(String customerId, String name, String tier) {
        return new Customer(customerId, name, tier, "customer." + customerId + "@example.com");
    }

    static List<OrderLine> buildStandardLines() {
        List<OrderLine> lines = new ArrayList<OrderLine>();
        lines.add(new OrderLine("SKU-4410", "Industrial label printer", 2, 45999));
        lines.add(new OrderLine("SKU-4411", "Thermal paper roll", 12, 899));
        lines.add(new OrderLine("SKU-4412", "Packing tape", 6, 349));
        return lines;
    }

    static List<OrderLine> buildExpressLines() {
        List<OrderLine> lines = new ArrayList<OrderLine>();
        lines.add(new OrderLine("SKU-4413", "Barcode scanner", 1, 18999));
        lines.add(new OrderLine("SKU-4414", "Pallet wrap", 4, 1299));
        return lines;
    }

    static int subtotalCents(List<OrderLine> lines) {
        int total = 0;
        for (int i = 0; i < lines.size(); i++) {
            OrderLine line = lines.get(i);
            total += line.getUnitCents() * line.getQuantity();
        }
        return total;
    }

    static int loyaltyDiscountCents(Customer customer, int subtotal) {
        int percent = 0;
        if ("GOLD".equals(customer.getTier())) {
            percent = 10;
        } else if ("SILVER".equals(customer.getTier())) {
            percent = 5;
        }
        return subtotal * percent / 100;
    }

    static int shippingCents(Customer customer, int subtotal) {
        if (subtotal >= 20000) {
            return 0;
        }
        if ("GOLD".equals(customer.getTier())) {
            return 0;
        }
        return 699;
    }

    /** Customer master record as kept by the CRM. */
    static class Customer {
        private final String customerId;
        private final String name;
        private final String tier;
        private final String email;

        Customer(String customerId, String name, String tier, String email) {
            this.customerId = customerId;
            this.name = name;
            this.tier = tier;
            this.email = email;
        }

        String getCustomerId() {
            return customerId;
        }

        String getName() {
            return name;
        }

        String getTier() {
            return tier;
        }

        String getEmail() {
            return email;
        }
    }

    /** One order line: sku, description, quantity and unit price in cents. */
    static class OrderLine {
        private final String sku;
        private final String description;
        private final int quantity;
        private final int unitCents;

        OrderLine(String sku, String description, int quantity, int unitCents) {
            this.sku = sku;
            this.description = description;
            this.quantity = quantity;
            this.unitCents = unitCents;
        }

        String getSku() {
            return sku;
        }

        String getDescription() {
            return description;
        }

        int getQuantity() {
            return quantity;
        }

        int getUnitCents() {
            return unitCents;
        }
    }

    /** Order header with its customer reference and line items. */
    static class Order {
        private final String orderId;
        private final Customer customer;
        private final List<OrderLine> lines;
        private final String status;

        Order(String orderId, Customer customer, List<OrderLine> lines, String status) {
            this.orderId = orderId;
            this.customer = customer;
            this.lines = lines;
            this.status = status;
        }

        String getOrderId() {
            return orderId;
        }

        Customer getCustomer() {
            return customer;
        }

        List<OrderLine> getLines() {
            return lines;
        }

        String getStatus() {
            return status;
        }
    }
}
