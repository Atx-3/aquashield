"""
AQUA SHIELD AI Intent & Tool Routing Interactive CLI.

Enters an interactive loop by default, sending user requests to the local
Qwen3 1.7B model via Ollama and displaying the validated intent and arguments.

This is a stand-alone test tool for the AI router (the web app uses the router through
backend/voice_assistant.py instead). Three ways to run it:
    python main.py                     -> interactive: type commands one by one
    python main.py --query "forecast"  -> answer one command and exit
    python main.py --demo              -> run 6 built-in sample commands
"""

import argparse
import sys

from app.llm import OllamaClient
from app.router import AquaShieldRouter


def run_interactive():
    """Run interactive prompt loop for testing AQUA SHIELD investigation commands."""
    print("=================================================================")
    print("        AQUA SHIELD AI - Oil Spill Investigation Intent Router        ")
    print("                 Powered by Qwen3 1.7B (Ollama)                  ")
    print("=================================================================")

    # Check that the Ollama server is reachable before starting; exit with an error if not
    client = OllamaClient()
    if not client.is_available():
        print(f"\n[!] Error: Cannot connect to Ollama at {client.base_url}")
        print("    Please ensure the Ollama service is running ('ollama serve')")
        print("    and the model is pulled ('ollama pull qwen3:1.7b').\n")
        sys.exit(1)

    print(f"[*] Connected to Ollama at: {client.base_url}")
    print(f"[*] Active Model: {client.model_name}")
    print(f"[*] Request Timeout: {client.timeout}s")
    print("\nAvailable Investigation Commands:")
    print("  - analyze_spill         - find_probable_origin")
    print("  - find_nearby_vessels   - get_vessel_trajectory")
    print("  - compare_vessels       - forecast_spill")
    print("  - get_evidence          - generate_report")
    print("\nType your natural language request below, or type 'exit' / 'quit' to stop.")
    print("-----------------------------------------------------------------")

    router = AquaShieldRouter(llm_client=client, verbose=True)

    # Read-route-print loop until the user types exit/quit or presses Ctrl+C
    while True:
        try:
            print("\nEnter AQUA SHIELD command:")
            user_input = input(">> ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q", ":q"}:
                print("\nExiting AQUA SHIELD AI Router. Goodbye!")
                break

            # Send the text to the LLM, validate its answer, and print the final JSON
            result = router.route(user_input)
            print("\n[Final Validated Response JSON]")
            print(result.to_json(indent=2))

        # Ctrl+C (KeyboardInterrupt) or end of input (EOFError) -> exit cleanly
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting AQUA SHIELD AI Router. Goodbye!")
            break


def run_single_query(query: str):
    """Execute a single query against Ollama and exit."""
    client = OllamaClient()
    if not client.is_available():
        print(f"[!] Error: Cannot connect to Ollama at {client.base_url}")
        sys.exit(1)

    router = AquaShieldRouter(llm_client=client, verbose=True)
    result = router.route(query)
    print("\n[Final Validated Response JSON]")
    print(result.to_json(indent=2))


def run_batch_demo():
    """Optional batch test runner, only executed if --demo is explicitly passed."""
    client = OllamaClient()
    if not client.is_available():
        print(f"[!] Error: Cannot connect to Ollama at {client.base_url}")
        sys.exit(1)

    router = AquaShieldRouter(llm_client=client, verbose=True)
    # The last query is deliberately off-topic: it should come back as "unsupported"
    sample_queries = [
        "Show me vessels near the spill.",
        "Find vessels within 20 km of the spill.",
        "Where did this oil spill come from?",
        "Forecast the spill drift for the next 24 hours.",
        "Generate final investigation report as a PDF.",
        "What is the capital of France?",
    ]

    print(f"Running {len(sample_queries)} sample queries in batch mode...\n")
    for i, q in enumerate(sample_queries, 1):
        print(f"\n>>> Query {i}/{len(sample_queries)}: {q}")
        res = router.route(q)
        print(res.to_json(indent=2))


def main():
    # Parse command-line flags (--query / --demo) to choose the mode
    parser = argparse.ArgumentParser(
        description="AQUA SHIELD AI Intent & Tool Routing Layer"
    )
    parser.add_argument(
        "--query", "-q", type=str, help="Run a single natural language query and exit"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Run optional batch demo queries (explicit only)"
    )

    args = parser.parse_args()

    if args.query:
        run_single_query(args.query)
    elif args.demo:
        run_batch_demo()
    else:
        # Default behavior: Interactive CLI
        run_interactive()


if __name__ == "__main__":
    main()
