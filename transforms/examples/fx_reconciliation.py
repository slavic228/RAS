"""
Example transform: merge transaction rows with FX rates.

This function is referenced from the YAML as:
  transform:
    module: "transforms.examples.fx_reconciliation"
    function: "merge_with_rates"

It demonstrates a multi-source transform that joins a SQL result (transactions)
with an API result (FX rates) on the shared 'currency_code' column.
"""

from __future__ import annotations

import pandas as pd


def merge_with_rates(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Left-join transactions with FX rates and compute MDL-equivalent amounts.

    Expected sources:
        "transactions"  — columns: transaction_id, amount, currency_code
        "fx_rates"      — columns: currency_code, rate

    Returns a DataFrame with columns:
        transaction_id, amount, currency_code, rate, amount_mdl
    """
    transactions: pd.DataFrame = sources["transactions"]
    fx_rates: pd.DataFrame = sources["fx_rates"]

    merged = transactions.merge(fx_rates, on="currency_code", how="left")
    merged["amount_mdl"] = merged["amount"] * merged["rate"]

    return merged[["transaction_id", "amount", "currency_code", "rate", "amount_mdl"]]
