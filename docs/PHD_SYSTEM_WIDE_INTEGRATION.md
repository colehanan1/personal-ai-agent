# PhD Awareness - System-Wide Integration

## Overview

Your PhD research plan is now integrated **everywhere** in Milton, not just briefings. Every interaction with Milton is PhD-aware.

## What's PhD-Aware Now

### ✅ 1. Briefings (Morning & Evening)
- **Location:** [scripts/phd_aware_morning_briefing.py](../scripts/phd_aware_morning_briefing.py), [scripts/phd_aware_evening_briefing.py](../scripts/phd_aware_evening_briefing.py)
- **What:** Shows PhD goals, current year projects, immediate steps, relevant papers, progress tracking
- **Replaces:** `enhanced_morning_briefing.py` (does everything it did PLUS PhD)

### ✅ 2. Nexus Agent (ALL Conversations)
- **Location:** [agents/nexus.py](../agents/nexus.py:182-191)
- **What:** Every response includes PhD context in system prompt
- **Impact:** Milton always knows:
  - You're a PhD student (Year 1, neuroscience)
  - Your research focus (olfactory BCI)
  - Your current projects (1.1, 1.2, 1.3)
  - Your immediate priorities

### ✅ 3. Memory System
- **Location:** [agents/nexus.py](../agents/nexus.py:422-492)
- **What:** PhD-aware context building
- **Features:**
  - PhD-related queries get more memory context (12 vs 8 items)
  - Lower recency bias for PhD (0.2 vs 0.35) - long-term goals matter!
  - PhD messages automatically tagged with `phd`, `research`
  - Higher importance (0.4 vs 0.2) for PhD memories
  - Automatically includes PhD projects and steps in context

### ✅ 4. Central PhD Context Module
- **Location:** [phd_context.py](../phd_context.py)
- **What:** Single source of truth for PhD awareness
- **Functions:**
  ```python
  get_phd_context()           # Get comprehensive PhD state
  get_current_year()          # Year 1-4
  get_current_projects()      # Active project IDs
  is_phd_related()            # Check if text is PhD-related
  should_include_phd_context() # Decide if PhD context needed
  get_phd_summary_for_agent() # PhD summary for agent prompts
  ```

### ✅ 5. Automatic Briefing System
- **Location:** [scripts/setup_morning_briefing.sh](../scripts/setup_morning_briefing.sh), [scripts/setup_phone_delivery.sh](../scripts/setup_phone_delivery.sh)
- **What:** Updated to use PhD-aware briefings by default
- **Runs:** Automatically at 8:00 AM daily (if configured)

## How It Works

### When You Ask Milton Anything

1. **System Prompt Enhancement** ([nexus.py:182-191](../agents/nexus.py))
   ```
   Your base system prompt
   +
   USER CONTEXT - PhD Research:
   - PhD student in Year 1 of neuroscience program
   - Focus: Olfactory brain-computer interface (BCI) in Drosophila
   - Current projects: 1.1, 1.2, 1.3
   - Goal: 6-8 high-impact publications + 2-3 patents → startup
   - Immediate priorities: [your current steps]
   ```

2. **PhD Detection** ([phd_context.py:92-108](../phd_context.py))
   - Milton checks if your message contains PhD keywords
   - Keywords: phd, research, olfactory, bci, drosophila, calcium imaging, connectome, orns, pns, kcs, odor, 2-photon, gcamp, paper, publication, experiment, protocol, lab, flies, etc.

3. **Memory Retrieval Adjustment** ([nexus.py:435-447](../agents/nexus.py))
   - PhD-related: 12 memory items, 0.2 recency bias
   - Non-PhD: 8 memory items, 0.35 recency bias
   - This means PhD long-term goals are weighted more heavily

4. **Context Injection** ([nexus.py:468-485](../agents/nexus.py))
   - If PhD-related, adds your current projects to context
   - Adds immediate next steps
   - Milton sees this BEFORE generating response

5. **Memory Tagging** ([nexus.py:771-786](../agents/nexus.py))
   - PhD messages tagged: `["request", "route:...", "phd", "research"]`
   - Higher importance: 0.4 (vs 0.2 for general messages)
   - Ensures PhD memories persist in long-term storage

## Testing PhD Awareness

### Test 1: Ask General Question
```bash
# Milton should NOT inject PhD context
echo "What's the weather?" | python -c "from agents.nexus import NEXUS; n=NEXUS(); print(n.process_message(input()).text)"
```

### Test 2: Ask PhD Question
```bash
# Milton SHOULD inject PhD context
echo "What's my current PhD project?" | python -c "from agents.nexus import NEXUS; n=NEXUS(); print(n.process_message(input()).text)"
```

Milton will include:
- Your Year 1 status
- Projects 1.1, 1.2, 1.3 descriptions
- Immediate next steps
- Overall BCI goal

### Test 3: Check Memory Tagging
```python
from memory.retrieve import query_relevant

# Should return PhD-tagged memories
results = query_relevant("PhD project 1.1", limit=5)
for r in results:
    print(r.tags)  # Should include 'phd', 'research', 'year-1'
```

