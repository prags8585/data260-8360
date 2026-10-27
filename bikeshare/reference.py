import re
from dataclasses import dataclass

from bikeshare.tools import TripStore


@dataclass
class Rates:
    unlock: float = 1.00          # single ride: unlock fee
    classic_per_min: float = 0.19  # single ride: classic bike
    ebike_per_min: float = 0.49    # single ride: ebike
    pass_fee: float = 29.00        # month pass, per month
    free_minutes: int = 45         # month pass: free minutes per classic ride
    member_over_per_min: float = 0.17  # month pass: classic minutes after the free 45
    member_ebike_per_min: float = 0.17  # month pass: every ebike minute (unlock is free)


def _block_rules(lines: list[str], plan: str, label: str) -> list[str]:
    """The rule lines listed under `label` (e.g. 'Classic bike prices') in the block that starts at the line `plan` + a bare price."""
    for i, line in enumerate(lines[:-1]):
        if line == plan and lines[i + 1].startswith("$"):
            tail = lines[i:]
            if label in tail:
                start = tail.index(label) + 1
                return tail[start:start + 5]
    return []


def _num(pattern: str, text: str, default: float) -> float:
    m = re.search(pattern, text)
    return float(m.group(1)) if m else default


def rates_from_snapshot(text: str) -> Rates:
    """Read the rates out of the saved pricing-page text. On the Bay Wheels page every plan block lists the rules of the five plans in
    the order Single ride, Day pass, Month pass, Lyft Bike, Lyft Pink, so the Single ride rule is entry 1 and the Month pass rule entry 3."""
    lines = text.split("\n")
    classic, ebike = _block_rules(lines, "Month pass", "Classic bike prices"), _block_rules(lines, "Month pass", "Ebike prices")
    if len(classic) < 3 or len(ebike) < 3:
        return Rates()
    return Rates(
        unlock=_num(r"\$(\d+(?:\.\d+)?) to unlock", classic[0], 1.00),
        classic_per_min=_num(r"then \$(\d+(?:\.\d+)?)/min", classic[0], 0.19),
        ebike_per_min=_num(r"\+ \$(\d+(?:\.\d+)?)/min", ebike[0], 0.49),
        pass_fee=_num(r"\$(\d+(?:\.\d+)?)/month", text, 29.00),
        free_minutes=int(_num(r"(\d+) min free", classic[2], 45)),
        member_over_per_min=_num(r"then \$(\d+(?:\.\d+)?)/min", classic[2], 0.17),
        member_ebike_per_min=_num(r"\+ \$(\d+(?:\.\d+)?)/min", ebike[2], 0.17),
    )


def reference_costs(store: TripStore, rates: Rates) -> dict:
    rows = store.con.execute("SELECT duration_min, is_ebike, week_start, started_at FROM trips ORDER BY started_at").fetchall()
    ppu = member_residual = 0.0
    weekly: dict[str, dict] = {}
    for minutes, is_ebike, week, _ in rows:
        cost = rates.unlock + (rates.ebike_per_min if is_ebike else rates.classic_per_min) * minutes
        over = rates.member_ebike_per_min * minutes if is_ebike else rates.member_over_per_min * max(minutes - rates.free_minutes, 0)
        ppu += cost
        member_residual += over
        w = weekly.setdefault(week, {"week_start": week, "rides": 0, "minutes": 0.0, "spend": 0.0})
        w["rides"] += 1
        w["minutes"] += minutes
        w["spend"] += cost
    first, last = rows[0][3][:7], rows[-1][3][:7]
    months = (int(last[:4]) - int(first[:4])) * 12 + int(last[5:7]) - int(first[5:7]) + 1
    membership_total = rates.pass_fee * months + member_residual
    n = len(rows)
    return {
        "rides": n, "months_spanned": months, "pay_per_use_total": round(ppu, 2), "membership_fee_total": round(rates.pass_fee * months, 2),
        "membership_residual": round(member_residual, 2), "membership_total": round(membership_total, 2),
        "decision": "Buy Monthly Membership" if membership_total < ppu else "Pay Per Ride/Minute",
        "avg_ppu_per_ride": round(ppu / n, 4), "break_even_rides_per_month": round(rates.pass_fee / (ppu / n), 2),
        "actual_rides_per_month": round(n / months, 2),
        "weekly": [{"week_start": w["week_start"], "rides": w["rides"], "avg_min": round(w["minutes"] / w["rides"], 1), "spend": round(w["spend"], 2)}
                   for w in sorted(weekly.values(), key=lambda x: x["week_start"])],
    }
