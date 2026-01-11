# Golden Retrieval Dataset

This directory contains a small, deterministic golden dataset for retrieval benchmarking.

## Structure

- `documents.json`: Corpus of 8 documents covering various topics
- `queries.json`: 5 test queries with expected relevant documents

## Document Topics

- **Programming**: Python, JavaScript (doc1, doc5)
- **AI/ML**: Machine learning, deep learning, NLP (doc2, doc4, doc6)
- **Geography**: European capitals (doc3, doc7)
- **Computer Science**: Data structures (doc8)

## Usage

```python
from benchmarks.tiers.retrieval import load_golden_set
from pathlib import Path

golden_dir = Path("benchmarks/goldens")
documents, queries = load_golden_set(golden_dir)
```

## Evaluation Metrics

- **Precision**: What fraction of retrieved documents are relevant?
- **Recall**: What fraction of relevant documents were retrieved?
- **F1 Score**: Harmonic mean of precision and recall

Example:
- Query: "What is machine learning?"
- Expected relevant: doc2 (machine learning), doc4 (deep learning)
- Retrieved: doc2, doc4, doc6
- Precision: 2/3 = 0.667 (2 relevant out of 3 retrieved)
- Recall: 2/2 = 1.0 (both relevant docs retrieved)
- F1: 2 * (0.667 * 1.0) / (0.667 + 1.0) = 0.800
