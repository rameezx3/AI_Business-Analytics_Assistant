# Exploratory Data Analysis Report

Generated automatically from the live PostgreSQL database (post-cleaning, Module 4;
post-validation, Module 5). Every number below comes directly from the queries in
`services/eda.py` - none of it is illustrative.

## 1. Order Volume Trend
Peak month: **2017-11-01** with **7544** orders,
across 25 months of data.
See `01_monthly_order_trend.png`.

## 2. Order Status
**97.0%** of 99441 total
orders reached 'delivered' status. See `02_order_status_distribution.png`.

## 3. Revenue by Category
Top category by revenue: **health_beauty**
(R$ 1,233,131.72). See `03_top_categories_by_revenue.png`.

## 4. Payment Methods
Most common payment method: **credit_card**
(73.9% of payments). See `04_payment_type_distribution.png`.

## 5. Review Scores
Average review score: **4.09 / 5**.
57.8% of reviews are 5-star, 11.5% are 1-star.
See `05_review_score_distribution.png`.

## 6. Price Distribution
Median item price: **R$ 74.99**, 95th percentile:
R$ 349.9, maximum: R$ 6735.0.
Distribution is heavily right-skewed - see `06_price_distribution.png` (log scale).

## 7. Delivery Time
Average delivery time: **12.6 days** (median: 10.2,
95th percentile: 29.3 days). See `07_delivery_time_distribution.png`.

## 8. Geographic Concentration
Top state by order volume: **SP** with
41746 orders. See `08_orders_by_state.png`.

## 9. Correlations
Correlation between delivery time and review score: **-0.304**
(negative = slower delivery associates with lower review scores). See `09_correlation_heatmap.png`.
