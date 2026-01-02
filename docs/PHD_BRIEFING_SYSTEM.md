# PhD-Aware Briefing System for Milton

This document describes the PhD-aware briefing system that helps you track progress towards your 4-5 year PhD research goals.

## Overview

Milton now has your complete PhD research plan stored in long-term memory and will help you:
- Track progress against your research timeline
- Suggest daily tasks aligned with your current year projects
- Include relevant papers in your briefings
- Maintain focus on publishable, defensible IP
- Reflect on research progress daily

## Your PhD Research Plan

**Goal:** Olfactory BCI in 2 Layers (Decode + Encode)
**Timeline:** 4-5 years
**Output:** 6-8 high-impact publications + 2-3 patents + startup-ready technology

### Layer 1: Decoding (Years 1-2.5)
Decode odor identity and intensity from fruit fly brain imaging using connectome-constrained ML models.

**Projects:**
- 1.1: ORN Population Decoding (Months 1-6)
- 1.2: Connectome-Constrained ML Model (Months 6-12)
- 1.3: Learning-Dependent Plasticity (Months 10-15)
- 2.1: Three-Layer Simultaneous Decoding (Months 15-24)
- 2.2: Sparse Coding & Dimensionality Reduction (Months 20-30)
- 2.3: Upgrade to 2-Photon Imaging (Months 25-35)

### Layer 2: Encoding (Years 2.5-4)
Design electrical stimulation patterns that recreate natural odor responses, test in flies and humans.

**Projects:**
- 3.1: Reverse-Engineering Stimulation Patterns (Months 30-45)
- 3.2: Virtual Odor Learning Behavioral Test (Months 40-60)
- 3.3: Connectome-Optimized Stimulation Design (Months 50-70)
- 4.1: Human EEG Decoding Transfer (Months 70-90)
- 4.2: Non-Invasive Trigeminal Stimulation (Months 85-110)
- 4.3: Integrated Closed-Loop Proof-of-Concept (Months 110-150)

## Using the PhD-Aware Briefing System

### Initial Setup

1. **Initialize your PhD research plan** (already done):
   ```bash
   python3 scripts/init_phd_research_plan.py
   ```

   This stores:
   - Overall research plan and goals
   - All 12 project descriptions with timelines
   - Immediate next steps
   - Reading list
   - Updates your user profile with PhD context

### Daily Workflow

#### Morning Briefing

Generate your PhD-aware morning briefing:

```bash
python3 scripts/phd_aware_morning_briefing.py
```

**What it includes:**
- 🎓 PhD Research Focus
  - Overall goal reminder
  - Current year projects (Projects 1.1-1.3 if Year 1)
  - Immediate next steps
- ✓ Goals for Today
- 🌙 Overnight job results
- ☀️ Weather
- 📄 Recent Papers (filtered for PhD relevance)
- 💡 Suggested Focus

**Output location:** `~/.local/state/milton_os/inbox/morning/YYYY-MM-DD_phd_aware.md`

#### Evening Briefing

Generate your PhD-aware evening briefing:

```bash
python3 scripts/phd_aware_evening_briefing.py
```

**Interactive prompts:**
- Day summary
- General wins
- **PhD research progress today** (new!)
- **Papers read/skimmed today** (new!)
- Blockers
- Tomorrow priorities (including PhD tasks)
- Notes/decisions
- Overnight jobs to queue

**What it includes:**
- 📝 Day Summary
- 🎓 PhD Research Progress
- 📄 Papers Read/Skimmed
- ✓ General Wins
- ⚠️ Blockers
- 📅 Tomorrow Priorities
- 💭 Notes/Decisions
- 🎯 Active Goals
- 🌙 Overnight Jobs
- 🤔 Reflection prompts

**Output location:** `~/.local/state/milton_os/inbox/evening/YYYY-MM-DD_phd_aware.md`

### Non-Interactive Usage

You can also provide inputs via command line:

```bash
# Morning briefing
python3 scripts/phd_aware_morning_briefing.py --max-papers 5

# Evening briefing
python3 scripts/phd_aware_evening_briefing.py \
  --summary "Worked on ORN imaging protocol" \
  --phd-progress "Designed odor panel with 8 odorants" \
  --phd-progress "Met with advisor about 2-photon timeline" \
  --papers-read "Calcium imaging review paper (Nature Methods)" \
  --tomorrow "Finalize imaging parameters" \
  --tomorrow "Order GCaMP flies" \
  --non-interactive
```

Or via JSON stdin:

