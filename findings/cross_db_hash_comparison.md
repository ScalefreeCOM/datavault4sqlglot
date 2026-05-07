# Cross-Database Hash Formula Comparison

Compares `datavault4dbt` per-adapter hash macros against the current
`datavault4sqlglot` implementation (`BaseGenerator._clean_column` /
`_build_hash_expression`).

Source files compared:
- `datavault4dbt/macros/supporting/hash_standardization.sql`
- `datavault4dbt/macros/supporting/hash.sql`
- `datavault4sqlglot/generators/base.py`

---

## 1. CAST Type

| Adapter    | datavault4dbt        | Python (`_clean_column`) | Match? |
|------------|----------------------|--------------------------|--------|
| Snowflake  | `STRING`             | `VARCHAR`                | ~ sqlglot transpiles VARCHAR→STRING |
| BigQuery   | `STRING`             | `VARCHAR`                | ~ same |
| Databricks | `STRING`             | `VARCHAR`                | ~ same |
| Postgres   | `VARCHAR`            | `VARCHAR`                | ✓ |
| Redshift   | none (no CAST)       | `VARCHAR`                | ~ VARCHAR is fine |
| Synapse    | `VARCHAR(4000)`      | `VARCHAR`                | ✗ Synapse requires explicit length |
| Oracle     | `VARCHAR2(2000)`     | `VARCHAR`                | ✗ Oracle needs VARCHAR2 |
| Exasol     | `VARCHAR(20000) UTF8`| `VARCHAR`                | ✗ needs explicit length + UTF8 modifier |

---

## 2. Quote Wrapper

Each column value is wrapped as `"value"`. How the quotes are applied differs.

| Adapter    | datavault4dbt                                    | Python                    | Match? |
|------------|--------------------------------------------------|---------------------------|--------|
| Snowflake  | `CONCAT('\"', ..., '\"')` → `"val"` on ESCAPE_STRING=TRUE | `CONCAT('"', ..., '"')`   | ✓ same result on user's Snowflake |
| BigQuery   | `CONCAT('\"', ..., '\"')`                        | `CONCAT('"', ..., '"')`   | ~ functionally same |
| Databricks | `CONCAT('\"', ..., '\"')`                        | `CONCAT('"', ..., '"')`   | ~ |
| Postgres   | `'"' \|\| ... \|\| '"'`                          | `CONCAT('"', ..., '"')`   | ~ different syntax, same result |
| Redshift   | `'"' \|\| ... \|\| '"'`                          | `CONCAT('"', ..., '"')`   | ~ |
| Synapse    | `CONCAT('"', ..., '"')` + `NULLIF(..., '""')`    | `CONCAT('"', ..., '"')`   | ✗ missing `NULLIF(..., '""')` — empty string not collapsed |
| Oracle     | `'"' \|\| ... \|\| '"'` + `NULLIF(..., '""')`   | `CONCAT('"', ..., '"')`   | ✗ missing `NULLIF` |
| Exasol     | `CONCAT('"', ..., '"')` + `NULLIF(..., '""')`    | `CONCAT('"', ..., '"')`   | ✗ missing `NULLIF` |

---

## 3. Backslash Escape (`\` → `\\`)

| Adapter    | datavault4dbt                                | Python                                    | Match? |
|------------|----------------------------------------------|-------------------------------------------|--------|
| Snowflake  | `REPLACE(col, '\\', '\\\\')`                 | `REPLACE(col, CHR(92), CONCAT(CHR(92), CHR(92)))` | ~ same result; CHR() is more portable |
| BigQuery   | `REGEXP_REPLACE(col, r'\\', r'\\\\')`        | `REPLACE(col, CHR(92), ...)`              | ~ different function, same result |
| Databricks | `REGEXP_REPLACE(col, r'\\', r'\\\\')`        | `REPLACE(col, CHR(92), ...)`              | ~ |
| Postgres   | `REPLACE(col, '\\', '\\\\')`                 | `REPLACE(col, CHR(92), ...)`              | ~ |
| Oracle     | `REPLACE(col, '\\\', '\\\\\')` (Jinja-escaped)| `REPLACE(col, CHR(92), ...)`             | ~ actual SQL is identical |
| Exasol     | `REPLACE(col, '\\\', '\\\\\')` (Jinja-escaped)| `REPLACE(col, CHR(92), ...)`             | ~ |

Note: `CHR(92)` is the preferred portable form. sqlglot renders it as `CHR()` on
Snowflake/Postgres/Oracle and `CHAR()` on T-SQL/MySQL automatically.

---

## 4. Control Character Removal (newline, tab, vertical tab, carriage return)

| Adapter    | datavault4dbt method                        | Python                                  | Match? |
|------------|---------------------------------------------|-----------------------------------------|--------|
| Snowflake  | `REGEXP_REPLACE(x, char(10), '')` × 4       | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ✓ |
| BigQuery   | `REGEXP_REPLACE(x, r'\\n', '')` × 4         | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ~ BigQuery accepts CHR in regex |
| Databricks | `REGEXP_REPLACE(x, r'\\n', '')` × 4         | same                                    | ~ |
| Postgres   | `REGEXP_REPLACE(x, '\\n', '')` × 4          | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ~ |
| Redshift   | `REPLACE(x, '\\\\n', '')` × 4               | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ✗ Redshift does not support REGEXP_REPLACE the same way |
| Synapse    | `REPLACE(x, CHAR(10), '')` × 4              | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ✗ T-SQL has no REGEXP_REPLACE |
| Oracle     | `REPLACE(x, chr(10), '')` × 4               | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ~ Oracle has REGEXP_REPLACE, works fine |
| Exasol     | `REPLACE(x, char(10), '')` × 4              | `REGEXP_REPLACE(x, CHR(10), '')` × 4   | ~ Exasol has REGEXP_REPLACE |

