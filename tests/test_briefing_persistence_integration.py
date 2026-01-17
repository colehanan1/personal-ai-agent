"""Integration test for briefing persistence across API restart.

This test shells out to scripts/test_briefing_persistence.sh to verify
that briefing items persist in SQLite across API server restarts.

Marked as integration test and opt-in via RUN_INTEGRATION=1 environment variable.
"""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="Integration test - set RUN_INTEGRATION=1 to enable"
)
def test_briefing_persistence_across_restart():
    """Test that briefing items persist across API server restart.
    
    This is a smoke test that shells out to the bash script which performs:
    1. Start API server
    2. Create a briefing item
    3. Stop server cleanly
    4. Restart server
    5. Verify the item still exists
    
    The bash script handles all the details including:
    - PID-based process control
    - Health check waiting
    - Clean shutdown
    - Deterministic verification
    """
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "test_briefing_persistence.sh"
    
    # Verify script exists
    assert script_path.exists(), f"Script not found: {script_path}"
    assert script_path.is_file(), f"Path is not a file: {script_path}"
    
    # Run the script
    result = subprocess.run(
        ["bash", str(script_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=120  # 2 minute timeout
    )
    
    # Check exit code
    if result.returncode != 0:
        # Print diagnostic output on failure
        print("\n=== STDOUT ===")
        print(result.stdout)
        print("\n=== STDERR ===")
        print(result.stderr)
        pytest.fail(
            f"Briefing persistence test failed with exit code {result.returncode}.\n"
            "See output above for details."
        )
    
    # Verify the script reported success
    assert "TEST PASSED" in result.stdout, \
        "Script exited 0 but did not report TEST PASSED"
    assert "Briefing item persisted across restart" in result.stdout, \
        "Script did not confirm persistence"
