-- Report source: Transactions (for FX enrichment)
-- Returns today's transactions with their currency codes,
-- to be merged with FX rates fetched from the API.
SELECT
    t.transaction_id,
    t.amount,
    t.currency_code
FROM
    transactions t
WHERE
    TRUNC(t.value_date) = TRUNC(SYSDATE)
    AND t.status = 'SETTLED'
ORDER BY
    t.transaction_id
