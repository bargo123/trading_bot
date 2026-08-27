# Research Factory Integrity Design

## Goal

Make `aegis.research_factory` an auditable, research-only orchestrator that uses real point-in-time data, real model training, executable hypotheses, broker-native replay costs, governed experiment persistence, and one sealed evaluation per frozen candidate and dataset fingerprint.

## Safety Constraints

- Never place orders or access a live account. MT5 access is read-only.
- Never edit live trading YAML or runner configuration.
- Never write `intel/intelligent_champion.json` outside the governed promotion scripts and gates.
- Record every attempted experiment through `ExperimentRegistry`, including failed and non-executable attempts.
- Never synthesize data, labels, hypotheses, costs, trades, model metrics, replay metrics, AI output, or successful status.
- Missing evidence fails closed as `NO_DATA`, `NO_EVIDENCE`, `NOT_EXECUTABLE`, or an explicit failed experiment.
- Features never inspect future observations. Labels may use matured future outcomes only after the decision timestamp and must be purged across split boundaries.
- Research remains net of observed or broker-native costs.
- The factory remains stopped until focused and full verification pass.

## Architecture

`ResearchFactory` remains the public CLI and orchestration boundary. Domain behavior delegates to the existing governed modules under `aegis.research`, `aegis.intel`, and `ai_council` rather than maintaining parallel implementations in `research_factory/core.py`.

The recovery is split into three independently testable subprojects:

1. Canonical point-in-time data and real ML training.
2. Executable hypotheses, broker-native replay, registry persistence, and sealed promotion.
3. Shared AI Council streaming and Book Brain evidence.

## Canonical Data And ML

### Source Discovery

The factory uses a configurable source catalog built from existing read-only helpers:

- Completed broker bars and ticks from the MT5 research engine.
- Incremental completed-bar ingestion.
- Journal-derived clips and persisted research datasets.
- Existing `data/cafb_snapshots` CSV files plus their metadata.

Each row retains source identity, source quality, symbol, timeframe, and point-in-time provenance. Mixed symbols and timeframes remain separate during feature, label, split, and replay operations. No machine-specific absolute data path is embedded in production code.

### Feature And Label Contract

One canonical dataframe contains raw market fields, point-in-time features, matured labels, and provenance. Features are grouped by symbol and timeframe and may use only current or earlier observations.

Labels are computed independently per symbol and timeframe. They may inspect observations after the decision timestamp to record matured outcomes, but:

- Barrier labels identify which barrier was reached first.
- Unknown trailing outcomes remain unknown and are excluded from supervised samples.
- No constant or default outcome is inserted.
- Dataset-wide statistics used by labels are fitted on training data only.
- Every chronological boundary purges at least the maximum label horizon.
- All rows sharing a timestamp remain in the same partition.

The exact canonical dataframe is the input to train, validation, test, and sealed splitting. Engineered features must not be bypassed.

### ML Contract

`MLPipeline` requires an explicit target and rejects missing or single-class targets with an auditable failure. Label and metadata columns cannot enter model features. Preprocessing is fitted once on training data and applied once during inference. Model selection and threshold selection are chronological and validation-only. Repeated training resets model state.

Walk-forward evaluation uses expanding chronological windows, retrains on each fold, and reports real per-fold sample counts, trades, gross return, costs, net return, expectancy, drawdown, and stability. Training and fold failures are recorded rather than converted to an empty successful result.

## Hypotheses, Replay, And Promotion

### Structured Hypotheses

There is one serialized hypothesis schema. It contains provenance, side, structured entry and exit rules, falsification criteria, required features, and optional stop, target, and elapsed-time limits. It does not invent dates, effects, direction, or price geometry.

A compiler validates rule types, required fields, required columns, side-specific geometry, and source evidence. It returns either an executable rule set or `NOT_EXECUTABLE` with reasons. Unknown and partially implemented rule types never become all-false signals and never reach replay.

### Broker-Native Replay

Replay receives an explicit symbol specification and observed cost profile. If required evidence is unavailable, replay returns `NO_EVIDENCE`.

The replay contract is:

