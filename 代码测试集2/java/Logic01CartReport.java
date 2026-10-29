import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/**
 * Cart and billing report used by the storefront checkout.
 *
 * <p>The report folds a shopping cart into the numbers that are shown on the
 * order confirmation page: the average unit price, the coupon discount, the
 * wholesale total, the legacy report subtotal, the shipping fee and the
 * cheapest item of the cart. Every case below reproduces one checkout defect
 * that was reported by the customer support team.</p>
 */
public class Logic01CartReport {

    static final String USAGE = "usage: L1 L2 L3 L4 L5 L6";
    static final String COUPON_PREFIX = "SAVE";
    static final int COUPON_VALUE_CENTS = 350;
    static final int HEAVY_PARCEL_GRAMS = 15000;
    static final int BULK_QUANTITY = 500000;

    public static void main(String[] args) {
        if (args.length == 0) {
            System.out.println(USAGE);
            return;
        }
        String request = args[0];
        if ("L1".equals(request)) {
            System.out.println(caseL1());
        } else if ("L2".equals(request)) {
            System.out.println(caseL2());
        } else if ("L3".equals(request)) {
            System.out.println(caseL3());
        } else if ("L4".equals(request)) {
            System.out.println(caseL4());
        } else if ("L5".equals(request)) {
            System.out.println(caseL5());
        } else if ("L6".equals(request)) {
            System.out.println(caseL6());
        } else {
            System.err.println("unknown case: " + request);
            System.exit(2);
        }
    }

    // ---------------------------------------------------------------------
    // L1: average unit price of the cart
    // ---------------------------------------------------------------------

    static String caseL1() {
        List<CartItem> cart = buildCart();
        int averageCents = averageUnitPriceCents(cart);
        return formatPlainCents(averageCents);
    }

    // ---------------------------------------------------------------------
    // L2: coupon discount of the cart
    // ---------------------------------------------------------------------

    static String caseL2() {
        List<CartItem> cart = buildCart();
        String requestedCode = buildCouponCode(COUPON_PREFIX, COUPON_VALUE_CENTS);
        String catalogCode = catalogCouponCode(COUPON_PREFIX, COUPON_VALUE_CENTS);
        int discountCents = couponDiscountCents(cart, requestedCode, catalogCode);
        return formatPlainCents(discountCents);
    }

    // ---------------------------------------------------------------------
    // L3: wholesale order total for a bulk purchase order
    // ---------------------------------------------------------------------

    static String caseL3() {
        List<Product> catalog = buildCatalog();
        Product product = findProduct(catalog, "SKU-9001");
        int orderCents = overflowOrderTotalCents(product, BULK_QUANTITY);
        return formatPlainCents(orderCents);
    }

    // ---------------------------------------------------------------------
    // L4: legacy report subtotal of the cart
    // ---------------------------------------------------------------------

    static String caseL4() {
        List<CartItem> cart = buildCart();
        int subtotalCents = legacyReportSubtotalCents(cart);
        return formatPlainCents(subtotalCents);
    }

    // ---------------------------------------------------------------------
    // L5: shipping fee for a standard parcel
    // ---------------------------------------------------------------------

    static String caseL5() {
        List<CartItem> cart = buildCart();
        int grams = packageWeightGrams(cart);
        int shippingCents = shippingCents("STANDARD", grams);
        return formatPlainCents(shippingCents);
    }

    // ---------------------------------------------------------------------
    // L6: cheapest item of the cart
    // ---------------------------------------------------------------------

    static String caseL6() {
        List<CartItem> cart = buildCart();
        return firstItemName(cart);
    }

    // ---------------------------------------------------------------------
    // Shared cart and catalog data
    // ---------------------------------------------------------------------

    static List<CartItem> buildCart() {
        List<CartItem> cart = new ArrayList<CartItem>();
        cart.add(new CartItem("CAB-100", "Cable", 599, 3, 40));
        cart.add(new CartItem("KEY-200", "Keyboard", 3499, 1, 600));
        cart.add(new CartItem("MON-300", "Monitor", 12999, 2, 4200));
        cart.add(new CartItem("MOU-400", "Mouse", 1899, 1, 90));
        return cart;
    }

    static List<Product> buildCatalog() {
        List<Product> catalog = new ArrayList<Product>();
        catalog.add(new Product("SKU-9001", "Wholesale thermal printer", 4999));
        catalog.add(new Product("SKU-9002", "Wholesale paper roll", 899));
        catalog.add(new Product("SKU-9003", "Wholesale barcode scanner", 18999));
        return catalog;
    }

