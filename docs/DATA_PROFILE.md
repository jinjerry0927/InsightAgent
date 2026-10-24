# Olist 데이터 실측 보고서

생성 시각(UTC): 2026-10-24T00:56:47.739757+00:00

`python -m scripts.profile_data`로 생성한 로컬 실측 결과다. 원본 행을 삭제·중복 제거·보정하지 않았다.
KPI 계산 기준은 [METRICS.md](METRICS.md)의 승인 대기 초안을 참조한다.

## 테이블·파일 근거

| 테이블 | 역할 | 파일 | 행 수 | 타입 변환 후 전체 컬럼 중복 행(초과분) |
| --- | --- | --- | ---: | ---: |
| category_translation | 상품 카테고리 원문과 영어 이름 연결 | product_category_name_translation.csv | 71 | 0 |
| customers | 주문용 고객 ID와 고유 고객 ID·지역 연결 | olist_customers_dataset.csv | 99,441 | 0 |
| geolocation | 우편번호 접두사별 여러 좌표·지역명 | olist_geolocation_dataset.csv | 1,000,163 | 261,831 |
| order_items | 주문 내 상품 행·판매자·상품금액·배송비 | olist_order_items_dataset.csv | 112,650 | 0 |
| order_payments | 주문 내 결제 순번·수단·금액 | olist_order_payments_dataset.csv | 103,886 | 0 |
| order_reviews | 주문별 리뷰 이벤트·평점·텍스트 | olist_order_reviews_dataset.csv | 99,224 | 0 |
| orders | 주문 상태·고객 연결·구매·배송 시각 | olist_orders_dataset.csv | 99,441 | 0 |
| products | 상품 ID·카테고리·물리적 속성 | olist_products_dataset.csv | 32,951 | 0 |
| sellers | 판매자 ID·지역 | olist_sellers_dataset.csv | 3,095 | 0 |

## 컬럼 타입·결측·범위

빈 CSV 필드는 NULL로 적재했다. 식별자·우편번호는 VARCHAR, 금액은 DECIMAL(18,2)이다.
TIMESTAMP는 원본의 시간대 없는 값을 보존한다. 아래 날짜 범위가 모든 기간에 데이터가 존재함을 뜻하지는 않는다.

### customers

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| customer_id | VARCHAR | 0 | 99,441 | — | — |
| customer_unique_id | VARCHAR | 0 | 96,096 | — | — |
| customer_zip_code_prefix | VARCHAR | 0 | 14,994 | — | — |
| customer_city | VARCHAR | 0 | 4,119 | — | — |
| customer_state | VARCHAR | 0 | 27 | — | — |

### geolocation

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| geolocation_zip_code_prefix | VARCHAR | 0 | 19,015 | — | — |
| geolocation_lat | DOUBLE | 0 | 717,372 | -36.6053744107061 | 45.06593318269697 |
| geolocation_lng | DOUBLE | 0 | 717,615 | -101.46676644931476 | 121.10539381057764 |
| geolocation_city | VARCHAR | 0 | 8,011 | — | — |
| geolocation_state | VARCHAR | 0 | 27 | — | — |

### order_items

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| order_id | VARCHAR | 0 | 98,666 | — | — |
| order_item_id | BIGINT | 0 | 21 | 1 | 21 |
| product_id | VARCHAR | 0 | 32,951 | — | — |
| seller_id | VARCHAR | 0 | 3,095 | — | — |
| shipping_limit_date | TIMESTAMP | 0 | 93,318 | 2016-09-19 00:15:34 | 2020-04-09 22:35:08 |
| price | DECIMAL(18,2) | 0 | 5,968 | 0.85 | 6735.00 |
| freight_value | DECIMAL(18,2) | 0 | 6,999 | 0.00 | 409.68 |

### order_payments

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| order_id | VARCHAR | 0 | 99,440 | — | — |
| payment_sequential | BIGINT | 0 | 29 | 1 | 29 |
| payment_type | VARCHAR | 0 | 5 | — | — |
| payment_installments | BIGINT | 0 | 24 | 0 | 24 |
| payment_value | DECIMAL(18,2) | 0 | 29,077 | 0.00 | 13664.08 |

