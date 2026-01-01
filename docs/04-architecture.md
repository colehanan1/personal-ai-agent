# Milton Three-Prong Architecture

## System Architecture Overview

This document describes the technical architecture for Milton's three-prong self-improvement system, including data flow, component interactions, and implementation details.

---

## High-Level System Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER INTERACTION LAYER                         │
│  (CLI, Scripts, Automation, ntfy Notifications)                         │
└────────────────────┬────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         AGENT ORCHESTRATION                             │
│   ┌─────────┐        ┌──────────┐        ┌──────────┐                  │
│   │  NEXUS  │◄──────►│  CORTEX  │◄──────►│ FRONTIER │                  │
│   │ (Router)│        │(Executor)│        │ (Scout)  │                  │
│   └────┬────┘        └─────┬────┘        └────┬─────┘                  │
└────────┼──────────────────┼──────────────────┼────────────────────────┘
         │                  │                  │
         └──────────────────┼──────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
              ▼                           ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│   MEMORY SYSTEM          │   │   INFERENCE ENGINE       │
│   (Prong 1)              │   │   (vLLM Server)          │
│                          │   │                          │
│ ┌──────────────────────┐ │   │ ┌──────────────────────┐ │
│ │ Short-Term Memory    │ │   │ │ Base Model           │ │
│ │ (24-48h)             │ │   │ │ Llama-3.1-8B         │ │
│ └──────────────────────┘ │   │ └──────────┬───────────┘ │
│ ┌──────────────────────┐ │   │            │             │
│ │ Working Memory       │ │   │ ┌──────────▼───────────┐ │
│ │ (Active Tasks)       │ │   │ │ LoRA Adapter         │ │
│ └──────────────────────┘ │   │ │ (Personalized)       │ │
│ ┌──────────────────────┐ │   │ └──────────────────────┘ │
│ │ Long-Term Memory     │ │   │                          │
│ │ (Compressed)         │ │   └──────────────────────────┘
│ └──────────────────────┘ │
│                          │
│ ┌──────────────────────┐ │
│ │ Vector Embeddings    │ │
│ │ (Semantic Search)    │ │
│ └──────────────────────┘ │
└────────┬─────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                    TRAINING PIPELINE (Prong 2)                │
│                                                                │
│  ┌────────────┐    ┌─────────────┐    ┌──────────────┐       │
│  │  Export    │───►│   Prepare   │───►│    Train     │       │
│  │  Convos    │    │   Dataset   │    │  LoRA Model  │       │
│  └────────────┘    └─────────────┘    └──────┬───────┘       │
│                                               │               │
│  ┌────────────┐    ┌─────────────┐    ┌──────▼───────┐       │
│  │  Update    │◄───│  Validate   │◄───│   Evaluate   │       │
│  │  Adapter   │    │  Quality    │    │    Model     │       │
│  └────────────┘    └─────────────┘    └──────────────┘       │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                  MODEL EVOLUTION (Prong 3)                    │
│                                                                │
│  ┌────────────┐    ┌─────────────┐    ┌──────────────┐       │
│  │ Knowledge  │───►│ Progressive │───►│ Quantization │       │
│  │Distillation│    │   Pruning   │    │   (4-bit)    │       │
│  └────────────┘    └─────────────┘    └──────────────┘       │
│                                                                │
│  Output: Compressed, specialized, edge-deployable model       │
└──────────────────────────────────────────────────────────────┘
```

---

## Prong 1: Memory System Architecture

### Components

#### 1.1 Weaviate Vector Database

**Configuration** (`docker-compose.yml`):
```yaml
services:
  weaviate:
    image: semitechnologies/weaviate:latest
    ports:
      - "8080:8080"
    environment:
      PERSISTENCE_DATA_PATH: '/var/lib/weaviate'
      QUERY_DEFAULTS_LIMIT: 25
      AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED: 'true'
    volumes:
      - weaviate_data:/var/lib/weaviate
