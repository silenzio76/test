"""Chronological evaluation of weekly demand; no patient-level predictors.

Input is a single coherent site/service/regime cohort, with certified complete
weekly observation. Demand counts must include all requests, including requests
not booked. Never derive this series from annual production or booked visits only.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def validate_weekly(frame):
    if set(['week', 'requests', 'complete']) - set(frame.columns):
        raise ValueError('Richieste colonne week, requests, complete.')
    df = frame[['week', 'requests', 'complete']].copy()
    df['week'] = pd.to_datetime(df.week, errors='raise')
    if df.week.dt.tz is not None or not (df.week.dt.dayofweek == 0).all() or not (df.week == df.week.dt.normalize()).all():
        raise ValueError('week deve essere il lunedì locale, senza orario o fuso.')
    df = df.sort_values('week').reset_index(drop=True)
    if df.week.duplicated().any() or not (df.week.diff().dropna() == pd.Timedelta(days=7)).all():
        raise ValueError('Settimane duplicate o mancanti: non riempire automaticamente con zero.')
    if not df.complete.map(lambda v: v is True or isinstance(v, (bool, np.bool_)) and bool(v)).all():
        raise ValueError('Copertura settimanale non verificata; complete deve essere booleano True.')
    df['requests'] = pd.to_numeric(df.requests, errors='raise')
    if not np.isfinite(df.requests).all() or (df.requests < 0).any() or (df.requests % 1 != 0).any():
        raise ValueError('Conteggi richieste non validi.')
    if len(df) < 52:
        raise ValueError('Servono almeno 52 settimane complete; preferibili più anni per stagionalità.')
    return df


def features(values, date):
    return [values[-1], values[-4], float(np.mean(values[-4:])), values[-13],
            np.sin(2 * np.pi * date.dayofyear / 365.25), np.cos(2 * np.pi * date.dayofyear / 365.25)]


def evaluate_demand(frame, *, holdout=12, horizon=4):
    """Frozen model, rolling one-step holdout; recursive future horizon reported separately.

    Lag features for each holdout week use only earlier observed weeks. No random
    split, no feature selection on holdout, and no automatic deployment.
    """
    from sklearn.ensemble import RandomForestRegressor
    df = validate_weekly(frame)
    if not isinstance(holdout, int) or not 4 <= holdout <= len(df) - 39 or not isinstance(horizon, int) or not 1 <= horizon <= 13:
        raise ValueError('Holdout o orizzonte incompatibile con lo storico.')
    values = df.requests.to_numpy(dtype=float)
    x = np.asarray([features(values[:i], df.week.iloc[i]) for i in range(13, len(df))])
    y = values[13:]
    cut = len(y) - holdout
    def fitted(xtrain, ytrain):
        # A zero-only training cohort has no informative count model.
        if ytrain.sum() == 0:
            raise ValueError('Storico di training privo di richieste: modello non stimabile.')
        model = RandomForestRegressor(n_estimators=100, max_depth=5, min_samples_leaf=4, random_state=0, n_jobs=1)
        model.fit(xtrain, ytrain)
        return model
    model = fitted(x[:cut], y[:cut])
    prediction = model.predict(x[cut:])
    baseline = values[-holdout-1:-1]
    actual = y[cut:]
    def metrics(pred):
        error = np.abs(pred - actual)
        return {'mae': float(error.mean()), 'wape': float(error.sum() / actual.sum()) if actual.sum() else None}
    model_metrics, baseline_metrics = metrics(prediction), metrics(baseline)
    refit = fitted(x, y)
    history = list(values)
    future = []
    for step in range(1, horizon + 1):
        date = df.week.iloc[-1] + pd.Timedelta(weeks=step)
        value = float(refit.predict(np.asarray([features(history, date)]))[0])
        if not np.isfinite(value):
            raise ValueError('Previsione non finita.')
        future.append({'week': date, 'predicted_requests': value})
        history.append(value)
    result = {
        'training_weeks': cut, 'holdout_weeks': holdout,
        'estimator': 'RandomForestRegressor, fixed parameters; no holdout tuning',
        'training_end': str(df.week.iloc[-holdout-1].date()),
        'holdout_start': str(df.week.iloc[-holdout].date()),
        'model': model_metrics, 'last_week_baseline': baseline_metrics,
        'better_than_baseline_mae': model_metrics['mae'] < baseline_metrics['mae'],
        'evaluation': 'one-step, observed earlier weeks; frozen training model',
        'future': 'recursive, refitted on all observed weeks; no calibrated prediction intervals',
    }
    return result, pd.DataFrame({'week': df.week.iloc[-holdout:].to_numpy(), 'actual': actual, 'prediction': prediction, 'baseline': baseline}), pd.DataFrame(future)
