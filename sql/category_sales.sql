-- NULL top_n is reserved for the internal all-category reconciliation.
WITH eligible_orders AS (
    SELECT order_id FROM orders
    WHERE order_status = 'delivered'
      AND order_purchase_timestamp >= CAST($start_at AS TIMESTAMP)
      AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)
)
SELECT p.product_category_name AS category_code,
    coalesce(t.product_category_name_english, p.product_category_name, '미분류') AS category_name,
    COUNT(*) AS item_count,
    COUNT(*) FILTER (WHERE i.price IS NULL) AS items_without_price,
    SUM(i.price) AS known_merchandise_value,
    CASE WHEN COUNT(*) FILTER (WHERE i.price IS NULL) > 0 THEN NULL
         ELSE SUM(i.price) END AS merchandise_value
FROM eligible_orders o
JOIN order_items i USING (order_id)
LEFT JOIN products p USING (product_id)
LEFT JOIN category_translation t USING (product_category_name)
GROUP BY p.product_category_name, t.product_category_name_english
ORDER BY merchandise_value DESC NULLS LAST, category_code ASC NULLS LAST
LIMIT $top_n;
