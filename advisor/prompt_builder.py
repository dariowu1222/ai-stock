def build_strategy_prompt(user_need: str, market_context: dict) -> str:
    """Return a local prompt string for future LLM integration.

    The MVP does not send this prompt to any model. It is kept only to preserve
    the planned module boundary.
    """
    return (
        "請依據使用者需求與市場情境，建議可回測的策略模板與參數。"
        f"\n使用者需求：{user_need}"
        f"\n市場情境：{market_context}"
    )
