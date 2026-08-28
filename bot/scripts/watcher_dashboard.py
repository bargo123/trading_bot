#!/usr/bin/env python3
"""Local, read-only dashboard for Watcher blocked-trade studies."""
from __future__ import annotations

import argparse
import gzip
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlsplit

try:
    from .watcher_parquet import (
        load_study_from_parquet,
        load_study_from_pending,
        load_study_index,
        load_pending_offset_index,
    )
except ImportError:
    from watcher_parquet import load_study_from_parquet, load_study_from_pending, load_study_index, load_pending_offset_index

ROOT = Path(__file__).resolve().parents[1]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    try:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8") if path.suffix == ".gz" else opener(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    yield row
    except OSError:
        return


def load_blocked_studies(report_dir: Path) -> list[dict[str, Any]]:
    """Load only Watcher-produced studies; malformed or partial lines are skipped."""
    root = Path(report_dir)
    records: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    paths = sorted((root / "archives").glob("blocked_strategy_studies_*.jsonl.gz"))
    paths.append(root / "blocked_strategy_studies.jsonl")
    for path in paths:
        for row in _jsonl(path):
            key = _text(row.get("study_id"))
            if key:
                records[key] = row
            else:
                unkeyed.append(row)
    return [*records.values(), *unkeyed]


_INDEX_FIELDS = {"record_type", "study_id", "blocked_event_id", "timestamp", "candidate_state", "strategy_count"}
_INDEX_FIELD_RE = re.compile(r'"(record_type|study_id|blocked_event_id|timestamp|candidate_state|strategy_count)"\s*:\s*')
_OPINION_RE = re.compile(r'"opinion"\s*:\s*"([^"]+)"')
_DECODER = json.JSONDecoder()


