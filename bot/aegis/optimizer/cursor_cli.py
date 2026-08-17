"""Optional Cursor CLI hook. Python cycle does not depend on it."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from aegis.optimizer.paths import AGENT_PROMPT, OPTIMIZER_DIR, REPO_ROOT

ALLOWED_YAML_PATCH_KEYS = frozenset(
    {
        "firehose_tp_pips",
        "firehose_sl_pips",
        "max_spread_pips",
        "max_spread_price",
        "max_positions",
        "scratch_losers",
        "symbols",
        "symbol",
        "firehose_min_er",
        "firehose_min_range_pips",
        "max_hold_seconds",
        "flatten_if_profit_usd",
        "cost_buffer",
        "firehose_every_bar",
        "firehose_skip_doji",
        "firehose_require_body",
        "firehose_book_filter",
        "session_start_utc",
        "session_end_utc",
        "firehose_jpy_cluster_max",
        "firehose_vpa_filter",
        "firehose_brooks_range",
        "firehose_damir_structure",
        "firehose_chart_read",
        "close_if_gave_back",
        "lock_mfe_usd",
        "giveback_floor_usd",
        "giveback_frac",
        "firehose_stack",
        "firehose_max_per_symbol",
        "firehose_clip_interval_s",
        "firehose_jansen_filter",
        "jansen_score_min",
        "firehose_harris_jump",
        "harris_jump_atr",
        "oms_pretrade",
        "max_quote_age_s",
        "firehose_no_stack_if_red",
        "intel_enabled",
        "intel_skip_rsi_ext",
        "intel_max_ema_streak",
        "intel_quality_min",
        "intel_skip_impulse_against",
        "intel_skip_wrong_edge",
        "intel_wrong_buy_loc",
        "intel_wrong_sell_loc",
        "intel_rsi_buy_max",
        "intel_rsi_sell_min",
        "intel_skip_weak_adx_edge",
        "intel_weak_adx",
        "intel_skip_incomplete",
        "intel_skip_extreme_doji",
        "intel_skip_floor_chop_sell",
        "intel_floor_chop_er",
        "intel_floor_chop_loc",
        "intel_skip_late_buy_chase",
        "intel_skip_ceiling_stretch_buy",
        "intel_ceiling_stretch_loc",
        "intel_ceiling_stretch_ema_pips",
        "intel_skip_hour_13_dead_er_buy",
        "intel_hour_13_dead_er",
        "intel_skip_ny_hour_18_stretch_buy",
        "intel_hour_18_ema_pips",
        "intel_skip_london_dead_er",
        "intel_skip_doji_against",
        "intel_skip_ceiling_doji_buy",
        "intel_skip_below_range_sell",
        "intel_skip_stretched_doji_buy",
        "intel_stretched_doji_loc",
        "intel_stretched_doji_ema_pips",
        "intel_skip_barbwire_sell",
        "intel_skip_barbwire_buy",
        "intel_skip_chop_doji",
        "intel_max_atr_expand",
        "intel_skip_stretched_sell",
        "intel_stretched_sell_ema_pips",
        "intel_skip_range_mid_sell",
        "intel_skip_ret3_chase_sell",
        "intel_ret3_chase_pips",
        "intel_skip_london_hour_12_sell",
        "intel_skip_above_range_buy",
        "intel_skip_stretched_buy",
        "intel_stretched_buy_loc",
        "intel_stretched_buy_ema_pips",
        "intel_skip_floor_run_sell",
        "intel_floor_run_loc",
        "intel_floor_run_er",
        "intel_skip_ny_hour_19_sell",
        "intel_skip_london_open_chase_buy",
        "intel_london_open_ret3",
        "intel_skip_hour_21_sell",
        "intel_skip_asia_hour_4_sell",
        "intel_skip_hour_0_dead_er_sell",
        "intel_hour_0_dead_er",
        "intel_skip_asia_hour_5_stretch_buy",
        "intel_hour_5_ema_pips",
        "intel_hour_5_loc",
        "intel_skip_strong_adx_stretch_buy",
        "intel_strong_adx",
        "intel_strong_adx_ema_pips",
        "firehose_anchor_quote",
        "scratch_never_green_seconds",
        "scratch_cooldown_s",
    }
)
BLOCKED_YAML_KEYS = frozenset(
    {
        "allow_live",
        "engine",
        "mt5_login",
        "mt5_password",
        "mt5_server",
        "paper_trading_enabled",
        "kill_switch",
        "allow_unsafe_high_risk",
    }
)


def _latest_agent_node() -> list[str] | None:
    root = Path.home() / "AppData" / "Local" / "cursor-agent" / "versions"
    if not root.exists():
        return None
    dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name, reverse=True)
    for folder in dirs:
        node = folder / "node.exe"
        index = folder / "index.js"
        if node.exists() and index.exists():
            return [str(node), str(index)]
    return None


def detect_cursor_cli() -> dict[str, Any]:
    argv = _latest_agent_node()
    agent_cmd = shutil.which("agent")
    if agent_cmd and agent_cmd.lower().endswith(".ps1"):
        cmd_alias = Path(agent_cmd).with_suffix(".cmd")
        if cmd_alias.exists():
            agent_cmd = str(cmd_alias)
    if not agent_cmd:
        local = Path.home() / "AppData" / "Local" / "cursor-agent" / "agent.cmd"
        if local.exists():
            agent_cmd = str(local)
    cursor = shutil.which("cursor")
    return {
        "agent": agent_cmd,
        "agent_argv": argv or ([agent_cmd] if agent_cmd else None),
        "cursor": cursor,
        "found": bool(argv or agent_cmd),
        "install_hint": (
            "Install the Cursor agent CLI once, then auth: "
            "https://cursor.com/docs/cli/overview  "
            "In PowerShell: irm 'https://cursor.com/install?win32=true' | iex   "
            "Then run: & \"$env:LOCALAPPDATA\\cursor-agent\\agent.cmd\" login. "
            "Python optimizer cycles still run without it."
        ),
    }


def extract_proposal(text: str) -> dict[str, Any] | None:
    if not text or not text.strip():
        return None
    raw = text.strip()
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    patch = data.get("patch")
    if not isinstance(patch, dict) or not patch:
        return None
    if any(k in BLOCKED_YAML_KEYS for k in patch):
        return None
    if any(k not in ALLOWED_YAML_PATCH_KEYS for k in patch):
        return None
    if patch.get("firehose_every_bar") is False:
        return None
    if "session_start_utc" in patch or "session_end_utc" in patch:
        return None
    slug = str(data.get("id") or "cursor_patch").strip() or "cursor_patch"
    weakness = str(data.get("weakness") or "high_wr_neg_e")
    rationale = str(data.get("rationale") or "Cursor CLI proposal")
    return {
        "id": slug[:40],
        "weakness": weakness,
        "patch": patch,
        "rationale": rationale,
        "source": "cursor",
    }


def extract_proposal_from_cli(stdout: str, stderr: str) -> dict[str, Any] | None:
    blob = f"{stdout or ''}\n{stderr or ''}"
    hit = extract_proposal(blob)
    if hit:
        return hit
    for chunk in blob.splitlines():
        line = chunk.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        for key in ("result", "text", "message", "content", "response"):
            val = obj.get(key)
            if isinstance(val, str):
                hit = extract_proposal(val)
                if hit:
                    return hit
            if isinstance(val, dict) and "patch" in val:
                hit = extract_proposal(json.dumps(val))
                if hit:
                    return hit
    return None


def maybe_propose_with_cursor(*, enabled: bool) -> dict[str, Any]:
    detected = detect_cursor_cli()
    if not enabled:
        detected["ran"] = False
        detected["message"] = "Cursor CLI hook disabled"
        return detected
    if not detected["found"]:
        detected["ran"] = False
        detected["message"] = detected["install_hint"]
        return detected
    agent_file = OPTIMIZER_DIR / "cursor_agent.json"
    agent_id = ""
    if agent_file.exists():
        try:
            payload = json.loads(agent_file.read_text(encoding="utf-8"))
            agent_id = str(payload.get("id") or payload.get("agent_id") or "")
        except json.JSONDecodeError:
            agent_id = ""
    argv = detected.get("agent_argv") or ([detected["agent"]] if detected.get("agent") else None)
    if not argv:
        detected["ran"] = False
        detected["message"] = detected["install_hint"]
        return detected
    prompt_text = ""
    if AGENT_PROMPT.exists():
        prompt_text = AGENT_PROMPT.read_text(encoding="utf-8")
    if not prompt_text.strip():
        prompt_text = (
            "Propose one YAML patch JSON: "
            '{"id":"slug","patch":{"firehose_tp_pips":2},'
            '"weakness":"high_wr_neg_e","rationale":"..."}. '
            "Do not place orders."
        )
    cmd = [
        *argv,
        "--print",
        "--trust",
        "--mode",
        "ask",
        "--output-format",
        "json",
        "--workspace",
        str(REPO_ROOT),
    ]
    if agent_id:
        cmd.extend(["--resume", agent_id])
    cmd.append(prompt_text)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            check=False,
            cwd=str(REPO_ROOT),
        )
        detected["ran"] = True
        detected["returncode"] = proc.returncode
        detected["stdout_tail"] = (proc.stdout or "")[-2000:]
        detected["stderr_tail"] = (proc.stderr or "")[-1000:]
        detected["cmd"] = cmd
        proposal = extract_proposal_from_cli(proc.stdout or "", proc.stderr or "")
        if proposal:
            detected["proposal"] = proposal
        else:
            detected["message"] = "Cursor CLI ran but produced no valid YAML patch JSON"
    except (OSError, subprocess.TimeoutExpired) as exc:
        detected["ran"] = False
        detected["message"] = str(exc)
    return detected
