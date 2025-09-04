from __future__ import annotations
from typing import List, Dict, Set, Tuple
import time
import unicodedata

def _normalize(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())

def _ngrams(s: str, n: int = 3) -> List[str]:
    s = _normalize(s)
    if not s:
        return []
    if len(s) < n:
        return [s]
    return [s[i:i+n] for i in range(len(s) - n + 1)]

class AutocompleteIndex:
    """
    In-memory prefix + n-gram index (no DB).
    """
    def __init__(self, n: int = 3):
        self.n = int(n)
        self.texts: List[str] = []
        self.gram_index: Dict[str, Set[int]] = {}
        self.prefix_map: Dict[str, Set[int]] = {}
        self.freq: Dict[int, int] = {}
        self.last_used: Dict[int, float] = {}

    def rebuild(self, texts: List[str]) -> None:
        self.texts = []
        self.gram_index.clear()
        self.prefix_map.clear()
        self.freq.clear()
        self.last_used.clear()

        seen = set()
        for t in texts:
            nt = _normalize(t)
            if not nt or nt in seen:
                continue
            idx = len(self.texts)
            self.texts.append(nt)
            seen.add(nt)
            # grams
            grams = _ngrams(nt, self.n) or [nt]
            for g in grams:
                self.gram_index.setdefault(g, set()).add(idx)
            # prefix shard (by first char)
            k = nt[0]
            self.prefix_map.setdefault(k, set()).add(idx)

    def _prefix_candidates(self, prefix: str) -> List[int]:
        if not prefix:
            return list(range(min(len(self.texts), 200)))
        k = prefix[0]
        return list(self.prefix_map.get(k, set()))

    def query(self, prefix: str, top_k: int = 10) -> List[Tuple[str, float]]:
        p = _normalize(prefix)
        cand_idx = self._prefix_candidates(p)
        grams_p = set(_ngrams(p, self.n) or ([p] if p else []))

        scored: List[Tuple[int, float, int, str]] = []
        for idx in cand_idx:
            cand = self.texts[idx]
            starts = cand.startswith(p) if p else False
            grams_c = set(_ngrams(cand, self.n) or [cand])
            inter = len(grams_p & grams_c) if grams_p else 0
            union = len(grams_p | grams_c) if grams_p else len(grams_c)
            jacc = (inter / union) if union > 0 else 0.0
            f = self.freq.get(idx, 0)
            score = (2.0 if starts else 0.0) + jacc + (0.05 * f)
            scored.append((idx, score, len(cand), cand))

        scored.sort(key=lambda x: (-x[1], x[2], x[3]))
        return [(self.texts[i], s) for (i, s, _, _) in scored[:top_k]]

    def mark_used(self, text: str) -> None:
        nt = _normalize(text)
        try:
            idx = self.texts.index(nt)
        except ValueError:
            return
        self.freq[idx] = self.freq.get(idx, 0) + 1
        self.last_used[idx] = time.time()