PY := .venv/bin/python
S ?= all

.PHONY: setup keys dev test scenario demo-check reset web web-build demo record golden

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
