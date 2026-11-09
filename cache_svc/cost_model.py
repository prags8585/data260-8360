"""HW9 Part 3.4 cost model. The prices were fixed before the sweep was run and are not tuned to its results.

cache miss        = one agent-pipeline run (Planner + Writer model calls, about 3k tokens in total). At hosted-model prices
                    (~$3 / 1M input and ~$15 / 1M output tokens) that is about one cent.
cache hit         = one embedding, one vector search and one MySQL version check; compute is negligible but not zero.
false hit/support = a student is told the seats, instructor or title of the WRONG course, notices (or does not) and a
                    registrar/support person spends about three minutes at ~$20/hour to correct it, plus the risk of a
                    wrong enrolment decision; set to $1.00, one hundred times a miss.
"""

COST_MISS = 0.01
COST_HIT = 0.0001
COST_FALSE_HIT = 1.00


def total_cost(hits: int, misses: int, false_hits: int) -> float:
    return round(misses * COST_MISS + hits * COST_HIT + false_hits * COST_FALSE_HIT, 4)
