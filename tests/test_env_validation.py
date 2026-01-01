from pathlib import Path

from milton_orchestrator.env_validation import validate_env_values


def test_env_validation_missing_required_vars():
    result = validate_env_values({})
    assert any("PERPLEXITY_API_KEY" in error for error in result.errors)
    assert any("TARGET_REPO" in error for error in result.errors)


def test_env_validation_target_repo_must_exist(tmp_path: Path):
    env = {
        "PERPLEXITY_API_KEY": "fake-key",
        "TARGET_REPO": str(tmp_path / "missing"),
    }
    result = validate_env_values(env)
    assert any("TARGET_REPO does not exist" in error for error in result.errors)


def test_env_validation_ok(tmp_path: Path):
    env = {
        "PERPLEXITY_API_KEY": "fake-key",
        "TARGET_REPO": str(tmp_path),
    }
    result = validate_env_values(env)
    assert not result.errors