## Configuration

### PhD Timeline Settings
Edit [phd_context.py](../phd_context.py):
```python
PHD_START_DATE = datetime(2025, 9, 1, tzinfo=timezone.utc)  # Your actual start
PHD_DURATION_MONTHS = 54  # 4.5 years
```

### Memory Context Limits
Add to `.env`:
```bash
# PhD-specific memory settings
MILTON_PHD_MEMORY_CONTEXT_LIMIT=12      # More context for PhD queries
MILTON_PHD_MEMORY_RECENCY_BIAS=0.2      # Lower bias (prioritize long-term)

# General memory settings
MILTON_MEMORY_CONTEXT_LIMIT=8           # Standard context
MILTON_MEMORY_RECENCY_BIAS=0.35         # Standard bias
```

### PhD Keywords
Edit [phd_context.py:92](../phd_context.py):
```python
def is_phd_related(text: str) -> bool:
    phd_keywords = {
        "phd", "dissertation", "olfactory", "bci",
        # ... add more keywords specific to your research
    }
```

## Examples

### Example 1: Planning
```
You: "What should I work on today?"

Milton's Context:
  - Sees: You're in Year 1, Project 1.1
  - Retrieves: Immediate steps (read papers, design protocol, start imaging)
  - Response: "Based on your PhD Year 1 timeline, I suggest..."
```

### Example 2: Research Question
```
You: "How does calcium imaging work in ORNs?"

Milton's Context:
  - Detects: "calcium imaging" + "ORNs" = PhD-related
  - Prioritizes: PhD memories over general knowledge
  - Includes: Your Project 1.1 context (you're working on this!)
  - Response: "For your Project 1.1 (ORN Population Decoding), calcium imaging..."
```

### Example 3: Progress Tracking
```
You: "Summarize my research progress this week"

Milton's Context:
  - Retrieves: All memories tagged 'phd', 'research' from last 7 days
  - Includes: Evening briefing PhD progress entries
  - Compares: Against Year 1 project timeline
  - Response: "This week on Project 1.1, you..."
```

## Files Modified/Created

### Created
- [phd_context.py](../phd_context.py) - Central PhD awareness module
- [scripts/phd_aware_morning_briefing.py](../scripts/phd_aware_morning_briefing.py) - PhD-aware morning briefing
- [scripts/phd_aware_evening_briefing.py](../scripts/phd_aware_evening_briefing.py) - PhD-aware evening briefing
- [scripts/init_phd_research_plan.py](../scripts/init_phd_research_plan.py) - Initialize PhD plan in memory
- [docs/PHD_BRIEFING_SYSTEM.md](./PHD_BRIEFING_SYSTEM.md) - Briefing system docs
- [docs/PHD_SYSTEM_WIDE_INTEGRATION.md](./PHD_SYSTEM_WIDE_INTEGRATION.md) - This document

### Modified
- [agents/nexus.py](../agents/nexus.py) - PhD-aware agent core
- [scripts/setup_morning_briefing.sh](../scripts/setup_morning_briefing.sh) - Use PhD briefings
- [scripts/setup_phone_delivery.sh](../scripts/setup_phone_delivery.sh) - Use PhD briefings
- [.env](../.env) - Added WEATHER_API_KEY

## What This Means For You

### Every Day
1. **Morning (8:00 AM):** PhD-aware briefing delivered to phone
   - Current year projects highlighted
   - Immediate steps listed
   - Relevant papers included

2. **Throughout Day:** Every Milton interaction is PhD-aware
   - "What should I do?" → Milton suggests PhD tasks
   - "Find papers on..." → Milton filters for your research area
   - "Progress update" → Milton tracks against timeline

3. **Evening (6:00 PM):** PhD-aware reflection
   - Track research progress
   - Note papers read
   - Record blockers
   - Plan tomorrow's PhD work

### Long-Term
- **Memory:** All PhD work is tagged, high-importance, easily retrievable
- **Timeline:** Milton knows if you're on track with Year 1 goals
- **Publications:** Milton can remind you to draft papers early
- **Startup:** Milton remembers your end goal (2-3 patents → $1-2M seed)

## Next Steps

1. **Update your PhD start date** in [phd_context.py](../phd_context.py:17)
2. **Run morning briefing:**
   ```bash
   python3 scripts/phd_aware_morning_briefing.py
   ```
3. **Test PhD awareness:**
   ```bash
   # Ask Milton a PhD question
   python -c "from agents.nexus import NEXUS; n=NEXUS(); print(n.process_message('What are my current PhD projects?').text)"
   ```
4. **Set up automatic briefings:**
   ```bash
   bash scripts/setup_morning_briefing.sh
   bash scripts/setup_phone_delivery.sh
   ```

---

**PhD awareness is now pervasive throughout Milton. Every interaction, memory, and response is aligned with your 4-5 year research goal!** 🎓✨