```

**Schema** (`memory/init_db.py`):
```python
collections = {
    "ShortTermMemory": {
        "properties": [
            {"name": "timestamp", "dataType": ["date"]},
            {"name": "agent", "dataType": ["text"]},
            {"name": "content", "dataType": ["text"]},
            {"name": "context", "dataType": ["text"]},
            {"name": "metadata", "dataType": ["text"]},
            {"name": "embedding", "dataType": ["number[]"]}  # Added in Phase 3
        ],
        "vectorizer": "none"  # Manual embeddings via sentence-transformers
    },
    "WorkingMemory": {
        "properties": [
            {"name": "task_id", "dataType": ["text"]},
            {"name": "timestamp", "dataType": ["date"]},
            {"name": "agent", "dataType": ["text"]},
            {"name": "task_type", "dataType": ["text"]},
            {"name": "status", "dataType": ["text"]},
            {"name": "content", "dataType": ["text"]},
            {"name": "dependencies", "dataType": ["text[]"]},
            {"name": "metadata", "dataType": ["text"]}
        ]
    },
    "LongTermMemory": {
        "properties": [
            {"name": "timestamp", "dataType": ["date"]},
            {"name": "category", "dataType": ["text"]},
            {"name": "summary", "dataType": ["text"]},
            {"name": "importance", "dataType": ["number"]},
            {"name": "tags", "dataType": ["text[]"]},
            {"name": "metadata", "dataType": ["text"]},
            {"name": "embedding", "dataType": ["number[]"]}  # Added in Phase 3
        ]
    }
}
```

#### 1.2 Memory Operations API

**File**: `memory/operations.py`

**Key Operations**:
```python
class MemoryOperations:
    # Short-term
    add_short_term(agent, content, context, metadata) → uuid
    get_recent_short_term(hours, agent) → List[Dict]
    delete_old_short_term(hours) → int

    # Working memory
    add_working_memory(task_id, agent, task_type, content, ...) → uuid
    update_working_memory_status(task_id, status) → bool
    get_working_tasks(status, agent) → List[Dict]
    clear_completed_tasks() → int

    # Long-term
    add_long_term(category, summary, importance, tags, ...) → uuid
    search_long_term(category, tags, min_importance, limit) → List[Dict]
    compress_to_long_term(short_term_entries, summary) → uuid

    # Phase 3 additions
    search_similar_memories(query, limit, hours) → List[Dict]
    calculate_importance(memory) → float
    auto_prune_memories(threshold) → int
```

#### 1.3 Embeddings Layer (Phase 3)

**File**: `memory/embeddings.py`

```python
from sentence_transformers import SentenceTransformer

class MemoryEmbeddings:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        """
        Initialize embeddings model.

        Model options:
        - all-MiniLM-L6-v2: 384 dim, fast, 80MB
        - all-mpnet-base-v2: 768 dim, better quality, 420MB
        """
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()

    def embed_conversation(self, text: str) -> List[float]:
        """Generate embedding for conversation text."""
        return self.model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Batch embedding for efficiency."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings.tolist()

    def compute_similarity(self, text1: str, text2: str) -> float:
        """Cosine similarity between two texts."""
        emb1 = self.embed_conversation(text1)
        emb2 = self.embed_conversation(text2)
        return np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2))
```

#### 1.4 Context Injection Manager (Phase 3)

**File**: `agents/context_manager.py`

```python
class ContextManager:
    def __init__(self, memory_ops: MemoryOperations):
        self.memory = memory_ops

    def get_relevant_context(self, query: str, limit: int = 3) -> str:
        """
        Retrieve relevant context for a query.

        Returns formatted context string to inject into system prompt.
        """
        # Semantic search for similar past conversations
        similar = self.memory.search_similar_memories(query, limit=limit)

        if not similar:
            return ""

        context_parts = ["RELEVANT CONTEXT FROM PAST CONVERSATIONS:\n"]

        for i, mem in enumerate(similar, 1):
            days_ago = (datetime.now() - mem['timestamp']).days
            time_str = f"{days_ago} days ago" if days_ago > 0 else "today"

            context_parts.append(
                f"{i}. [{time_str}] {mem['content'][:200]}..."
            )

        return "\n".join(context_parts)

    def inject_context(self, system_prompt: str, user_query: str) -> str:
        """
        Inject relevant context into system prompt.

        Before: "You are Milton, a helpful AI assistant..."
        After:  "You are Milton, a helpful AI assistant...
                 RELEVANT CONTEXT:
                 1. [2 days ago] User prefers Python with type hints
                 ..."
        """
        context = self.get_relevant_context(user_query)

        if context:
            return f"{system_prompt}\n\n{context}\n"
        else:
            return system_prompt
