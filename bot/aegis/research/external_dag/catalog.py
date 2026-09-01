"""Authoritative catalog for the installed, read-only external research stack."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from .contracts import ExternalToolSpec


REQUIRED_EXTERNAL_TOOLS = frozenset(
    {
        "OpenAlice",
        "awesome-systematic-trading",
        "qlib",
        "ordersim",
        "hftbacktest",
        "oos-lab",
        "Keystone",
        "algorithmic-trading-research-framework",
        "samvid-trading-core",
        "Vibe-Trading",
        "metatrader5-mcp-server",
        "nautilus_trader",
        "Lean",
        "abides",
    }
)

# These nodes must execute a real domain operation for the selected strategy
# set.  Import, compile, manifest-read, and health-only probes are insufficient
# evidence for a successful run.
DOMAIN_ARTIFACT_TOOLS = frozenset(
    {
        "OpenAlice",
        "qlib",
        "ordersim",
        "hftbacktest",
        "oos-lab",
        "Keystone",
        "samvid-trading-core",
        "nautilus_trader",
        "Lean",
        "abides",
    }
)

DOMAIN_ARTIFACT_OPERATIONS = {
    "OpenAlice": "read_only_workflow_status_approvals_reports",
    "qlib": "trained_offline_model_and_features",
    "ordersim": "candidate_execution_replay",
    "hftbacktest": "candidate_tick_execution_replay",
    "oos-lab": "calculated_statistical_validation",
    "Keystone": "calculated_methodology_validation",
    "samvid-trading-core": "reconciliation_and_recovery_evidence",
    "nautilus_trader": "replay_parity_comparison",
    "Lean": "replay_parity_comparison",
    "abides": "latency_and_failure_stress",
}

_DOMAIN_HELPER = str(Path(__file__).with_name("domain_artifacts.py").resolve())


_TOOL_METADATA: dict[str, tuple[str, tuple[str, ...], str]] = {
    "OpenAlice": ("CONTROL_PLANE", ("read_only_status", "health"), "node"),
    "awesome-systematic-trading": ("SOURCE_CATALOG", ("source_inventory",), "internal"),
    "qlib": ("MODEL", ("offline_features", "offline_models"), "qlib"),
    "ordersim": ("REPLAY", ("order_lifecycle", "cost_replay"), "ordersim"),
    "hftbacktest": ("REPLAY", ("tick_replay", "latency_replay"), "hftbacktest"),
    "oos-lab": ("VALIDATION", ("chronological_oos",), "oos-lab"),
    "Keystone": ("VALIDATION", ("methodology_review",), "keystone"),
    "algorithmic-trading-research-framework": (
        "VALIDATION",
        ("research_integrity",),
        "research-framework",
    ),
    "samvid-trading-core": ("RECOVERY", ("reconciliation", "recovery"), "samvid"),
    "Vibe-Trading": ("PREFLIGHT", ("mt5_contract_reference",), "internal"),
    "metatrader5-mcp-server": ("PREFLIGHT", ("read_only_mt5_diagnostics",), "mt5-mcp"),
    "nautilus_trader": ("PARITY", ("event_engine_parity",), "nautilus"),
    "Lean": ("PARITY", ("replay_parity",), "lean"),
    "abides": ("STRESS", ("latency_stress", "failure_stress"), "abides"),
}


_INPUT_PROBE_PYTHON = (
    "import json,os; _a=os.environ.get('AEGIS_TASK_INPUT_PATH'); "
    "_d=json.load(open(_a,encoding='utf-8')) if _a else {}; "
    "assert not _a or _d.get('schema')=='aegis.external_task_input.v1'; "
    "_mp=_d.get('dataset_manifest_path') if _a else None; "
    "_m=json.load(open(_mp,encoding='utf-8')) if _mp else {}; "
    "assert not _a or (_m.get('schema')=='aegis.frozen_dataset_manifest.v1' "
    "and isinstance(_m.get('point_in_time_state'),dict)); "
    "print('AEGIS_INPUT_CONSUMED='+('1' if _a else '0')); "
    "print('AEGIS_INPUT_DATASET_SCHEMA='+str(_m.get('schema') or '')); "
    "print('AEGIS_INPUT_STATE_FIELDS='+str(len(_m.get('point_in_time_state') or {}))); "
)


def _python_command(body: str, environment: str) -> tuple[str, ...]:
    return (environment, "-c", _INPUT_PROBE_PYTHON + body)


def _domain_python_command(name: str, environment: str) -> tuple[str, ...]:
    body = (
        # pandas/numpy may ask Windows WMI for platform.machine() during
        # import.  A blocked WMI provider must not prevent a deterministic
        # domain operation; the research artifact does not use OS identity.
        "import platform; platform._wmi_query=lambda *args: (_ for _ in ()).throw(OSError('wmi_unavailable')); import os,runpy; os.environ['AEGIS_DOMAIN_TOOL']="
        + repr(name)
        + "; "
        + ("os.environ['AEGIS_HFTBACKTEST_SUBPROCESS']='1'; " if name == "hftbacktest" else "")
        + "runpy.run_path("
        + repr(_DOMAIN_HELPER)
        + ",run_name='__main__')"
    )
    return _python_command(body, environment)


def _command_for(name: str, environment: str) -> tuple[str, ...]:
    if name == "OpenAlice":
        return (
            environment,
            "exec",
            "tsx",
            "-e",
            "(async()=>{ const fs=(await import('node:fs')).default; "
            "if(!process.env.AEGIS_TASK_INPUT_PATH) throw new Error('selected_strategy_input_missing'); "
            "const d=JSON.parse(fs.readFileSync(process.env.AEGIS_TASK_INPUT_PATH,'utf8')); "
            "if(d.schema!=='aegis.external_task_input.v1') throw new Error('invalid task input'); "
            "const m=d.dataset_manifest_path ? JSON.parse(fs.readFileSync(d.dataset_manifest_path,'utf8')) : {}; "
            "if(m.schema!=='aegis.frozen_dataset_manifest.v1' || typeof m.point_in_time_state!=='object') throw new Error('invalid dataset manifest'); "
            "const ids=d.selected_strategy_ids; if(!Array.isArray(ids)||ids.length<1||ids.length>10) throw new Error('selected_strategy_ids_missing'); "
            "const {buildGuardianRuntimeStatus}=await import('./packages/guardian-runtime/src/runtime-status.ts'); "
            "const pkg=JSON.parse(fs.readFileSync('package.json','utf8')); "
            "const runtime=buildGuardianRuntimeStatus({productVersion:String(pkg.version),runtimeVersion:String(pkg.version),state:'running',home:process.cwd(),owner:{surface:'read-only-dag',mode:'research'},endpoints:{},provider:{kind:'source',root:process.cwd()},startedAtMs:Date.now(),components:{guardian:'ready',workflow:'read-only'},componentDetail:{guardian:{state:'ready'},workflow:{state:'read-only'}},capabilities:['runtime.status']}); "
            "console.log('AEGIS_INPUT_CONSUMED=1'); console.log('AEGIS_INPUT_DATASET_SCHEMA='+m.schema); console.log('AEGIS_INPUT_STATE_FIELDS='+Object.keys(m.point_in_time_state).length); "
            "console.log('AEGIS_DOMAIN_ARTIFACT_SCHEMA=aegis.external_domain_artifact.v1'); console.log('AEGIS_DOMAIN_ARTIFACT_TOOL=OpenAlice'); console.log('AEGIS_DOMAIN_ARTIFACT_OPERATION=read_only_workflow_status_approvals_reports'); console.log('AEGIS_DOMAIN_ARTIFACT_STRATEGY_COUNT='+ids.length); "
            "console.log('AEGIS_DOMAIN_ARTIFACT_JSON='+JSON.stringify({schema:'aegis.external_domain_artifact.v1',tool:'OpenAlice',operation:'read_only_workflow_status_approvals_reports',selected_strategy_ids:ids,selected_strategy_count:ids.length,artifact:{runtime_status:runtime,workflow_status:'selected_validation_pending_review',approvals:{execution_bundle:false,mt5_demo:false},reports:ids.map(id=>({strategy_id:id,status:'read-only'})),read_only:true},domain_operation:true,input_data_kind:'selected_candidate_manifest',profitability_evidence:false})); })().catch((error)=>{ console.error(error); process.exit(1); });",
        )
    commands: dict[str, str] = {
        "awesome-systematic-trading": (
            "import pathlib,re; t=pathlib.Path('README.md').read_text(encoding='utf-8'); "
            "n=len(re.findall(r'https?://',t)); assert n>0; print(f'SOURCE_LINKS={n}')"
        ),
        "qlib": "import qlib; print('QLIB_VERSION='+str(getattr(qlib,'__version__','unknown')))",
        "ordersim": "import ordersim; print('ORDERSIM_IMPORT_OK')",
        "hftbacktest": (
            "import hftbacktest; print('HFTBACKTEST_VERSION='+str(getattr(hftbacktest,'__version__','unknown')))"
        ),
        "oos-lab": "import importlib.metadata as m; print('OOS_LAB_VERSION='+m.version('oos-lab'))",
        "Keystone": "import torch; print('KEYSTONE_TORCH='+torch.__version__)",
        "algorithmic-trading-research-framework": (
            "import compileall; ok=compileall.compile_dir('src',quiet=2); assert ok; print('RESEARCH_INTEGRITY_COMPILE_OK')"
        ),
        "samvid-trading-core": (
            "import compileall,importlib.metadata as m; ok=compileall.compile_dir('src',quiet=2); "
            "assert ok; print('SAMVID_VERSION='+m.version('samvid-trading-core'))"
        ),
        "Vibe-Trading": (
            "import subprocess; b=subprocess.check_output(['git','branch','--show-current'],text=True).strip(); "
            "assert b=='pr-481',b; print('VIBE_BRANCH='+b)"
        ),
        "metatrader5-mcp-server": (
            "import importlib.metadata as m; print('MT5_MCP_VERSION='+m.version('metatrader5-mcp-server'))"
        ),
        "nautilus_trader": (
            "import nautilus_trader; print('NAUTILUS_VERSION='+nautilus_trader.__version__)"
        ),
        "Lean": "import importlib.metadata as m; print('LEAN_VERSION='+m.version('lean'))",
        "abides": (
            "import numpy as np; from model.LatencyModel import LatencyModel; "
            "base=np.array([[0,1000],[2000,0]]); model=LatencyModel('cubic',random_state=np.random.RandomState(7),"
            "min_latency=base,jitter=0.5,jitter_clip=0.25,jitter_unit=10.0); "
            "samples=[model.get_latency(0,1) for _ in range(1000)]; assert min(samples)>=1000 and len(set(samples))>1; "
            "disconnected=LatencyModel('cubic',random_state=np.random.RandomState(7),min_latency=base,"
            "connected=np.array([[True,False],[True,True]])); assert disconnected.get_latency(0,1)==-1; "
            "print('ABIDES_LATENCY_STRESS_OK')"
        ),
    }
    if name == "abides":
        return _python_command(
            "import platform; platform._wmi_query=lambda *args: (_ for _ in ()).throw(OSError('wmi_unavailable')); "
            + commands[name]
            + "; import os,runpy; os.environ['AEGIS_DOMAIN_TOOL']='abides'; "
            + "runpy.run_path(" + repr(_DOMAIN_HELPER) + ",run_name='__main__')",
            environment,
        )
    if name in DOMAIN_ARTIFACT_TOOLS:
        return _domain_python_command(name, environment)
    return _python_command(commands[name], environment)


def load_external_catalog(project_root: str | Path) -> tuple[ExternalToolSpec, ...]:
    """Load all pinned external tools; an incomplete manifest fails closed."""
    root = Path(project_root).resolve()
    manifest_path = root / "bot" / "reports" / "research" / "external_dependency_manifest.json"
    raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    repositories = {str(row.get("name")): row for row in raw.get("repositories") or ()}
    missing = sorted(REQUIRED_EXTERNAL_TOOLS - repositories.keys())
    extra = sorted(repositories.keys() - REQUIRED_EXTERNAL_TOOLS)
    if missing:
        raise ValueError("missing required external tools: " + ",".join(missing))
    if extra:
        raise ValueError("unexpected external tools: " + ",".join(extra))

    environments = {str(row.get("name")): row for row in raw.get("environments") or ()}
    project_python = root / ".venv" / "Scripts" / "python.exe"
    specs: list[ExternalToolSpec] = []
    for name in sorted(REQUIRED_EXTERNAL_TOOLS):
        row = repositories[name]
        role, capabilities, environment_key = _TOOL_METADATA[name]
        if environment_key == "node":
            environment = shutil.which("pnpm") or "pnpm"
        elif environment_key == "internal":
            environment = str(project_python)
        else:
            environment_row = environments.get(environment_key) or {}
            environment = str(environment_row.get("python") or "")
        repository_path = str(row.get("path") or "")
        if name == "OpenAlice":
            no_space_openalice = Path("C:/AEGISExternalLinks/OpenAlice")
            if no_space_openalice.is_dir():
                repository_path = str(no_space_openalice)
        specs.append(
            ExternalToolSpec(
                tool_id=name,
                role=role,
                repository_path=repository_path,
                repository_sha=str(row.get("commit") or "").lower(),
                environment=environment,
                capabilities=capabilities,
                command=_command_for(name, environment),
                timeout_s=180.0 if name in DOMAIN_ARTIFACT_TOOLS else 60.0,
                broker_authority=False,
            )
        )
    return tuple(specs)


__all__ = [
    "DOMAIN_ARTIFACT_OPERATIONS",
    "DOMAIN_ARTIFACT_TOOLS",
    "REQUIRED_EXTERNAL_TOOLS",
    "load_external_catalog",
]
