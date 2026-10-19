import json
import os
import math
import sys
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime, timezone

DATA_DIR = 'data'

# ── Constants ─────────────────────────────────────────────────
PPDA_BOOST      = 0.05   # +5% attack if PPDA < 9
INJURY_PENALTY  = 0.15   # -15% attack per key injury
FORM_FACTOR     = 0.10   # ±10% based on form
VALUE_THRESHOLD = 0.05   # min edge to flag value bet
CONF_THRESHOLD  = 0.65   # min confidence

def poisson_prob(lam, k):
    """P(X=k) for Poisson distribution"""
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

def match_probs(lambda_home, lambda_away, max_goals=6):
    """Calculate 1X2 and over/under probs via Bivariate Poisson"""
    p1 = px = p2 = 0.0
    p_over = p_under = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = poisson_prob(lambda_home, i) * poisson_prob(lambda_away, j)
            if i > j:  p1 += p
            elif i == j: px += p
            else:        p2 += p
            if i + j > 2.5:  p_over  += p
            else:             p_under += p
    return p1, px, p2, p_over, p_under

def implied_prob(odds):
    """Convert decimal odds to implied probability"""
    if not odds or odds <= 1:
        return None
    return 1.0 / odds

def find_team_stats(team_name, xg_stats):
    """Fuzzy match team name to xg_stats key"""
    name_lower = team_name.lower()
    # exact
    for key, val in xg_stats.items():
        if key.lower() == name_lower:
            return val
    # partial
    for key, val in xg_stats.items():
        words = name_lower.split()
        if any(w in key.lower() for w in words if len(w) > 3):
            return val
    return None

def find_odds(home, away, odds_data, league=None):
    """Find odds entry for a match"""
    for key, val in odds_data.items():
        if league and val.get('league') != league:
            continue
        kh = val.get('home', '').lower()
        ka = val.get('away', '').lower()
        if home.lower() in kh or kh in home.lower():
            if away.lower() in ka or ka in away.lower():
                return val
    return None

def normalize_team_name(name):
    """Normalize names for conservative matching against bookmaker outcomes."""
    normalized = unicodedata.normalize('NFKD', name.casefold())
    tokens = normalized.split()
    tokens = [token for token in tokens if token not in {'fc', 'cf', 'afc', 'sc', 'ac', 'ssc', 'de'}]
    return ' '.join(''.join(char for char in token if char.isalnum()) for token in tokens)

def find_team_odds(team_name, h2h):
    """Return a team's price only when its name matches an outcome."""
    target = normalize_team_name(team_name)
    target_tokens = target.split()
    for outcome, price in h2h.items():
        candidate = normalize_team_name(outcome)
        candidate_tokens = candidate.split()
        shorter_tokens, longer_tokens = sorted((target_tokens, candidate_tokens), key=len)
        tokens_match = len(shorter_tokens) >= 2 and all(
            any(SequenceMatcher(None, token, other).ratio() >= 0.72 for other in longer_tokens)
            for token in shorter_tokens
        )
        shorter, longer = sorted((target.replace(' ', ''), candidate.replace(' ', '')), key=len)
        single_name_match = len(shorter) >= 8 and shorter in longer
        if target == candidate or tokens_match or single_name_match:
            return price
    return None

def find_total_odds(totals, outcome, point=2.5):
    """Find an Over/Under price for the requested goal line only."""
    for name, market in totals.items():
        if name.casefold() != outcome.casefold():
            continue
        if abs(float(market.get('point', 0)) - point) <= 0.01:
            return market.get('price')
    return None

def get_injury_count(team_name, injuries_data):
    """Count injured players for a team"""
    name_lower = team_name.lower()
    for key, players in injuries_data.items():
        if name_lower in key.lower() or key.lower() in name_lower:
            return len(players)
    return 0