```

### Data Flow: Conversation → Memory

```
User Query
    │
    ▼
┌─────────────────┐
│  NEXUS Agent    │  Routes query to appropriate agent
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Context Manager │  Retrieves relevant past conversations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   vLLM Server   │  Generates response with context
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Memory Storage  │  Stores conversation + embedding
│                 │  - content: user query + response
│                 │  - embedding: vector for semantic search
│                 │  - metadata: timestamp, agent, tags
└─────────────────┘
```

### Memory Compression Pipeline

```
Daily (2 AM):
┌────────────────────────────────────────────────────┐
│  Short-Term Memory (24-48h conversations)          │
│  100 entries, detailed, high granularity           │
└──────────────────┬─────────────────────────────────┘
                   │ LLM summarization
                   ▼
┌────────────────────────────────────────────────────┐
│  Working Memory (Active tasks)                     │
│  10 entries, task-focused, medium granularity      │
└──────────────────┬─────────────────────────────────┘
                   │
Weekly (Sunday 2 AM):
                   │ Compress + importance scoring
                   ▼
┌────────────────────────────────────────────────────┐
│  Long-Term Memory (Learned patterns)               │
│  50 entries, highly compressed, tagged, scored     │
│  Only importance > 0.5 retained after 90 days      │
└────────────────────────────────────────────────────┘
```

---

## Prong 2: Continuous Training Architecture

### Training Pipeline Components

#### 2.1 Data Export

**File**: `training/export_conversations.py`

```python
def export_conversations(
    since_date: Optional[datetime] = None,
    min_length: int = 50,
    exclude_patterns: List[str] = None
) -> List[Dict]:
    """
    Export conversations from Weaviate for training.

    Filters:
    - Exclude sensitive data (API keys, passwords)
    - Minimum conversation length
    - Only conversations since last training
    """
    with MemoryOperations() as mem:
        # Get recent conversations
        if since_date:
            hours = (datetime.now() - since_date).total_seconds() / 3600
            memories = mem.get_recent_short_term(hours=int(hours))
        else:
            memories = mem.get_recent_short_term(hours=24*30)  # Last 30 days

        # Filter and format
        conversations = []
        for memory in memories:
            # Exclude sensitive data
            if exclude_patterns and any(p in memory['content'].lower() for p in exclude_patterns):
                continue

            # Minimum length
            if len(memory['content']) < min_length:
                continue

            conversations.append({
                "instruction": extract_user_query(memory['content']),
                "input": memory.get('context', ''),
                "output": extract_assistant_response(memory['content']),
                "metadata": {
                    "timestamp": memory['timestamp'],
                    "agent": memory['agent']
                }
            })

        return conversations
```

#### 2.2 LoRA Training

**File**: `training/lora_finetune.py`

**Configuration**:
```python
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer

# LoRA hyperparameters
LORA_CONFIG = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    inference_mode=False,
    r=16,                          # Rank (higher = more parameters, better quality)
    lora_alpha=32,                 # Scaling factor (typically 2*r)
    lora_dropout=0.1,              # Regularization
    target_modules=[               # Which layers to add LoRA adapters
        "q_proj", "v_proj",        # Attention query/value
        "k_proj", "o_proj",        # Attention key/output
        # "gate_proj", "up_proj", "down_proj"  # FFN (optional, more parameters)
    ],
    bias="none"
)

