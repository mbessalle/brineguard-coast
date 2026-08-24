# BrineGuard Coast prototype

This repository implements the offline architectural slice in `BUILD_PLAN.md` §12. It is a
synthetic screening and coordination proof, not a calibrated coastal-plume forecast or a claim of
regulatory compliance.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
python -m pytest
python -m brineguard run-first-slice --config configs/first_slice.yaml
```

The last command needs only the saved YAML config and writes the complete standard output contract
under `runs/first-slice/`. Use `--run-id another-name` for subsequent immutable runs.
