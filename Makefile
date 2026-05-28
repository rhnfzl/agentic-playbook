.PHONY: install check eval test new doctor doctor-verify help list status update remove sync-mattpocock sync-curated-skills sync-distribution sync-distribution-memory init audit audit-security targets-list targets-doctor trajectory-check verify-trajectory trajectory-coverage-ratio trajectory-calibrate record-trajectory ai-bom telemetry-init telemetry-stop telemetry-report telemetry-collector-py

PYTHON ?= python3

help:
	@echo "Coding Agents Playbook - available targets:"
	@echo ""
	@echo "  make install                       Interactive: detect installed agents, materialize files"
	@echo "                                     (prompts for target project directory)"
	@echo "  make install TARGET=/path          Non-interactive target, still prompts for agents"
	@echo "  make install AGENTS=auto           Use all detected agents (requires TARGET)"
	@echo "  make install AGENTS=auto TARGET=/path"
	@echo "                                     Fully non-interactive install"
	@echo "  make list                          List installed playbook content per adapter"
	@echo "  make status                        Show installed vs playbook drift summary"
	@echo "  make update                        Re-materialize playbook content into current adapters"
	@echo "  make remove                        Remove materialized playbook content per adapter"
	@echo "  make audit                         Run external-skill security audit (block-by-default)"
	@echo "  make audit-security                Run supply-chain gate: Snyk scanner + skill-evaluator + DDIPE + AI-BOM"
	@echo "                                     STRICT_SECURITY=1 escalates skipped wrappers to errors"
	@echo "  make ai-bom                        Regenerate docs/security/ai-bom.json without other checks"
	@echo "  make telemetry-init                Bring up the OTLP collector (docker-compose, opt-in)"
	@echo "  make telemetry-stop                Stop the OTLP collector"
	@echo "  make telemetry-collector-py        Run the pure-Python OTLP collector (no docker)"
	@echo "  make telemetry-report              Per-skill 30d trigger count + latency + tokens"
	@echo "                                     Set TELEMETRY=off to disable every telemetry path"
	@echo "  make sync-mattpocock               Pull mattpocock/skills updates into skills/imported/mattpocock/"
	@echo "  make sync-distribution MANIFEST=/path/to/manifest.toml"
	@echo "                                     Sync base/ to external destination per ADR-0042 (manifest-driven)"
	@echo "  make sync-distribution-memory MANIFEST=/path/to/manifest.toml"
	@echo "                                     Port curated memory entries to external destination"
	@echo "  make init TARGET=/path             Per-project init: scaffold AGENTS.md + .playbook-config.yaml"
	@echo "  make trajectory-check              Live trajectory matrix (default MAX_SPAWNS=8 cap)"
	@echo "                                     Overrides: SKILL=<name> ADAPTER=<name> JUDGE=1"
	@echo "                                     STRICT=1 MAX_SPAWNS=N MAX_JUDGE_CALLS=N MAX_RETRIES=N DRY_RUN=1"
	@echo "  make check                         Full check: frontmatter, AGENTS.md, audit, size, decay, em-dash, no-versions"
	@echo "  make eval                          Run skill eval suites (LLM-judge driven; slower)"
	@echo "  make test                          Adapter smoke tests + pytest lifecycle scenarios"
	@echo "  make new SKILL=<name>              Scaffold a new skill (in skills/<category>/<name>/)"
	@echo "                                     Optional: CATEGORY=engineering|productivity|observability|meta"
	@echo "  make new TRAJECTORY=<skill>:<scenario>"
	@echo "                                     Scaffold a new trajectory under base/trajectories/<skill>/"
	@echo "  make doctor                        Diagnose setup: which agents detected, which not, why"
	@echo "  make doctor-verify                 Layer-3 verify: lockfile vs native config vs on-disk (ADR-0036)"
	@echo "  make targets-list                  Multi-project: list every target where init has been run"
	@echo "  make targets-doctor                Multi-project: report registry state (read-only by default)"
	@echo "  make targets-doctor PRUNE=1        Multi-project: report + prune entries pointing at missing dirs"
	@echo ""

