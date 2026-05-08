import pandas as pd


def rank_screening_result(df: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    return (
        df.sort_values(["technical_score", "signal_date"], ascending=[False, False])
        .head(int(top_n))
        .reset_index(drop=True)
    )