# Training hyperparameters
TRAINING_ARGS = TrainingArguments(
    output_dir="checkpoints/lora_training",
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,      # Effective batch size = 16
    learning_rate=3e-4,
    num_train_epochs=3,
    max_steps=100,                      # Override epochs for quick training
    logging_steps=10,
    save_strategy="epoch",
    evaluation_strategy="epoch",
    fp16=True,                          # Mixed precision
    optim="paged_adamw_8bit",          # Memory-efficient optimizer
    gradient_checkpointing=True,        # Reduce VRAM usage
    warmup_steps=10,
    lr_scheduler_type="cosine"
)
```

**Training Loop**:
```python
def train_lora_adapter(
    training_data: List[Dict],
    base_model_name: str = "llama31-8b-instruct",
    output_dir: str = None
) -> str:
    """
    Fine-tune LoRA adapter on conversation data.

    Returns path to trained adapter.
    """
    # Load base model in 4-bit for memory efficiency
    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        load_in_4bit=True,
        device_map="auto",
        trust_remote_code=True
    )

    # Prepare for k-bit training
    model = prepare_model_for_kbit_training(model)

    # Add LoRA adapters
    model = get_peft_model(model, LORA_CONFIG)
    model.print_trainable_parameters()
    # Output: trainable params: 20M || all params: 8B || trainable%: 0.25%

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    tokenizer.pad_token = tokenizer.eos_token

    # Format dataset
    dataset = format_dataset(training_data, tokenizer)

    # Train
    trainer = Trainer(
        model=model,
        args=TRAINING_ARGS,
        train_dataset=dataset["train"],
        eval_dataset=dataset["validation"]
    )

    trainer.train()

    # Save adapter
    adapter_path = output_dir or f"checkpoints/lora_adapters/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)

    return adapter_path
```

#### 2.3 Model Evaluation

**File**: `training/evaluate_model.py`

```python
def evaluate_model(adapter_path: str, eval_dataset: List[Dict]) -> Dict[str, float]:
    """
    Evaluate fine-tuned model on held-out test set.

    Metrics:
    - Perplexity (cross-entropy loss)
    - ROUGE-L (response similarity)
    - Human eval score (1-5 on sample questions)
    """
    # Load model with adapter
    model = load_model_with_adapter(adapter_path)

    # Perplexity
    perplexity = compute_perplexity(model, eval_dataset)

    # ROUGE score
    rouge_scores = []
    for example in eval_dataset:
        generated = model.generate(example['instruction'])
        rouge = compute_rouge_l(generated, example['output'])
        rouge_scores.append(rouge)

    avg_rouge = np.mean(rouge_scores)

    # Human eval (sample 10 questions)
    human_score = run_human_evaluation(model, sample(eval_dataset, 10))

    return {
        "perplexity": perplexity,
        "rouge_l": avg_rouge,
        "human_score": human_score,
        "timestamp": datetime.now().isoformat()
    }
```

#### 2.4 Automated Scheduler

**File**: `scripts/daily_lora_update.py`

```python
def daily_training_workflow():
    """
    Automated daily LoRA training workflow.

    Triggered by systemd timer at 2 AM.
    """
    logger = setup_logger("daily_training")

    # 1. Check if enough new data
    last_training = load_last_training_date()
    new_conversations = export_conversations(since_date=last_training)

    if len(new_conversations) < MIN_TRAINING_SAMPLES:
        logger.info(f"Only {len(new_conversations)} new conversations, skipping")
        return

    logger.info(f"Found {len(new_conversations)} new conversations, starting training")

    # 2. Prepare dataset
    training_data = prepare_dataset(new_conversations)

    # 3. Train LoRA adapter
    adapter_path = train_lora_adapter(training_data)
    logger.info(f"Training complete: {adapter_path}")

    # 4. Evaluate
    eval_results = evaluate_model(adapter_path, load_eval_dataset())
    logger.info(f"Evaluation: {eval_results}")

    # 5. Quality check
    if eval_results['perplexity'] > QUALITY_THRESHOLD_PERPLEXITY:
        logger.warning(f"Quality degradation detected, rolling back")
        rollback_to_previous_adapter()
        send_notification("Training failed quality check", "warning")
        return

    # 6. Update vLLM inference
    update_vllm_adapter(adapter_path)
    logger.info("vLLM updated with new adapter")

    # 7. Log metrics
    log_to_tensorboard(eval_results)
    save_training_date(datetime.now())

    # 8. Cleanup old checkpoints (keep last 7)
    cleanup_old_checkpoints(keep=7)

    send_notification(f"Training successful: perplexity={eval_results['perplexity']:.2f}", "success")
