"""
Single source of truth for MRM risk maths.

The legacy Flask app computed risk in three different ways (a colour lookup in the
hazard registry and live preview, a raw likelihood x severity score on save, and
another raw score in the PDF). The raw-score shortcut disagreed with the official
PAF Risk Matrix for three cells (5E, 4E, 1A), so approval authority could be
under-escalated. Everything here uses the official matrix (assets/risk_matrix.png).
"""
from dataclasses import dataclass

LIKELIHOODS = {
    5: 'Frequent', 4: 'Occasional', 3: 'Remote', 2: 'Improbable', 1: 'Extremely Improbable',
}
SEVERITIES = {
    'A': 'Catastrophic', 'B': 'Hazardous', 'C': 'Major', 'D': 'Minor', 'E': 'Negligible',
}

# Official Safety Risk matrix, keyed "<likelihood><severity>".
RED = frozenset({'5A', '5B', '5C', '4A', '4B', '3A'})
YELLOW = frozenset({'5D', '5E', '4C', '4D', '4E', '3B', '3C', '3D', '2A', '2B', '2C', '1A'})
GREEN = frozenset({'3E', '2D', '2E', '1B', '1C', '1D', '1E'})

HIGH, MEDIUM, LOW = 'HIGH', 'MEDIUM', 'LOW'
_POINTS = {HIGH: 3, MEDIUM: 2, LOW: 1}

# Decision-authority tiers, ordered by escalation. (upper bound of residual-risk %, code)
AUTHORITY_TIERS = [
    (50, 'OPERATOR'),
    (65, 'SUPERVISOR'),
    (75, 'SQUADRON_COMMANDER'),
    (85, 'DIRECTOR_FOR_OPERATIONS'),
    (100, 'COMMANDER'),
]
AUTHORITY_LABELS = {
    'OPERATOR': 'Operator',
    'SUPERVISOR': 'Supervisor',
    'SQUADRON_COMMANDER': 'Squadron Commander',
    'DIRECTOR_FOR_OPERATIONS': 'Director for Operations',
    'COMMANDER': 'Commander',
}
AUTHORITY_RANGE_LABELS = {
    'OPERATOR': '≤50%',
    'SUPERVISOR': '51–65%',
    'SQUADRON_COMMANDER': '66–75%',
    'DIRECTOR_FOR_OPERATIONS': '76–85%',
    'COMMANDER': '86–100%',
}


class RiskInputError(ValueError):
    pass


def normalize(likelihood, severity):
    try:
        likelihood = int(likelihood)
    except (TypeError, ValueError):
        raise RiskInputError(f'Likelihood must be 1-5, got {likelihood!r}.')
    severity = str(severity or '').strip().upper()
    if likelihood not in LIKELIHOODS:
        raise RiskInputError(f'Likelihood must be 1-5, got {likelihood!r}.')
    if severity not in SEVERITIES:
        raise RiskInputError(f'Severity must be A-E, got {severity!r}.')
    return likelihood, severity


def rating(likelihood, severity):
    likelihood, severity = normalize(likelihood, severity)
    return f'{likelihood}{severity}'


def level(rating_code):
    """HIGH / MEDIUM / LOW for a rating such as '4B'."""
    if rating_code in RED:
        return HIGH
    if rating_code in YELLOW:
        return MEDIUM
    if rating_code in GREEN:
        return LOW
    raise RiskInputError(f'Unknown risk rating {rating_code!r}.')


def level_for(likelihood, severity):
    return level(rating(likelihood, severity))


def points(likelihood, severity):
    return _POINTS[level_for(likelihood, severity)]


def authority_for_percent(percent):
    for upper, code in AUTHORITY_TIERS:
        if percent <= upper:
            return code
    return AUTHORITY_TIERS[-1][1]


def category_for_percent(percent):
    """Coarse category used for analytics (kept from the legacy system)."""
    if percent <= 50:
        return 'Low'
    if percent <= 75:
        return 'Medium'
    return 'High'


@dataclass(frozen=True)
class RiskSummary:
    max_risk: int
    residual_risk: int
    total_percent: float
    authority_level: str
    risk_category: str

    @property
    def uoms_level(self):
        """Map onto the UOMS Mission RiskLevel scale (LOW/MEDIUM/HIGH/EXTREMELY_HIGH)."""
        if self.authority_level == 'COMMANDER':
            return 'EXTREMELY_HIGH'
        return {'Low': 'LOW', 'Medium': 'MEDIUM', 'High': 'HIGH'}[self.risk_category]


def summarize(residual_pairs):
    """
    residual_pairs: iterable of (likelihood, severity) — the *effective residual*
    rating of each selected hazard (override if set, otherwise the registry's
    after-mitigation value).
    """
    pairs = list(residual_pairs)
    max_risk = len(pairs) * 3 or 1
    residual = sum(points(l, s) for l, s in pairs)
    percent = (residual / max_risk) * 100 if pairs else 0.0
    return RiskSummary(
        max_risk=max_risk,
        residual_risk=residual,
        total_percent=round(percent, 1),
        authority_level=authority_for_percent(percent) if pairs else 'OPERATOR',
        risk_category=category_for_percent(percent),
    )
