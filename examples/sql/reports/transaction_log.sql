-- Report: Transaction Log
-- Returns all transactions processed today from the DWH.
SELECT
    t.transaction_id,
    t.account_id,
    t.transaction_type,
    t.amount,
    t.currency_code,
    t.processed_at,
    t.status
FROM
    dbo.transactions t
WHERE
    CAST(t.processed_at AS DATE) = CAST(GETDATE() AS DATE)
ORDER BY
    t.processed_at DESC