```

**Systemd Timer** (`scripts/systemd/milton-daily-training.timer`):
```ini
[Unit]
Description=Milton Daily LoRA Training

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### Training Data Flow

```
Weaviate DB (Short-Term Memory)
        │
        ▼
Export Conversations (filter sensitive data)
        │
        ▼
Format as QA Pairs
{
  "instruction": "User query",
  "input": "Additional context",
  "output": "Expected response"
}
        │
        ▼
Tokenize + Create Batches
        │
        ▼
LoRA Fine-tuning (3 epochs, ~10 min)
        │
        ▼
Evaluate (perplexity, ROUGE, human eval)
        │
        ▼
Quality Check (rollback if degraded)
        │
        ▼
Update vLLM with New Adapter
        │
        ▼
Log Metrics to TensorBoard
```

---

## Prong 3: Model Evolution Architecture

### Evolution Pipeline

#### 3.1 Knowledge Distillation

**Teacher-Student Setup**:
```
Teacher Model (Llama-3.1-70B or GPT-4)
        │
        ▼
Generate Synthetic Training Data
- 100 user research topics
- 500 questions per topic
- High-quality answers from teacher
        │
        ▼
Student Model (Llama-3.1-8B)
- Train with distillation loss
- Match teacher's output distribution
        │
        ▼
Compressed Specialized Model
- 80-90% of teacher capability
- 10% of teacher size
- Domain-specialized
```

**File**: `evolution/distill_teacher.py`

```python
def knowledge_distillation(
    teacher_model: str,
    student_model: str,
    topics: List[str],
    questions_per_topic: int = 500
) -> str:
    """
    Distill knowledge from large teacher to small student.
    """
    # Generate synthetic data
    synthetic_data = []
    for topic in topics:
        questions = generate_questions(topic, count=questions_per_topic)
        for q in questions:
            answer = teacher_model.generate(q, temperature=0.7)
            synthetic_data.append({
                "instruction": q,
                "output": answer,
                "topic": topic
            })

    # Train student with distillation loss
    def distillation_loss(student_logits, teacher_logits, labels, alpha=0.5, temp=2.0):
        """
        Combined loss:
        - Hard targets (labels): Cross-entropy
        - Soft targets (teacher): KL divergence
        """
        ce_loss = F.cross_entropy(student_logits, labels)

        soft_student = F.log_softmax(student_logits / temp, dim=-1)
        soft_teacher = F.softmax(teacher_logits / temp, dim=-1)
        kl_loss = F.kl_div(soft_student, soft_teacher, reduction='batchmean')

        return alpha * ce_loss + (1 - alpha) * (temp ** 2) * kl_loss

    # Train student
    student = train_with_custom_loss(
        model=student_model,
        data=synthetic_data,
        loss_fn=distillation_loss
    )

    return student
```

#### 3.2 Progressive Pruning

**Iterative Pruning Schedule**:
```
Iteration 1:  Prune 10% → Retrain → Eval
Iteration 2:  Prune 10% → Retrain → Eval
Iteration 3:  Prune 10% → Retrain → Eval
...
Stop when quality drops below threshold
```

**File**: `evolution/prune_model.py`

```python
import torch.nn.utils.prune as prune

def progressive_pruning(
    model_path: str,
    pruning_ratio: float = 0.1,
    max_iterations: int = 5,
    quality_threshold: float = 0.9
) -> str:
    """
    Iteratively prune and retrain model.
    """
    model = load_model(model_path)
    baseline_quality = evaluate_model(model)

    for iteration in range(max_iterations):
        # Prune by magnitude
        for name, module in model.named_modules():
            if isinstance(module, torch.nn.Linear):
                prune.l1_unstructured(module, name='weight', amount=pruning_ratio)

        # Retrain (fine-tune on original data)
        model = finetune_model(model, epochs=3)

        # Evaluate
        quality = evaluate_model(model)
        quality_ratio = quality / baseline_quality

        logger.info(f"Iteration {iteration+1}: Quality {quality_ratio:.2%}")

        if quality_ratio < quality_threshold:
            logger.warning("Quality threshold breached, stopping pruning")
            break

        # Make pruning permanent
        for name, module in model.named_modules():
            if isinstance(module, torch.nn.Linear):
                prune.remove(module, 'weight')

    output_path = f"checkpoints/compressed/pruned_{iteration}x{pruning_ratio}"
    model.save_pretrained(output_path)
    return output_path
```

