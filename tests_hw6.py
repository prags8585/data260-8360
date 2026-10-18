#!/usr/bin/env python3

import json
import sys
from datetime import datetime, timedelta, timezone

import file_memory as fm
from agent_memory import episodes, prompt, summaries
from agent_memory.policies import compress_window, first_sentence

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
FRESH_STAMP = "<!-- last-consolidated: 2026-10-13T11:00:00Z -->"


def facts_text(n: int, stamp: str = FRESH_STAMP) -> str:
    return stamp + "\n" + "\n".join(f"- (2026-09-01) topic_{i}: value {i}" for i in range(n)) + "\n"


def test_count_ignores_blank_and_comment_lines():
    text = "# MEMORY.md\n<!-- comment -->\n\n- (2026-09-01) a: 1\n\n<!-- another -->\n- (2026-09-01) b: 2\n"
    assert fm.count_memory_lines(text) == 3          # heading + two facts


def test_consolidation_required_over_40_lines():
    assert fm.needs_consolidation(facts_text(41), NOW)[0] is True
    assert fm.needs_consolidation(facts_text(40), NOW)[0] is False


def test_consolidation_required_when_stamp_older_than_24h():
    stale = "<!-- last-consolidated: 2026-10-11T08:00:00Z -->"
    required, reason = fm.needs_consolidation(facts_text(5, stale), NOW)
    assert required is True and "24 h" in reason
    assert fm.read_last_consolidated(facts_text(5, stale)) == datetime(2026, 10, 11, 8, 0, tzinfo=timezone.utc)


def test_consolidation_merges_duplicates_and_resolves_contradictions():
    text = ("- (2026-09-01) name: Maya Chen\n- (2026-09-02) name: Maya Chen\n"
            "- (2026-09-01) theme: dark mode\n- (2026-09-05) theme: light mode\n")
    new, rep = fm.consolidate(text, NOW)
    assert rep.duplicates_merged == 1 and len(rep.contradictions) == 1
    assert "(x2)" in new and "light mode" in new
    assert 'superseded "dark mode"' in new           # older value kept for audit, never silently dropped


def test_consolidation_of_the_55_line_memory_file():
    text = open("reports/hw06/raw/memory_consolidation/MEMORY.original.md").read()
    assert len(text.splitlines()) == 55
    new, rep = fm.consolidate(text, NOW)
    assert len(new.splitlines()) < 40
    assert rep.duplicates_merged >= 3 and len(rep.contradictions) >= 3
    for r in rep.contradictions:                       # every superseded value is still present in the output
        assert r["superseded"] in new
    assert fm.consolidate(new, NOW)[0] == new           # idempotent


def test_memory_health_report():
    report = fm.memory_health_report(facts_text(41, "<!-- last-consolidated: 2026-10-12T08:00:00Z -->"), NOW)
    assert report["entries"] == 41 and report["needs_consolidation"] is True
    assert report["age_hours"] == 28.0


def test_commands_help_and_unknown():
    assert "/compact" in fm.handle_command("/help")
    assert fm.handle_command("hello there") is None
    assert "Unknown command" in fm.handle_command("/bogus")


def test_system_prompt_contains_both_files():
    out = fm.build_system_prompt("AGENT RULES", "MEMORY FACTS")
    assert "AGENT RULES" in out and "MEMORY FACTS" in out


def test_summarization_trigger_every_m_user_messages():
    assert [summaries.should_summarize(n) for n in (0, 4, 5, 10, 11)] == [False, False, True, True, False]


def test_fact_parser_limits_and_clamps():
    raw = json.dumps({"facts": [{"fact": f"f{i}", "importance": 2 if i == 0 else 0.5} for i in range(5)]})
    facts = episodes.parse_facts(raw)
    assert len(facts) == 3 and facts[0]["importance"] == 1.0
    assert episodes.parse_facts("not json") == []


def test_prompt_assembly_order_and_components():
    window = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    messages, comp = prompt.assemble("what now?", window, "session summary", "life summary",
                                     [{"fact": "likes mornings", "importance": 0.8}])
    assert messages[0][0] == "system" and "life summary" in messages[0][1] and "session summary" in messages[0][1]
    assert messages[-1][0] == "user" and "likes mornings" in messages[-1][1]
    assert comp["episodic_facts"] > 0 and comp["short_term_window"] > 0


def test_compress_policy_shortens_old_assistant_turns_only():
    window = []
    for i in range(6):
        window += [{"role": "user", "content": f"user {i}"},
                   {"role": "assistant", "content": "First sentence here. " + "Long filler. " * 30}]
    out = compress_window(window)
    assert len(out) == len(window)
    assert out[1]["content"] == "First sentence here."          # old assistant turn compressed
    assert out[0]["content"] == "user 0"                         # user turns untouched
    assert out[-1]["content"] == window[-1]["content"]           # newest messages verbatim
    assert first_sentence("One two three. Four.") == "One two three."


def test_memory_health_report_handles_missing_stamp():
    assert fm.memory_health_report("", NOW)["last_consolidated"] is None


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]


def main() -> int:
    passed = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError as exc:
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:
            print(f"FAIL  {test.__name__}: unexpected {type(exc).__name__}: {exc}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
