"""Operational statistics with explicit cohorts, missingness and denominators.

Completion timestamps are registration times, not clinical start times. Reports
describe the current snapshot; reconstructing past backlog requires event history.
"""
from __future__ import annotations
import math
import pandas as pd

GROUPS = ['organisation', 'site', 'service', 'regime', 'priority', 'access_kind']


def wilson(successes, total):
    if total == 0:
        return float('nan'), float('nan')
    z = 1.959963984540054
    p = successes / total
    scale = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / scale
    radius = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / scale
    return centre - radius, centre + radius


def operational_report(frame, *, as_of=None):
    """Current snapshot, split by regime/site; no legal-compliance certification.

    No-show denominator = resolved appointments (executed or no-show), due by
    as_of, with recorded outcomes by as_of. Pending and cancelled are separate.
    Request-to-slot includes first visits only, non-cancelled, known real request.
    Missing dates are not replaced by booking creation dates.
    """
    required = set(GROUPS + ['id', 'status', 'created_at', 'starts_at', 'requested_at', 'executed_at'])
    if required - set(frame.columns):
        raise ValueError('Colonne mancanti: ' + ', '.join(sorted(required - set(frame.columns))))
    now = pd.Timestamp(as_of or pd.Timestamp.now(tz='UTC'))
    if now.tzinfo is None:
        raise ValueError('as_of deve includere un fuso orario.')
    df = frame.copy()
    if df.id.duplicated().any():
        raise ValueError('Identificativi prenotazione duplicati.')
    from visit_workflow import STATES
    if not df.status.isin(STATES).all():
        raise ValueError('Stati prenotazione non riconosciuti.')
    for col in ['created_at', 'starts_at', 'requested_at', 'executed_at']:
        # Require timezone explicitly, do not interpret naive timestamps as UTC.
        from visit_workflow import timestamp
        df[col] = pd.to_datetime(df[col].map(lambda v: timestamp(v) if pd.notna(v) else None), utc=True)
    if df[['created_at', 'starts_at']].isna().any().any():
        raise ValueError('Data di creazione o appuntamento mancante.')
    if (df.requested_at > df.created_at).any():
        raise ValueError('Richiesta successiva alla prenotazione.')
    if ((df.status == 'eseguita') != df.executed_at.notna()).any():
        raise ValueError('Stato e registrazione esecuzione incoerenti.')
    if (df.executed_at > now).any() or (df.created_at > now).any():
        raise ValueError('Lo snapshot contiene eventi futuri rispetto ad as_of.')
    for col in GROUPS:
        df[col] = df[col].fillna('NON_INDICATO').replace('', 'NON_INDICATO')
    rows = []
    for keys, group in df.groupby(GROUPS, dropna=False, sort=True):
        due = group.starts_at <= now
        executed = group.status == 'eseguita'
        absent = group.status == 'non_presentato'
        if ((executed | absent) & ~due).any():
            raise ValueError('Esito terminale precedente all’appuntamento.')
        pending = group.status.isin(['prenotata', 'confermata', 'accettata'])
        eligible = (group.access_kind == 'PRIMO') & (group.status != 'annullata')
        waits = (group.starts_at - group.requested_at).dt.total_seconds() / 86400
        valid_wait = eligible & waits.notna() & (waits >= 0)
        valid_backlog = pending & group.requested_at.notna()
        ages = (now - group.loc[valid_backlog, 'requested_at']).dt.total_seconds() / 86400
        denominator = int((due & (executed | absent)).sum())
        misses = int((due & absent).sum())
        low, high = wilson(misses, denominator)
        rows.append(dict(zip(GROUPS, keys)) | {
            'bookings': len(group), 'executed': int(executed.sum()),
            'cancelled': int((group.status == 'annullata').sum()),
            'backlog': int(pending.sum()), 'overdue_unresolved': int((pending & due).sum()),
            'resolved_due': denominator, 'no_show': misses,
            'no_show_rate': misses / denominator if denominator else float('nan'),
            'no_show_ci95_low': low, 'no_show_ci95_high': high,
            'wait_eligible': int(eligible.sum()), 'wait_observed': int(valid_wait.sum()),
            'missing_request': int(group.requested_at.isna().sum()),
            'request_to_current_slot_median_days': waits[valid_wait].median(),
            'request_to_current_slot_p90_days': waits[valid_wait].quantile(.9),
            'backlog_age_observed': int(valid_backlog.sum()),
            'backlog_age_p90_days': ages.quantile(.9),
        })
    return pd.DataFrame(rows)


def capacity_report(booked, capacity):
    """Compare scheduled minutes with explicit capacity at the same grain.

    Input: organisation/site/regime/period + booked_minutes or available_minutes.
    Missing capacity yields NaN, zero capacity is reported explicitly. This is
    agenda saturation, not clinical productivity or actual room utilisation.
    """
    keys = ['organisation', 'site', 'regime', 'period']
    booked, capacity = booked.copy(), capacity.copy()
    for df, value in [(booked, 'booked_minutes'), (capacity, 'available_minutes')]:
        if set(keys + [value]) - set(df.columns) or df[keys].isna().any().any():
            raise ValueError('Schema capacità o chiavi incompleti.')
        df[value] = pd.to_numeric(df[value], errors='raise')
        if df.duplicated(keys).any() or df[value].isna().any() or (df[value] < 0).any() or not df[value].map(math.isfinite).all():
            raise ValueError('Capacità/carico non valido o chiavi duplicate.')
    result = booked.merge(capacity, how='outer', on=keys, validate='one_to_one')
    result['capacity_known'] = result.available_minutes.notna()
    result['load_known'] = result.booked_minutes.notna()
    result['saturation'] = result.booked_minutes / result.available_minutes.where(result.available_minutes > 0)
    return result


def public_annual_report(frame):
    """Annual SSR production. Provider nature stays distinct from payment regime."""
    keys = ['anno', 'cod_ats_erogazione', 'desc_ats_erogazione', 'pubb_priv']
    result = frame.groupby(keys, dropna=False, as_index=False).agg(volume=('volume', 'sum'), source_rows=('source_rows', 'sum'))
    unknown = frame.assign(unknown_volume=frame.volume.where(frame.cod_class_priorita == 'NON_INDICATA', 0))
    unknown = unknown.groupby(keys, dropna=False, as_index=False).unknown_volume.sum()
    result = result.merge(unknown, on=keys, validate='one_to_one').sort_values(keys[1:] + ['anno'])
    grouping = result.groupby(keys[1:], dropna=False)
    previous = grouping.volume.shift()
    contiguous = result.anno - grouping.anno.shift() == 1
    result['yoy_fraction'] = ((result.volume - previous) / previous.where(previous > 0)).where(contiguous)
    result['unknown_priority_fraction'] = result.unknown_volume / result.volume.where(result.volume > 0)
    return result