#### 3.3 Quantization

**File**: `evolution/quantize_model.py`

**GPTQ (GPU-friendly 4-bit)**:
```python
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

def quantize_gptq(model_path: str, calibration_data: List[str]) -> str:
    """
    Quantize model to 4-bit using GPTQ.
    """
    quantize_config = BaseQuantizeConfig(
        bits=4,                   # 4-bit quantization
        group_size=128,           # Quantization group size
        desc_act=False,           # Disable for speed
        sym=True,                 # Symmetric quantization
        damp_percent=0.1          # Dampening factor
    )

    model = AutoGPTQForCausalLM.from_pretrained(
        model_path,
        quantize_config=quantize_config
    )

    # Calibrate on representative data
    model.quantize(calibration_data)

    output_path = "checkpoints/compressed/llama31-8b-gptq-4bit"
    model.save_quantized(output_path)

    # Verify quality
    perplexity = evaluate_perplexity(model)
    logger.info(f"4-bit model perplexity: {perplexity}")

    return output_path
```

**GGUF (CPU-friendly llama.cpp format)**:
```bash
# Convert to GGUF for CPU deployment
python tools/convert_llama_to_gguf.py \
    --input checkpoints/base/llama31-8b \
    --output checkpoints/compressed/llama31-8b-q4.gguf \
    --quant-type q4_k_m
```

### Model Evolution Data Flow

```
Base Model (Llama-3.1-8B, 16GB)
        │
        ├─────────────────────────┐
        │                         │
        ▼                         ▼
Knowledge Distillation    Progressive Pruning
(from 70B teacher)        (iterative)
        │                         │
        ▼                         ▼
Specialized Model         Pruned Model (10GB)
        │                         │
        └─────────┬───────────────┘
                  │
                  ▼
         Quantization (4-bit)
                  │
                  ▼
    Final Compressed Model (3-4GB)
    - Runs on CPU
    - <2s latency
    - 90-95% quality retention
```

---

## Integration Architecture

### Complete System Data Flow

```
1. USER QUERY
       │
       ▼
2. NEXUS AGENT
   - Retrieves context from memory (Prong 1)
   - Injects into system prompt
       │
       ▼
3. vLLM INFERENCE
   - Base: Llama-3.1-8B (or quantized variant)
   - Adapter: LoRA fine-tuned on user conversations (Prong 2)
       │
       ▼
4. RESPONSE GENERATION
   - Context-aware
   - Personalized to user style
       │
       ▼
5. MEMORY STORAGE
   - Store conversation + embedding
   - Update importance scores
       │
       ▼
6. NIGHTLY TRAINING (2 AM)
   - Export new conversations
   - Fine-tune LoRA adapter (Prong 2)
   - Update inference server
       │
       ▼
7. WEEKLY COMPRESSION (Sunday 2 AM)
   - Compress short-term → long-term (Prong 1)
   - Prune low-importance memories
       │
       ▼
8. MONTHLY EVOLUTION (1st of month, 3 AM)
   - Re-distill from teacher (Prong 3)
   - Progressive pruning iteration
   - Update quantized model
```

---

## Deployment Architecture

### Current (Phase 2) - Single Machine

```
┌────────────────────────────────────────────────────┐
│  Ubuntu 22.04 LTS (RTX 5090, 32GB RAM)             │
│                                                     │
│  ┌──────────────┐    ┌──────────────┐              │
│  │ vLLM Server  │    │  Weaviate DB │              │
│  │ (port 8000)  │    │ (port 8080)  │              │
│  └──────────────┘    └──────────────┘              │
│                                                     │
│  ┌──────────────────────────────────┐              │
│  │  Milton Agents                   │              │
│  │  - NEXUS, CORTEX, FRONTIER       │              │
│  └──────────────────────────────────┘              │
│                                                     │
│  ┌──────────────────────────────────┐              │
│  │  Systemd Timers                  │              │
│  │  - Morning briefing (8 AM)       │              │
│  │  - Evening briefing (8 PM)       │              │
│  │  - Daily training (2 AM)         │              │
│  │  - Weekly compression (Sun 2 AM) │              │
│  └──────────────────────────────────┘              │
└────────────────────────────────────────────────────┘
```