    static Product findProduct(List<Product> catalog, String sku) {
        for (int i = 0; i < catalog.size(); i++) {
            Product product = catalog.get(i);
            if (product.getSku().equals(sku)) {
                return product;
            }
        }
        throw new IllegalArgumentException("unknown sku: " + sku);
    }

    // ---------------------------------------------------------------------
    // Pricing helpers
    // ---------------------------------------------------------------------

    static int unitTotalCents(CartItem item) {
        return item.getUnitCents() * item.getQuantity();
    }

    static int subtotalCents(List<CartItem> items) {
        int total = 0;
        for (int i = 0; i < items.size(); i++) {
            total += unitTotalCents(items.get(i));
        }
        return total;
    }

    static int itemCount(List<CartItem> items) {
        return items.size();
    }

    static int averageUnitPriceCents(List<CartItem> items) {
        int total = subtotalCents(items);
        int count = itemCount(items);
        return total / count;
    }

    static int couponDiscountCents(List<CartItem> items, String requestedCode, String catalogCode) {
        int subtotal = subtotalCents(items);
        if (requestedCode == catalogCode) {
            int discount = couponValueCents(requestedCode);
            if (discount > subtotal) {
                return subtotal;
            }
            return discount;
        }
        return 0;
    }

    static int couponValueCents(String code) {
        if (code.length() <= COUPON_PREFIX.length()) {
            return 0;
        }
        return Integer.parseInt(code.substring(COUPON_PREFIX.length()));
    }

    static String buildCouponCode(String prefix, int amount) {
        StringBuilder builder = new StringBuilder();
        builder.append(prefix);
        builder.append(amount);
        return builder.toString();
    }

    static String catalogCouponCode(String prefix, int amount) {
        return new String(prefix + amount);
    }

    static int overflowOrderTotalCents(Product product, int quantity) {
        return product.getUnitCents() * quantity;
    }

    static int legacyReportSubtotalCents(List<CartItem> items) {
        int total = 0;
        for (int i = 0; i < items.size() - 1; i++) {
            total += unitTotalCents(items.get(i));
        }
        return total;
    }

    static int packageWeightGrams(List<CartItem> items) {
        int grams = 0;
        for (int i = 0; i < items.size(); i++) {
            CartItem item = items.get(i);
            grams += item.getWeightGrams() * item.getQuantity();
        }
        return grams;
    }

    static int shippingCents(String tier, int weightGrams) {
        int shipping;
        switch (tier) {
            case "STANDARD":
                shipping = 499;
            case "EXPRESS":
                shipping = 999;
                break;
            case "OVERNIGHT":
                shipping = 1299;
                break;
            default:
                shipping = 1499;
                break;
        }
        if (weightGrams > HEAVY_PARCEL_GRAMS) {
            shipping += 200;
        }
        return shipping;
    }

    static List<CartItem> sortCheapestFirst(List<CartItem> items) {
        List<CartItem> sorted = new ArrayList<CartItem>(items);
        Collections.sort(sorted, new Comparator<CartItem>() {
            public int compare(CartItem left, CartItem right) {
                return Integer.compare(right.getUnitCents(), left.getUnitCents());
            }
        });
        return sorted;
    }

    static String firstItemName(List<CartItem> items) {
        List<CartItem> sorted = sortCheapestFirst(items);
        return sorted.get(0).getName();
    }

    static String formatPlainCents(int cents) {
        return String.valueOf(cents);
    }

    /** One line of the shopping cart. */
    static class CartItem {
        private final String sku;
        private final String name;
        private final int unitCents;
        private final int quantity;
        private final int weightGrams;

        CartItem(String sku, String name, int unitCents, int quantity, int weightGrams) {
            this.sku = sku;
            this.name = name;
            this.unitCents = unitCents;
            this.quantity = quantity;
            this.weightGrams = weightGrams;
        }

        String getSku() {
            return sku;
        }

        String getName() {
            return name;
        }

        int getUnitCents() {
            return unitCents;
        }

        int getQuantity() {
            return quantity;
        }

        int getWeightGrams() {
            return weightGrams;
        }
    }

    /** Catalog entry used by the wholesale order desk. */
    static class Product {
        private final String sku;
        private final String name;
        private final int unitCents;

        Product(String sku, String name, int unitCents) {
            this.sku = sku;
            this.name = name;
            this.unitCents = unitCents;
        }

        String getSku() {
            return sku;
        }

        String getName() {
            return name;
        }

        int getUnitCents() {
            return unitCents;
        }
    }
}
