"""Convert numbers to words (English) for vouchers."""

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_thousand(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ((" " + ONES[n % 10]) if n % 10 else "")
    return ONES[n // 100] + " Hundred" + ((" and " + _under_thousand(n % 100)) if n % 100 else "")


def amount_to_words(amount: float, currency_name: str = "Naira", subunit: str = "Kobo") -> str:
    try:
        amount = float(amount)
    except Exception:
        return ""
    neg = amount < 0
    amount = abs(amount)
    whole = int(amount)
    frac = int(round((amount - whole) * 100))
    parts = []
    if whole == 0:
        parts.append("Zero")
    else:
        billions = whole // 1_000_000_000
        millions = (whole // 1_000_000) % 1000
        thousands = (whole // 1000) % 1000
        rest = whole % 1000
        if billions:
            parts.append(_under_thousand(billions) + " Billion")
        if millions:
            parts.append(_under_thousand(millions) + " Million")
        if thousands:
            parts.append(_under_thousand(thousands) + " Thousand")
        if rest:
            parts.append(_under_thousand(rest))
    words = " ".join(parts) + f" {currency_name}"
    if frac:
        words += f" and {_under_thousand(frac)} {subunit}"
    words += " Only"
    if neg:
        words = "Negative " + words
    return words
