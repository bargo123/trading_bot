# External Research DAG and Rapid Firehose Design

## Purpose

Connect every installed GitHub research system and every implemented
book-informed Watcher algorithm into one auditable AEGIS research pipeline,
while making the MT5 DEMO Firehose faster and more responsive rather than
slower.

The integration must not pretend that installation or an import check is
research evidence. Each external system receives a defined role, consumes a
versioned input, produces a hashed artifact, and records a real success,
failure, timeout, or non-applicability result.

The prediction path is intentionally limited to the pinned GitHub systems and
the authoritative book-algorithm registry. AEGIS Council and Research Factory
are not prediction dependencies, do not vote on candidates, and do not grant
execution authority.

## Non-negotiable boundaries

- `bot/scripts/run_broker_paper.py` remains the only broker-execution owner.
- External tools, Watcher algorithms, Book Brain, replay engines and research
  workflows remain read-only with respect to MT5.
- MT5 execution remains DEMO-only with `allow_live=false`.
- No external process runs synchronously inside the tick-to-order hot path.
- No missing tool result, failed adapter, book consensus or synthetic replay
  may fabricate `P_CAPTURED_WIN`, positive EV or execution authority.
- The intentional configured per-trade risk ceiling remains `$0.15`.
- No martingale, forced trade, risk escalation after losses or duplicate
  execution owner is permitted.
- Existing dirty worktree changes are preserved.

## Architecture

AEGIS uses a role-based directed acyclic graph (DAG):

```text
Point-in-time market/replay dataset
        |
        +--> all implemented book algorithms --> attributed signal artifact
        +--> Qlib -----------------------------> model artifact
        +--> ordersim / hftbacktest -----------> executable replay artifacts
        +--> OOS-Lab / Keystone / research FW -> validation artifacts
        +--> ABIDES ----------------------------> latency/failure stress artifact
        +--> LEAN / NautilusTrader ------------> parity artifacts
        +--> catalog / Vibe / MT5-MCP ---------> provenance/preflight artifacts
        +--> Samvid ----------------------------> recovery/reconciliation artifact
        +--> OpenAlice -------------------------> read-only run/health view
                                                     |
                                                     v
                                             ResearchBundle
                                                     |
                                            ExperimentRegistry
                                                     |
                                      governed PromotionDecision
                                                     |
                                      immutable ExecutionBundle
                                                     |
                                in-memory rapid Firehose consumer
                                                     |
                                      run_broker_paper.py only
```

The orchestrator runs outside the Firehose process. It schedules independent
nodes concurrently when their dependencies are satisfied, but commits results
to the bundle in deterministic topological order. Node timeouts and failures
are data, not exceptions that silently disappear.

## External tool roles

The catalog is fixed to the 14 installed repositories recorded in
`external_dependency_manifest.json`:

1. OpenAlice: read-only control-plane health and workflow visibility.
2. Awesome Systematic Trading: provenance-preserving source catalog.
3. Qlib: offline feature/model research.
4. ordersim: order-lifecycle and cost replay.
5. hftbacktest: tick/queue/latency replay.
6. OOS-Lab: chronological OOS validation.
7. Keystone: methodology and adversarial validation checks.
8. Algorithmic Trading Research Framework: research-integrity checks.
9. Samvid Trading Core: event, recovery and reconciliation checks.
10. Vibe-Trading: MT5 contract/preflight reference checks.
11. MetaTrader5 MCP Server: read-only terminal/account/market diagnostics.
12. NautilusTrader: isolated event-engine parity.
13. LEAN: isolated replay parity.
14. ABIDES: synthetic latency, disconnection and failure stress.

Each catalog entry declares repository SHA, license, environment, supported
capabilities, input schema, output schema, timeout, deterministic command and
whether a node is required for a particular workflow. No adapter exposes
`order_send`, order placement, modification, cancellation or close methods.

## Contracts and artifact store

The integration adds versioned immutable contracts:

- `ExternalToolSpec`: identity, role, repository SHA, environment and command.
- `WorkflowSpec`: DAG nodes, dependencies, required/optional status and limits.
- `ExternalTaskRequest`: workflow/run/node identity and hashed input references.
- `ExternalTaskResult`: status, timestamps, exit code, bounded logs and outputs.
- `ArtifactEnvelope`: schema, producer, provenance, content hash and payload.
- `ResearchBundle`: deterministic set of node artifacts plus completeness state.
- `ExecutionBundle`: the small governed subset safe to load into the Firehose.

Artifacts are written atomically under
`bot/research/external_runs/<workflow_id>/<run_id>/`. The ExperimentRegistry
stores the workflow definition hash, dataset hash, node results, bundle hash
and terminal status. Re-running the same immutable request is idempotent and
reuses content-addressed artifacts.

## Book algorithm integration

