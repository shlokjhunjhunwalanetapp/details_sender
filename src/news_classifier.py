from __future__ import annotations

import re

# Words that are ignored when building a title fingerprint for deduplication.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "shall", "can", "need", "must", "ought",
        "to", "of", "in", "on", "at", "by", "for", "with", "about", "from",
        "as", "into", "through", "after", "before", "between", "up", "down",
        "out", "off", "over", "under", "again", "then", "once", "here",
        "there", "when", "where", "why", "how", "all", "both", "each",
        "few", "more", "most", "other", "some", "such", "no", "not", "only",
        "own", "same", "so", "than", "too", "very", "just", "but", "and",
        "or", "nor", "if", "its", "it", "this", "that", "these", "those",
        "he", "she", "they", "we", "you", "i", "my", "your", "his", "her",
        "our", "their", "what", "which", "who", "whom", "says", "said",
        "amid", "while", "despite", "yet", "still",
    }
)

# ── Criticality keyword rules ──────────────────────────────────────────────────
# Evaluated in order; first match wins.

_CRITICAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bfraud\b",
        r"\bscam\b",
        r"\bscandal\b",
        r"\binvestigation\b",
        r"\bED\b",          # Enforcement Directorate
        r"\bCBI\b",
        r"\bSFIO\b",
        r"\bSEBI\b.{0,30}(notice|order|ban|penalty|action|probe|raid|fine)",
        r"\bRBI\b.{0,30}(ban|penalty|action|fine|order)",
        r"\bdefault\b",
        r"\bbankrupt",
        r"\binsolvency\b",
        r"\bliquidat",
        r"\blicense\b.{0,20}(revok|cancel|suspend)",
        r"\bcollaps",
        r"\bcrash(ed|es|ing)?\b",
        r"\bplunge[sd]?\b",
        r"\b(massive|sharp|steep|severe).{0,20}(loss|decline|fall|drop|write)",
        r"\bwrite.?off\b",
        r"\bdowngrad(e[sd]?|ing)\b",
        r"\bresign(ed|s|ation)?\b.{0,30}(CEO|MD|CFO|chairman|director)",
        r"\b(CEO|MD|CFO|chairman).{0,30}\bresign",
    ]
]

_KEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bQ[1-4]\b.{0,20}(result|earning|profit|revenue)",
        r"\b(quarterly|annual)\b.{0,20}(result|earning|profit|revenue)",
        r"\bresult[s]?\b",
        r"\bearning[s]?\b",
        r"\bdividend\b",
        r"\bbuyback\b",
        r"\bbonus\b.{0,10}(share|stock)",
        r"\bstock\b.{0,10}split\b",
        r"\bmerger\b",
        r"\bacquir(e[sd]?|ing|es)\b",
        r"\bacquisition\b",
        r"\btakeover\b",
        r"\bdemerger\b",
        r"\bIPO\b",
        r"\bQIP\b",
        r"\bright[s]? issue\b",
        r"\b(major|large|record|biggest).{0,20}(deal|contract|order|win|project)",
        r"\b(deal|contract|order)\b.{0,20}(win|award|signed|bagged)",
        r"\b(appointed|named|elevated).{0,30}(CEO|MD|CFO|chairman|director)",
        r"\b(CEO|MD|CFO).{0,30}(appointed|named|resign|change|replac)",
        r"\bcredit.{0,10}(rating|outlook)\b",
        r"\bupgrad(e[sd]?|ing)\b",
        r"\bFII\b.{0,20}(buy|sell|stake|hold)",
        r"\bDII\b.{0,20}(buy|sell|stake|hold)",
        r"\bblock\b.{0,10}deal\b",
        r"\bbulk\b.{0,10}deal\b",
        r"\bJoint\s+Venture\b",
        r"\b\bJV\b\b",
        r"\bpartnership\b",
        r"\bMoU\b",
    ]
]


def classify_headline(title: str) -> str:
    """Return a criticality label for a news headline.

    Returns one of:
      "⚠️ CRITICAL"  – high-impact events (fraud, default, crash, key exec exit…)
      "📌 KEY"        – significant corporate events (results, M&A, dividends…)
      ""              – routine/no special flag
    """
    for pattern in _CRITICAL_PATTERNS:
        if pattern.search(title):
            return "⚠️ CRITICAL"
    for pattern in _KEY_PATTERNS:
        if pattern.search(title):
            return "📌 KEY"
    return ""


def title_fingerprint(title: str) -> frozenset[str]:
    """Reduce a headline to a set of significant words for similarity checks."""
    words = re.sub(r"[^a-z0-9\s]", " ", title.lower()).split()
    return frozenset(w for w in words if len(w) > 3 and w not in _STOPWORDS)


def is_duplicate_title(
    fp: frozenset[str],
    seen_fingerprints: list[frozenset[str]],
    threshold: float = 0.38,
) -> bool:
    """Return True if `fp` overlaps too strongly with any already-seen fingerprint.

    Uses Jaccard similarity: |intersection| / |union|.
    Fingerprints smaller than 4 words are never matched (too short to be reliable).
    """
    if len(fp) < 4:
        return False
    for seen in seen_fingerprints:
        if not seen:
            continue
        intersection = len(fp & seen)
        union = len(fp | seen)
        if union > 0 and intersection / union >= threshold:
            return True
    return False