install:
	@$(PYTHON) scripts/install.py \
		$(if $(filter auto,$(AGENTS)),--non-interactive) \
		$(if $(TARGET),--target $(TARGET)) \
		$(if $(PROFILE),--profile $(PROFILE))

list:
	@$(PYTHON) scripts/install.py --list

status:
	@$(PYTHON) scripts/install.py --status \
		$(if $(TARGET),--target $(TARGET)) \
		$(if $(PROFILE),--profile $(PROFILE))

update:
	@$(PYTHON) scripts/install.py --update \
		$(if $(TARGET),--target $(TARGET)) \
		$(if $(PROFILE),--profile $(PROFILE))

remove:
	@$(PYTHON) scripts/install.py --remove \
		$(if $(TARGET),--target $(TARGET))

audit:
	@$(PYTHON) scripts/audit_external_skill.py

audit-security:
	@$(PYTHON) scripts/audit_security.py

ai-bom:
	@$(PYTHON) scripts/security/ai_bom.py

telemetry-init:
	@if [ "$$TELEMETRY" = "off" ] || [ "$$TELEMETRY_ENABLED" = "0" ] || [ "$$PLAYBOOK_TELEMETRY" = "off" ]; then \
		echo "  .  telemetry disabled (TELEMETRY=off); refusing to start collector"; \
		exit 0; \
	fi
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "  x  docker not on PATH; use 'make telemetry-collector-py' instead"; \
		exit 1; \
	fi
	@cd scripts/telemetry/otel_collector && docker compose up -d

telemetry-stop:
	@cd scripts/telemetry/otel_collector && docker compose down 2>/dev/null || true

telemetry-collector-py:
	@$(PYTHON) scripts/telemetry/pyotel_collector.py

telemetry-report:
	@$(PYTHON) scripts/skill_telemetry_report.py $(if $(DAYS),--days $(DAYS)) $(if $(JSON),--json)

sync-mattpocock:
	@bash scripts/sync_mattpocock.sh

sync-curated-skills:
	@$(PYTHON) scripts/sync_curated_skills.py

sync-distribution:
	@if [ -z "$(MANIFEST)" ]; then echo "Usage: make sync-distribution MANIFEST=/path/to/manifest.toml [DRY_RUN=1]"; exit 1; fi
	@$(PYTHON) scripts/sync_distribution.py --manifest "$(MANIFEST)" $(if $(DRY_RUN),--dry-run,)

sync-distribution-memory:
	@if [ -z "$(MANIFEST)" ]; then echo "Usage: make sync-distribution-memory MANIFEST=/path/to/manifest.toml [DRY_RUN=1]"; exit 1; fi
	@$(PYTHON) scripts/sync_distribution.py memory --manifest "$(MANIFEST)" $(if $(DRY_RUN),--dry-run,)

init:
	@if [ -z "$(TARGET)" ]; then echo "Usage: make init TARGET=/path/to/project"; exit 1; fi
	@$(PYTHON) scripts/playbook_init.py --target "$(TARGET)"

check:
	@$(PYTHON) scripts/check.py

eval:
	@$(PYTHON) scripts/eval_runner.py

test:
	@$(PYTHON) scripts/test_adapters.py
	@$(PYTHON) -m pytest tests/ -q

