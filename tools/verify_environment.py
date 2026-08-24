#!/usr/bin/env python3
"""Cross-project-style environment check; scientific behavior stays in brineguard."""
import importlib
import json
import shutil
import sys

required = ["numpy", "scipy", "xarray", "pandas", "pyarrow", "pyomo", "highspy", "zarr", "matplotlib"]
versions = {}
missing = []
for name in required:
    try:
        module = importlib.import_module(name)
        versions[name] = getattr(module, "__version__", "installed")
    except ImportError:
        missing.append(name)
result = {"ok": not missing and sys.version_info >= (3, 11), "python": sys.version, "packages": versions,
          "missing": missing, "git": shutil.which("git") is not None}
print(json.dumps(result, indent=2))
raise SystemExit(0 if result["ok"] else 1)