```bash
echo '{
  "summary": "Good progress on imaging setup",
  "phd_progress": ["Designed odor panel", "Tested GCaMP expression"],
  "papers_read": ["Calcium imaging review"],
  "tomorrow": ["Order flies", "Calibrate olfactometer"],
  "wins": ["Protocol working!"],
  "blockers": []
}' | python3 scripts/phd_aware_evening_briefing.py --use-stdin --non-interactive
```

## Integration with Milton's Memory

All briefings are stored in Milton's long-term memory with tags:
- `briefing`, `morning` or `evening`
- `phd-aware`
- `date:YYYY-MM-DD`

This means Milton can:
- Recall your PhD progress over time
- Answer questions like "What did I work on last week?"
- Track which papers you've read
- Identify blockers across multiple days
- Suggest tasks based on your research timeline

## User Profile Updates

Your user profile now includes:

**Stable Facts:**
- PhD student in neuroscience (olfactory BCI)
- Working on Drosophila calcium imaging + connectomics
- Goal: 6-8 publications + 2-3 patents
- Timeline: 4-5 years
- Current year: 1 (baseline decoding)

**Preferences:**
- Prioritize PhD research in daily planning
- Track progress against timeline
- Include relevant papers in briefings
- Maintain focus on publishable IP
- Remind about immediate next steps

## Example Daily Routine

### Morning (8:00 AM)
```bash
# Generate and review morning briefing
python3 scripts/phd_aware_morning_briefing.py
cat ~/.local/state/milton_os/inbox/morning/$(date +%Y-%m-%d)_phd_aware.md

# Milton reminds you:
# - You're in Year 1, Project 1.1 (ORN Population Decoding)
# - Next step: Design imaging protocol with advisor
# - 2 relevant papers published yesterday
```

### Evening (6:00 PM)
```bash
# Generate evening briefing (interactive)
python3 scripts/phd_aware_evening_briefing.py

# Answer prompts:
# > PhD research progress today: Tested GCaMP expression in Orco-Gal4 flies
# > Papers read: "Intraglomerular ORN activity patterns" (Nature 2023)
# > Tomorrow: Finalize odor panel, order chemicals
```

### Result
Milton now has a complete memory of:
- Your long-term PhD goals (4-5 years)
- Your current project status
- Papers you've read
- Progress made each day
- Blockers encountered
- Next steps planned

## Querying Milton About Your PhD

You can now ask Milton questions like:

- "What's my current PhD project?"
- "What papers should I read for Project 1.1?"
- "Summarize my PhD progress this week"
- "What are my immediate next steps?"
- "Am I on track with my Year 1 timeline?"

Milton will retrieve this information from long-term memory and provide contextualized answers.

## Customization

### Update Your PhD Plan

If your research plan changes, you can:

1. Edit [scripts/init_phd_research_plan.py](../scripts/init_phd_research_plan.py)
2. Re-run the initialization: `python3 scripts/init_phd_research_plan.py`

This will update your long-term memory with the new plan.

### Adjust Briefing Format

Edit the markdown builders:
- Morning: `_build_phd_aware_markdown()` in [scripts/phd_aware_morning_briefing.py](../scripts/phd_aware_morning_briefing.py)
- Evening: `_build_phd_aware_evening_markdown()` in [scripts/phd_aware_evening_briefing.py](../scripts/phd_aware_evening_briefing.py)

### Change Paper Queries

Edit `_get_relevant_papers()` in the morning briefing script to search for different topics:

```python
queries = [
    "olfactory calcium imaging Drosophila",
    "connectome neural decoding",
    "brain-computer interface olfaction"
]
```

## Files Created

- [scripts/init_phd_research_plan.py](../scripts/init_phd_research_plan.py) - Initialize PhD plan in memory
- [scripts/phd_aware_morning_briefing.py](../scripts/phd_aware_morning_briefing.py) - Morning briefing generator
- [scripts/phd_aware_evening_briefing.py](../scripts/phd_aware_evening_briefing.py) - Evening briefing generator
- [docs/PHD_BRIEFING_SYSTEM.md](./PHD_BRIEFING_SYSTEM.md) - This documentation

## Next Steps

1. **Run your first morning briefing:**
   ```bash
   python3 scripts/phd_aware_morning_briefing.py
   ```

2. **Set up daily automation** (optional):
   ```bash
   # Add to crontab
   0 8 * * * cd ~/milton && python3 scripts/phd_aware_morning_briefing.py
   0 18 * * * cd ~/milton && python3 scripts/phd_aware_evening_briefing.py
   ```

3. **Start tracking your PhD progress daily!**

---

*Your PhD research plan is now integrated into Milton's long-term memory. Milton will help you stay focused, track progress, and achieve your goal of building a world-class olfactory BCI and launching a startup.*