### order_reviews

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| review_id | VARCHAR | 0 | 98,410 | — | — |
| order_id | VARCHAR | 0 | 98,673 | — | — |
| review_score | BIGINT | 0 | 5 | 1 | 5 |
| review_comment_title | VARCHAR | 87,656 | 4,527 | — | — |
| review_comment_message | VARCHAR | 58,247 | 36,159 | — | — |
| review_creation_date | TIMESTAMP | 0 | 636 | 2016-10-02 00:00:00 | 2018-08-31 00:00:00 |
| review_answer_timestamp | TIMESTAMP | 0 | 98,248 | 2016-10-07 18:32:28 | 2018-10-29 12:27:35 |

### orders

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| order_id | VARCHAR | 0 | 99,441 | — | — |
| customer_id | VARCHAR | 0 | 99,441 | — | — |
| order_status | VARCHAR | 0 | 8 | — | — |
| order_purchase_timestamp | TIMESTAMP | 0 | 98,875 | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 |
| order_approved_at | TIMESTAMP | 160 | 90,733 | 2016-09-15 12:16:38 | 2018-09-03 17:40:06 |
| order_delivered_carrier_date | TIMESTAMP | 1,783 | 81,018 | 2016-10-08 10:34:01 | 2018-09-11 19:48:28 |
| order_delivered_customer_date | TIMESTAMP | 2,965 | 95,664 | 2016-10-11 13:46:32 | 2018-10-17 13:22:46 |
| order_estimated_delivery_date | TIMESTAMP | 0 | 459 | 2016-09-30 00:00:00 | 2018-11-12 00:00:00 |

### products

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| product_id | VARCHAR | 0 | 32,951 | — | — |
| product_category_name | VARCHAR | 610 | 73 | — | — |
| product_name_lenght | BIGINT | 610 | 66 | 5 | 76 |
| product_description_lenght | BIGINT | 610 | 2,960 | 4 | 3992 |
| product_photos_qty | BIGINT | 610 | 19 | 1 | 20 |
| product_weight_g | BIGINT | 2 | 2,204 | 0 | 40425 |
| product_length_cm | BIGINT | 2 | 99 | 7 | 105 |
| product_height_cm | BIGINT | 2 | 102 | 2 | 105 |
| product_width_cm | BIGINT | 2 | 95 | 6 | 118 |

### sellers

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| seller_id | VARCHAR | 0 | 3,095 | — | — |
| seller_zip_code_prefix | VARCHAR | 0 | 2,246 | — | — |
| seller_city | VARCHAR | 0 | 611 | — | — |
| seller_state | VARCHAR | 0 | 23 | — | — |

### category_translation

| 컬럼 | 타입 | NULL 행 수 | NULL 제외 고유값 | 최솟값 | 최댓값 |
| --- | --- | ---: | ---: | --- | --- |
| product_category_name | VARCHAR | 0 | 71 | — | — |
| product_category_name_english | VARCHAR | 0 | 71 | — | — |

## 키 후보 검증

고유 고객 식별자와 우편번호의 반복은 기본키로 쓸 수 없다는 근거다. 반복 자체를 오류로 삭제하지 않는다.

| 테이블 | 후보 키 | NULL 키 행 | 고유 키 수 | 중복 키 행(초과분) |
| --- | --- | ---: | ---: | ---: |
| customers | customer_id | 0 | 99,441 | 0 |
| customers | customer_unique_id | 0 | 96,096 | 3,345 |
| geolocation | geolocation_zip_code_prefix | 0 | 19,015 | 981,148 |
| order_items | order_id, order_item_id | 0 | 112,650 | 0 |
| order_payments | order_id, payment_sequential | 0 | 103,886 | 0 |
| order_reviews | review_id | 0 | 98,410 | 814 |
| order_reviews | review_id, order_id | 0 | 99,224 | 0 |
| orders | order_id | 0 | 99,441 | 0 |
| products | product_id | 0 | 32,951 | 0 |
| sellers | seller_id | 0 | 3,095 | 0 |
| category_translation | product_category_name | 0 | 71 | 0 |

