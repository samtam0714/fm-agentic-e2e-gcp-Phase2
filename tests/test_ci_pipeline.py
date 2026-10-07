"""CI pipeline configuration smoke tests that do not run Cloud Build."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ci_release_script_exists():
    script = ROOT / "scripts" / "ci_release.sh"
    assert script.exists()
    assert script.stat().st_mode & 0o111, "ci_release.sh should be executable"


def test_submit_ci_build_script_exists():
    script = ROOT / "scripts" / "submit_ci_build.sh"
    assert script.exists()


def test_cloudbuild_ci_yaml_structure():
    path = ROOT / "deployment" / "cloudbuild-ci.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    step_ids = [step.get("id") for step in config["steps"]]
    assert "test-eval-gate" in step_ids
    assert "build-image" in step_ids
    assert "deploy-cloud-run" in step_ids

    test_step = next(s for s in config["steps"] if s["id"] == "test-eval-gate")
    assert "ci_release.sh" in test_step["args"][-1]

    assert config.get("timeout") == "3600s"
    assert config["substitutions"]["_EVAL_DATASET"] == "all"


def test_cloudbuild_ci_defaults_to_reusing_local_eval():
    """Cloud Build defaults to reusing local eval_report.json and running gates."""
    path = ROOT / "deployment" / "cloudbuild-ci.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    assert config["substitutions"]["_SKIP_AGENT_EVAL"] == "true"

    test_step = next(s for s in config["steps"] if s["id"] == "test-eval-gate")
    inline = test_step["args"][-1]
    # Cloud Build must require eval_report.json when evaluation is skipped.
    assert "eval_report.json" in inline
    assert "SKIP_AGENT_EVAL=" in inline


def test_submit_ci_build_passes_skip_agent_eval_substitution():
    """The submit script passes _SKIP_AGENT_EVAL and validates the local report."""
    script = (ROOT / "scripts" / "submit_ci_build.sh").read_text(encoding="utf-8")
    assert "_SKIP_AGENT_EVAL=" in script
    assert "eval_report.json" in script


def test_baseline_and_regression_rules_exist_for_ci_gate():
    """The CI gate requires baseline, absolute, and regression rule files."""
    assert (ROOT / "eval_harness" / "reports" / "baseline.json").exists()
    assert (ROOT / "eval_harness" / "gates" / "absolute_rules.yaml").exists()
    assert (ROOT / "eval_harness" / "gates" / "regression_rules.yaml").exists()
    # Sprint 1 / 2.1.5: versioned milestone baseline is authoritative.
    assert (
        ROOT / "eval_harness" / "baselines" / "phase2-adk-skills.json"
    ).exists()


def test_retrieval_baseline_exists_for_sprint6():
    assert (
        ROOT / "eval_harness" / "baselines" / "phase2-retrieval.json"
    ).exists()


def test_cloud_build_upload_prerequisites():
    """gcloud submission includes uv.lock, baseline, and reusable evaluation reports."""
    assert (ROOT / "uv.lock").exists(), "uv.lock is required for uv sync --frozen"
    gcloudignore = (ROOT / ".gcloudignore").read_text(encoding="utf-8")
    assert "!eval_harness/reports/baseline.json" in gcloudignore
    assert "!eval_harness/reports/eval_report.json" in gcloudignore


def test_nightly_scripts_exist_and_executable():
    """Sprint 2.2.5 nightly evaluation and scheduler scripts are executable."""
    nightly = ROOT / "scripts" / "nightly_eval.sh"
    scheduler = ROOT / "scripts" / "setup_nightly_scheduler.sh"
    assert nightly.exists() and nightly.stat().st_mode & 0o111
    assert scheduler.exists() and scheduler.stat().st_mode & 0o111


def test_cloudbuild_nightly_yaml_structure():
    """Nightly configuration evaluates and gates without building or deploying."""
    path = ROOT / "deployment" / "cloudbuild-nightly.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    step_ids = [step.get("id") for step in config["steps"]]
    assert "nightly-eval-gate" in step_ids
    # Nightly is monitoring only and must not build or deploy.
    assert "build-image" not in step_ids
    assert "deploy-cloud-run" not in step_ids

    step = next(s for s in config["steps"] if s["id"] == "nightly-eval-gate")
    assert "nightly_eval.sh" in step["args"][-1]
    # Full evaluation needs a longer timeout than regular CI.
    assert int(config["timeout"].rstrip("s")) >= 3600


def test_nightly_eval_runs_full_eval_not_skipped():
    """Nightly must run evaluation rather than reuse an old report."""
    script = (ROOT / "scripts" / "nightly_eval.sh").read_text(encoding="utf-8")
    assert "run_agent_eval.py" in script
    assert "release_gate/gate.py" in script
    # Archive history for seven-day trend analysis.
    assert "history" in script


def test_dockerfile_copies_mcp_servers_for_cloud_run():
    """The Cloud Run image includes MCP servers required by USE_MCP_TOOLS."""
    dockerfile = (ROOT / "deployment" / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY mcp_servers/" in dockerfile
    assert "COPY skills/" in dockerfile


def test_cloud_run_deploy_enables_mcp_tools():
    """Sprint 3.4 deployment and CI pass USE_MCP_TOOLS to Cloud Run."""
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "USE_MCP_TOOLS" in deploy
    assert "MCP_TOOL_TIMEOUT_SECONDS" in deploy

    path = ROOT / "deployment" / "cloudbuild-ci.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config["substitutions"].get("_USE_MCP_TOOLS") == "1"
    deploy_step = next(s for s in config["steps"] if s["id"] == "deploy-cloud-run")
    inline = deploy_step["args"][-1]
    assert "USE_MCP_TOOLS=${_USE_MCP_TOOLS}" in inline


def test_cloud_run_deploy_wires_sprint4_observability_flags():
    """Sprint 4 Cloud Trace and BigQuery switches are configurable and default off."""
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert "ENABLE_CLOUD_TRACE" in deploy
    assert "ENABLE_BIGQUERY" in deploy
    assert "BIGQUERY_DATASET" in deploy

    path = ROOT / "deployment" / "cloudbuild-ci.yaml"
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config["substitutions"].get("_ENABLE_CLOUD_TRACE") == "0"
    assert config["substitutions"].get("_ENABLE_BIGQUERY") == "0"
    deploy_step = next(s for s in config["steps"] if s["id"] == "deploy-cloud-run")
    inline = deploy_step["args"][-1]
    assert "ENABLE_CLOUD_TRACE=${_ENABLE_CLOUD_TRACE}" in inline
    assert "ENABLE_BIGQUERY=${_ENABLE_BIGQUERY}" in inline


def test_mcp_timeout_smoke_script_exists():
    script = ROOT / "scripts" / "smoke_mcp_docker.sh"
    assert script.exists()
    assert "USE_MCP_TOOLS=1" in script.read_text(encoding="utf-8")
