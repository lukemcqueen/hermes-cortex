SNIPPETS = [
    (
        "sql/create_table.md",
        "sql",
        ["sql", "ddl", "constraints"],
        "CREATE TABLE with Constraints",
        "Table creation with PRIMARY KEY, FOREIGN KEY, UNIQUE, NOT NULL, DEFAULT, CHECK, and indexes.",
        "pattern",
        """-- Users table with all common constraints
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(50) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    full_name       VARCHAR(100) NOT NULL,
    age             INTEGER CHECK (age >= 0 AND age <= 150),
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Orders table with foreign key constraint
CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled')),
    total           NUMERIC(10,2) NOT NULL CHECK (total >= 0),
    shipped_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_orders_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);

-- Order items join table with composite primary key
CREATE TABLE order_items (
    order_id        INTEGER NOT NULL,
    product_id      INTEGER NOT NULL,
    quantity        INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price      NUMERIC(10,2) NOT NULL,

    PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_oi_order
        FOREIGN KEY (order_id) REFERENCES orders(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_oi_product
        FOREIGN KEY (product_id) REFERENCES products(id)
        ON DELETE RESTRICT
);

-- Indexes for performance
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created_at ON orders(created_at);
CREATE UNIQUE INDEX idx_active_user_roles ON users(username) WHERE is_active = TRUE;
""",
    ),
    (
        "sql/crud.md",
        "sql",
        ["sql", "dml", "crud"],
        "Basic CRUD Operations",
        "INSERT, SELECT, UPDATE, and DELETE with WHERE, ORDER BY, LIMIT, and RETURNING clauses.",
        "pattern",
        """-- INSERT: Create a new user
INSERT INTO users (username, email, full_name, age, role)
VALUES ('jdoe', 'jdoe@example.com', 'Jane Doe', 32, 'editor')
RETURNING *;

-- INSERT multiple rows
INSERT INTO products (name, sku, price, stock)
VALUES
    ('Widget Alpha', 'WGT-001', 19.99, 100),
    ('Widget Beta',  'WGT-002', 29.99, 200),
    ('Widget Gamma', 'WGT-003', 39.99, 150)
RETURNING id, name, sku;

-- SELECT with filtering, ordering, and limiting
SELECT id, username, email, role, created_at
FROM users
WHERE is_active = TRUE
  AND role IN ('editor', 'admin')
ORDER BY created_at DESC
LIMIT 20;

-- UPDATE with WHERE and RETURNING
UPDATE orders
SET status = 'shipped',
    shipped_at = NOW()
WHERE status = 'pending'
  AND created_at < NOW() - INTERVAL '2 days'
RETURNING id, user_id, status, shipped_at;

-- DELETE with subquery condition
DELETE FROM order_items
WHERE order_id IN (
    SELECT id FROM orders WHERE status = 'cancelled'
)
RETURNING *;

-- Full SELECT with offset for pagination
SELECT o.id, o.total, u.username, o.created_at
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'pending'
ORDER BY o.created_at ASC
LIMIT 25 OFFSET 0;
""",
    ),
    (
        "sql/joins.md",
        "sql",
        ["sql", "query", "joins"],
        "JOIN Operations",
        "INNER, LEFT, RIGHT, and FULL OUTER JOINs with multiple tables.",
        "pattern",
        """-- INNER JOIN: only matching rows
SELECT o.id AS order_id, o.total, c.name AS customer, c.email
FROM orders o
INNER JOIN customers c ON o.customer_id = c.id;

-- LEFT JOIN: all customers, orders where they exist
SELECT c.name, c.email, o.id AS order_id, o.total
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id;

-- RIGHT JOIN: all orders, customer info where it exists
SELECT o.id AS order_id, o.total, c.name
FROM customers c
RIGHT JOIN orders o ON c.id = o.customer_id;

-- FULL OUTER JOIN: everything from both sides
SELECT e.name AS employee, d.name AS department
FROM employees e
FULL OUTER JOIN departments d ON e.dept_id = d.id;

-- Multiple joins across three tables
SELECT u.username, o.id AS order_id, p.name AS product, oi.quantity
FROM users u
INNER JOIN orders o ON u.id = o.user_id
INNER JOIN order_items oi ON o.id = oi.order_id
INNER JOIN products p ON oi.product_id = p.id
WHERE o.status = 'delivered'
ORDER BY o.created_at DESC;

-- Self-join: employees and their managers
SELECT e.name AS employee, m.name AS manager
FROM employees e
LEFT JOIN employees m ON e.manager_id = m.id;
""",
    ),
    (
        "sql/aggregation.md",
        "sql",
        ["sql", "query", "aggregation", "group-by"],
        "Aggregation & GROUP BY",
        "COUNT, SUM, AVG, MIN, MAX with GROUP BY, HAVING, and GROUPING SETS.",
        "pattern",
        """-- Basic aggregate functions
SELECT
    COUNT(*)                    AS total_orders,
    COUNT(DISTINCT user_id)     AS unique_customers,
    SUM(total)                  AS revenue,
    AVG(total)                  AS avg_order_value,
    MIN(total)                  AS smallest_order,
    MAX(total)                  AS largest_order
FROM orders
WHERE created_at >= '2024-01-01';

-- GROUP BY with HAVING filter
SELECT
    u.role,
    COUNT(u.id)                    AS user_count,
    ROUND(AVG(o.total), 2)         AS avg_spend
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.role
HAVING COUNT(o.id) > 5
ORDER BY avg_spend DESC;

-- GROUP BY multiple columns
SELECT
    EXTRACT(YEAR FROM o.created_at)  AS year,
    EXTRACT(MONTH FROM o.created_at) AS month,
    o.status,
    COUNT(*)                         AS order_count,
    SUM(o.total)                     AS monthly_revenue
FROM orders o
GROUP BY year, month, o.status
ORDER BY year DESC, month DESC, o.status;

-- GROUPING SETS: subtotals and grand totals
SELECT
    COALESCE(p.category, 'ALL')       AS category,
    COALESCE(p.name, 'ALL')           AS product,
    SUM(oi.quantity)                  AS units_sold,
    SUM(oi.quantity * oi.unit_price)  AS revenue
FROM order_items oi
JOIN products p ON oi.product_id = p.id
GROUP BY GROUPING SETS (
    (p.category, p.name),
    (p.category),
    ()
)
ORDER BY category, product;
""",
    ),
    (
        "sql/subqueries_cte.md",
        "sql",
        ["sql", "query", "subqueries", "cte"],
        "Subqueries & Common Table Expressions",
        "Scalar subqueries, correlated subqueries, WITH/CTE, and recursive CTEs.",
        "pattern",
        """-- Scalar subquery in SELECT
SELECT
    o.id,
    o.total,
    (SELECT AVG(total) FROM orders) AS overall_avg,
    o.total - (SELECT AVG(total) FROM orders) AS difference_from_avg
FROM orders o;

-- Subquery in WHERE clause
SELECT u.username, u.email
FROM users u
WHERE u.id IN (
    SELECT user_id FROM orders
    WHERE total > 1000 AND status = 'delivered'
);

-- Correlated subquery: each user's latest order
SELECT u.username, u.email, o.id AS order_id, o.total, o.created_at
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE o.created_at = (
    SELECT MAX(o2.created_at)
    FROM orders o2
    WHERE o2.user_id = u.id
);

-- Simple CTE
WITH user_revenue AS (
    SELECT
        u.id,
        u.username,
        COUNT(o.id) AS order_count,
        SUM(o.total) AS total_spent
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    GROUP BY u.id, u.username
)
SELECT * FROM user_revenue
WHERE total_spent > 500
ORDER BY total_spent DESC;

-- Recursive CTE: organizational hierarchy
WITH RECURSIVE org_tree AS (
    -- Base case: top-level employees
    SELECT id, name, manager_id, 1 AS level
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: direct reports
    SELECT e.id, e.name, e.manager_id, t.level + 1
    FROM employees e
    JOIN org_tree t ON e.manager_id = t.id
)
SELECT * FROM org_tree
ORDER BY level, name;

-- CTE chain (multiple CTEs)
WITH
    active_users AS (
        SELECT id, username, email FROM users WHERE is_active = TRUE
    ),
    user_orders AS (
        SELECT u.id, u.username, COUNT(o.id) AS cnt
        FROM active_users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.id, u.username
    )
SELECT * FROM user_orders WHERE cnt = 0;
""",
    ),
    (
        "sql/window_functions.md",
        "sql",
        ["sql", "query", "window-functions"],
        "Window Functions",
        "ROW_NUMBER, RANK, DENSE_RANK, LAG/LEAD, SUM OVER PARTITION BY, and NTILE.",
        "pattern",
        """-- ROW_NUMBER: rank orders per user by date
SELECT
    u.username,
    o.id AS order_id,
    o.total,
    o.created_at,
    ROW_NUMBER() OVER (PARTITION BY u.id ORDER BY o.created_at DESC) AS order_num
FROM users u
JOIN orders o ON u.id = o.user_id;

-- RANK and DENSE_RANK: product sales ranking
SELECT
    p.name,
    SUM(oi.quantity) AS units_sold,
    RANK()       OVER (ORDER BY SUM(oi.quantity) DESC) AS rank,
    DENSE_RANK() OVER (ORDER BY SUM(oi.quantity) DESC) AS dense_rank
FROM products p
JOIN order_items oi ON p.id = oi.product_id
GROUP BY p.id, p.name;

-- LAG and LEAD: compare current order to previous
SELECT
    u.username,
    o.id,
    o.total,
    o.created_at,
    LAG(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS prev_order_total,
    LEAD(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS next_order_total,
    o.total - LAG(o.total, 1) OVER (PARTITION BY u.id ORDER BY o.created_at) AS diff_from_prev
FROM users u
JOIN orders o ON u.id = o.user_id;

-- Moving sum over partition
SELECT
    o.user_id,
    o.created_at::DATE AS order_date,
    o.total,
    SUM(o.total) OVER (
        PARTITION BY o.user_id
        ORDER BY o.created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_total
FROM orders o
ORDER BY o.user_id, o.created_at;

-- NTILE: divide users into deciles by spend
SELECT
    u.username,
    SUM(o.total) AS total_spent,
    NTILE(4) OVER (ORDER BY SUM(o.total) DESC) AS quartile
FROM users u
JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username
ORDER BY total_spent DESC;

-- First and last values in a window
SELECT DISTINCT
    u.username,
    FIRST_VALUE(o.id) OVER (
        PARTITION BY u.id ORDER BY o.created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_order_id,
    LAST_VALUE(o.id) OVER (
        PARTITION BY u.id ORDER BY o.created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_order_id
FROM users u
JOIN orders o ON u.id = o.user_id;
""",
    ),
    (
        "sql/indexes_performance.md",
        "sql",
        ["sql", "ddl", "performance", "indexes"],
        "Indexes & Performance Tuning",
        "CREATE INDEX, composite indexes, partial indexes, EXPLAIN ANALYZE, and covering indexes.",
        "pattern",
        """-- Single-column B-tree index
CREATE INDEX idx_users_email ON users(email);

-- Composite index (column order matters: most selective first)
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- Partial index: only active users
CREATE INDEX idx_users_active ON users(username) WHERE is_active = TRUE;

-- Unique partial index: enforce one active admin per email
CREATE UNIQUE INDEX idx_unique_active_admin
ON users(email) WHERE role = 'admin' AND is_active = TRUE;

-- Covering index (INCLUDE columns to avoid table lookups)
CREATE INDEX idx_orders_list ON orders(user_id, created_at DESC)
INCLUDE (total, status);

-- Index on expression
CREATE INDEX idx_users_lower_email ON users(LOWER(email));

-- Using EXPLAIN ANALYZE to check query plan
EXPLAIN ANALYZE
SELECT u.username, o.total, o.created_at
FROM users u
JOIN orders o ON u.id = o.user_id
WHERE u.email = 'jdoe@example.com'
ORDER BY o.created_at DESC
LIMIT 10;

-- Understanding the plan output
-- Seq Scan on users  (cost=0.00..12.32 rows=1 width=...)
--   Filter: (email = 'jdoe@example.com'::text)
--   ->  Index Scan using idx_orders_user_created on orders  (cost=...)
--         Index Cond: (user_id = users.id)

-- Drop indexes when no longer needed
DROP INDEX IF EXISTS idx_old_unused_index;
""",
    ),
    (
        "sql/transactions.md",
        "sql",
        ["sql", "dml", "transactions", "concurrency"],
        "Transactions & Concurrency Control",
        "BEGIN, COMMIT, ROLLBACK, SAVEPOINT, isolation levels, and explicit locking.",
        "pattern",
        """-- Basic transaction with COMMIT
BEGIN;
UPDATE accounts SET balance = balance - 100.00 WHERE id = 1;
UPDATE accounts SET balance = balance + 100.00 WHERE id = 2;
COMMIT;

-- Transaction with ROLLBACK on error
BEGIN;
DELETE FROM orders WHERE id = 9999;
-- Oops, wrong order — undo it
ROLLBACK;

-- SAVEPOINT for partial rollback
BEGIN;
INSERT INTO orders (user_id, total) VALUES (1, 250.00);
SAVEPOINT order_created;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (LASTVAL(), 42, 2, 125.00);

-- Something went wrong with items, rollback just that part
ROLLBACK TO SAVEPOINT order_created;
-- Order still exists, fix the items
INSERT INTO order_items (order_id, product_id, quantity, unit_price)
VALUES (LASTVAL(), 42, 1, 250.00);
COMMIT;

-- Explicit isolation level
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
UPDATE inventory SET stock = stock - 5 WHERE product_id = 10 AND stock >= 5;
COMMIT;

-- Row-level locking (prevent concurrent updates)
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- Now safely update knowing no one else changed it
UPDATE accounts SET balance = balance - 50 WHERE id = 1;
COMMIT;

-- Advisory lock for application-level concurrency
BEGIN;
SELECT pg_advisory_xact_lock(12345);
-- Critical section — only one session at a time
UPDATE counters SET value = value + 1 WHERE name = 'api_calls';
COMMIT;
""",
    ),
    (
        "sql/views.md",
        "sql",
        ["sql", "ddl", "views"],
        "Views & Materialized Views",
        "CREATE VIEW, CREATE MATERIALIZED VIEW, WITH CHECK OPTION, and refreshing.",
        "pattern",
        """-- Simple view: active users only
CREATE VIEW active_users AS
SELECT id, username, email, full_name, role, created_at
FROM users
WHERE is_active = TRUE;

-- View with CHECK OPTION: prevents inserts/updates that would make rows invisible
CREATE VIEW high_value_orders AS
SELECT id, user_id, total, status, created_at
FROM orders
WHERE total >= 500
WITH CHECK OPTION;

-- Attempting INSERT below threshold fails:
-- INSERT INTO high_value_orders (user_id, total, status)
-- VALUES (1, 100, 'pending');  -- ERROR: new row violates WITH CHECK OPTION

-- View joining multiple tables
CREATE VIEW customer_order_summary AS
SELECT
    u.id AS user_id,
    u.username,
    u.email,
    COUNT(o.id) AS order_count,
    SUM(o.total) AS lifetime_value,
    MAX(o.created_at) AS last_order_date
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.id, u.username, u.email;

-- Materialized view for expensive aggregations
CREATE MATERIALIZED VIEW mv_monthly_sales AS
SELECT
    EXTRACT(YEAR FROM o.created_at)  AS year,
    EXTRACT(MONTH FROM o.created_at) AS month,
    p.category,
    COUNT(DISTINCT o.id)              AS order_count,
    SUM(oi.quantity)                  AS units_sold,
    SUM(oi.quantity * oi.unit_price)  AS revenue
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
GROUP BY year, month, p.category
WITH DATA;

-- Refresh materialized view (blocking)
REFRESH MATERIALIZED VIEW mv_monthly_sales;

-- Non-blocking refresh (PostgreSQL 9.4+)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_sales;

-- Drop a view
DROP VIEW IF EXISTS old_unused_view CASCADE;
""",
    ),
    (
        "sql/string_date_functions.md",
        "sql",
        ["sql", "functions", "strings", "dates"],
        "String & Date Functions",
        "UPPER/LOWER, TRIM, SUBSTRING, REPLACE, CONCAT, EXTRACT, DATE_TRUNC, and AT TIME ZONE.",
        "pattern",
        """-- String case conversion
SELECT
    UPPER(username)    AS upper_name,
    LOWER(email)       AS lower_email,
    INITCAP(full_name) AS title_case
FROM users;

-- Trimming and padding
SELECT
    TRIM(LEADING FROM '  hello  ')        AS trimmed,
    TRIM(TRAILING 'xyz' FROM 'helloxyz')   AS trimmed_suffix,
    LPAD(CAST(id AS TEXT), 6, '0')         AS padded_id,
    RPAD(name, 20, '.')                    AS padded_name
FROM products;

-- Substring and position
SELECT
    SUBSTRING(email FROM '@(.+)$')          AS domain,
    POSITION('@' IN email)                  AS at_position,
    LEFT(email, POSITION('@' IN email) - 1) AS local_part
FROM users;

-- Replace and concatenation
SELECT
    REPLACE(username, '_', '-')                   AS clean_username,
    CONCAT(full_name, ' <', email, '>')           AS mailto_string,
    full_name || ' (' || role || ')'              AS display_label
FROM users;

-- Extract date parts
SELECT
    EXTRACT(YEAR FROM created_at)      AS year,
    EXTRACT(MONTH FROM created_at)     AS month,
    EXTRACT(DOW FROM created_at)       AS day_of_week,
    EXTRACT(HOUR FROM created_at)      AS hour,
    created_at::DATE                   AS date_only
FROM orders;

-- Date truncation for grouping
SELECT
    DATE_TRUNC('month', created_at)     AS month_bucket,
    DATE_TRUNC('week', created_at)      AS week_bucket,
    COUNT(*)                            AS cnt
FROM orders
GROUP BY month_bucket, week_bucket
ORDER BY month_bucket;

-- Time zone conversion
SELECT
    created_at AT TIME ZONE 'UTC'              AS utc_time,
    created_at AT TIME ZONE 'America/New_York' AS ny_time,
    created_at AT TIME ZONE 'Asia/Tokyo'       AS tokyo_time,
    (created_at AT TIME ZONE 'UTC')
        AT TIME ZONE 'America/Los_Angeles'     AS la_time
FROM orders;

-- Date arithmetic
SELECT
    created_at,
    created_at + INTERVAL '7 days'     AS one_week_later,
    created_at - INTERVAL '1 month'    AS one_month_ago,
    AGE(NOW(), created_at)             AS age
FROM orders;
""",
    ),
    (
        "sql/conditional_logic.md",
        "sql",
        ["sql", "query", "conditional"],
        "Conditional Logic & Null Handling",
        "CASE WHEN, COALESCE, NULLIF, FILTER clause, and boolean expressions.",
        "pattern",
        """-- CASE WHEN for value mapping
SELECT
    username,
    CASE
        WHEN age < 18 THEN 'minor'
        WHEN age BETWEEN 18 AND 64 THEN 'adult'
        ELSE 'senior'
    END AS age_group,
    CASE role
        WHEN 'admin'   THEN 'Full Access'
        WHEN 'editor'  THEN 'Read/Write'
        WHEN 'viewer'  THEN 'Read Only'
        ELSE 'Unknown'
    END AS access_level
FROM users;

-- CASE inside aggregate for conditional counting
SELECT
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*)                                         AS total,
    COUNT(CASE WHEN status = 'delivered' THEN 1 END) AS delivered,
    COUNT(CASE WHEN status = 'shipped'   THEN 1 END) AS shipped,
    COUNT(CASE WHEN status = 'pending'   THEN 1 END) AS pending
FROM orders
GROUP BY month
ORDER BY month;

-- COALESCE: first non-null value
SELECT
    COALESCE(shipped_at::TEXT, 'not yet shipped') AS shipping_status,
    COALESCE(discount, 0)                         AS effective_discount,
    COALESCE(notes, '(no notes)')                 AS order_notes
FROM orders;

-- NULLIF: avoid division by zero
SELECT
    product_id,
    SUM(quantity)                    AS units_sold,
    COUNT(DISTINCT order_id)         AS order_count,
    ROUND(
        SUM(quantity)::NUMERIC / NULLIF(COUNT(DISTINCT order_id), 0),
        2
    ) AS avg_units_per_order
FROM order_items
GROUP BY product_id;

-- FILTER clause (PostgreSQL): cleaner than CASE in aggregates
SELECT
    DATE_TRUNC('month', created_at) AS month,
    COUNT(*)                                           AS total_orders,
    COUNT(*) FILTER (WHERE status = 'delivered')        AS delivered,
    COUNT(*) FILTER (WHERE status = 'cancelled')        AS cancelled,
    SUM(total) FILTER (WHERE status != 'cancelled')     AS real_revenue
FROM orders
GROUP BY month
ORDER BY month;

-- Boolean expressions
SELECT
    username,
    is_active,
    is_active AND role = 'admin'       AS is_active_admin,
    is_active OR role = 'superuser'    AS can_login,
    NOT is_active                      AS is_disabled
FROM users;

-- Simple if-then with COALESCE + NULLIF combo
SELECT
    username,
    COALESCE(NULLIF(phone, ''), NULLIF(email, ''), 'no contact') AS best_contact
FROM users;
""",
    ),
    (
        "sql/alter_table.md",
        "sql",
        ["sql", "ddl", "schema", "alter"],
        "Table Constraints & ALTER TABLE Operations",
        "ALTER TABLE ADD/DROP COLUMN, ADD/DROP CONSTRAINT, modify types, and RENAME.",
        "pattern",
        """-- Add a new column
ALTER TABLE users
ADD COLUMN phone VARCHAR(20);

-- Add column with default value (non-nullable after backfill)
ALTER TABLE users
ADD COLUMN timezone VARCHAR(50) NOT NULL DEFAULT 'UTC';

-- Drop a column
ALTER TABLE users
DROP COLUMN IF EXISTS obsolete_field;

-- Add a check constraint
ALTER TABLE orders
ADD CONSTRAINT chk_positive_total CHECK (total >= 0);

-- Add a foreign key constraint
ALTER TABLE order_items
ADD CONSTRAINT fk_oi_product
    FOREIGN KEY (product_id) REFERENCES products(id)
    ON DELETE RESTRICT;

-- Add a unique constraint
ALTER TABLE users
ADD CONSTRAINT uq_users_phone UNIQUE (phone);

-- Drop a constraint
ALTER TABLE orders
DROP CONSTRAINT IF EXISTS chk_positive_total;

-- Modify column data type
ALTER TABLE products
ALTER COLUMN price TYPE NUMERIC(12,2);

-- Set / drop column default
ALTER TABLE orders
ALTER COLUMN status SET DEFAULT 'pending';

ALTER TABLE orders
ALTER COLUMN status DROP DEFAULT;

-- Set NOT NULL / drop NOT NULL
ALTER TABLE users
ALTER COLUMN phone SET NOT NULL;

ALTER TABLE users
ALTER COLUMN phone DROP NOT NULL;

-- Rename a column
ALTER TABLE users
RENAME COLUMN full_name TO display_name;

-- Rename the table itself
ALTER TABLE old_table_name RENAME TO new_table_name;

-- Add a primary key (composite)
ALTER TABLE order_items
ADD PRIMARY KEY (order_id, product_id);

-- Enable/disable a trigger
ALTER TABLE orders DISABLE TRIGGER trg_orders_updated_at;
ALTER TABLE orders ENABLE TRIGGER trg_orders_updated_at;
""",
    ),
]
