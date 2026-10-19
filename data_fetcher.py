import requests
import json
import os
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import time

# ── CONFIG ────────────────────────────────────────────────────
load_dotenv()
FOOTBALL_DATA_API_KEY = os.getenv('FOOTBALL_DATA_KEY', 'YOUR_KEY_HERE')
ODDS_API_KEY          = os.getenv('ODDS_API_KEY', 'YOUR_KEY_HERE')
DATA_DIR = 'data'
os.makedirs(DATA_DIR, exist_ok=True)

LEAGUES = {
    'Premier League': {
        'fd_code': 'PL',
        'understat': 'EPL',
        'odds_key': 'soccer_epl',
        'flag': '\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F'
    },
    'La Liga': {
        'fd_code': 'PD',
        'understat': 'La_liga',
        'odds_key': 'soccer_spain_la_liga',
        'flag': '\U0001F1EA\U0001F1F8'
    },
    'Serie A': {
        'fd_code': 'SA',
        'understat': 'Serie_A',
        'odds_key': 'soccer_italy_serie_a',
        'flag': '\U0001F1EE\U0001F1F9'
    },
    'Bundesliga': {
        'fd_code': 'BL1',
        'understat': 'Bundesliga',
        'odds_key': 'soccer_germany_bundesliga',
        'flag': '\U0001F1E9\U0001F1EA'
    },
    'Champions League': {
        'fd_code': 'CL',
        'odds_key': 'soccer_uefa_champs_league',
        'flag': '\U0001F3C6'
    },
}

# ── 1. FIXTURES (football-data.org) ──────────────────────────
def fetch_fixtures():
    headers = {'X-Auth-Token': FOOTBALL_DATA_API_KEY}
    all_fixtures = []
    successful_leagues = set()
    date_from = datetime.now().strftime('%Y-%m-%d')
    date_to   = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

    for league_name, cfg in LEAGUES.items():
        url = (
            f"https://api.football-data.org/v4/competitions/"
            f"{cfg['fd_code']}/matches"
            f"?dateFrom={date_from}&dateTo={date_to}&status=SCHEDULED"
        )
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            successful_leagues.add(league_name)
            matches = r.json().get('matches', [])
            for m in matches:
                all_fixtures.append({
                    'id':       m['id'],
                    'league':   league_name,
                    'flag':     cfg['flag'],
                    'date':     m['utcDate'][:10],
                    'time':     m['utcDate'][11:16],
                    'home':     m['homeTeam']['name'],
                    'away':     m['awayTeam']['name'],
                    'matchday': m.get('matchday'),
                    'venue':    m.get('venue', ''),
                    'status':   m['status'],
                })
            time.sleep(1)
        except Exception as e:
            print(f'[Fixtures] {league_name}: {e}')

    fixtures_file = f'{DATA_DIR}/fixtures.json'
    if not successful_leagues:
        print('[Fixtures] No leagues refreshed; preserving cached fixtures')
        return None

    if os.path.exists(fixtures_file):
        with open(fixtures_file, 'r', encoding='utf-8') as f:
            cached_fixtures = json.load(f)
        all_fixtures.extend(
            fixture for fixture in cached_fixtures
            if fixture.get('league') not in successful_leagues
        )

    with open(fixtures_file, 'w', encoding='utf-8') as f:
        json.dump(all_fixtures, f, indent=2, ensure_ascii=False)
    print(f'[Fixtures] Loaded {len(all_fixtures)} matches')
    return all_fixtures

# ── COMPLETED MATCHES (football-data.org) ────────────────────
def fetch_results(days_back=30):
    """Fetch recent final scores for evaluating archived predictions."""
    headers = {'X-Auth-Token': FOOTBALL_DATA_API_KEY}
    date_to = datetime.now()
    date_from = date_to - timedelta(days=days_back)
    results_file = f'{DATA_DIR}/results.json'
    results_by_id = {}

    if os.path.exists(results_file):
        with open(results_file, 'r', encoding='utf-8') as f:
            results_by_id = {str(item['id']): item for item in json.load(f)}

    for league_name, cfg in LEAGUES.items():
        url = f"https://api.football-data.org/v4/competitions/{cfg['fd_code']}/matches"
        try:
            response = requests.get(
                url,
                headers=headers,
                params={
                    'dateFrom': date_from.strftime('%Y-%m-%d'),
                    'dateTo': date_to.strftime('%Y-%m-%d'),
                    'status': 'FINISHED',
                },
                timeout=10,
            )
            response.raise_for_status()
            for match in response.json().get('matches', []):
                score = (match.get('score') or {}).get('fullTime') or {}
                home_goals = score.get('home')
                away_goals = score.get('away')
                if home_goals is None or away_goals is None:
                    continue
                results_by_id[str(match['id'])] = {
                    'id': match['id'],
                    'league': league_name,
                    'date': match.get('utcDate', ''),
                    'home': match['homeTeam']['name'],
                    'away': match['awayTeam']['name'],
                    'home_goals': home_goals,
                    'away_goals': away_goals,
                }
            time.sleep(1)
        except Exception as e:
            print(f'[Results] {league_name}: {e}')

    results = sorted(results_by_id.values(), key=lambda item: item.get('date', ''))
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f'[Results] Cached {len(results)} completed matches')
    return results

