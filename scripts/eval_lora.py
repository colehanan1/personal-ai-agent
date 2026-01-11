#!/usr/bin/env python3
"""
LoRA Adapter Evaluation Harness

Evaluates trained LoRA adapters using:
1. Test set metrics (perplexity, loss, token accuracy)
2. Sanity prompts (qualitative responses)
3. Task-specific benchmarks (Milton-specific tests)

Auto-promotes to "candidate" status if benchmarks pass.

Usage:
    python scripts/eval_lora.py --run-id lora_20260105_142301 [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)

# Lazy imports for heavy dependencies
def _import_eval_deps():
    """Lazy import of evaluation dependencies."""
    global torch, transformers, peft, datasets, np
    try:
        import torch
        import transformers
        from peft import PeftModel, PeftConfig
        from datasets import load_dataset
        import datasets
        import numpy as np
    except ImportError as e:
        logger.error(f"Missing evaluation dependencies: {e}")
        logger.error("Install with: pip install transformers peft datasets torch numpy")
        sys.exit(1)


def load_adapter_model(run_id: str) -> Tuple[Any, Any]:
    """
    Load base model + LoRA adapter.

    Args:
        run_id: Adapter run ID (e.g., lora_20260105_142301)

    Returns:
        Tuple of (model, tokenizer)
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel, PeftConfig
    import torch

    adapter_dir = ROOT_DIR / "adapters" / run_id

    if not adapter_dir.exists():
        raise FileNotFoundError(f"Adapter not found: {adapter_dir}")

    # Load metadata to get base model path
    metadata_path = adapter_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Metadata not found: {metadata_path}")

    with metadata_path.open("r") as f:
        metadata = json.load(f)

    base_model_path = metadata["training"]["config"]["base_model_path"]

    logger.info(f"Loading adapter from {adapter_dir}...")
    logger.info(f"  Base model: {base_model_path}")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(adapter_dir)

    # Load base model
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True
    )

    # Load adapter
    model = PeftModel.from_pretrained(base_model, adapter_dir)
    model.eval()

    logger.info("✅ Model loaded successfully")

    return model, tokenizer


def compute_test_metrics(
    model,
    tokenizer,
    test_file: Path,
    batch_size: int = 4
) -> Dict[str, Any]:
    """
    Compute evaluation metrics on held-out test set.

    Args:
        model: PEFT model
        tokenizer: Tokenizer
        test_file: Path to test.jsonl
        batch_size: Batch size for evaluation

    Returns:
        Dictionary with perplexity, eval_loss, token_accuracy
    """
    from datasets import load_dataset
    from torch.utils.data import DataLoader
    import torch
    import numpy as np

    logger.info(f"Computing test set metrics on {test_file}...")

    # Load test data
    dataset = load_dataset("json", data_files=str(test_file))["train"]

    # Tokenize
    def tokenize_function(examples):
        texts = []
        for messages in examples["messages"]:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=False
            )
            texts.append(text)

        result = tokenizer(
            texts,
            truncation=True,
            max_length=2048,
            padding="max_length",
            return_tensors="pt"
        )
        result["labels"] = result["input_ids"].clone()
        return result

    tokenized = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=dataset.column_names,
        desc="Tokenizing test set"
    )

    # Create dataloader
    tokenized.set_format("torch")
    dataloader = DataLoader(tokenized, batch_size=batch_size)

    # Evaluate
    model.eval()
    total_loss = 0.0
    total_tokens = 0
    correct_tokens = 0

    with torch.no_grad():
        for batch in dataloader:
            # Move to device
            input_ids = batch["input_ids"].to(model.device)
            attention_mask = batch["attention_mask"].to(model.device)
            labels = batch["labels"].to(model.device)

            # Forward pass
            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels
            )

            # Accumulate loss
            total_loss += outputs.loss.item() * input_ids.size(0)

            # Token accuracy (where labels != -100)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=-1)

            # Mask padding tokens
            valid_mask = (labels != -100) & (labels != tokenizer.pad_token_id)
            correct = (predictions == labels) & valid_mask
            correct_tokens += correct.sum().item()
            total_tokens += valid_mask.sum().item()

    # Compute metrics
    avg_loss = total_loss / len(dataset)
    perplexity = np.exp(avg_loss)
    token_accuracy = correct_tokens / total_tokens if total_tokens > 0 else 0.0

    metrics = {
        "perplexity": float(perplexity),
        "eval_loss": float(avg_loss),
        "token_accuracy": float(token_accuracy),
        "num_examples": len(dataset)
    }

    logger.info(f"✅ Test metrics:")
    logger.info(f"   Perplexity: {perplexity:.4f}")
    logger.info(f"   Loss: {avg_loss:.4f}")
    logger.info(f"   Token accuracy: {token_accuracy:.4f}")

    return metrics


