import json
from pathlib import Path

from src.model_client import ModelClient

AGENT_MD_PATH = Path("AGENT.md")


def load_system_prompt() -> str:
    return AGENT_MD_PATH.read_text()


def print_turn_usage(result):
    print(f"[tokens] input: {result.input_tokens}  output: {result.output_tokens}  total: {result.total_tokens}")


def print_stats(client, history):
    stats = client.stats()
    serialized_len = len(json.dumps(history))
    print("\n----- /stats -----")
    print(f"Turn count                 : {stats['turn_count']}")
    print(f"Cumulative input tokens    : {stats['cumulative_input_tokens']}")
    print(f"Cumulative output tokens   : {stats['cumulative_output_tokens']}")
    print(f"Cumulative total tokens    : {stats['cumulative_total_tokens']}")
    print(f"Serialized history length  : {serialized_len} chars")
    print("------------------\n")


def main():
    client = ModelClient(model="qwen3:8b", temperature=0.0)
    history = [("system", load_system_prompt())]

    print("hw1_client -- type a message, '/stats' for usage, or 'exit'/'quit' to end.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except EOFError:
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break
        if user_input == "/stats":
            print_stats(client, history)
            continue

        history.append(("user", user_input))
        print(f"\n=== Turn {client.turn_count + 1} ===")
        print(f"User: {user_input}")
        result = client.complete(history)
        history.append(("assistant", result.content))

        print(f"Assistant:\n{result.content}\n")
        print_turn_usage(result)
        print()

    # Part 4.4: on exit, print cumulative input tokens, output tokens, and turn count.
    final = client.stats()
    print("\n========== FINAL TOTALS ==========")
    print(f"Total turns              : {final['turn_count']}")
    print(f"Cumulative input tokens  : {final['cumulative_input_tokens']}")
    print(f"Cumulative output tokens : {final['cumulative_output_tokens']}")
    print(f"Cumulative total tokens  : {final['cumulative_total_tokens']}")


if __name__ == "__main__":
    main()
