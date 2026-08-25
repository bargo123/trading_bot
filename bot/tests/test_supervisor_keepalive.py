from pathlib import Path


def test_keepalive_starts_the_predictive_video_style_runner():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "supervisor_keepalive.ps1"
    ).read_text(encoding="utf-8")

    assert '"-u", "scripts\\run_broker_paper.py"' in script
    assert '"--config", $PaperCfg' in script
    assert '"--video-style"' in script
