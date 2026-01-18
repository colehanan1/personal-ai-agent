#!/usr/bin/env python3
"""
System Health Check Script
Checks vLLM, Weaviate, and agent status
Outputs JSON status report
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
import requests
import subprocess

from milton_orchestrator.state_paths import resolve_state_dir

ROOT_DIR = Path(__file__).resolve().parents[1]

def check_vllm():
    """Check if vLLM inference server is running"""
    try:
        # Use API key if available (vLLM may or may not require auth)
        api_key = os.getenv("VLLM_API_KEY") or os.getenv("LLM_API_KEY")
        headers = {}
        if api_key:
            headers = {"Authorization": f"Bearer {api_key}"}
        
        r = requests.get("http://localhost:8000/v1/models", headers=headers, timeout=2)
        if r.status_code == 200:
            data = r.json()
            model = data.get('data', [{}])[0].get('id', 'unknown')
            return {
                "service": "vLLM",
                "port": 8000,
                "status": "UP",
                "model": model,
                "last_check": datetime.now(timezone.utc).isoformat() + "Z",
                "issues": []
            }
        else:
            return {"service": "vLLM", "status": "DOWN", "issues": [f"HTTP {r.status_code}"]}
    except Exception as e:
        return {"service": "vLLM", "status": "DOWN", "issues": [str(e)]}

def check_weaviate():
    """Check if Weaviate vector DB is running"""
    try:
        r = requests.get("http://localhost:8080/v1/meta", timeout=2)
        if r.status_code == 200:
            data = r.json()
            version = data.get('version', 'unknown')
            return {
                "service": "Weaviate",
                "port": 8080,
                "status": "UP",
                "version": version,
                "issues": []
            }
        else:
            return {"service": "Weaviate", "status": "DOWN", "issues": [f"HTTP {r.status_code}"]}
    except Exception as e:
        return {"service": "Weaviate", "status": "DOWN", "issues": [str(e)]}

def check_agents():
    """Check if agents can be imported"""
    agents_status = {}

    for agent_name in ["nexus", "cortex", "frontier"]:
        try:
            module = __import__(f"agents.{agent_name}", fromlist=[agent_name.upper()])
            agents_status[agent_name] = {
                "status": "IMPORTABLE",
                "issues": []
            }
        except Exception as e:
            agents_status[agent_name] = {
                "status": "IMPORT_FAILED",
                "issues": [str(e)]
            }

    return agents_status

def check_logs():
    """Check if log directories have recent activity"""
    log_dir = resolve_state_dir() / "logs"
    log_status = {}

    for agent in ["nexus", "cortex", "frontier"]:
        agent_log_dir = log_dir / agent
        if agent_log_dir.exists():
            log_files = list(agent_log_dir.glob("*.log"))
            log_status[f"{agent}_recent"] = len(log_files) > 0
            log_status[f"{agent}_count"] = len(log_files)
        else:
            log_status[f"{agent}_recent"] = False
            log_status[f"{agent}_count"] = 0

    return log_status

def main():
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "system_root": str(ROOT_DIR),
        "components": {
            "inference": check_vllm(),
            "memory": check_weaviate(),
            "agents": check_agents()
        },
        "logs": check_logs(),
        "issues_found": [],
        "confidence_level": "HIGH"
    }

    # Collect all issues
    for component, data in status["components"].items():
        if isinstance(data, dict):
            if data.get("status") in ["DOWN", "IMPORT_FAILED"]:
                for issue in data.get("issues", []):
                    status["issues_found"].append({
                        "severity": "CRITICAL",
                        "component": component,
                        "issue": issue
                    })

    # Determine confidence level
    critical_count = len([i for i in status["issues_found"] if i["severity"] == "CRITICAL"])
    if critical_count == 0:
        status["confidence_level"] = "HIGH"
        status["notes"] = "All systems operational"
    elif critical_count <= 2:
        status["confidence_level"] = "MEDIUM"
        status["notes"] = f"{critical_count} critical issues found"
    else:
        status["confidence_level"] = "LOW"
        status["notes"] = f"{critical_count} critical issues - system degraded"

    print(json.dumps(status, indent=2))

    # Exit with error code if issues found
    return 0 if critical_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