def evaluate_sanity_prompts(
    model,
    tokenizer,
    prompts_file: Path,
    run_dir: Path
) -> Dict[str, Any]:
    """
    Generate responses for sanity check prompts.

    Args:
        model: PEFT model
        tokenizer: Tokenizer
        prompts_file: Path to sanity_prompts.json
        run_dir: Run directory for saving responses

    Returns:
        Dictionary with prompt evaluation summary
    """
    import torch

    if not prompts_file.exists():
        logger.warning(f"Sanity prompts file not found: {prompts_file}")
        return {"status": "skipped", "reason": "prompts file not found"}

    logger.info(f"Evaluating sanity prompts from {prompts_file}...")

    # Load prompts
    with prompts_file.open("r") as f:
        prompts = json.load(f)

    responses = []
    model.eval()

    for i, prompt_data in enumerate(prompts):
        prompt_text = prompt_data["prompt"]
        category = prompt_data.get("category", "general")

        # Format as chat message
        messages = [
            {"role": "system", "content": "You are Milton, a personal AI assistant."},
            {"role": "user", "content": prompt_text}
        ]

        # Apply chat template
        input_text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        # Tokenize
        inputs = tokenizer(input_text, return_tensors="pt").to(model.device)

        # Generate
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )

        # Decode
        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        responses.append({
            "prompt": prompt_text,
            "category": category,
            "response": response
        })

        logger.info(f"  Prompt {i+1}/{len(prompts)} ({category}): ✓")

    # Save responses for manual review
    responses_file = run_dir / "sanity_responses.json"
    with responses_file.open("w") as f:
        json.dump(responses, indent=2, fp=f)

    logger.info(f"✅ Sanity prompts evaluated: {responses_file}")

    return {
        "status": "completed",
        "num_prompts": len(prompts),
        "responses_file": str(responses_file.relative_to(ROOT_DIR))
    }


def evaluate_task_benchmarks(
    model,
    tokenizer,
    benchmarks_file: Path
) -> Dict[str, Any]:
    """
    Run Milton-specific task benchmarks.

    Args:
        model: PEFT model
        tokenizer: Tokenizer
        benchmarks_file: Path to task_benchmarks.json

    Returns:
        Dictionary with benchmark results and pass rate
    """
    import torch

    if not benchmarks_file.exists():
        logger.warning(f"Benchmarks file not found: {benchmarks_file}")
        return {"status": "skipped", "reason": "benchmarks file not found"}

    logger.info(f"Running task benchmarks from {benchmarks_file}...")

    # Load benchmarks
    with benchmarks_file.open("r") as f:
        benchmarks = json.load(f)

    results = {}
    total_tests = 0
    total_passed = 0

    model.eval()

    for category, tests in benchmarks.items():
        category_passed = 0
        category_total = len(tests)

        logger.info(f"  Category: {category} ({category_total} tests)")

        for test in tests:
            prompt = test["prompt"]
            expected_keywords = test.get("expected_keywords", [])
            must_not_contain = test.get("must_not_contain", [])

            # Format as chat
            messages = [
                {"role": "system", "content": "You are Milton, a personal AI assistant."},
                {"role": "user", "content": prompt}
            ]

            input_text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )

            # Generate
            inputs = tokenizer(input_text, return_tensors="pt").to(model.device)
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=256,
                    temperature=0.7,
                    top_p=0.9,
                    do_sample=False,  # Deterministic for testing
                    pad_token_id=tokenizer.eos_token_id
                )

            response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

            # Check criteria
            passed = True

            # Check expected keywords
            if expected_keywords:
                for keyword in expected_keywords:
                    if keyword.lower() not in response.lower():
                        passed = False
                        break

            # Check forbidden content
            if must_not_contain:
                for forbidden in must_not_contain:
                    if forbidden.lower() in response.lower():
                        passed = False
                        break

            if passed:
                category_passed += 1
                total_passed += 1

            total_tests += 1

        category_pass_rate = category_passed / category_total if category_total > 0 else 0.0

        results[category] = {
            "pass": category_passed,
            "total": category_total,
            "pass_rate": category_pass_rate
        }

        logger.info(f"    {category}: {category_passed}/{category_total} ({category_pass_rate:.1%})")

    # Overall pass rate
    overall_pass_rate = total_passed / total_tests if total_tests > 0 else 0.0

    results["overall_pass_rate"] = overall_pass_rate

    logger.info(f"✅ Benchmarks complete: {total_passed}/{total_tests} ({overall_pass_rate:.1%})")

    return results


def should_promote_to_candidate(metrics: Dict[str, Any], threshold: float = 0.90) -> bool:
    """
    Decide if adapter should be auto-promoted to candidate.

    Args:
        metrics: Evaluation metrics dictionary
        threshold: Minimum pass rate for auto-promotion

    Returns:
        True if should promote, False otherwise
    """
    if "task_benchmarks" not in metrics:
        logger.warning("No task benchmarks found, skipping auto-promotion")
        return False

    pass_rate = metrics["task_benchmarks"].get("overall_pass_rate", 0.0)

    if pass_rate >= threshold:
        logger.info(f"✅ Pass rate {pass_rate:.1%} ≥ {threshold:.1%}, auto-promoting to candidate")
        return True
    else:
        logger.info(f"⚠️  Pass rate {pass_rate:.1%} < {threshold:.1%}, NOT auto-promoting")
        return False


