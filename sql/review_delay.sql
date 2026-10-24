-- Select the latest review first. An unusable latest score is not backfilled.
WITH eligible_orders AS (
    SELECT order_id,
        CASE WHEN CAST(order_delivered_customer_date AS DATE)
                    > CAST(order_estimated_delivery_date AS DATE)
             THEN 'late' ELSE 'on_time' END AS delivery_group
    FROM orders
    WHERE order_status = 'delivered'
      AND order_purchase_timestamp >= CAST($start_at AS TIMESTAMP)
      AND order_purchase_timestamp < CAST($end_at AS TIMESTAMP)
      AND order_delivered_customer_date IS NOT NULL
      AND order_estimated_delivery_date IS NOT NULL
), ranked_reviews AS (
    SELECT r.order_id, r.review_score,
        row_number() OVER (
            PARTITION BY r.order_id
            ORDER BY r.review_answer_timestamp DESC NULLS LAST,
                r.review_creation_date DESC NULLS LAST, r.review_id ASC NULLS LAST
        ) AS review_rank
    FROM order_reviews r
    JOIN eligible_orders o USING (order_id)
)
SELECT o.delivery_group, COUNT(*) AS comparable_orders,
    COUNT(*) FILTER (WHERE r.review_score BETWEEN 1 AND 5) AS rated_orders,
    COUNT(*) FILTER (WHERE r.review_score IS NULL OR r.review_score NOT BETWEEN 1 AND 5)
        AS excluded_unrated_orders,
    AVG(CASE WHEN r.review_score BETWEEN 1 AND 5 THEN r.review_score END) AS mean_review_score
FROM eligible_orders o
LEFT JOIN ranked_reviews r ON o.order_id = r.order_id AND r.review_rank = 1
GROUP BY o.delivery_group
ORDER BY o.delivery_group;