def _skip_json_string(text: str, start: int) -> int:
    index = start + 1
    escaped = False
    while index < len(text):
        char = text[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            return index + 1
        index += 1
    return len(text)


def _lightweight_study(line: str, path: Path, line_number: int) -> dict[str, Any] | None:
    """Extract index fields without decoding the large strategies array."""
    fields: dict[str, Any] = {}
    for match in _INDEX_FIELD_RE.finditer(line):
        key = match.group(1)
        if key in fields:
            continue
        try:
            value, _ = _DECODER.raw_decode(line, match.end())
        except json.JSONDecodeError:
            continue
        fields[key] = value
    if fields.get("record_type") != "blocked_strategy_study" or not _text(fields.get("study_id")):
        return None
    counts = {"BUY": 0, "SELL": 0, "NO_TRADE": 0, "NOT_APPLICABLE": 0}
    for opinion in _OPINION_RE.findall(line):
        opinion = opinion.upper()
        if opinion in counts:
            counts[opinion] += 1
    fields["_opinion_counts"] = counts
    fields["_source_path"] = str(path)
    fields["_source_line"] = line_number
    return fields


def _index_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return
    try:
        opener = gzip.open if path.suffix == ".gz" else Path.open
        with opener(path, "rt", encoding="utf-8") if path.suffix == ".gz" else opener(path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if line.strip():
                    row = _lightweight_study(line, path, line_number)
                    if row is not None:
                        yield row
    except OSError:
        return


class StudyStore:
    """Cache the immutable-in-between-refresh JSONL snapshot for fast polling."""

    def __init__(self, report_dir: Path):
        self.report_dir = Path(report_dir)
        self.path = self.report_dir / "blocked_strategy_studies.jsonl"
        self.library_path = self.report_dir / "knowledge_library.json"
        self._signature: Any = None
        self._studies: list[dict[str, Any]] | None = None
        self._index_signature: Any = None
        self._index_studies: list[dict[str, Any]] | None = None
        self._pending_signature: tuple[int, int] | None = None
        self._pending_offsets: dict[str, int] = {}
        self._library_signature: tuple[int, int] | None = None
        self._metadata: dict[str, dict[str, Any]] = {}

    def load(self) -> list[dict[str, Any]]:
        signature_rows: list[tuple[str, int, int]] = []
        for path in [self.path, *sorted((self.report_dir / "archives").glob("blocked_strategy_studies_*.jsonl.gz"))]:
            try:
                stat = path.stat()
            except OSError:
                continue
            signature_rows.append((str(path), stat.st_mtime_ns, stat.st_size))
        signature = tuple(signature_rows)
        if self._studies is None or signature != self._signature:
            self._studies = load_blocked_studies(self.report_dir)
            self._signature = signature
        return self._studies

    def load_index(self) -> list[dict[str, Any]]:
        compact_rows = load_study_index(self.report_dir)
        if compact_rows:
            self._index_studies = compact_rows
            self._index_signature = "parquet-index"
            return self._index_studies
        signature_rows: list[tuple[str, int, int]] = []
        paths = [*sorted((self.report_dir / "archives").glob("blocked_strategy_studies_*.jsonl.gz")), self.path]
        for path in paths:
            try:
                stat = path.stat()
            except OSError:
                continue
            signature_rows.append((str(path), stat.st_mtime_ns, stat.st_size))
        signature = tuple(signature_rows)
        if self._index_studies is None or signature != self._index_signature:
            records: dict[str, dict[str, Any]] = {}
            for path in paths:
                for row in _index_jsonl(path):
                    records[_text(row["study_id"])] = row
            self._index_studies = list(records.values())
            self._index_signature = signature
        return self._index_studies

    def load_detail(self, study_id: str) -> dict[str, Any] | None:
        index_row = next((row for row in self.load_index() if _text(row.get("study_id")) == study_id), None)
        pending_offset = index_row.get("pending_offset") if index_row else None
        try:
            stat = (self.report_dir / "blocked_strategy_studies_pending.jsonl").stat()
            pending_signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            pending_signature = None
        if pending_signature != self._pending_signature:
            self._pending_offsets = load_pending_offset_index(self.report_dir)
            self._pending_signature = pending_signature
        if pending_offset is None:
            pending_offset = self._pending_offsets.get(study_id)
        if pending_offset is not None:
            pending_study = load_study_from_pending(self.report_dir, study_id, offset=int(pending_offset))
            if pending_study is not None:
                return pending_study
        parquet_study = load_study_from_parquet(self.report_dir, study_id)
        if parquet_study is not None:
            return parquet_study
        if pending_offset is None:
            pending_study = load_study_from_pending(self.report_dir, study_id)
            if pending_study is not None:
                return pending_study
        if index_row is None:
            return None
        path = Path(str(index_row["_source_path"]))
        target_line = int(index_row["_source_line"])
        try:
            opener = gzip.open if path.suffix == ".gz" else Path.open
            with opener(path, "rt", encoding="utf-8") if path.suffix == ".gz" else opener(path, encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if line_number == target_line:
                        row = json.loads(line)
                        return row if isinstance(row, dict) else None
        except (OSError, json.JSONDecodeError, ValueError):
            return None
        return None

    def hydrate(self, study: Mapping[str, Any]) -> dict[str, Any]:
        """Join stable book provenance to the compact per-study results."""
        try:
            stat = self.library_path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            signature = None
        if signature != self._library_signature:
            self._metadata = {}
            try:
                library = json.loads(self.library_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                library = {}
            for record in library.get("records", []) if isinstance(library, Mapping) else []:
                if not isinstance(record, Mapping) or record.get("category") != "strategy":
                    continue
                raw = record.get("raw_record") if isinstance(record.get("raw_record"), Mapping) else {}
                provenance = record.get("provenance") if isinstance(record.get("provenance"), Mapping) else {}
                record_id = _text(record.get("record_id"))
                if record_id:
                    self._metadata[record_id] = {
                        "book": provenance.get("book") or raw.get("book"),
                        "source_file": record.get("source_file"),
                        "source_line": record.get("source_line"),
                        "strategy_family": raw.get("strategy_family") or raw.get("concept"),
                        "side_rule": raw.get("side_rule"),
                        "validation_status": record.get("validation_status"),
                        "provenance": provenance,
                    }
            self._library_signature = signature
        hydrated = dict(study)
        hydrated["strategies"] = [
            {**self._metadata.get(_text(row.get("record_id")), {}), **dict(row)}
            for row in study.get("strategies", [])
            if isinstance(row, Mapping)
        ]
        return hydrated


def _state(study: Mapping[str, Any]) -> Mapping[str, Any]:
    value = study.get("candidate_state")
    return value if isinstance(value, Mapping) else {}


def _opinion_counts(strategies: Any) -> dict[str, int]:
    counts = {"BUY": 0, "SELL": 0, "NO_TRADE": 0, "NOT_APPLICABLE": 0}
    for row in strategies if isinstance(strategies, list) else []:
        if isinstance(row, Mapping):
            opinion = _text(row.get("opinion")).upper()
            if opinion in counts:
                counts[opinion] += 1
    return counts


def _sort_key(study: Mapping[str, Any]) -> tuple[int, str]:
    timestamp = study.get("timestamp") or _state(study).get("timestamp")
    try:
        return (1, f"{float(timestamp):020.6f}")
    except (TypeError, ValueError):
        return (0, _text(timestamp))


def build_blocked_trade_index(studies: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return compact list data; strategy rows are fetched only on expansion."""
    rows: list[dict[str, Any]] = []
    for study in studies:
        if not isinstance(study, Mapping) or _text(study.get("record_type")) != "blocked_strategy_study":
            continue
        state = _state(study)
        strategies = study.get("strategies")
        opinion_counts = study.get("_opinion_counts")
        rows.append({
            "study_id": study.get("study_id"),
            "blocked_event_id": study.get("blocked_event_id"),
            "timestamp": study.get("timestamp"),
            "candidate_id": state.get("candidate_id"),
            "symbol": _text(state.get("symbol")).upper() or None,
            "side": _text(state.get("side")).upper() or None,
            "mechanism": state.get("mechanism"),
            "horizon_s": state.get("horizon_s"),
            "reason": state.get("reason") or state.get("reject_reason") or state.get("block_reason"),
            "strategy_count": study.get("strategy_count") or (len(strategies) if isinstance(strategies, list) else 0),
            "opinion_counts": (
                opinion_counts
                if isinstance(opinion_counts, Mapping)
                else study.get("opinion_counts")
                if isinstance(study.get("opinion_counts"), Mapping)
                else _opinion_counts(strategies)
            ),
        })
    return sorted(rows, key=_sort_key, reverse=True)


def study_detail(studies: Iterable[Mapping[str, Any]], study_id: str) -> dict[str, Any] | None:
    for study in reversed(list(studies)):
        if _text(study.get("study_id")) == study_id:
            return dict(study)
    return None


def render_dashboard_html() -> str:
    return r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AEGIS Watcher Studies</title>
<style>
:root { color-scheme: dark; --bg:#10151c; --panel:#18212c; --line:#2b3948; --text:#e8eef5; --muted:#9aabba; --accent:#62b0ff; --bad:#ff8a8a; --good:#8fe0a5; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 system-ui,Segoe UI,sans-serif; }
header { padding:22px 28px 14px; border-bottom:1px solid var(--line); position:sticky; top:0; background:rgba(16,21,28,.96); z-index:2; }
h1 { margin:0 0 5px; font-size:22px; }
.sub, .muted { color:var(--muted); }
.toolbar { display:flex; gap:10px; flex-wrap:wrap; margin-top:14px; }
input { background:var(--panel); border:1px solid var(--line); color:var(--text); border-radius:6px; padding:9px 11px; min-width:300px; }
main { padding:20px 28px 44px; max-width:1800px; margin:auto; }
.card { background:var(--panel); border:1px solid var(--line); border-radius:8px; margin:10px 0; overflow:hidden; }
.summary { display:grid; grid-template-columns:1.6fr .8fr .8fr 1.1fr .6fr 1.1fr; gap:12px; align-items:center; padding:14px 16px; cursor:pointer; }
.summary:hover { border-color:var(--accent); }
.candidate { color:var(--accent); font-weight:650; }
.pill { display:inline-block; border:1px solid var(--line); border-radius:999px; padding:2px 8px; margin:2px 3px 2px 0; font-size:12px; }
.buy { color:var(--good); } .sell, .reason { color:var(--bad); }
.detail { border-top:1px solid var(--line); padding:16px; overflow:auto; }
.facts { display:flex; gap:18px; flex-wrap:wrap; margin-bottom:14px; }
.fact b { display:block; color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }
table { border-collapse:collapse; width:100%; min-width:900px; }
th, td { text-align:left; padding:7px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }
th { color:var(--muted); font-size:11px; text-transform:uppercase; position:sticky; top:0; background:var(--panel); }
.empty { padding:35px; text-align:center; color:var(--muted); }
@media (max-width:900px) { .summary { grid-template-columns:1fr 1fr; } input { min-width:220px; width:100%; } }
</style>
</head>
<body>
<header>
  <h1>AEGIS Watcher — Blocked Trade Studies</h1>
  <div class="sub">Read-only local view. Production execution is not connected. Click a trade to expand All strategies.</div>
  <div class="toolbar">
    <input id="search" placeholder="Filter symbol, side, mechanism, horizon, reason, or candidate">
    <span id="status" class="muted">Loading…</span>
  </div>
</header>
<main id="trades"></main>
<script>
const trades = document.getElementById('trades');
const search = document.getElementById('search');
const status = document.getElementById('status');
let index = [];
let expandedStudyId = null;
let expandedDetailHtml = null;
let expandedDetailLoaded = false;
let expandedDetailLoading = false;
const esc = (v) => String(v ?? '—').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const pct = (v) => v == null ? '—' : `${Number(v).toFixed(2)}%`;
const pills = (counts) => Object.entries(counts || {}).filter(([,n]) => n).map(([k,n]) => `<span class="pill ${k === 'BUY' ? 'buy' : k === 'SELL' ? 'sell' : ''}">${esc(k)} ${n}</span>`).join('');
function currentExpandedCard() {
  if (!expandedStudyId) return null;
  return [...document.querySelectorAll('.card')].find(card => card.dataset.id === expandedStudyId) || null;
}
function captureExpandedDetail() {
  const card = currentExpandedCard();
  if (!card) return;
  const detail = card.querySelector('.detail');
  if (detail.hidden) return;
  expandedDetailLoaded = Boolean(detail.dataset.loaded);
  expandedDetailLoading = !expandedDetailLoaded;
  expandedDetailHtml = expandedDetailLoaded ? detail.innerHTML : null;
}
function restoreExpandedDetail() {
  const card = currentExpandedCard();
  if (!card) return;
  const detail = card.querySelector('.detail');
  detail.hidden = false;
  if (expandedDetailLoaded && expandedDetailHtml !== null) {
    detail.innerHTML = expandedDetailHtml;
    detail.dataset.loaded = '1';
  } else if (expandedDetailLoading) {
    detail.innerHTML = '<div class="muted">Loading all strategies…</div>';
  }
}
function render() {
  captureExpandedDetail();
  const q = search.value.trim().toLowerCase();
  const rows = index.filter(x => JSON.stringify(x).toLowerCase().includes(q));
  if (!rows.length) { trades.innerHTML = '<div class="empty">No blocked trades found.</div>'; return; }
  trades.innerHTML = rows.map(x => `<section class="card" data-id="${esc(x.study_id)}">
    <div class="summary" role="button" tabindex="0">
      <div><div class="candidate">${esc(x.candidate_id || x.blocked_event_id)}</div><div class="muted">${esc(x.symbol)} · ${esc(x.side)} · ${esc(x.horizon_s)}s</div></div>
      <div>${esc(x.mechanism)}</div><div>${pills(x.opinion_counts)}</div><div class="reason">${esc(x.reason)}</div>
      <div>Strategies<br><b>${esc(x.strategy_count)}</b></div><div class="muted">${esc(x.timestamp)}</div>
    </div><div class="detail" hidden>Click to load all strategy evidence.</div>
  </section>`).join('');
  document.querySelectorAll('.summary').forEach(el => el.addEventListener('click', () => expand(el.parentElement)));
  restoreExpandedDetail();
}
async function expand(card) {
  const detail = card.querySelector('.detail');
  if (!detail.hidden && detail.dataset.loaded) {
    detail.hidden = true;
    expandedStudyId = null; expandedDetailHtml = null; expandedDetailLoaded = false; expandedDetailLoading = false;
    return;
  }
  expandedStudyId = card.dataset.id; expandedDetailHtml = null; expandedDetailLoaded = false; expandedDetailLoading = true;
  detail.hidden = false; detail.innerHTML = '<div class="muted">Loading all strategies…</div>';
  try {
    const response = await fetch('/api/blocked-trade/' + encodeURIComponent(card.dataset.id));
    if (!response.ok) throw new Error('study not found');
    const study = await response.json(); const state = study.candidate_state || {};
    const prediction = study.prediction_evidence || {source: 'UNAVAILABLE', probability: null, reason: 'prediction_not_recorded_in_source_event'};
    const predictionText = prediction.probability == null ? 'UNAVAILABLE' : `${Number(prediction.probability).toFixed(4)}`;
    const sideComparison = prediction.side_comparison ? JSON.stringify(prediction.side_comparison) : '—';
    const predictionHtml = `<div class="prediction"><b>Candidate ML prediction</b><div>Source: ${esc(prediction.source)} · Probability: ${esc(predictionText)} · Decision: ${esc(prediction.decision)} · Abstain: ${esc(prediction.abstain)} · Reason: ${esc(prediction.abstain_reason || prediction.reason)}</div><div>BUY/SELL evidence: ${esc(sideComparison)}</div></div>`;
    const reasonText = s => (s.reasons || (s.reason_codes || []).map(code => (study.reason_dictionary || [])[code] || `reason_${code}`)).join('; ');
    const rows = (study.strategies || []).map(s => `<tr><td>${esc(s.record_id)}</td><td>${esc(s.book)}</td><td>${esc(s.strategy_family)}</td><td class="${s.opinion === 'BUY' ? 'buy' : s.opinion === 'SELL' ? 'sell' : ''}">${esc(s.opinion)}</td><td>${esc(s.applicability)}</td><td>${esc(s.evidence_status || 'UNAVAILABLE')}</td><td>${pct(s.p_captured_win_percent)}</td><td>${pct(s.exact_win_rate_percent)}</td><td>${pct(s.proxy_win_rate_percent)}</td><td>${esc(s.p_captured_win_sample_size || 0)}</td><td>${esc(s.p_captured_win_source)}</td><td>${esc(reasonText(s))}</td></tr>`).join('');
    expandedDetailHtml = `<div class="facts"><div class="fact"><b>Candidate</b>${esc(state.candidate_id)}</div><div class="fact"><b>Symbol / side</b>${esc(state.symbol)} / ${esc(state.side)}</div><div class="fact"><b>Mechanism / horizon</b>${esc(state.mechanism)} / ${esc(state.horizon_s)}s</div><div class="fact"><b>Strategy count</b>${esc(study.strategy_count)}</div><div class="fact"><b>Study ID</b>${esc(study.study_id)}</div></div>${predictionHtml}<table><thead><tr><th>Record ID</th><th>Book</th><th>Family</th><th>Opinion</th><th>Applicability</th><th>Evidence status</th><th>P_CAPTURED_WIN</th><th>Exact %</th><th>Proxy %</th><th>Sample N</th><th>Evidence source</th><th>Reasons</th></tr></thead><tbody>${rows}</tbody></table>`;
    expandedDetailLoaded = true; expandedDetailLoading = false;
    const current = currentExpandedCard();
    if (current) {
      const currentDetail = current.querySelector('.detail');
      currentDetail.hidden = false; currentDetail.innerHTML = expandedDetailHtml; currentDetail.dataset.loaded = '1';
    }
  } catch (error) {
    expandedDetailHtml = `<div class="reason">${esc(error.message)}</div>`;
    expandedDetailLoaded = true; expandedDetailLoading = false;
    const current = currentExpandedCard();
    if (current) { const currentDetail = current.querySelector('.detail'); currentDetail.hidden = false; currentDetail.innerHTML = expandedDetailHtml; }
  }
}
async function loadIndex() {
  try { const response = await fetch('/api/blocked-trades'); index = await response.json(); status.textContent = `${index.length} blocked studies · auto-refresh 5s`; render(); }
  catch (error) { status.textContent = 'Dashboard data unavailable'; trades.innerHTML = `<div class="empty">${esc(error.message)}</div>`; }
}
search.addEventListener('input', render); loadIndex(); setInterval(loadIndex, 5000);
</script>
</body>
</html>'''


def _json_response(handler: BaseHTTPRequestHandler, value: Any, status: int = 200) -> None:
    payload = json.dumps(value, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def make_handler(report_dir: Path) -> type[BaseHTTPRequestHandler]:
    root = Path(report_dir)
    store = StudyStore(root)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/":
                payload = render_dashboard_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            if path == "/api/blocked-trades":
                _json_response(self, build_blocked_trade_index(store.load_index()))
                return
            prefix = "/api/blocked-trade/"
            if path.startswith(prefix):
                study = store.load_detail(unquote(path[len(prefix):]))
                if study is not None:
                    study = store.hydrate(study)
                _json_response(self, study if study is not None else {"error": "not found"}, 200 if study else 404)
                return
            _json_response(self, {"error": "not found"}, 404)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


def serve(report_dir: Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("dashboard must bind to localhost")
    server = ThreadingHTTPServer((host, port), make_handler(report_dir))
    print(f"WATCHER_DASHBOARD=http://{host}:{port}/", flush=True)
    server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the read-only Watcher dashboard")
    parser.add_argument("--reports", type=Path, default=ROOT / "reports" / "watcher")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.reports, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