def update_registry(run_id: str, metrics: Dict[str, Any], status: str):
    """
    Update models/registry.json with evaluation results.

    Args:
        run_id: Adapter run ID
        metrics: Evaluation metrics
        status: New status ("training" or "candidate")
    """
    registry_path = ROOT_DIR / "models" / "registry.json"

    # Load registry
    if not registry_path.exists():
        raise FileNotFoundError(f"Registry not found: {registry_path}")

    with registry_path.open("r") as f:
        registry = json.load(f)

    # Load adapter metadata
    adapter_dir = ROOT_DIR / "adapters" / run_id
    metadata_path = adapter_dir / "metadata.json"

    with metadata_path.open("r") as f:
        adapter_metadata = json.load(f)

    # Update metadata with evaluation results
    adapter_metadata["status"] = status
    adapter_metadata["evaluated_at"] = datetime.now(timezone.utc).isoformat()
    adapter_metadata["evaluation"] = metrics

    if status == "candidate":
        adapter_metadata["promoted_at"] = datetime.now(timezone.utc).isoformat()

    # Update adapter metadata file
    with metadata_path.open("w") as f:
        json.dump(adapter_metadata, f, indent=2)

    # Check if adapter already in registry
    existing_idx = None
    for i, adapter in enumerate(registry["adapters"]):
        if adapter["run_id"] == run_id:
            existing_idx = i
            break

    if existing_idx is not None:
        # Update existing entry
        registry["adapters"][existing_idx] = adapter_metadata
    else:
        # Add new entry
        registry["adapters"].append(adapter_metadata)

    # Save registry with atomic write
    temp_path = registry_path.with_suffix(".json.tmp")
    with temp_path.open("w") as f:
        json.dump(registry, f, indent=2)
    temp_path.replace(registry_path)

    logger.info(f"✅ Registry updated: {registry_path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate LoRA adapter")
    parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Adapter run ID (e.g., lora_20260105_142301)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show evaluation plan without executing"
    )
    parser.add_argument(
        "--no-auto-promote",
        action="store_true",
        help="Skip auto-promotion to candidate even if benchmarks pass"
    )
    args = parser.parse_args()

    print("=== Milton LoRA Evaluation ===\n")

    try:
        run_id = args.run_id
        run_dir = ROOT_DIR / "runs" / run_id
        adapter_dir = ROOT_DIR / "adapters" / run_id

        # Check adapter exists
        if not adapter_dir.exists():
            logger.error(f"Adapter not found: {adapter_dir}")
            sys.exit(1)

        logger.info(f"Evaluating adapter: {run_id}")

        if args.dry_run:
            print("\n=== DRY RUN MODE ===")
            print(f"Would evaluate: {run_id}")
            print(f"Adapter: {adapter_dir}")
            print(f"Run dir: {run_dir}")
            return

        # Import dependencies
        logger.info("Loading evaluation libraries...")
        _import_eval_deps()

        # Load model
        model, tokenizer = load_adapter_model(run_id)

        # 1. Test set metrics
        test_file = ROOT_DIR / "training" / "data" / "exported" / "test.jsonl"
        test_metrics = compute_test_metrics(model, tokenizer, test_file)

        # 2. Sanity prompts
        prompts_file = ROOT_DIR / "training" / "data" / "sanity_prompts.json"
        sanity_results = evaluate_sanity_prompts(model, tokenizer, prompts_file, run_dir)

        # 3. Task benchmarks
        benchmarks_file = ROOT_DIR / "training" / "data" / "task_benchmarks.json"
        benchmark_results = evaluate_task_benchmarks(model, tokenizer, benchmarks_file)

        # Aggregate metrics
        metrics = {
            "test_set": test_metrics,
            "sanity_prompts": sanity_results,
            "task_benchmarks": benchmark_results
        }

        # Save metrics
        metrics_file = run_dir / "metrics.json"
        with metrics_file.open("w") as f:
            json.dump(metrics, f, indent=2)

        logger.info(f"✅ Metrics saved: {metrics_file}")

        # Auto-promotion decision
        status = "training"  # Default status
        if not args.no_auto_promote and should_promote_to_candidate(metrics):
            status = "candidate"

        # Update registry
        update_registry(run_id, metrics, status)

        print(f"\n✅ Evaluation complete!")
        print(f"   Status: {status}")
        print(f"   Metrics: {metrics_file}")

        if status == "candidate":
            print(f"\n   Next step: python scripts/promote_adapter.py {run_id} --to-production")
        else:
            print(f"\n   Adapter needs improvement before promotion")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
