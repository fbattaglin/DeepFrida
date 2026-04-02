#!/usr/bin/env python3
"""
Interactive REPL for local LLM inference via Ollama.

Usage:
    python repl.py
    python repl.py --model deepseek-r1:14b --temperature 0.6 --ctx 2048

Commands inside the REPL:
    /reset              clear conversation history
    /stats              show turn count and estimated token usage
    /system <text>      set a new system prompt (clears history)
    /model <name>       switch model mid-session (clears history)
    /options            show current inference options
    /set <key> <value>  change an option live (e.g. /set temperature 0.2)
    /quit               exit
"""

import argparse

from ollama_client import ChatSession, is_model_loaded, warmup, DEFAULT_MODEL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ollama interactive REPL")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--system", default="", help="System prompt")
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--ctx", type=int, default=4096, dest="num_ctx")
    parser.add_argument("--no-warmup", action="store_true")
    return parser.parse_args()


def print_header(model: str, options: dict):
    print(f"\n{'=' * 56}")
    print(f"  Ollama REPL — {model}")
    print(f"  temp={options['temperature']}  ctx={options['num_ctx']}")
    print(f"  Commands: /reset /stats /system /model /set /quit")
    print(f"{'=' * 56}\n")


def handle_command(cmd: str, session: ChatSession) -> bool:
    """
    Process a slash command.
    Returns True to keep the REPL running, False to quit.
    """
    parts = cmd.strip().split(maxsplit=1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb == "/quit":
        return False

    elif verb == "/reset":
        session.reset()
        print("[history cleared]")

    elif verb == "/stats":
        print(f"  Model         : {session.model}")
        print(f"  History turns : {session.turn_count}")
        print(f"  Approx tokens : {session.approx_tokens}")
        print(f"  Options       : {session.options}")

    elif verb == "/options":
        for k, v in session.options.items():
            print(f"  {k} = {v}")

    elif verb == "/system":
        if not arg:
            print(f"  Current system prompt: {session.system!r}")
        else:
            session.system = arg
            session.reset()
            print("[system prompt updated, history cleared]")

    elif verb == "/model":
        if not arg:
            print(f"  Current model: {session.model}")
        else:
            session.model = arg
            session.reset()
            print(f"[switched to {arg}, history cleared]")
            try:
                if not is_model_loaded(arg):
                    print(f"  Loading {arg}...", end=" ", flush=True)
                    t = warmup(arg)
                    print(f"ready in {t}s")
            except RuntimeError as e:
                print(f"  Warning: {e}")

    elif verb == "/set":
        kv = arg.split(maxsplit=1)
        if len(kv) != 2:
            print("  Usage: /set <key> <value>")
        else:
            key, val = kv
            try:
                session.options[key] = float(val) if "." in val else int(val)
            except ValueError:
                session.options[key] = val
            print(f"  {key} = {session.options[key]}")

    else:
        print(f"  Unknown command: {verb}")

    return True


def main():
    args = parse_args()

    options = {
        "temperature": args.temperature,
        "num_ctx": args.num_ctx,
    }

    try:
        if not args.no_warmup and not is_model_loaded(args.model):
            print(f"Loading {args.model}...", end=" ", flush=True)
            t = warmup(args.model)
            print(f"ready in {t}s")
    except RuntimeError as e:
        print(f"Error: {e}")
        raise SystemExit(1)

    session = ChatSession(
        model=args.model,
        system=args.system,
        options=options,
    )

    print_header(args.model, options)

    while True:
        try:
            user_input = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            if not handle_command(user_input, session):
                break
            continue

        short_name = session.model.split(":")[0]
        print(f"\n{short_name}> ", end="", flush=True)
        session.chat(user_input)
        print()


if __name__ == "__main__":
    main()
