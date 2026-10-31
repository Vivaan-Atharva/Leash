"""Money is integer paise everywhere. These helpers only format for humans."""


def _group_indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def inr(paise: int) -> str:
    """4500 -> '₹45', 396000 -> '₹3,960', 4550 -> '₹45.50', -100 -> '-₹1'."""
    if not isinstance(paise, int) or isinstance(paise, bool):
        raise TypeError("paise must be int")
    sign = "-" if paise < 0 else ""
    rupees, p = divmod(abs(paise), 100)
    out = f"{sign}₹{_group_indian(rupees)}"
    return out + (f".{p:02d}" if p else "")


def rupees(r: int) -> int:
    """Whole rupees -> paise."""
    return r * 100
