PY := .venv/bin/python
S ?= all
# Any Python 3.11+ works; prefer the newest found.
SYSPY := $(shell for p in python3.13 python3.12 python3.11 python3; do command -v $$p >/dev/null && $$p -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null && echo $$p && break; done)

.PHONY: setup keys dev test scenario demo-check reset web web-build demo record golden

setup:
	@test -n "$(SYSPY)" || (echo "Need Python 3.11+ (python.org or brew install python)"; exit 1)
	$(SYSPY) -m venv .venv
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

web-build:
	cd web && npm run build

demo: keys
	$(PY) -m scripts.demo

# Record a LIVE LLM run of one scenario (needs Ollama). PROMOTE=1 saves it as the golden REPLAY trace
# if the outcome matches the scenario's expected result.
record:
	$(PY) -m agent.runner $(S) --mode live $(if $(PROMOTE),--promote,)

golden:
	for s in S0 S1 S2 S3 S4 S5; do $(PY) -m agent.runner $$s --mode live --promote; done
