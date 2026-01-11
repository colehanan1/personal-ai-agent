"""
CORTEX - Execution Agent
Handles task execution, code generation, and overnight job processing.
"""
import requests
from typing import Dict, Any, Optional, List, Union
import os
import json
import subprocess
from datetime import datetime
from dotenv import load_dotenv
import logging

from agents.memory_hooks import (
    MemoryContextHook,
    build_memory_context,
    record_memory,
    should_store_responses,
)
from agents.contracts import (
    TaskRequest,
    TaskPlan,
    TaskStep,
    TaskResult,
    TaskStatus,
    AgentReport,
    generate_task_id,
    generate_iso_timestamp,
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
        adapter_name: Optional[str] = None,
    ):
        """
        Initialize CORTEX agent.

        Args:
            model_url: vLLM API URL (defaults to env var)
            model_name: Model name (defaults to env var)
            adapter_name: LoRA adapter name to load (optional)
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
        
        # Initialize memory context hook with semantic search
        self.memory_hook = MemoryContextHook(
            agent="CORTEX",
            use_semantic=True,
            semantic_weight=0.6,  # Slight bias toward semantic for execution context
        )
        
        # Load LoRA adapter if specified
        self.adapter_info = None
        if adapter_name:
            self._load_adapter(adapter_name)
        elif os.getenv("CORTEX_ADAPTER"):
            self._load_adapter(os.getenv("CORTEX_ADAPTER"))

        logger.info("CORTEX agent initialized with semantic memory context")

    def _load_adapter(self, adapter_name: str) -> None:
        """
        Load LoRA adapter information.
        
        Note: Actual adapter loading would happen at the LLM server level.
        This method loads adapter metadata for provenance tracking.
        
        Args:
            adapter_name: Name of adapter to load
        """
        try:
            from training.adapter_manager import AdapterManager
            
            manager = AdapterManager()
            adapter = manager.get_adapter(adapter_name)
            
            if adapter:
                self.adapter_info = adapter
                logger.info(
                    f"Loaded adapter metadata: {adapter_name} "
                    f"(quality={adapter.quality_score:.2%})"
                )
            else:
                logger.warning(f"Adapter not found: {adapter_name}")
                
        except Exception as e:
            logger.warning(f"Failed to load adapter metadata: {e}")

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

        # Use new MemoryContextHook with semantic search
        memory_context = self.memory_hook.build_context(prompt, agent="CORTEX")
        if memory_context:
            messages.append({"role": "system", "content": memory_context})

        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        
        # Add adapter provenance metadata if adapter loaded
        if self.adapter_info:
            payload["metadata"] = {
                "adapter": self.adapter_info.name,
                "adapter_version": self.adapter_info.version,
                "adapter_quality": self.adapter_info.quality_score,
                "train_timestamp": self.adapter_info.timestamp,
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

    def generate_plan(self, user_request: Union[str, TaskRequest]) -> TaskPlan:
        """
        Generate execution plan for user request.

        Args:
            user_request: Task description string or TaskRequest object

        Returns:
            TaskPlan object with validated steps and metadata

        Example:
            >>> cortex = CORTEX()
            >>> plan = cortex.generate_plan("Analyze fMRI data and generate report")
            >>> print(plan.steps)
        """
        # Handle both string and TaskRequest inputs for backward compatibility
        if isinstance(user_request, TaskRequest):
            task_id = user_request.task_id
            description = user_request.task_description
        else:
            task_id = generate_task_id("cortex")
            description = user_request

        prompt = f"""
Generate a detailed execution plan for the following task:

Task: {description}

Provide a JSON work plan with:
1. Steps (numbered, actionable) - each step must have:
   - step_number (int, starting from 1)
   - action (string, clear description)
   - dependencies (list of step numbers that must complete first)
   - estimated_complexity (low/medium/high)
   - success_criteria (string, how to verify completion)
2. overall_complexity (low/medium/high)
3. required_tools (list of tool names)
4. estimated_duration (optional human-readable string)

Format as valid JSON.
"""

        response = self._call_llm(prompt, system_prompt=self.system_prompt)

        try:
            # Extract JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            plan_json = response[json_start:json_end]
            plan_data = json.loads(plan_json)

            # Convert to TaskPlan format
            steps = []
            for step_data in plan_data.get("steps", []):
                step = TaskStep(
                    step_number=step_data.get("step_number", step_data.get("step", len(steps) + 1)),
                    action=step_data.get("action", ""),
                    dependencies=step_data.get("dependencies", []),
                    estimated_complexity=step_data.get("estimated_complexity", "medium"),
                    success_criteria=step_data.get("success_criteria", ""),
                )
                steps.append(step)

            # If no steps parsed, create a fallback single step
            if not steps:
                steps = [
                    TaskStep(
                        step_number=1,
                        action=description,
                        estimated_complexity="medium",
                        success_criteria="Task completed successfully",
                    )
                ]

            plan = TaskPlan(
                task_id=task_id,
                created_at=generate_iso_timestamp(),
                agent="cortex",
                steps=steps,
                overall_complexity=plan_data.get("overall_complexity", plan_data.get("complexity", "medium")),
                required_tools=plan_data.get("required_tools", []),
                estimated_duration=plan_data.get("estimated_duration", ""),
            )

        except Exception as e:
            logger.error(f"Failed to parse plan: {e}")
            # Create fallback plan
            plan = TaskPlan(
                task_id=task_id,
                created_at=generate_iso_timestamp(),
                agent="cortex",
                steps=[
                    TaskStep(
                        step_number=1,
                        action=description,
                        estimated_complexity="medium",
                        success_criteria="Task completed successfully",
                    )
                ],
                overall_complexity="medium",
                required_tools=[],
            )

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

    def process_overnight_job(self, job: Dict[str, Any]) -> TaskResult:
        """
        Process an overnight job from the queue.

        Args:
            job: Job specification dict with 'id' and 'task' fields

        Returns:
            TaskResult object with execution details

        Example:
            >>> job = {"id": "job_001", "task": "Analyze logs and generate report"}
            >>> result = cortex.process_overnight_job(job)
            >>> print(result.status)
        """
        job_id = job.get("id", generate_task_id("job"))
        task_desc = job.get("task", "")

        logger.info(f"Processing overnight job: {job_id}")

        try:
            # Generate plan
            plan = self.generate_plan(task_desc)

            # Execute steps
            context = {}
            results = []

            for step in plan.steps:
                step_result = self.execute_step(step.to_dict(), context)
                results.append(step_result)

                # Update context with result
                context[f"step_{step.step_number}"] = step_result

            # Generate report
            report_text = self.generate_report(results)

            # Create successful result
            result = TaskResult(
                task_id=job_id,
                completed_at=generate_iso_timestamp(),
                agent="cortex",
                status=TaskStatus.COMPLETED,
                output=report_text,
                output_paths=[],
                evidence_refs=[],
                metadata={
                    "plan": plan.to_dict(),
                    "step_count": len(results),
                    "job_data": job,
                },
            )

        except Exception as e:
            logger.error(f"Job execution failed: {e}", exc_info=True)
            # Create failed result
            result = TaskResult(
                task_id=job_id,
                completed_at=generate_iso_timestamp(),
                agent="cortex",
                status=TaskStatus.FAILED,
                output="",
                error_message=str(e),
                metadata={"job_data": job},
            )

        return result


if __name__ == "__main__":
    # Simple test
    cortex = CORTEX()
    print("CORTEX agent initialized")
    print(f"Model: {cortex.model_name}")
    print(f"API URL: {cortex.model_url}")
