from __future__ import annotations
import argparse
from brineguard.experiments.runner import run


def main() -> None:
    parser = argparse.ArgumentParser(prog="brineguard")
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("run-first-slice", help="run the complete offline 40x60 vertical slice")
    first.add_argument("--config", "-c", required=True)
    first.add_argument("--run-id")
    args = parser.parse_args()
    if args.command == "run-first-slice":
        path = run(args.config, args.run_id)
        print(path)


if __name__ == "__main__":
    main()