### Target (Phase 3) - Edge Deployment

```
┌────────────────────────────────────────────────────┐
│  Laptop / Raspberry Pi 5 (8GB RAM, no GPU)         │
│                                                     │
│  ┌──────────────┐    ┌──────────────┐              │
│  │ Ollama/llama │    │  ChromaDB    │              │
│  │ (CPU only)   │    │ (lightweight)│              │
│  │ 4-bit GGUF   │    │              │              │
│  └──────────────┘    └──────────────┘              │
│                                                     │
│  Model: 3-4GB quantized + pruned                   │
│  Latency: <2s per response (CPU)                   │
│  Offline: Full functionality                       │
└────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Component | Current (Phase 2) | Target (Phase 3) |
|-----------|-------------------|------------------|
| **Inference** | vLLM | vLLM or Ollama (CPU fallback) |
| **Model** | Llama-3.1-8B (bf16) | Llama-3.1-8B (4-bit GPTQ/GGUF) |
| **Memory DB** | Weaviate | Weaviate or ChromaDB |
| **Embeddings** | None | sentence-transformers |
| **Training** | None | PyTorch + PEFT (LoRA) |
| **Compression** | None | GPTQ + llama.cpp |
| **Monitoring** | Logs | TensorBoard + logs |
| **Automation** | systemd | systemd |

---

## Performance Specifications

### Current (Phase 2)

| Metric | Value |
|--------|-------|
| Model size | 16GB (bf16) |
| Inference latency | 50ms (GPU) |
| Memory DB size | ~100MB (1000 conversations) |
| Training | N/A |

### Target (Phase 3 - Month 3)

| Metric | Value |
|--------|-------|
| Model size | 3-4GB (4-bit quantized) |
| Inference latency | 60ms (GPU), 1500ms (CPU) |
| Memory DB size | ~50MB (10K conversations, pruned) |
| LoRA training time | 10-15 min (daily update) |
| Personalization accuracy | >80% |
| Quality retention | >90% vs base model |

---

## Security & Privacy Architecture

### Data Protection

**All data stays local**:
- No external API calls for inference (except optional integrations: weather, arXiv)
- Weaviate DB stored on disk (not cloud)
- Training data never leaves machine

**Sensitive Data Filtering**:
```python
EXCLUDE_PATTERNS = [
    r'api[_-]key',
    r'password',
    r'secret',
    r'token',
    r'[A-Za-z0-9]{32,}',  # Long hashes/keys
    r'sk-[A-Za-z0-9]+',   # OpenAI keys
]

def filter_sensitive_data(text: str) -> bool:
    """Return True if text contains sensitive data."""
    return any(re.search(pattern, text, re.I) for pattern in EXCLUDE_PATTERNS)
```

### Model Alignment

**Maintain safety after fine-tuning**:
- Evaluate for harmful outputs after each training run
- Include alignment examples in training data
- Automatic rollback if safety checks fail

```python
def safety_check(model: Model) -> bool:
    """
    Test model for harmful outputs.
    """
    harmful_prompts = load_harm_eval_dataset()
    for prompt in harmful_prompts:
        response = model.generate(prompt)
        if is_harmful(response):
            logger.error(f"Safety check failed: {prompt[:50]}...")
            return False
    return True
```

---

## Conclusion

This architecture provides:

1. **Prong 1 (Memory)**: 3-tier system with semantic search and context injection
2. **Prong 2 (Training)**: Automated LoRA fine-tuning pipeline with quality checks
3. **Prong 3 (Evolution)**: Knowledge distillation, pruning, and quantization for edge deployment

All components are designed to work together seamlessly while maintaining **privacy, reproducibility, and efficiency**.

---

**Next**: See [Roadmap](03-roadmap.md) for implementation timeline.