---

## 5. Hash Function & Outer NULL Handling

| Adapter    | datavault4dbt                                                         | Python                                | Match? |
|------------|-----------------------------------------------------------------------|---------------------------------------|--------|
| Snowflake  | `IFNULL(LOWER(MD5(...)), zero_key)`                                   | `COALESCE(LOWER(MD5(...)), zero_key)` | ~ semantically equivalent |
| BigQuery   | `IFNULL(TO_HEX(MD5(...)), zero_key)`                                  | `COALESCE(LOWER(MD5(...)), zero_key)` | ✗ BigQuery MD5 returns BYTES — must use `TO_HEX()` |
| Databricks | `IFNULL(LOWER(MD5(...)), zero_key)`                                   | `COALESCE(LOWER(MD5(...)), zero_key)` | ~ |
| Postgres   | `COALESCE(LOWER(MD5(...)), zero_key)`                                 | `COALESCE(LOWER(MD5(...)), zero_key)` | ✓ |
| Redshift   | `COALESCE(LOWER(MD5(...)), zero_key)`                                 | `COALESCE(LOWER(MD5(...)), zero_key)` | ✓ |
| Synapse    | `ISNULL(LOWER(CONVERT(VARCHAR(32), HASHBYTES('MD5', ...), 2)), zero_key)` | `COALESCE(LOWER(MD5(...)), zero_key)` | ✗ T-SQL has no `MD5()` — must use `HASHBYTES` + `CONVERT` |
| Oracle     | `NVL(LOWER(CAST(standard_hash(...,'MD5') AS VARCHAR2(40))), zero_key)` | `COALESCE(LOWER(MD5(...)), zero_key)` | ✗ Oracle has no `MD5()` — must use `standard_hash()` |
| Exasol     | `NULLIF(HASH_MD5(...), zero_key)`                                     | `COALESCE(LOWER(MD5(...)), zero_key)` | ~ Exasol also supports `MD5()` |

---

## 6. TRIM Syntax

| Adapter  | datavault4dbt                    | Python          | Match? |
|----------|----------------------------------|-----------------|--------|
| Snowflake | `TRIM(CAST(...))`               | `TRIM(CAST(...))` | ✓ |
| Postgres  | `TRIM(BOTH ' ' FROM CAST(...))` | `TRIM(CAST(...))` | ~ sqlglot handles transpilation |
| Redshift  | `TRIM(BOTH ' ' FROM ...)`       | `TRIM(CAST(...))` | ~ sqlglot handles transpilation |
| Synapse   | `LTRIM(RTRIM(CAST(...)))`        | `TRIM(CAST(...))` | ~ sqlglot transpiles TRIM to LTRIM+RTRIM for T-SQL |
| Oracle    | `TRIM(CAST(...))`               | `TRIM(CAST(...))` | ✓ |

---

## Summary: What Needs Code Changes vs. What sqlglot Handles

### sqlglot handles automatically

- `VARCHAR` → `STRING` on BigQuery / Databricks / Snowflake
- `TRIM()` → `LTRIM(RTRIM(...))` on T-SQL dialects
- `CHR()` → `CHAR()` on T-SQL / MySQL
- `COALESCE(x, y)` works on all dialects (semantically identical to IFNULL/ISNULL/NVL)

### Requires explicit code changes per dialect

| Issue | Affects | Required change |
|-------|---------|----------------|
| `REGEXP_REPLACE` → `REPLACE` for control chars | Redshift, Synapse | Use `REPLACE(x, CHR(n), '')` instead of `REGEXP_REPLACE` for these dialects |
| `MD5()` → `TO_HEX(MD5())` | BigQuery | Wrap hash expression in `exp.Anonymous('TO_HEX', ...)` or dialect branch |
| `MD5()` → `HASHBYTES('MD5',...)` + `CONVERT` | Synapse | Full replacement of hash expression for T-SQL |
| `MD5()` → `standard_hash(...,'MD5')` | Oracle | Replace hash function call |
| `VARCHAR` → `VARCHAR2(2000)` | Oracle | Oracle-specific CAST type in `_clean_column` |
| `VARCHAR` → `VARCHAR(20000) UTF8` | Exasol | Exasol-specific CAST type |
| Missing `NULLIF(..., '""')` on quote wrapper | Synapse, Oracle, Exasol | Add `NULLIF` wrapping the `CONCAT('"', ..., '"')` expression |

### Priority ranking (by implementation complexity)

1. **BigQuery** — only `TO_HEX()` wrapper needed around the hash. Low effort.
2. **Postgres / Redshift** — replace `REGEXP_REPLACE` with `REPLACE` for control chars only.
3. **Exasol** — VARCHAR length + UTF8 modifier + NULLIF wrapper. Medium effort.
4. **Oracle** — `standard_hash()` + `VARCHAR2` type + NULLIF wrapper. Medium effort.
5. **Synapse** — `HASHBYTES+CONVERT` + `VARCHAR(4000)` + `CHAR()` + no `REGEXP_REPLACE`. Highest effort.
