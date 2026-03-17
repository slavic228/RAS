-- Report: Account Balances
-- Returns end-of-day account balances for all active accounts.
SELECT
    a.account_id,
    a.account_name,
    a.currency_code,
    b.closing_balance,
    b.balance_date
FROM
    accounts a
    JOIN daily_balances b ON a.account_id = b.account_id
WHERE
    b.balance_date = TRUNC(SYSDATE)
    AND a.status = 'ACTIVE'
ORDER BY
    a.account_name