def generate_predictions():
    """Full prediction pipeline using real API data"""
    os.makedirs(DATA_DIR, exist_ok=True)

    # ── Load data ────────────────────────────────────────────
    fixtures_file  = f'{DATA_DIR}/fixtures.json'
    xg_file        = f'{DATA_DIR}/xg_stats.json'
    odds_file      = f'{DATA_DIR}/odds.json'
    injuries_file  = f'{DATA_DIR}/injuries.json'

    # If data files missing, run fetcher first
    if not os.path.exists(fixtures_file) or not os.path.exists(xg_file):
        print('[Predictor] Data files missing, running data_fetcher...')
        try:
            import subprocess
            subprocess.run([sys.executable, 'data_fetcher.py'], timeout=120)
        except Exception as e:
            print(f'[Predictor] Fetcher error: {e}')

    fixtures  = json.load(open(fixtures_file))  if os.path.exists(fixtures_file)  else []
    xg_stats  = json.load(open(xg_file))        if os.path.exists(xg_file)        else {}
    odds_data = json.load(open(odds_file))       if os.path.exists(odds_file)       else {}
    injuries  = json.load(open(injuries_file))   if os.path.exists(injuries_file)   else {}

    print(f'[Predictor] {len(fixtures)} fixtures, {len(xg_stats)} team stats, {len(odds_data)} odds markets')

    predictions = []
    generated_at = datetime.now(timezone.utc).isoformat(timespec='seconds')

    for fix in fixtures:
        home = fix.get('home', '')
        away = fix.get('away', '')
        league = fix.get('league', '')

        # ── Get xG stats ─────────────────────────────────────
        home_stats = find_team_stats(home, xg_stats)
        away_stats = find_team_stats(away, xg_stats)

        # Fallback defaults if no stats found
        h_xg  = home_stats['xG_avg']   if home_stats else 1.3
        h_xga = home_stats['xGA_avg']  if home_stats else 1.3
        h_ppda = home_stats['ppda']    if home_stats else 10.0
        h_form = home_stats['form_pts'] if home_stats else 6

        a_xg  = away_stats['xG_avg']   if away_stats else 1.1
        a_xga = away_stats['xGA_avg']  if away_stats else 1.3
        a_ppda = away_stats['ppda']    if away_stats else 10.0
        a_form = away_stats['form_pts'] if away_stats else 6

        # ── Injuries ─────────────────────────────────────────
        h_injuries = get_injury_count(home, injuries)
        a_injuries = get_injury_count(away, injuries)

        # ── Build lambdas ────────────────────────────────────
        # Base: home attack vs away defence, with home advantage
        lambda_home = ((h_xg + a_xga) / 2) * 1.1  # +10% home advantage
        lambda_away = (a_xg  + h_xga) / 2

        # PPDA adjustment (high press = low PPDA value)
        if h_ppda < 9:  lambda_home *= (1 + PPDA_BOOST)
        if a_ppda < 9:  lambda_away *= (1 + PPDA_BOOST)

        # Form adjustment
        max_pts = 15
        h_form_factor = (h_form - max_pts / 2) / max_pts * FORM_FACTOR
        a_form_factor = (a_form - max_pts / 2) / max_pts * FORM_FACTOR
        lambda_home *= (1 + h_form_factor)
        lambda_away *= (1 + a_form_factor)

        # Injury penalty
        lambda_home *= max(0.5, 1 - h_injuries * INJURY_PENALTY)
        lambda_away *= max(0.5, 1 - a_injuries * INJURY_PENALTY)

        lambda_home = round(max(0.3, lambda_home), 2)
        lambda_away = round(max(0.3, lambda_away), 2)

        # ── Probabilities ────────────────────────────────────
        p1, px, p2, p_over, p_under = match_probs(lambda_home, lambda_away)
        p1    = round(p1 * 100, 1)
        px    = round(px * 100, 1)
        p2    = round(p2 * 100, 1)
        p_over  = round(p_over  * 100, 1)
        p_under = round(p_under * 100, 1)

        # ── Odds lookup ──────────────────────────────────────
        odds_entry = find_odds(home, away, odds_data, league)
        h2h = odds_entry.get('h2h', {}) if odds_entry else {}
        totals_odds = odds_entry.get('totals', {}) if odds_entry else {}

        odds_home = find_team_odds(home, h2h)
        odds_draw = next((price for name, price in h2h.items() if name.casefold() == 'draw'), None)
        odds_away = find_team_odds(away, h2h)

        # ── Confidence score ─────────────────────────────────
        conf = 70
        if home_stats: conf += 8
        if away_stats: conf += 8
        if odds_entry: conf += 7
        if h_injuries > 2 or a_injuries > 2: conf -= 10
        conf = min(95, max(50, conf))

        # ── Value bets ───────────────────────────────────────
        value_bets = []
        checks = [
            ('Home Win', p1 / 100, odds_home),
            ('Draw',     px / 100, odds_draw),
            ('Away Win', p2 / 100, odds_away),
            ('Over 2.5', p_over / 100, find_total_odds(totals_odds, 'Over')),
            ('Under 2.5', p_under / 100, find_total_odds(totals_odds, 'Under')),
        ]
        for bet_type, model_prob, odds_val in checks:
            if not odds_val:
                continue
            imp = implied_prob(odds_val)
            if imp and model_prob > 0:
                edge = (model_prob / imp) - 1
                if edge > VALUE_THRESHOLD and conf / 100 > CONF_THRESHOLD:
                    value_bets.append({
                        'type':    bet_type,
                        'value%':  round(edge * 100, 1),
                        'prob':    round(model_prob * 100, 1),
                        'odds':    odds_val
                    })

        predictions.append({
            'match_id':     fix.get('id'),
            'league':       league,
            'home':         home,
            'away':         away,
            'date':         fix.get('date', ''),
            'time':         fix.get('time', ''),
            'lambda_home':  lambda_home,
            'lambda_away':  lambda_away,
            'predictions': {
                '1X2': {'1': p1, 'X': px, '2': p2},
                'totals': {'over2_5': p_over, 'under2_5': p_under}
            },
            'value_bets':   value_bets,
            'confidence':   conf,
            'injuries':     {'home': h_injuries, 'away': a_injuries},
            'odds':         {'home': odds_home, 'draw': odds_draw, 'away': odds_away}
        })

    # Save
    out = f'{DATA_DIR}/predictions.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, indent=2, ensure_ascii=False)
    print(f'[Predictor] Generated {len(predictions)} predictions -> {out}')

    history_file = f'{DATA_DIR}/prediction_history.json'
    history = []
    if os.path.exists(history_file):
        with open(history_file, 'r', encoding='utf-8') as f:
            history = json.load(f)
    history.extend(
        {**prediction, 'generated_at': generated_at}
        for prediction in predictions
        if prediction.get('match_id') is not None
    )
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f'[Predictor] Archived {len(predictions)} forecasts -> {history_file}')
    return predictions

if __name__ == '__main__':
    # Fetch data only when required inputs are missing.
    generate_predictions()
