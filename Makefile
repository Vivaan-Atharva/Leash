PY := .venv/bin/python
S ?= all

.PHONY: setup keys dev test scenario demo-check reset web demo

setup:
	python3.12 -m venv .venv
	$(PY) -m pip install -q -r requirements.txt
	$(MAKE) keys
	cd web && npm install

keys:
	$(PY) -m scripts.gen_keys

dev: keys
	$(PY) -m scripts.dev

test: keys
	$(PY) -m pytest -q

scenario:
	$(PY) -m agent.run_scenarios $(S)

demo-check:
	$(PY) -m scripts.demo_check

reset:
	curl -s -X POST http://127.0.0.1:8000/demo/reset; echo

web:
	cd web && npm run dev
