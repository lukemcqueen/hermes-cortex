---
language: sql
tags: [sql, functions, strings, dates]
title: String & Date Functions
description: UPPER/LOWER, TRIM, SUBSTRING, REPLACE, CONCAT, EXTRACT, DATE_TRUNC, and AT TIME ZONE.
source: pattern
---

```sql
-- String case conversion
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

```
