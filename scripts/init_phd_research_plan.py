#!/usr/bin/env python3
"""Initialize Cole's PhD research plan into Milton's long-term memory."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from memory.schema import MemoryItem
from memory.store import add_memory, upsert_user_profile

# PhD Research Plan - Olfactory BCI Layers 1 & 2
PHD_RESEARCH_PLAN = {
    "title": "PhD Research Plan: Olfactory BCI Layers 1 & 2",
    "duration": "4-5 years",
    "goal": "Publishable, defensible IP leading to company post-graduation",

    "layer_1": {
        "name": "Decoding",
        "timeline": "Years 1-2.5",
        "description": "Decode odor identity + intensity from fruit fly ORN/PN calcium imaging",
        "key_technologies": [
            "Connectome (FlyWire) constrained ML models",
            "2-photon imaging",
            "GCaMP calcium imaging"
        ],
        "expected_output": "3-4 publishable papers, patent on decoding algorithms"
    },

    "layer_2": {
        "name": "Encoding",
        "timeline": "Years 2.5-4",
        "description": "Design electrical stimulation patterns that recreate natural odor responses",
        "key_technologies": [
            "Virtual odors via electrical brain stimulation",
            "Behavioral learning tests",
            "Non-invasive trigeminal nerve stimulation (human)"
        ],
        "expected_output": "3-4 publishable papers, patent on stimulation design, human feasibility data"
    },

    "projects": [
        # Year 1
        {
            "id": "1.1",
            "name": "ORN Population Decoding",
            "timeline": "First 6 months",
            "year": 1,
            "tasks": [
                "Image ORN responses to odors (30-50 glomeruli per fly)",
                "Build ML decoder for odor prediction from brain activity",
                "Test with odor panel: ethyl acetate, octanol, benzaldehyde, etc.",
                "Achieve 70-85% baseline accuracy"
            ],
            "expected_publication": "eLife or Neuron"
        },
        {
            "id": "1.2",
            "name": "Connectome-Constrained ML Model",
            "timeline": "Months 6-12",
            "year": 1,
            "tasks": [
                "Download ORN→PN synaptic weights from FlyWire",
                "Build RNN with actual synaptic connectivity",
                "Compare generic CNN vs connectome-informed decoding",
                "Validate predictions against actual PN imaging"
            ],
            "expected_publication": "Nature Neuroscience or Nature Methods"
        },
        {
            "id": "1.3",
            "name": "Learning-Dependent Plasticity",
            "timeline": "Months 10-15",
            "year": 1,
            "tasks": [
                "Image before/during/after optogenetic conditioning",
                "Quantify ORN vs PN response changes with learning",
                "Identify plastic vs hardwired neurons",
                "Test connectome prediction of plasticity"
            ],
            "expected_publication": "PNAS or Neuron"
        },

        # Year 2
        {
            "id": "2.1",
            "name": "Three-Layer Simultaneous Decoding",
            "timeline": "Months 15-24",
            "year": 2,
            "tasks": [
                "Image ORNs → PNs → KCs in same flies",
                "Decode at each circuit layer",
                "Quantify information bottlenecks",
                "Validate connectome predictions"
            ],
            "expected_publication": "1-2 papers (eLife, Neuron, Nature Communications)"
        },
        {
            "id": "2.2",
            "name": "Sparse Coding & Dimensionality Reduction",
            "timeline": "Months 20-30",
            "year": 2,
            "tasks": [
                "PCA on ORN, PN, KC population responses",
                "Quantify sparsity in KC code",
                "Determine minimal electrode requirements",
                "Information coding theory analysis"
            ],
            "expected_publication": "Nature Neuroscience or Nature Methods"
        },
        {
            "id": "2.3",
            "name": "Upgrade to 2-Photon Imaging",
            "timeline": "Months 25-35",
            "year": 2,
            "tasks": [
                "Collaborate with WashU 2-photon facility",
                "Achieve cellular resolution at 15-30 Hz",
                "Identify KC subtypes by morphology",
                "Test real-time decoding (<500ms latency)"
            ],
            "expected_publication": "Nature Neuroscience or eLife"
        },

        # Year 2.5-3
        {
            "id": "3.1",
            "name": "Reverse-Engineering Stimulation Patterns",
            "timeline": "Months 30-45",
            "year": 3,
            "tasks": [
                "Place multi-electrode array in antennal lobe",
                "Vary stimulation parameters (amplitude, frequency, pulse width)",
                "Find parameters recreating natural responses (fidelity >0.8)",
                "Design time-varying stimulation matching natural dynamics"
            ],
            "expected_publication": "eLife or Nature Communications"
        },
        {
            "id": "3.2",
            "name": "Virtual Odor Learning Behavioral Test",
            "timeline": "Months 40-60",
            "year": 3,
            "tasks": [
                "Test fly learning from electrical stim vs real odors",
                "Measure learning curves and discrimination accuracy",
                "Test virtual odor mixtures",
                "Correlate fidelity score with learning rate"
            ],
            "expected_publication": "1-2 papers (Nature Communications, PNAS, Neuron)"
        },
        {
            "id": "3.3",
            "name": "Connectome-Optimized Stimulation Design",
            "timeline": "Months 50-70",
            "year": 3,
            "tasks": [
                "Identify hub PNs with highest connectivity",
                "Compare stimulating hub vs non-hub neurons",
                "Multi-layer stimulation comparison (ORN/PN/KC)",
                "Define encoding efficiency metric"
            ],
            "expected_publication": "Nature Neuroscience Methods or eLife"
        },

        # Year 3.5-4
        {
            "id": "4.1",
            "name": "Human EEG Decoding Transfer",
            "timeline": "Months 70-90",
            "year": 4,
            "tasks": [
                "EEG study with n=20-30 healthy volunteers",
                "Transfer learning: fly→human decoding",
                "Compare human piriform/OFC to fly PN/KC",
                "Test if connectome principles generalize cross-species"
            ],
            "expected_publication": "Science Translational Medicine or Nature Neuroscience"
        },
        {
            "id": "4.2",
            "name": "Non-Invasive Trigeminal Stimulation (Human)",
            "timeline": "Months 85-110",
            "year": 4,
            "tasks": [
                "Pilot study: n=5-10 healthy subjects",
                "Map stimulation parameters to perception types",
                "3-day learning study with virtual odors",
                "Record EEG during trigeminal stimulation"
            ],
            "expected_publication": "Nature Biomedical Engineering or eLife"
        },
        {
            "id": "4.3",
            "name": "Integrated Closed-Loop Proof-of-Concept",
            "timeline": "Months 110-150",
            "year": 4,
            "tasks": [
                "Build complete system: imaging→decoding→stim→behavior",
                "Test fly-to-fly virtual odor transfer",
                "File patent applications",
                "Demonstrate real-time BCI loop"
            ],
            "expected_publication": "Nature, Science, or Science Advances"
        }
    ],

    "key_papers_to_read": [
        "Calcium imaging in olfactory circuit layers",
        "Intraglomerular ORN activity patterns",
        "Piriform neuron odor coding",
        "Deep learning for neural decoding review",
        "Connectome-based models of neural function",
        "Connectome-constrained feature selectivity",
        "Connectome predicts neural activity",
        "Brain-to-spine interface for sensory encoding",
        "Brain stimulation for artificial perception",
        "Rapid integration of artificial sensation",
        "Closed-loop neurofeedback framework",
        "Closed-loop BCI systems review"
    ],

    "expected_output": {
        "publications": "6-8 high-impact papers (Nature, eLife, PNAS, Neuron)",
        "patents": "2-3 patent applications",
        "software": "Open-source software toolkit",
        "human_data": "Preliminary human data (trigeminal stim feasibility)",
        "funding_ready": "Ready for startup seed funding ($1-2M)"
    },

    "immediate_next_steps": [
        "Read key papers (weeks 1-2)",
        "Design Project 1.1 imaging protocol with advisor (week 2-3)",
        "Start fly imaging with current setup (week 4+)",
        "Begin connectome analysis using FlyWire (parallel)",
        "Draft publications throughout (early and revise)"
    ]
}


def store_phd_research_plan() -> None:
    """Store PhD research plan in Milton's long-term memory."""
    print("Initializing PhD Research Plan into Milton's long-term memory...")

    # Store overall research plan
    overall_plan = MemoryItem(
        agent="system",
        type="fact",
        content=(
            f"PhD Research Plan: {PHD_RESEARCH_PLAN['title']}. "
            f"Duration: {PHD_RESEARCH_PLAN['duration']}. "
            f"Goal: {PHD_RESEARCH_PLAN['goal']}. "
            f"Layer 1 ({PHD_RESEARCH_PLAN['layer_1']['timeline']}): {PHD_RESEARCH_PLAN['layer_1']['description']}. "
            f"Layer 2 ({PHD_RESEARCH_PLAN['layer_2']['timeline']}): {PHD_RESEARCH_PLAN['layer_2']['description']}. "
            f"Expected output: {PHD_RESEARCH_PLAN['expected_output']['publications']}, "
            f"{PHD_RESEARCH_PLAN['expected_output']['patents']}, ready for startup funding."
        ),
        tags=["phd", "research-plan", "long-term-goal", "olfactory-bci"],
        importance=1.0,
        source="user-stated-goal",
        evidence=["phd-research-plan-2026"]
    )
    memory_id = add_memory(overall_plan)
    print(f"✓ Stored overall research plan: {memory_id}")

    # Store each project
    for project in PHD_RESEARCH_PLAN['projects']:
        project_memory = MemoryItem(
            agent="system",
            type="project",
            content=(
                f"PhD Project {project['id']}: {project['name']} ({project['timeline']}, Year {project['year']}). "
                f"Tasks: {'; '.join(project['tasks'])}. "
                f"Expected publication: {project['expected_publication']}."
            ),
            tags=[
                "phd",
                "research-project",
                f"year-{project['year']}",
                f"project-{project['id'].replace('.', '-')}",
                "olfactory-bci"
            ],
            importance=0.9,
            source="user-stated-goal",
            evidence=["phd-research-plan-2026"]
        )
        proj_id = add_memory(project_memory)
        print(f"✓ Stored project {project['id']}: {project['name']} [{proj_id}]")

    # Store immediate next steps
    for idx, step in enumerate(PHD_RESEARCH_PLAN['immediate_next_steps'], 1):
        step_memory = MemoryItem(
            agent="system",
            type="project",
            content=f"PhD immediate next step {idx}: {step}",
            tags=["phd", "immediate-action", "next-step"],
            importance=0.95,
            source="user-stated-goal",
            evidence=["phd-research-plan-2026"]
        )
        step_id = add_memory(step_memory)
        print(f"✓ Stored next step {idx}: {step[:50]}... [{step_id}]")

    # Store key papers to read
    papers_memory = MemoryItem(
        agent="system",
        type="fact",
        content=(
            "PhD key papers to read: " +
            "; ".join(PHD_RESEARCH_PLAN['key_papers_to_read'])
        ),
        tags=["phd", "reading-list", "literature"],
        importance=0.7,
        source="user-stated-goal",
        evidence=["phd-research-plan-2026"]
    )
    papers_id = add_memory(papers_memory)
    print(f"✓ Stored reading list: {papers_id}")

    # Update user profile with PhD goals
    profile_patch = {
        "stable_facts": [
            "PhD student in neuroscience focusing on olfactory BCI",
            "Working on fruit fly (Drosophila) calcium imaging and connectomics",
            "Goal: Build olfactory brain-computer interface in 2 layers (decode + encode)",
            "Target: 6-8 high-impact publications + 2-3 patents",
            "Timeline: 4-5 years to completion, ready for startup seed funding",
            "Current year: 1 (baseline decoding from ORN/PN populations)",
            "Long-term vision: Translate fly research to human trigeminal stimulation BCI"
        ],
        "preferences": [
            "Prioritize PhD research projects in daily/weekly planning",
            "Track progress against 4-5 year research timeline",
            "Include relevant papers and research updates in briefings",
            "Help maintain focus on publishable, defensible IP",
            "Remind about immediate next steps for current year projects"
        ]
    }

    updated_profile = upsert_user_profile(
        profile_patch,
        evidence_ids=[memory_id, papers_id]
    )
    print(f"✓ Updated user profile with PhD goals")
    print(f"  - Added {len(profile_patch['stable_facts'])} stable facts")
    print(f"  - Added {len(profile_patch['preferences'])} preferences")

    print("\n" + "="*70)
    print("PhD Research Plan successfully stored in Milton's long-term memory!")
    print("="*70)
    print("\nMilton will now:")
    print("  • Include PhD progress tracking in morning briefings")
    print("  • Suggest research tasks aligned with your current year/project")
    print("  • Help you stay focused on publication and IP goals")
    print("  • Track progress against the 4-5 year timeline")


if __name__ == "__main__":
    store_phd_research_plan()
