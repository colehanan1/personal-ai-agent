"""
CORTEX - Execution Agent
Handles task execution, code generation, and overnight job processing.
"""
import requests
from typing import Dict, Any, Optional, List
import os
import json
import subprocess
from datetime import datetime
from dotenv import load_dotenv
import logging

from agents.memory_hooks import (
    build_memory_context,
    record_memory,
    should_store_responses,
)
load_dotenv()

logger = logging.getLogger(__name__)


class CORTEX:
    """
    CORTEX execution agent.

    Responsibilities:
    - Generate work plans from user requests
    - Execute multi-step tasks
    - Write and run code
    - Process overnight jobs
    - Generate execution reports
    """

    def __init__(
        self,
        model_url: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Initialize CORTEX agent.

        Args:
            model_url: vLLM API URL (defaults to env var)
            model_name: Model name (defaults to env var)
        """
        self.model_url = (
            model_url
            or os.getenv("LLM_API_URL")
            or os.getenv("OLLAMA_API_URL", "http://localhost:8000")
        ).rstrip("/")
        self.model_name = (
            model_name
            or os.getenv("LLM_MODEL")
            or os.getenv("OLLAMA_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
        )
        self.system_prompt = self._load_system_prompt()

        logger.info("CORTEX agent initialized")

    def _load_system_prompt(self) -> str:
        """Load CORTEX system prompt from Prompts folder."""
        from agents import load_agent_context
        return load_agent_context("CORTEX")

    def _call_llm(
        self, prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 2000
    ) -> str:
        """
        Call vLLM API for inference.

        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            max_tokens: Maximum tokens to generate

        Returns:
            Model response
        """
        url = f"{self.model_url}/v1/chat/completions"
        api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("VLLM_API_KEY")
            or os.getenv("OLLAMA_API_KEY")
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        memory_context = build_memory_context("CORTEX", prompt)
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }

        try:
            response = requests.post(url, json=payload, timeout=120, headers=headers)
            response.raise_for_status()
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            record_memory(
                "CORTEX",
                prompt,
                memory_type="crumb",
                tags=["request"],
                importance=0.2,
                source="user",
            )
            if should_store_responses():
                record_memory(
                    "CORTEX",
                    reply,
                    memory_type="crumb",
                    tags=["response"],
                    importance=0.1,
                    source="assistant",
                )
            return reply
        except Exception as e:
            logger.error(f"LLM API error: {e}")
            raise

    def generate_plan(self, user_request: str) -> Dict[str, Any]:
        """
        Generate execution plan for user request.

        Args:
            user_request: Task description from user

        Returns:
            Work plan as JSON with steps, dependencies, and estimated complexity

        Example:
            >>> cortex = CORTEX()
            >>> plan = cortex.generate_plan("Analyze fMRI data and generate report")
            >>> print(plan["steps"])
        """
        prompt = f"""
Generate a detailed execution plan for the following task:

Task: {user_request}

Provide a JSON work plan with:
1. Steps (numbered, actionable)
2. Dependencies between steps
3. Required tools/integrations
4. Estimated complexity (low, medium, high)
5. Success criteria

Format as valid JSON.
"""

        response = self._call_llm(prompt, system_prompt=self.system_prompt)

        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            plan_json = response[json_start:json_end]
            plan = json.loads(plan_json)
        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            plan = {
                "steps": [{"step": 1, "action": user_request}],
                "complexity": "unknown",
            }

        return plan

    def execute_step(self, step: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single step from work plan.

        Args:
            step: Step dictionary from plan
            context: Execution context (previous results, environment, etc.)

        Returns:
            Execution result
        """
        logger.info(f"Executing step: {step}")

        prompt = f"""
Execute the following step:

Step: {step}

Context:
{json.dumps(context, indent=2)}

Provide the result and any output.
"""

        result = self._call_llm(prompt, system_prompt=self.system_prompt)

        return {
            "step": step,
            "result": result,
            "timestamp": datetime.now().isoformat(),
            "status": "completed",
        }

    def write_code(self, task: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate code for a specific task.

        Args:
            task: Code generation task description
            context: Additional context (language, framework, etc.)

        Returns:
            Generated code
        """
        context_str = json.dumps(context, indent=2) if context else "No additional context"

        prompt = f"""
Write code for the following task:

Task: {task}

Context:
{context_str}

Provide clean, well-documented code with type hints and error handling.
"""

        code = self._call_llm(prompt, system_prompt=self.system_prompt, max_tokens=3000)

        return code

    def run_script(
        self, script_path: str, args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run a Python script.

        Args:
            script_path: Path to script
            args: Command-line arguments

        Returns:
            Execution result (stdout, stderr, return code)
        """
        cmd = ["python", script_path]

        if args:
            cmd.extend(args)

        logger.info(f"Running script: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "success": result.returncode == 0,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Script timeout: {script_path}")
            return {
                "stdout": "",
                "stderr": "Script execution timeout",
                "return_code": -1,
                "success": False,
            }
        except Exception as e:
            logger.error(f"Script execution error: {e}")
            return {
                "stdout": "",
                "stderr": str(e),
                "return_code": -1,
                "success": False,
            }

    def generate_report(self, execution_results: List[Dict[str, Any]]) -> str:
        """
        Generate execution report from results.

        Args:
            execution_results: List of step execution results

        Returns:
            Formatted report
        """
        prompt = f"""
Generate a concise execution report from the following results:

{json.dumps(execution_results, indent=2)}

Include:
- Summary of completed tasks
- Key outcomes
- Any errors or issues
- Recommendations for next steps

Format as a clear, readable report.
"""

        report = self._call_llm(prompt, system_prompt=self.system_prompt, max_tokens=1500)

        return report

    def process_overnight_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process an overnight job from the queue.

        Args:
            job: Job specification

        Returns:
            Job execution result
        """
        logger.info(f"Processing overnight job: {job.get('id', 'unknown')}")

        # Generate plan
        plan = self.generate_plan(job["task"])

        # Execute steps
        context = {}
        results = []

        for step in plan.get("steps", []):
            result = self.execute_step(step, context)
            results.append(result)

            # Update context with result
            context[f"step_{step.get('step', len(results))}"] = result

        # Generate report
        report = self.generate_report(results)

        return {
            "job_id": job.get("id"),
            "task": job["task"],
            "plan": plan,
            "results": results,
            "report": report,
            "completed_at": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    # Simple test
    cortex = CORTEX()
    print("CORTEX agent initialized")
    print(f"Model: {cortex.model_name}")
    print(f"API URL: {cortex.model_url}")