new:
	@if [ -n "$(TRAJECTORY)" ]; then \
		colons=$$(printf %s "$(TRAJECTORY)" | tr -cd ':' | wc -c | tr -d ' '); \
		if [ "$$colons" != "1" ]; then \
			echo "error: TRAJECTORY must be exactly <skill>:<scenario> with one colon (got $$colons)"; \
			exit 1; \
		fi; \
		skill=$$(printf %s "$(TRAJECTORY)" | cut -d: -f1); \
		scenario=$$(printf %s "$(TRAJECTORY)" | cut -d: -f2); \
		if [ -z "$$skill" ] || [ -z "$$scenario" ]; then \
			echo "Usage: make new TRAJECTORY=<skill>:<scenario>"; exit 1; \
		fi; \
		$(PYTHON) scripts/new_trajectory.py --skill "$$skill" --scenario "$$scenario"; \
	elif [ -n "$(SKILL)" ]; then \
		$(PYTHON) scripts/new_skill.py --name "$(SKILL)" --category "$(if $(CATEGORY),$(CATEGORY),engineering)" --scope "$(if $(SCOPE),$(SCOPE),base)"; \
	else \
		echo "Usage: make new SKILL=<name> [CATEGORY=<cat>] [SCOPE=base|team]"; \
		echo "   or: make new TRAJECTORY=<skill>:<scenario>"; \
		exit 1; \
	fi

trajectory-check:
	@$(PYTHON) scripts/trajectory_harness.py \
		$(if $(SKILL),--skill "$(SKILL)") \
		$(if $(ADAPTER),--adapter "$(ADAPTER)") \
		$(if $(STRICT),--strict) \
		$(if $(JUDGE),--judge) \
		$(if $(MAX_SPAWNS),--max-spawns $(MAX_SPAWNS),--max-spawns 8) \
		$(if $(MAX_JUDGE_CALLS),--max-judge-calls $(MAX_JUDGE_CALLS)) \
		$(if $(MAX_RETRIES),--max-retries $(MAX_RETRIES)) \
		$(if $(DRY_RUN),--dry-run)

verify-trajectory:
	@if [ -z "$(SKILL)" ] || [ -z "$(SCENARIO)" ]; then \
		echo "Usage: make verify-trajectory SKILL=<name> SCENARIO=<name> FIXTURE=<path>"; exit 1; \
	fi
	@$(PYTHON) scripts/trajectory_verify.py --skill "$(SKILL)" --scenario "$(SCENARIO)" \
		$(if $(FIXTURE),--fixture "$(FIXTURE)")

trajectory-coverage-ratio:
	@$(PYTHON) scripts/trajectory_coverage.py $(if $(JSON),--json)

trajectory-calibrate:
	@if [ -z "$(SKILL)" ] || [ -z "$(SCENARIO)" ]; then \
		echo "Usage: make trajectory-calibrate SKILL=<name> SCENARIO=<name> [RUNS=N] [JSON=1]"; exit 1; \
	fi
	@$(PYTHON) scripts/trajectory_calibrate.py \
		--skill "$(SKILL)" --scenario "$(SCENARIO)" \
		$(if $(RUNS),--runs $(RUNS)) \
		$(if $(JSON),--json)

record-trajectory:
	@if [ -z "$(SKILL)" ] || [ -z "$(SCENARIO)" ] || [ -z "$(PROMPT)" ]; then \
		echo "Usage: make record-trajectory SKILL=<name> SCENARIO=<name> PROMPT=\"<user prompt>\""; exit 1; \
	fi
	@$(PYTHON) scripts/trajectory_record.py \
		--skill "$(SKILL)" --scenario "$(SCENARIO)" --prompt "$(PROMPT)"

doctor:
	@$(PYTHON) scripts/install.py --diagnose

doctor-verify:
	@$(PYTHON) scripts/install.py --verify \
		$(if $(TARGET),--target $(TARGET))

targets-list:
	@$(PYTHON) -c "import sys; sys.path.insert(0, 'scripts'); from target_registry import cmd_targets_list; sys.exit(cmd_targets_list())"

targets-doctor:
	@$(PYTHON) -c "import os, sys; sys.path.insert(0, 'scripts'); from target_registry import cmd_targets_doctor; sys.exit(cmd_targets_doctor(prune=os.environ.get('PRUNE', '').lower() in {'1', 'true', 'yes', 'on'}))"
