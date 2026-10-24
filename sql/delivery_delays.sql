-- Compare calendar dates, never estimated midnight against actual time of day.
WITH eligible_orders AS (
    SELECT CAST(date_trunc('month', order_purchase_timestamp) AS DATE) AS purchase_month,
        order_delivered_customer_date AS actual_delivery,
        order_estimated_delivery_date AS estimated_delivery
    FROM orders
    WHERE order_status = 'delivered'
      AND order_purchase_timestamp >= CAST($start_at AS TIMESTAMP)
      AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)
), classified AS (
    SELECT *, actual_delivery IS NOT NULL AND estimated_delivery IS NOT NULL AS comparable,
        CAST(actual_delivery AS DATE) > CAST(estimated_delivery AS DATE) AS late
    FROM eligible_orders
)
SELECT purchase_month, COUNT(*) AS delivered_orders,
    COUNT(*) FILTER (WHERE comparable) AS comparable_orders,
    COUNT(*) FILTER (WHERE NOT comparable) AS excluded_delivery_orders,
    COUNT(*) FILTER (WHERE actual_delivery IS NULL) AS missing_delivery_orders,
    COUNT(*) FILTER (WHERE estimated_delivery IS NULL) AS missing_estimate_orders,
    COUNT(*) FILTER (WHERE comparable AND late) AS late_orders,
    COUNT(*) FILTER (WHERE comparable AND NOT late) AS on_time_orders,
    CAST(COUNT(*) FILTER (WHERE comparable AND late) AS DOUBLE)
        / nullif(COUNT(*) FILTER (WHERE comparable), 0) AS late_rate
FROM classified
GROUP BY purchase_month
ORDER BY purchase_month;
