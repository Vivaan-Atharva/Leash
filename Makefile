PY := .venv/bin/python
S ?= all
# MODEL=llama3.1:8b picks another Ollama model for the agent (shown on Mission Control).
ifdef MODEL
export LEASH_MODEL := $(MODEL)
endif
# Any Python 3.11+ works; prefer the newest found.
SYSPY := $(shell for p in python3.13 python3.12 python3.11 python3; do command -v $$p >/dev/null && $$p -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null && echo $$p && break; done)

.PHONY: setup keys dev test scenario demo-check reset web web-build demo record golden eval chart doctor bench

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
	$(PY) -m scripts.golden $(if $(LOOSE),--loose,)

# Is this laptop ready? (Python, Node, Ollama, model, ports, keys, disk, power, golden traces)
doctor:
	$(PY) -m scripts.doctor

# How fast is the model at one tool-calling step, and does it fall for the hidden "buy 40"?
bench:
	$(PY) -m scripts.bench

# Eval: LIVE (all 4 defences) if Ollama is up, else SCRIPTED (3 defences). Needs services running (`make dev`).
eval:
	$(PY) -m eval.harness $(if $(MODE),--mode $(MODE),) $(if $(RUNS),--runs $(RUNS),)

chart:
	$(PY) -m eval.chart
