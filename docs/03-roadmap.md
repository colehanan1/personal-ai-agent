# Milton Three-Prong Implementation Roadmap

## Overview

This roadmap details the implementation plan for Milton's **three-prong self-improvement strategy** over a 90-day (12-week) period.

**Start Date**: January 2026
**Target Completion**: March 2026
**Current Status**: Phase 2 Complete → Phase 3 Initialization

---

## Success Criteria

By the end of 90 days, Milton will:

1. **Learn from conversations** - Store and retrieve personalized context automatically
2. **Improve weekly** - LoRA fine-tuning on your conversation data
3. **Run efficiently** - Quantized model deployable on 8GB RAM devices
4. **Demonstrate growth** - Measurable improvement in response quality over baseline

---

## Phase 3 Month 1: Foundation (Weeks 1-4)

### Week 1: Environment Setup & Data Pipeline

#### Goals
- Install all training dependencies
- Export conversations from Weaviate to training format
- Create baseline evaluation dataset

#### Tasks

**1.1 Install Dependencies**
```bash
pip install peft>=0.7.0 transformers>=4.35.0 datasets>=2.14.0 \
    accelerate>=0.24.0 bitsandbytes>=0.41.0 torch>=2.1.0 \
    sentence-transformers>=2.2.0 tensorboard>=2.15.0
```

**1.2 Create Training Directory Structure**
```bash
mkdir -p training/{configs,scripts,data}
mkdir -p checkpoints/{base,lora_adapters,compressed}
mkdir -p evaluation/{datasets,results}
```

**1.3 Implement Data Export** (`training/export_conversations.py`)
- Pull last 30 days of conversations from Weaviate
- Filter out sensitive data (API keys, passwords)
- Format as instruction-following QA pairs
- Save to `training/data/conversations.jsonl`

**1.4 Create Evaluation Dataset** (`evaluation/datasets/eval_baseline.json`)
- 50 diverse questions covering:
  - Personal preferences (10 questions)
  - Code generation (10 questions)
  - Research queries (10 questions)
  - Morning briefing format (10 questions)
  - General knowledge (10 questions)

**Deliverables**
- [ ] All dependencies installed
- [ ] `training/export_conversations.py` script working
- [ ] Baseline evaluation dataset created
- [ ] At least 100 conversation pairs exported

---

### Week 2: LoRA Training Pipeline - Proof of Concept

#### Goals
- Implement basic LoRA fine-tuning script
- Successfully fine-tune on small dataset
- Measure quality improvement

#### Tasks

**2.1 Create LoRA Training Script** (`training/lora_finetune.py`)

**Key Features**:
```python
from peft import LoraConfig, get_peft_model, TaskType
from transformers import AutoModelForCausalLM, AutoTokenizer

# LoRA Configuration
lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,                    # Rank
    lora_alpha=32,          # Scaling
    lora_dropout=0.1,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    bias="none"
)

# Training arguments
training_args = {
    "per_device_train_batch_size": 4,
    "gradient_accumulation_steps": 4,  # Effective batch size = 16
    "learning_rate": 3e-4,
    "num_train_epochs": 3,
    "max_steps": 100,
    "logging_steps": 10,
    "save_strategy": "epoch"
}
```

**2.2 Test on Small Dataset**
- Use 20 conversation pairs
- Train for 100 steps (~5 minutes on RTX 5090)
- Compare before/after responses

**2.3 Implement Evaluation Script** (`evaluation/benchmark_qa.py`)

**Metrics**:
- Perplexity (lower is better)
- ROUGE-L score (response similarity)
- Human evaluation (1-5 scale on 10 test questions)

**2.4 Validate Training Works**
- Train on example: "I prefer Python" → model remembers in next response
- Save LoRA adapter to `checkpoints/lora_adapters/week2_poc/`

**Deliverables**
- [ ] `training/lora_finetune.py` script functional
- [ ] Proof-of-concept training completed successfully
- [ ] Evaluation shows measurable improvement (>5% ROUGE score increase)
- [ ] Documentation of training process and results

---

### Week 3: Memory Enhancement - Vector Embeddings

#### Goals
- Add semantic search to memory system
- Implement automated context retrieval
- Test memory-augmented responses

#### Tasks

**3.1 Add Sentence Embeddings to Memory** (`memory/embeddings.py`)

```python
from sentence_transformers import SentenceTransformer

class MemoryEmbeddings:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dim, fast

    def embed_conversation(self, text: str) -> List[float]:
        return self.model.encode(text).tolist()
```

