-- Precondition check: returns a non-null value when the EOD batch has completed.
-- Must return exactly one row and one column.
-- Precondition passes when the value is NOT NULL and NOT empty string.
SELECT
    MAX(completed_at) AS batch_completed_at
FROM
    batch_jobs
WHERE
    job_name = 'EOD_RECONCILIATION'
    AND TRUNC(completed_at) = TRUNC(SYSDATE)