# ── 2. xG STATS (understat.com scraping) ────────────────────
def fetch_xg_stats():
    stats = {}
    now = datetime.now()
    season = str(now.year if now.month >= 7 else now.year - 1)
    UNDERSTAT_LEAGUES = {
        'Premier League': 'EPL',
        'La Liga': 'La_liga',
        'Serie A': 'Serie_A',
        'Bundesliga': 'Bundesliga',
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36'
    }
    session = requests.Session()
    for league_name, slug in UNDERSTAT_LEAGUES.items():
        page_url = f'https://understat.com/league/{slug}/{season}'
        data_url = f'https://understat.com/getLeagueData/{slug}/{season}'
        try:
            page = session.get(page_url, headers=headers, timeout=15)
            page.raise_for_status()
            data_headers = {
                **headers,
                'Referer': page_url,
                'X-Requested-With': 'XMLHttpRequest',
            }
            response = session.get(data_url, headers=data_headers, timeout=15)
            response.raise_for_status()
            teams = response.json().get('teams', {})
            if not teams:
                raise ValueError('Understat returned no team records')

            for tdata in teams.values():
                name = tdata['title']
                history = tdata.get('history', [])
                recent = history[-5:]
                if not recent:
                    continue
                xg_avg = sum(float(g.get('xG', 0)) for g in recent) / len(recent)
                xga_avg = sum(float(g.get('xGA', 0)) for g in recent) / len(recent)
                ppda_att = sum(float(g.get('ppda', {}).get('att', 0)) for g in recent)
                ppda_def = sum(float(g.get('ppda', {}).get('def', 1)) for g in recent)
                ppda = ppda_att / max(ppda_def, 1)
                form = sum(
                    3 if g.get('result') == 'w' else (1 if g.get('result') == 'd' else 0)
                    for g in history[-5:]
                )
                stats[name] = {
                    'league': league_name,
                    'xG_avg': round(xg_avg, 2),
                    'xGA_avg': round(xga_avg, 2),
                    'ppda': round(ppda, 2),
                    'form_pts': form,
                    'goals_scored_5': sum(int(g.get('scored', 0)) for g in history[-5:]),
                    'goals_conceded_5': sum(int(g.get('missed', 0)) for g in history[-5:]),
                    'season': season,
                }
            time.sleep(2)
        except Exception as e:
            print(f'[xG] {league_name}: {e}')

    if not stats:
        print('[xG] No team stats retrieved; preserving any existing xG file')
        return stats

    with open(f'{DATA_DIR}/xg_stats.json', 'w', encoding='utf-8') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f'[xG] Loaded stats for {len(stats)} teams')
    return stats