**3.2 Update Weaviate Schema**
- Add vector property to `ShortTermMemory` collection
- Re-initialize with vectorization enabled
- Migrate existing memories (embed historical conversations)

**3.3 Implement Semantic Search** (`memory/operations.py`)

```python
def search_similar_memories(
    self,
    query: str,
    limit: int = 5,
    hours: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Find semantically similar past conversations."""
    query_vector = self.embeddings.embed_conversation(query)

    collection = self.client.collections.get("ShortTermMemory")
    results = collection.query.near_vector(
        near_vector=query_vector,
        limit=limit,
        return_metadata=['distance']
    )

    return [self._format_result(r) for r in results.objects]
```

**3.4 Implement Context Injection** (`agents/context_manager.py`)

**Before Each LLM Call**:
1. User asks question
2. Retrieve top 3 similar past conversations
3. Inject into system prompt:
   ```
   RELEVANT CONTEXT FROM PAST CONVERSATIONS:
   1. [2 weeks ago] User prefers concise Python code examples
   2. [1 week ago] User is researching reinforcement learning
   3. [3 days ago] User's morning briefing includes weather + arXiv papers

   USER QUERY: {current_question}
   ```

**3.5 Test Memory-Augmented Responses**
- Ask same question twice (1 week apart)
- Second response should reference first conversation
- Measure context injection effectiveness

**Deliverables**
- [ ] Sentence embeddings integrated into memory system
- [ ] Semantic search functional and tested
- [ ] Context injection working in NEXUS agent
- [ ] Evaluation showing >20% improvement in personalization

---

### Week 4: Automated Training Scheduler

#### Goals
- Automate daily LoRA updates
- Implement safety checks and rollback
- Monitor training metrics

#### Tasks

**4.1 Create Daily Training Script** (`scripts/daily_lora_update.py`)

**Workflow**:
```python
def daily_training_workflow():
    # 1. Check if enough new data (>50 conversations)
    new_conversations = export_new_conversations(since="last_training_date")
    if len(new_conversations) < 50:
        log("Insufficient data, skipping training")
        return

    # 2. Prepare training data
    training_data = prepare_dataset(new_conversations)

    # 3. Run LoRA fine-tuning
    adapter_path = lora_finetune(
        training_data,
        base_model="llama31-8b-instruct",
        output_dir=f"checkpoints/lora_adapters/{today_date}"
    )

    # 4. Evaluate on held-out set
    eval_score = evaluate_model(adapter_path)

    # 5. Safety check - rollback if quality drops
    if eval_score < QUALITY_THRESHOLD:
        log("Quality degradation detected, rolling back")
        rollback_to_previous_adapter()
        return

    # 6. Update vLLM to use new adapter
    update_inference_adapter(adapter_path)

    # 7. Log metrics to TensorBoard
    log_training_metrics(eval_score, adapter_path)
```

**4.2 Add Systemd Timer** (`scripts/systemd/milton-daily-training.timer`)

```ini
[Unit]
Description=Milton Daily LoRA Training Timer

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 02:00:00  # 2 AM daily
Persistent=true

[Install]
WantedBy=timers.target
```

**4.3 Implement Rollback Mechanism**
- Keep last 7 LoRA adapters
- Compare eval scores before switching
- Auto-rollback if degradation detected

**4.4 Add TensorBoard Logging**
```python
from torch.utils.tensorboard import SummaryWriter

writer = SummaryWriter('logs/training')
writer.add_scalar('eval/perplexity', perplexity, step)
writer.add_scalar('eval/rouge_l', rouge_score, step)
writer.add_scalar('training/loss', loss, step)
```

**Deliverables**
- [ ] Daily automated training working
- [ ] Safety checks prevent quality degradation
- [ ] TensorBoard dashboard shows training progress
- [ ] Documentation of training schedule and monitoring

---

## Phase 3 Month 2: Optimization (Weeks 5-8)

### Week 5: Importance Scoring & Memory Pruning

#### Goals
- Implement ML-based importance scoring
- Auto-prune low-value memories
- Prevent unbounded DB growth

#### Tasks

**5.1 Create Importance Scorer** (`memory/importance_scorer.py`)

