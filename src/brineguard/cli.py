from __future__ import annotations
import argparse
from brineguard.experiments.runner import run
from brineguard.experiments.benchmark import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(prog="brineguard")
    sub = parser.add_subparsers(dest="command", required=True)
    first = sub.add_parser("run-first-slice", help="run the complete offline 40x60 vertical slice")
    first.add_argument("--config", "-c", required=True)
    first.add_argument("--run-id")
    bench = sub.add_parser("run-benchmark", help="run the three-strategy benchmark harness")
    bench.add_argument("--config", "-c", action="append", dest="configs", required=True,
                        help="config path (repeatable)")
    bench.add_argument("--run-id", required=True)
    bench.add_argument("--output-root", default="runs")
    args = parser.parse_args()
    if args.command == "run-first-slice":
        path = run(args.config, args.run_id)
        print(path)
    elif args.command == "run-benchmark":
        path = run_benchmark(args.configs, args.run_id, args.output_root)
        print(path)


if __name__ == "__main__":
    main()
