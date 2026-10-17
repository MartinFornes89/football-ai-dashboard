"""Score archived pre-match predictions against completed match results."""

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path('data')


def parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def calibration_bins(samples, bin_count=10):
    bins = defaultdict(list)
    for probability, observed in samples:
        index = min(int(probability * bin_count), bin_count - 1)
        bins[index].append((probability, observed))

    return [
        {
            'range': f'{index * 100 / bin_count:.0f}-{(index + 1) * 100 / bin_count:.0f}%',
            'count': len(values),
            'mean_predicted': round(sum(p for p, _ in values) / len(values) * 100, 1),
            'observed_rate': round(sum(actual for _, actual in values) / len(values) * 100, 1),
        }
        for index, values in sorted(bins.items())
    ]


def evaluate_predictions(prediction_history, results):
    """Return proper scoring metrics and reliability bins for eligible forecasts."""
    results_by_id = {
        str(result.get('id')): result
        for result in results
        if result.get('id') is not None
        and result.get('home_goals') is not None
        and result.get('away_goals') is not None
    }
    latest_forecasts = {}

    for forecast in prediction_history:
        match_id = forecast.get('match_id')
        result = results_by_id.get(str(match_id))
        if result is None:
            continue

        kickoff = parse_datetime(result.get('date'))
        generated_at = parse_datetime(forecast.get('generated_at'))
        if kickoff is None or generated_at is None or generated_at >= kickoff:
            continue

        previous = latest_forecasts.get(str(match_id))
        if previous is None or generated_at > previous[0]:
            latest_forecasts[str(match_id)] = (generated_at, forecast, result)

    one_x_two_brier = 0.0
    one_x_two_log_loss = 0.0
    one_x_two_count = 0
    totals_brier = 0.0
    totals_log_loss = 0.0
    totals_count = 0
    calibration_samples = defaultdict(list)
    epsilon = 1e-15

    for _, forecast, result in latest_forecasts.values():
        home_goals = int(result['home_goals'])
        away_goals = int(result['away_goals'])
        actual_outcome = 0 if home_goals > away_goals else 1 if home_goals == away_goals else 2
        one_x_two = forecast.get('predictions', {}).get('1X2', {})
        probabilities = [float(one_x_two.get(key, 0)) / 100 for key in ('1', 'X', '2')]
        probability_sum = sum(probabilities)
        if probability_sum <= 0:
            continue
        probabilities = [probability / probability_sum for probability in probabilities]
        observed = [1 if index == actual_outcome else 0 for index in range(3)]
        one_x_two_brier += sum((p - actual) ** 2 for p, actual in zip(probabilities, observed)) / 3
        one_x_two_log_loss -= math.log(max(probabilities[actual_outcome], epsilon))
        one_x_two_count += 1

        for label, probability, actual in zip(('Home win', 'Draw', 'Away win'), probabilities, observed):
            calibration_samples[label].append((probability, actual))

        totals = forecast.get('predictions', {}).get('totals', {})
        over_probability = float(totals.get('over2_5', 0)) / 100
        under_probability = float(totals.get('under2_5', 0)) / 100
        totals_sum = over_probability + under_probability
        if totals_sum > 0:
            over_probability /= totals_sum
            under_probability /= totals_sum
            actual_over = 1 if home_goals + away_goals > 2 else 0
            totals_brier += (over_probability - actual_over) ** 2
            totals_log_loss -= math.log(max(over_probability if actual_over else under_probability, epsilon))
            totals_count += 1
            calibration_samples['Over 2.5'].append((over_probability, actual_over))
            calibration_samples['Under 2.5'].append((under_probability, 1 - actual_over))

    return {
        'eligible_matches': one_x_two_count,
        '1x2_brier_score': round(one_x_two_brier / one_x_two_count, 4) if one_x_two_count else None,
        '1x2_log_loss': round(one_x_two_log_loss / one_x_two_count, 4) if one_x_two_count else None,
        'totals_matches': totals_count,
        'totals_2_5_brier_score': round(totals_brier / totals_count, 4) if totals_count else None,
        'totals_2_5_log_loss': round(totals_log_loss / totals_count, 4) if totals_count else None,
        'reliability_bins': {
            label: calibration_bins(samples)
            for label, samples in calibration_samples.items()
        },
    }


def main():
    history_path = DATA_DIR / 'prediction_history.json'
    results_path = DATA_DIR / 'results.json'
    if not history_path.exists() or not results_path.exists():
        print('Evaluation data is missing. Run data_fetcher.py and predictor.py first.')
        return

    with history_path.open(encoding='utf-8') as f:
        prediction_history = json.load(f)
    with results_path.open(encoding='utf-8') as f:
        results = json.load(f)

    report = evaluate_predictions(prediction_history, results)
    print(json.dumps(report, indent=2))
    if report['eligible_matches'] == 0:
        print('No completed matches have a saved forecast made before kickoff yet.')


if __name__ == '__main__':
    main()