**Features**:
- Conversation length (longer = more important)
- User engagement (questions, clarifications = higher score)
- Topic relevance (matches user's research interests)
- Recency decay (older memories fade unless re-referenced)

**Scoring Function**:
```python
def calculate_importance(memory: Dict) -> float:
    score = 0.5  # Base score

    # Length factor (more detail = more important)
    if len(memory['content']) > 500:
        score += 0.1

    # Engagement (user asked follow-up questions)
    if memory.get('follow_up_count', 0) > 0:
        score += 0.2

    # Topic match (semantic similarity to research interests)
    research_topics = get_user_research_topics()
    similarity = compute_similarity(memory['content'], research_topics)
    score += similarity * 0.3

    # Recency decay
    days_old = (datetime.now() - memory['timestamp']).days
    decay = 1.0 / (1 + 0.1 * days_old)
    score *= decay

    return min(score, 1.0)
```

**5.2 Implement Auto-Pruning**
- Daily job: re-score all memories
- Delete memories with importance < 0.3 and age > 30 days
- Compress clusters of similar low-importance memories

**5.3 Update Memory Compression**
- Weekly job: compress short-term → long-term
- Use LLM to generate summary of related memories
- Tag with extracted topics and importance

**Deliverables**
- [ ] Importance scorer implemented and tested
- [ ] Auto-pruning prevents unbounded growth
- [ ] Memory DB size stable after 30 days of usage

---

### Week 6: Quantization - 4-bit Model

#### Goals
- Quantize Llama-3.1-8B to 4-bit
- Measure quality vs size tradeoff
- Deploy quantized model for edge testing

#### Tasks

**6.1 Install Quantization Tools**
```bash
pip install auto-gptq>=0.5.0
pip install llama-cpp-python>=0.2.0
```

**6.2 GPTQ Quantization** (`evolution/quantize_gptq.py`)

```python
from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

quantize_config = BaseQuantizeConfig(
    bits=4,
    group_size=128,
    desc_act=False
)

model = AutoGPTQForCausalLM.from_pretrained(
    "llama31-8b-instruct",
    quantize_config=quantize_config
)

model.quantize(calibration_data)
model.save_quantized("checkpoints/compressed/llama31-8b-gptq-4bit")
```

**6.3 GGUF Quantization for llama.cpp**

```bash
# Convert to GGUF format (for CPU inference)
python tools/convert_llama_weights_to_hf.py \
    --input checkpoints/base/llama31-8b \
    --output checkpoints/compressed/llama31-8b.gguf \
    --quant-type q4_k_m
```

**6.4 Benchmark Quantized Models**

| Model | Size | Latency (RTX 5090) | Latency (CPU) | Perplexity | Quality Score |
|-------|------|-------------------|---------------|------------|---------------|
| 16-bit bf16 | 16GB | 50ms | N/A (OOM) | 5.2 | 100% |
| 8-bit int8 | 8GB | 55ms | 800ms | 5.3 | 98% |
| 4-bit GPTQ | 4GB | 60ms | 1500ms | 5.8 | 95% |
| 4-bit GGUF | 4GB | 70ms | 1200ms | 6.0 | 93% |

**6.5 Deploy Quantized Model**
- Test on laptop without GPU
- Validate end-to-end workflow (memory + inference + LoRA)
- Document deployment process

**Deliverables**
- [ ] 4-bit quantized model created (GPTQ + GGUF)
- [ ] Quality evaluation complete (>90% baseline performance)
- [ ] CPU inference working on laptop
- [ ] Documentation for edge deployment

---

### Week 7-8: Knowledge Distillation (Optional Advanced)

**Note**: This is an advanced feature. If timeline is tight, prioritize Weeks 5-6 and skip to Month 3.

#### Goals
- Distill knowledge from larger teacher model
- Create domain-specific student model
- Evaluate knowledge transfer effectiveness

#### Tasks

**7.1 Set Up Teacher Model Access**

**Options**:
- Use Llama-3.1-70B via Ollama (if enough VRAM)
- Use GPT-4 API for synthetic data generation
- Use Claude API for high-quality conversation examples

**7.2 Generate Training Data** (`evolution/distill_teacher.py`)

**Process**:
1. Extract user's top 100 research topics from memory
2. Generate 500 diverse questions per topic using teacher model
3. Get teacher model responses
4. Format as training dataset for student

**Example**:
```python
def generate_synthetic_data(topics: List[str], count_per_topic: int):
    dataset = []
    for topic in topics:
        for i in range(count_per_topic):
            question = teacher_model.generate_question(topic)
            answer = teacher_model.answer(question)
            dataset.append({
                "instruction": question,
                "output": answer,
                "topic": topic
            })
    return dataset
```

**7.3 Train Student Model** (`evolution/train_student.py`)

**Distillation Loss**:
```python
# Standard cross-entropy loss
ce_loss = F.cross_entropy(student_logits, labels)

# KL divergence from teacher (knowledge transfer)
kl_loss = F.kl_div(
    F.log_softmax(student_logits / temperature, dim=-1),
    F.softmax(teacher_logits / temperature, dim=-1),
    reduction='batchmean'
)

# Combined loss
loss = alpha * ce_loss + (1 - alpha) * kl_loss
```

**7.4 Evaluate Knowledge Transfer**

**Metrics**:
- Student vs teacher agreement on test set
- Student vs base model performance
- Domain-specific accuracy (user's research topics)

**Deliverables**
- [ ] Synthetic training data generated (50K+ examples)
- [ ] Student model trained with distillation
- [ ] Evaluation shows knowledge transfer (>80% of teacher capability)

---

## Phase 3 Month 3: Polish & Validation (Weeks 9-12)

### Week 9: End-to-End Integration Testing

#### Goals
- Validate complete three-prong system
- Fix integration bugs
- Optimize performance

#### Tasks

**9.1 Integration Test Suite** (`tests/test_three_prong.py`)

**Tests**:
```python
def test_conversation_to_training_pipeline():
    # 1. User has conversation
    response = nexus.process_message("I prefer type-annotated Python code")

    # 2. Memory stores preference
    memories = mem.get_recent_short_term(hours=1)
    assert any("type-annotated" in m['content'] for m in memories)

    # 3. Training exports conversation
    conversations = export_conversations(since_hours=1)
    assert len(conversations) > 0

    # 4. LoRA training uses data
    adapter = lora_finetune(conversations)
    assert adapter.exists()

    # 5. Next response uses learned preference
    response2 = nexus.process_message("Write a CSV parser")
    assert "def parse_csv(file_path: str)" in response2  # Type hints!

def test_memory_augmented_generation():
    # Store context
    mem.add_short_term("nexus", "User researches neuroscience")

    # Ask related question
    response = nexus.process_message("Find recent papers on neural networks")

    # Should retrieve context and prioritize neuroscience papers
    assert "neuroscience" in response.lower()
```

**9.2 Performance Optimization**
- Profile memory retrieval latency
- Optimize vector search (index tuning)
- Reduce LoRA training time (gradient checkpointing)

**9.3 Load Testing**
- 1000 conversations in memory DB
- 100 concurrent inference requests
- Daily LoRA training with 500 new conversations

**Deliverables**
- [ ] All integration tests passing
- [ ] Performance benchmarks documented
- [ ] No memory leaks or crashes under load

---

### Week 10: User Experience Improvements

#### Goals
- Add user-facing features for transparency
- Improve feedback collection
- Polish automation workflows

#### Tasks

**10.1 Memory Inspection UI** (Optional - CLI tool)

```bash
# View what Milton remembers about you
milton memory list --category=preference
milton memory search "machine learning"
milton memory stats  # Show DB size, importance distribution
```

**10.2 Training Dashboard**

```bash
# View training history
milton training history
milton training rollback --to 2026-01-15
milton training export --format tensorboard
```

**10.3 Feedback Collection**

```python
# After each response, prompt for optional feedback
response = nexus.process_message(query)
print(response)

feedback = input("Rate this response (1-5, or skip): ")
if feedback:
    mem.add_long_term(
        category="feedback",
        summary=f"Response quality: {feedback}/5",
        importance=float(feedback) / 5.0,
        metadata={"query": query, "response_id": response_id}
    )
```

**10.4 Automation Polish**
- Morning briefing includes "What I learned this week" section
- Evening briefing prompts: "What should I remember from today?"
- Weekly summary email with training metrics

**Deliverables**
- [ ] CLI tools for memory/training inspection
- [ ] Feedback collection integrated
- [ ] Automation workflows polished

---

### Week 11: Documentation & Examples

#### Goals
- Create comprehensive user guides
- Write developer documentation
- Publish example workflows

#### Tasks

**11.1 User Guides**
- Getting started with three-prong learning
- How to review and curate your memories
- Understanding training metrics
- Troubleshooting guide

**11.2 Developer Documentation**
- Architecture deep-dive (update `04-architecture.md`)
- LoRA training customization guide
- Adding new memory categories
- Extending the evaluation framework

**11.3 Example Workflows**
- Research assistant setup (neuroscience focus)
- Code assistant setup (Python/ML engineering)
- Personal journal companion
- Lab automation assistant

**11.4 Video Demos** (Optional)
- "Milton learns your preferences in 2 weeks" (time-lapse)
- "How LoRA training works under the hood"
- "Deploying Milton on Raspberry Pi 5"

**Deliverables**
- [ ] User documentation complete
- [ ] Developer docs updated
- [ ] At least 3 example workflows documented

---

### Week 12: Validation & Pilot Testing

#### Goals
- Run 30-day pilot with real usage
- Collect qualitative feedback
- Measure quantitative improvements

#### Tasks

**12.1 Pilot Study Setup**
- Use Milton daily for all research/coding tasks
- Let automated training run without intervention
- Track metrics weekly

**12.2 Quantitative Metrics**

| Metric | Week 1 | Week 2 | Week 4 | Target |
|--------|--------|--------|--------|--------|
| Response quality (1-5) | 3.2 | 3.5 | 4.1 | >4.0 |
| Personalization % | 10% | 25% | 60% | >50% |
| Memory retrieval accuracy | 50% | 70% | 85% | >80% |
| Training improvements/week | - | +3% | +8% | >5% |
| Model size | 16GB | 16GB | 4GB | <5GB |

**12.3 Qualitative Feedback**
- Weekly journal: "What did Milton do well this week?"
- Failure analysis: "When did Milton get it wrong?"
- Feature requests: "What's missing?"

**12.4 Competitive Benchmarks**

**Compare Milton Week 4 vs**:
- ChatGPT (no memory, generic)
- Claude Projects (session memory only)
- Base Llama-3.1-8B (no personalization)

**Test Set**: 50 questions requiring personal context

**Expected Results**:
- Milton: 85% quality, 90% personalization
- ChatGPT: 90% quality, 10% personalization
- Claude Projects: 88% quality, 40% personalization
- Base Llama: 75% quality, 0% personalization

**Deliverables**
- [ ] 30-day pilot study completed
- [ ] Metrics show measurable improvement
- [ ] Qualitative feedback documented
- [ ] Competitive benchmark results published

---

## Success Metrics Summary

At the end of 90 days, Milton should achieve:

### Technical Metrics
- [x] **LoRA training pipeline**: Fully automated daily updates
- [x] **Memory system**: Semantic search + context injection working
- [x] **Model compression**: 4-bit quantized model (<5GB)
- [x] **Training latency**: <15 minutes per update
- [x] **Inference latency**: <2s per response (quantized)

### Quality Metrics
- [x] **Response quality**: >4.0/5.0 user rating
- [x] **Personalization**: >50% of responses use personal context
- [x] **Memory accuracy**: >80% recall of important conversations
- [x] **Improvement rate**: >5% quality gain per week

### User Experience Metrics
- [x] **Zero manual intervention**: Training runs automatically
- [x] **Transparency**: User can inspect all memories and training data
- [x] **Offline capable**: Full functionality without internet

---

## Risk Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **LoRA training degrades quality** | HIGH | MEDIUM | Automated rollback, quality thresholds |
| **Memory DB grows unbounded** | MEDIUM | HIGH | Auto-pruning, importance scoring |
| **Training takes too long** | MEDIUM | MEDIUM | Quantization, gradient checkpointing |
| **Quantized model too low quality** | MEDIUM | LOW | Use 8-bit instead of 4-bit |
| **User has <50 conversations/week** | LOW | MEDIUM | Lower training threshold or train weekly |

---

## Adaptive Roadmap

**If ahead of schedule**:
- Add knowledge distillation (Weeks 7-8)
- Implement multi-modal memory (images, voice)
- Build web UI for memory management

**If behind schedule**:
- Skip distillation (use base model + LoRA only)
- Simplify evaluation (manual testing vs automated benchmarks)
- Defer quantization to Month 4

**If blocked on dependencies**:
- Use Ollama instead of vLLM (simpler LoRA integration)
- Use ChromaDB instead of Weaviate (lighter weight)
- Use pre-quantized models (Hugging Face GGUF)

---

## Next Steps After 90 Days

**Phase 4 Planning (Q2 2026)**:
- Multi-user deployment (lab-wide Milton)
- Agent marketplace (share/sell custom agents)
- Mobile app (iOS/Android)
- Cloud-hosted option for GPU-less users

---

## Conclusion

This roadmap provides a structured path to implement Milton's three-prong self-improvement strategy. The critical path is:

1. **Month 1**: Build LoRA training pipeline + enhance memory
2. **Month 2**: Optimize (importance scoring + quantization)
3. **Month 3**: Validate and polish

The estimated effort is realistic for a single developer with ML experience. Adjust timeline based on available hours/week and prioritize core features (LoRA training + semantic search) over nice-to-haves (distillation, web UI).

**Most important**: Start with Week 1-2 to prove out the concept, then iterate based on real results.

---

**See**:
- [Vision](01-vision.md) for high-level strategy
- [Current State](02-current-state.md) for implementation gaps
- [Architecture](04-architecture.md) for technical design