`aegis.research.watcher_algorithms.ALGORITHM_MODULES` is authoritative. Every
registered algorithm must be evaluated exactly once for each point-in-time
Watcher state. The integration cannot use a hand-maintained subset.

The book node emits one result per registered algorithm with:

- algorithm ID and module identity;
- source books and source provenance;
- exact decision timestamp and state hash;
- applicability (`APPLICABLE`, `NOT_APPLICABLE`, `MISSING_DATA`, or error);
- view (`BUY`, `SELL`, `WAIT`, or unavailable);
- observed inputs and missing inputs;
- warnings and causal evidence status.

Coverage fails closed if the emitted algorithm ID set differs from
`ALGORITHM_MODULES`. Book output is contextual evidence only. It never becomes
a probability or an order intent. Historical outcomes are attached only after
the point-in-time decision artifact is sealed.

## Workflow execution

The first production workflow is `full_research_validation.v1`:

1. Freeze a causal input dataset and its manifest.
2. Run the complete book-algorithm node and source-catalog node.
3. Run Qlib model research and native AEGIS model research.
4. Run ordersim and hftbacktest executable replay.
5. Run OOS-Lab, Keystone and research-integrity validation.
6. Run ABIDES stress and Samvid recovery/reconciliation checks.
7. Run NautilusTrader and LEAN parity checks.
8. Run read-only MT5/Vibe diagnostics where a terminal is available.
9. Publish health and artifact references for OpenAlice.
10. Assemble a deterministic `ResearchBundle` and record it in
    ExperimentRegistry.
11. Build an `ExecutionBundle` only when every governed promotion condition
    passes. Otherwise publish `SHADOW_ONLY` with exact reasons.

Required node failure makes the bundle incomplete. Optional unavailability is
preserved explicitly and cannot be treated as positive evidence.

## Rapid Firehose behavior

The Firehose loads only a validated `ExecutionBundle`; it never waits for an
external tool. The bundle is verified by schema, content hash, dataset hash,
validation hash, expiry and symbol/horizon authorization before being swapped
atomically into memory.

For each genuine fresh broker event, the hot path:

1. updates point-in-time features;
2. generates the complete symbol x side x mechanism x horizon universe;
3. attaches available book context and validated model evidence from memory;
4. builds broker-valid geometry before scoring;
5. ranks one global pool by captured-win probability, after-cost EV,
   uncertainty, time-to-green, fast-winner/fast-loser similarity and portfolio
   impact;
6. freezes the exact selected identity;
7. reprices and revalidates quote, spread, EV, risk, margin, portfolio and OMS;
8. submits only through the existing runner and MT5 engine;
9. manages the basket using the canonical TradeController;
10. confirms close, records broker truth, releases the slot and immediately
    rescans.

The local decision-to-intent target remains p95 <= 50 ms excluding broker and
network latency. External orchestration latency is reported separately and
cannot contaminate this metric.

## Failure, recovery and observability

Every node has bounded execution, process-tree cleanup, retry policy and
cooldown. Retries reuse the same immutable request identity. Interrupted runs
resume only nodes without a valid content-addressed result.

The run journal exposes node state, dependency state, start/end time, duration,
artifact hash, logs, retry count and failure reason. Aggregate telemetry shows
workflow completeness, book coverage, parity disagreements, validation gates,
promotion status and the exact execution-bundle version loaded by the runner.

OpenAlice receives this read-only status representation; it does not control
orders or promotion.

## Verification and acceptance

Acceptance requires evidence for all of the following:

- all 14 catalog entries load and have a role-specific adapter;
- a deterministic fake-adapter DAG proves concurrency, ordering, timeout,
  failure, resume and idempotency;
- a real bounded workflow produces artifacts from every installed tool or an
  honest role-specific unavailable/failure result;
- the complete current book algorithm registry is evaluated with exact ID-set
  equality and no lookahead;
- all artifacts and bundles verify their hashes and reject mutation;
- ExperimentRegistry contains the full workflow and terminal outcomes;
- an invalid/incomplete/shadow bundle cannot authorize execution;
- a valid fixture bundle is loaded atomically without blocking the hot path;
- local 250 ms, 50 ms and 10 ms event benchmarks remain ordered and meet the
  p95 <= 50 ms bookkeeping target;
- exactly one MT5 DEMO execution owner exists and research broker-mutation hits
  remain zero;
- `allow_live=false` and the `$0.15` risk ceiling remain true;
- focused tests, full pytest and the Firehose verifier pass;
- runtime proof reports `NO LEGITIMATE SIGNAL - NO ORDER SENT` when no valid
  candidate exists rather than forcing a trade.

No claim that this is the "best" or profitable system is permitted without
positive executable chronological OOS and sealed evidence. The engineering
goal is the strongest truthful, rapid, observable and research-complete system
the available evidence supports.
