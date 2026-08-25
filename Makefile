.PHONY: install verify test first-slice evidence verify-evidence
install:
	python3 -m pip install -e '.[test]'
verify:
	python3 tools/verify_environment.py
test:
	python3 -m pytest
first-slice:
	python3 -m brineguard run-first-slice -c configs/first_slice.yaml
evidence:
	.venv/bin/python -m brineguard make-evidence
verify-evidence:
	.venv/bin/python -m brineguard make-evidence --verify
