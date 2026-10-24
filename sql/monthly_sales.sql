-- Approved: purchase month, delivered orders, item price only; no payments/reviews.
WITH eligible_orders AS (
    SELECT order_id, CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS purchase_month
    FROM orders
    WHERE order_status = 'delivered'
      AND order_purchase_timestamp >= CAST($start_at AS TIMESTAMP)
      AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)
), item_totals AS (
    SELECT order_id, COUNT(*) AS item_count, COUNT(*) FILTER (WHERE price IS NULL) AS missing_prices,
        SUM(price) AS item_value
    FROM order_items
    GROUP BY order_id
)
SELECT o.purchase_month, COUNT(DISTINCT o.order_id) AS order_count,
    SUM(coalesce(i.item_count, 0)) AS item_count,
    COUNT(*) FILTER (WHERE i.order_id IS NULL) AS orders_without_items,
    SUM(coalesce(i.missing_prices, 0)) AS items_without_price,
    SUM(i.item_value) AS known_merchandise_value,
    CASE WHEN COUNT(*) FILTER (WHERE i.order_id IS NULL) > 0
           OR SUM(coalesce(i.missing_prices, 0)) > 0
         THEN NULL ELSE SUM(i.item_value) END AS merchandise_value
FROM eligible_orders o
LEFT JOIN item_totals i USING (order_id)
GROUP BY o.purchase_month
ORDER BY o.purchase_month;