# ── 3. ODDS (the-odds-api.com) ────────────────────────────────
def fetch_odds():
    odds_data = {}
    for league_name, cfg in LEAGUES.items():
        odds_key = cfg.get('odds_key')
        if not odds_key:
            print(f'[Odds] Skipping {league_name}: sport key unavailable for this API')
            continue
        url = f"https://api.the-odds-api.com/v4/sports/{cfg['odds_key']}/odds/"
        try:
            r = requests.get(
                url,
                params={
                    'apiKey': ODDS_API_KEY,
                    'regions': 'eu',
                    'markets': 'h2h,totals,spreads',
                    'oddsFormat': 'decimal',
                    'dateFormat': 'iso',
                },
                timeout=10,
            )
            r.raise_for_status()
            for ev in r.json():
                key = f"{ev['home_team']} vs {ev['away_team']}"
                h2h, totals, spreads, btts = {}, [], [], {}
                for bm in ev.get('bookmakers', []):
                    for mkt in bm.get('markets', []):
                        market_key = mkt['key']
                        if market_key == 'h2h':
                            for o in mkt['outcomes']:
                                name = o['name']
                                h2h[name] = max(h2h.get(name, 0), o['price'])
                        elif market_key == 'totals':
                            for o in mkt['outcomes']:
                                point = float(o.get('point', 2.5))
                                name = o['name']
                                existing = next((
                                    item for item in totals
                                    if item['name'] == name and abs(item['point'] - point) < 0.01
                                ), None)
                                if existing is None:
                                    totals.append({'name': name, 'point': point, 'price': o['price']})
                                elif o['price'] > existing['price']:
                                    existing['price'] = o['price']
                        elif market_key == 'spreads':
                            for o in mkt['outcomes']:
                                name = o['name']
                                handicap = float(o.get('point', 0))
                                existing = next((
                                    item for item in spreads
                                    if item['name'] == name and abs(item['handicap'] - handicap) < 0.01
                                ), None)
                                if existing is None:
                                    spreads.append({'name': name, 'handicap': handicap, 'price': o['price']})
                                elif o['price'] > existing['price']:
                                    existing['price'] = o['price']
                        elif market_key == 'btts':
                            for o in mkt['outcomes']:
                                btts[o['name']] = o['price']
                odds_data[key] = {
                    'home': ev['home_team'], 'away': ev['away_team'],
                    'date': ev['commence_time'][:10],
                    'h2h': h2h,
                    'totals': totals,
                    'spreads': spreads,
                    'btts': btts,
                    'league': league_name,
                }
        except Exception as e:
            print(f'[Odds] {league_name}: request failed ({type(e).__name__})')

    with open(f'{DATA_DIR}/odds.json', 'w', encoding='utf-8') as f:
        json.dump(odds_data, f, indent=2, ensure_ascii=False)
    print(f'[Odds] Loaded {len(odds_data)} markets')
    return odds_data

# ── 4. INJURIES (Transfermarkt) ───────────────────────────────
def fetch_injuries():
    injuries = {}
    TEAMS = {
        'Manchester City FC': ('manchester-city', 281),
        'Arsenal FC':         ('fc-arsenal', 11),
        'Liverpool FC':       ('fc-liverpool', 31),
        'Chelsea FC':         ('fc-chelsea', 631),
        'Real Madrid CF':     ('real-madrid', 418),
        'FC Barcelona':       ('fc-barcelona', 131),
        'Atletico de Madrid': ('atletico-madrid', 13),
        'FC Bayern Munich':   ('fc-bayern-munchen', 27),
        'Borussia Dortmund':  ('borussia-dortmund', 16),
        'Juventus FC':        ('juventus-fc', 506),
        'FC Internazionale':  ('inter-mailand', 46),
        'AC Milan':           ('ac-mailand', 5),
    }
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36'
    }
    for team_name, (slug, tid) in TEAMS.items():
        url = f'https://www.transfermarkt.com/{slug}/sperrenundverletzungen/verein/{tid}'
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.content, 'lxml')
            rows = soup.select('table.items tbody tr')
            team_list = []
            for row in rows[:10]:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    player = cols[1].get_text(strip=True) if len(cols) > 1 else ''
                    reason = cols[3].get_text(strip=True) if len(cols) > 3 else ''
                    until  = cols[5].get_text(strip=True) if len(cols) > 5 else '?'
                    if player:
                        team_list.append({'player': player, 'reason': reason, 'until': until})
            injuries[team_name] = team_list
            time.sleep(2)
        except Exception as e:
            print(f'[Injuries] {team_name}: {e}')
            injuries[team_name] = []

    with open(f'{DATA_DIR}/injuries.json', 'w', encoding='utf-8') as f:
        json.dump(injuries, f, indent=2, ensure_ascii=False)
    print(f'[Injuries] Done')
    return injuries

# ── RUN ALL ───────────────────────────────────────────────────
def run_full_fetch():
    print(f"\n{'='*50}")
    print(f"Data update: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")
    fixtures = fetch_fixtures()
    fetch_xg_stats()
    fetch_odds()
    fetch_injuries()
    fetch_results()
    if fixtures is None:
        print('Data update incomplete: fixtures could not be refreshed')
        return False
    print('All data updated successfully')
    return True

if __name__ == '__main__':
    if not run_full_fetch():
        raise SystemExit(1)
