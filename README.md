# BrineGuard Coast prototype

This repository implements the offline architectural slice in `BUILD_PLAN.md` §12. It is a
synthetic screening and coordination proof, not a calibrated coastal-plume forecast or a claim of
regulatory compliance.

```bash
uv venv .venv   # or: python3 -m venv .venv -- fails on systems without python3-venv installed
. .venv/bin/activate
uv pip install -e '.[test]'   # or: python -m pip install -e '.[test]'
python -m pytest
python -m brineguard run-first-slice --config configs/first_slice.yaml

# Phase 3-5 pipelines (see BUILD_PLAN.md):
python -m brineguard run-benchmark --config configs/phase3.yaml --config configs/phase3_tidal.yaml --run-id headline
python -m brineguard run-ensemble -c configs/phase3_tidal.yaml --members 20 --seed 20260825 --run-id ens
python -m brineguard run-sensitivity -c configs/phase3.yaml --run-id sens
make evidence          # frozen evidence bundle per FREEZE.md
make verify-evidence   # reproducibility gate
```

The last command needs only the saved YAML config and writes the complete standard output contract
under `runs/first-slice/`. Use `--run-id another-name` for subsequent immutable runs.
