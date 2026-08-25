from __future__ import annotations
import argparse
from brineguard.experiments.runner import run
from brineguard.experiments.benchmark import run_benchmark
from brineguard.experiments.ensemble import run_ensemble
from brineguard.experiments.sensitivity import run_sensitivity


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
    ens = sub.add_parser("run-ensemble", help="run the common-schedule ensemble evaluation")
    ens.add_argument("--config", "-c", required=True)
    ens.add_argument("--members", type=int, default=20)
    ens.add_argument("--seed", type=int, default=None)
    ens.add_argument("--run-id")
    ens.add_argument("--output-root", default="runs")
    sens = sub.add_parser("run-sensitivity", help="run the Pareto frontier and sensitivity sweep")
    sens.add_argument("--config", "-c", required=True)
    sens.add_argument("--run-id")
    sens.add_argument("--n-points", type=int, default=8)
    sens.add_argument("--output-root", default="runs")
    args = parser.parse_args()
    if args.command == "run-first-slice":
        path = run(args.config, args.run_id)
        print(path)
    elif args.command == "run-benchmark":
        path = run_benchmark(args.configs, args.run_id, args.output_root)
        print(path)
    elif args.command == "run-ensemble":
        path = run_ensemble(args.config, args.run_id, n_members=args.members,
                            seed=args.seed, output_root=args.output_root)
        print(path)
    elif args.command == "run-sensitivity":
        path = run_sensitivity(args.config, args.run_id, n_points=args.n_points,
                               output_root=args.output_root)
        print(path)


if __name__ == "__main__":
    main()
