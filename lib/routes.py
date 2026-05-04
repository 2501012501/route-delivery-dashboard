"""Route master parsing helpers. No Streamlit calls — pure pandas/regex."""
import re
from typing import Optional

import pandas as pd

# Maps any common day spelling -> "Mon".."Sun"
_DAY_MAP = {
    'mon': 'Mon', 'monday': 'Mon', 'lun': 'Mon', 'lunes': 'Mon',
    'tue': 'Tue', 'tues': 'Tue', 'tuesday': 'Tue', 'mar': 'Tue', 'martes': 'Tue',
    'wed': 'Wed', 'weds': 'Wed', 'wednesday': 'Wed', 'mie': 'Wed', 'mié': 'Wed', 'miercoles': 'Wed', 'miércoles': 'Wed',
    'thu': 'Thu', 'thur': 'Thu', 'thurs': 'Thu', 'thursday': 'Thu', 'jue': 'Thu', 'jueves': 'Thu',
    'fri': 'Fri', 'friday': 'Fri', 'vie': 'Fri', 'viernes': 'Fri',
    'sat': 'Sat', 'saturday': 'Sat', 'sab': 'Sat', 'sáb': 'Sat', 'sabado': 'Sat', 'sábado': 'Sat',
    'sun': 'Sun', 'sunday': 'Sun', 'dom': 'Sun', 'domingo': 'Sun',
}
_LETTER_MAP = {'M':'Mon','T':'Tue','W':'Wed','R':'Thu','F':'Fri','S':'Sat','U':'Sun'}


def parse_service_days(value) -> set:
    """Returns {'Mon','Wed',...} from any free-form text in the Service Days column."""
    if pd.isna(value): return set()
    s = str(value).strip()
    if not s: return set()
    out = set()
    for tok in re.split(r'[,;/\s|+]+', s.lower()):
        if tok in _DAY_MAP:
            out.add(_DAY_MAP[tok])
    if out: return out
    for tok in re.findall(r'\b(Mo|Tu|We|Th|Fr|Sa|Su)\b', s, flags=re.I):
        out.add({'mo':'Mon','tu':'Tue','we':'Wed','th':'Thu','fr':'Fri','sa':'Sat','su':'Sun'}[tok.lower()])
    if out: return out
    s2 = s.replace('Th','R').replace('Su','U')
    for ch in s2:
        if ch in _LETTER_MAP:
            out.add(_LETTER_MAP[ch])
    return out


def find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Find a column whose normalized name matches any of `candidates`.
    Tolerant to case, accents, spaces, dots, dashes, underscores.
    """
    norm = {c: re.sub(r'[\s\.\-_]+','', c).lower() for c in df.columns}
    for cand in candidates:
        cand_n = re.sub(r'[\s\.\-_]+','', cand).lower()
        for c, n in norm.items():
            if n == cand_n: return c
        for c, n in norm.items():
            if cand_n in n: return c
    return None


def detect_route_columns(rm: pd.DataFrame) -> dict:
    """Returns dict with detected column names for the route master.
    Keys: route_no, route_afs, cluster, service, stops, cost_stop.
    Values may be None (caller decides which are required).
    """
    return {
        'route_no':  find_col(rm, 'Route No', 'Route Number', 'Route'),
        'route_afs': find_col(rm, 'Route_ID_AFS', 'Route ID AFS'),
        'cluster':   find_col(rm, 'Cluster'),
        'service':   find_col(rm, 'Service Days', 'ServiceDays', 'Days'),
        'stops':     find_col(rm, 'Stops'),
        'cost_stop': find_col(rm, 'Cost/Stop', 'CostPerStop', 'Cost/stop'),
    }


def annotate_service_days(rm: pd.DataFrame, service_col: str) -> pd.DataFrame:
    """Mutates rm by adding a `_days` column with set[str]. Returns rm."""
    rm['_days'] = rm[service_col].apply(parse_service_days)
    return rm
