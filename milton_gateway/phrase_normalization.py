"""Phrase normalization for similarity matching in learning system.

Provides deterministic fingerprinting of user utterances to enable
similarity-based matching for learned corrections.
"""

import re
from typing import Set


def normalize_phrase(text: str) -> str:
    """Normalize a phrase for similarity matching.
    
    Normalization steps:
    1. Lowercase
    2. Replace numbers with <num> token
    3. Normalize time expressions to <time> token
    4. Remove punctuation except spaces
    5. Collapse whitespace
    
    Args:
        text: Raw user utterance
        
    Returns:
        Normalized fingerprint string
    """
    text = text.lower().strip()
    
    # Replace numbers with <num>
    text = re.sub(r'\b\d+(?::\d+)?\s*(?:am|pm)?\b', '<time>', text)  # Times first
    text = re.sub(r'\b\d+\b', '<num>', text)
    
    # Normalize common time words
    time_normalizations = {
        'tmrw': 'tomorrow',
        'tom': 'tomorrow',
        'tomo': 'tomorrow',
        'mins': 'minutes',
        'min': 'minutes',
        'hrs': 'hours',
        'hr': 'hours',
        'wk': 'week',
        'mo': 'month',
        'yr': 'year',
    }
    
    for abbrev, full in time_normalizations.items():
        text = re.sub(rf'\b{abbrev}\b', full, text)
    
    # Remove punctuation except spaces
    text = re.sub(r'[^\w\s<>]', ' ', text)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def tokenize(text: str) -> Set[str]:
    """Tokenize normalized text into a set of tokens.
    
    Args:
        text: Normalized phrase
        
    Returns:
        Set of tokens
    """
    return set(text.split())


def jaccard_similarity(text1: str, text2: str) -> float:
    """Compute Jaccard similarity between two phrases.
    
    Jaccard similarity = |intersection| / |union|
    
    Args:
        text1: First normalized phrase
        text2: Second normalized phrase
        
    Returns:
        Similarity score between 0.0 and 1.0
    """
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)
    
    if not tokens1 and not tokens2:
        return 1.0
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    
    return len(intersection) / len(union)


def is_similar(text1: str, text2: str, threshold: float = 0.55) -> bool:
    """Check if two phrases are similar based on Jaccard similarity.
    
    Args:
        text1: First phrase (will be normalized)
        text2: Second phrase (will be normalized)
        threshold: Similarity threshold (default 0.55)
        
    Returns:
        True if similarity >= threshold
    """
    norm1 = normalize_phrase(text1)
    norm2 = normalize_phrase(text2)
    
    similarity = jaccard_similarity(norm1, norm2)
    
    return similarity >= threshold