## 연결 키 검사

NULL인 자식 키는 별도 컬럼 결측 표에서 확인한다.

| 자식 | 부모 | NULL 제외 연결되지 않는 행 |
| --- | --- | ---: |
| orders.customer_id | customers.customer_id | 0 |
| order_items.order_id | orders.order_id | 0 |
| order_items.product_id | products.product_id | 0 |
| order_items.seller_id | sellers.seller_id | 0 |
| order_payments.order_id | orders.order_id | 0 |
| order_reviews.order_id | orders.order_id | 0 |
| products.product_category_name | category_translation.product_category_name | 13 |

## 주문 상태·배송 결측

| 상태 | 행 수 | 고객 배송일 NULL | 승인일 NULL |
| --- | ---: | ---: | ---: |
| delivered | 96,478 | 8 | 14 |
| shipped | 1,107 | 1,107 | 0 |
| canceled | 625 | 619 | 141 |
| unavailable | 609 | 609 | 0 |
| invoiced | 314 | 314 | 0 |
| processing | 301 | 301 | 0 |
| created | 5 | 5 | 5 |
| approved | 2 | 2 | 0 |

## 구매 월별 원본 행 분포

전체 상태의 원본 주문 행 수다. 승인된 주문수 KPI가 아니다. 표에 없는 월은 관측 행이 없다.

| 구매 월 | 원본 주문 행 수 |
| --- | ---: |
| 2016-09 | 4 |
| 2016-10 | 324 |
| 2016-12 | 1 |
| 2017-01 | 800 |
| 2017-02 | 1,780 |
| 2017-03 | 2,682 |
| 2017-04 | 2,404 |
| 2017-05 | 3,700 |
| 2017-06 | 3,245 |
| 2017-07 | 4,026 |
| 2017-08 | 4,331 |
| 2017-09 | 4,285 |
| 2017-10 | 4,631 |
| 2017-11 | 7,544 |
| 2017-12 | 5,673 |
| 2018-01 | 7,269 |
| 2018-02 | 6,728 |
| 2018-03 | 7,211 |
| 2018-04 | 6,939 |
| 2018-05 | 6,873 |
| 2018-06 | 6,167 |
| 2018-07 | 6,292 |
| 2018-08 | 6,512 |
| 2018-09 | 16 |
| 2018-10 | 4 |

## 다중 연결 집계 위험

- 원본 주문 행: 99,441
- 상품이 여러 행인 주문: 9,803
- 결제가 여러 행인 주문: 2,961
- 리뷰가 여러 행인 주문: 547
- 주문→상품→결제→리뷰 LEFT JOIN 예상 행 수: 119,143
- 실제 동일 JOIN의 COUNT(*) 검증: 119,143
- JOIN 전 상품·결제·리뷰를 필요한 단위로 먼저 집계해야 한다. 이 검사는 매출 KPI 구현이 아니다.

## 리뷰 텍스트

- rows: 99,224
- with_title: 11,566
- with_message: 40,968
- with_any_text: 42,697

| 평점 | 행 수 |
| --- | ---: |
| 1 | 11,424 |
| 2 | 3,151 |
| 3 | 8,179 |
| 4 | 19,142 |
| 5 | 57,328 |

## 날짜 이상값

- 구매보다 이른 고객 배송일: 0행

## 로컬 원본 SHA-256

공식 배포 체크섬과 비교한 인증값이 아니라, 이번 로컬 입력의 재현용 지문이다.

| 파일 | SHA-256 |
| --- | --- |
| product_category_name_translation.csv | a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278 |
| olist_customers_dataset.csv | 983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2 |
| olist_geolocation_dataset.csv | b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6 |
| olist_order_items_dataset.csv | 0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279 |
| olist_order_payments_dataset.csv | 4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0 |
| olist_order_reviews_dataset.csv | 012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7 |
| olist_orders_dataset.csv | 8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf |
| olist_products_dataset.csv | 3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc |
| olist_sellers_dataset.csv | 1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e |