- Entries and exits use bid/ask or an equivalent broker-native conversion, with each cost charged exactly once.
- Tick size and tick value determine monetary movement, including non-USD quote currencies.
- Buy and sell geometry is symmetric and side-correct.
- Stops and targets on the wrong side of entry are rejected.
- Same-bar stop/target collisions resolve conservatively.
- Targets never receive favorable price improvement beyond the target.
- Holding limits use elapsed timestamps, not a seconds-to-bars guess.
- End-of-data positions are explicitly closed conservatively or recorded unresolved; they are never silently discarded.

Promotion thresholds use units matching replay metrics.

### Registry And Sealed Evaluation

Every attempted hypothesis is persisted through `ExperimentRegistry`, including `NO_DATA`, `NO_EVIDENCE`, `NOT_EXECUTABLE`, model failure, replay failure, rejection, and challenger outcomes.

The existing `SealedHoldoutStore` owns sealed evaluation. A candidate is frozen with its model, parameters, code identity, and dataset fingerprint. Each frozen candidate and holdout fingerprint pair may be evaluated once. A second attempt is rejected after process restart as well as within one process.

Sealed rows, labels, length, distribution, and fingerprint are unavailable to feature selection, threshold tuning, fold sizing, hypothesis generation, or model selection. Promotion remains routed through governed promotion code and never writes champion state directly from the factory.

## AI Council And Book Brain

### Shared Agent Adapter

Research Factory does not define independent Claude or Codex process clients. It uses the shared adapter in `bot/ai_council/agents.py` through one orchestration interface.

Live asks use `subprocess.Popen` and stream output while retaining a parseable response. Each emitted line is prefixed with `[CLAUDE]` or `[CODEX]`. AI failure returns an explicit unavailable/error result and never falls back to simulated text.

The sole permitted Codex call was already consumed externally. Persisted factory state therefore starts with the budget exhausted and performs no Codex status probe or ask unless a human explicitly grants a new budget.

### Book Brain Evidence

Book retrieval uses the existing knowledge retrieval and research intelligence records. Supporting and contradictory evidence are stored separately with source location, passage hash, polarity, and executable status. Unknown concepts return no evidence; they do not fall back to an unrelated concept. Non-executable or unavailable passages may inform a research note but cannot support executable replay.

## Failure Handling

Every generation produces an auditable result:

- `NO_DATA`: no legitimate source rows or no matured samples.
- `NO_EVIDENCE`: required broker specification, costs, or provenance are unavailable.
- `NOT_EXECUTABLE`: a hypothesis cannot compile to validated rules.
- `FAILED`: data, model, replay, persistence, or external-agent execution failed.
- `REJECTED`: execution completed but gates failed.
- `CHALLENGER`: non-sealed gates passed and the frozen candidate may be evaluated once.

Exceptions are logged and persisted with their stage and reason. No exception path manufactures replacement evidence or success.

## Verification

Deterministic tests use hand-calculated fixtures and cover:

- Source discovery, metadata, provenance, and full-content fingerprints.
- Symbol/timeframe isolation and strict timestamp partitioning.
- Barrier-first labels, unknown tails, and horizon purging.
- Canonical dataframe identity through train, validation, test, and sealed boundaries.
- Real model fit/predict, target validation, no label leakage, and expanding folds.
- Buy/sell symmetry, EURUSD/USDJPY tick economics, costs exactly once, irregular timestamps, conservative collisions, and end-of-data handling.
- Structured rule compilation and `NOT_EXECUTABLE` rejection.
- Experiment recording for every terminal status.
- Persistent once-per-candidate sealed evaluation and absence of sealed leakage.
- `[CLAUDE]`/`[CODEX]` streaming, retained responses, no simulated fallback, and exhausted Codex state.
- Supporting and contradictory Book Brain evidence with hashed provenance.

Focused suites run after each subproject. The complete command from `bot` is `..\.venv\Scripts\python.exe -m pytest -q`. No factory process is started until all required tests pass.

## Explicit Rulings

- “Evaluate once” means once per frozen candidate and holdout fingerprint, persisted across restarts.
- Point-in-time correctness distinguishes decision-time features from later-matured labels; future observations are permitted only for label maturation and never as model inputs.
- The prohibition on `subprocess.run(capture_output=True)` applies to Claude and Codex ask paths; cheap executable detection may remain non-streaming if it never consumes the one-call budget.
- The no-fabrication requirement overrides legacy tests that expect synthesized targets or trade geometry.
