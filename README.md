# ⚽ Football AI Betting Dashboard

**AI-powered football betting analytics** with xG, PPDA, injuries, odds analysis and value bet detection for **Premier League, La Liga, Serie A, Bundesliga**.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🚀 Features

- **📊 Live Match Data** - Upcoming fixtures from football-data.org API
- **🎯 xG & PPDA Analytics** - Expected Goals and pressing metrics from Understat
- **🏥 Injury Reports** - Real-time injury updates from Transfermarkt
- **💰 Live Odds** - 1X2, Over/Under from The Odds API
- **🤖 AI Predictions** - Bivariate Poisson model with injury/form adjustments
- **💎 Value Bet Detection** - Automated edge calculation vs bookmaker odds
- **🔍 Advanced Filters** - Filter by league, date range, value %
- **📈 Daily Auto-Updates** - Scheduled data refresh

---

## 📦 Installation

### 1. Clone Repository
```bash
git clone https://github.com/er9pro/football-ai-dashboard.git
cd football-ai-dashboard
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Set API Keys

Copy `.env.example` to `.env` in the project root and replace the placeholders with your API keys:
```env
FOOTBALL_DATA_KEY=your_football_data_api_key
ODDS_API_KEY=your_odds_api_key
```

**Get Free API Keys:**
- [football-data.org](https://www.football-data.org/) - 10 calls/min free
- [the-odds-api.com](https://the-odds-api.com/) - 500 requests/month free

---

## 🏃 Usage

### Fetch Data
```bash
python data_fetcher.py
```
This creates `data/` folder with:
- `fixtures.json` - Upcoming matches
- `xg_stats.json` - Team stats (xG, PPDA, form)
- `odds.json` - Live betting odds
- `injuries.json` - Injury reports

### Generate Predictions
```bash
python predictor.py
```
Creates `data/predictions.json` with:
- Match outcome probabilities (1X2)
- Over/Under predictions
- Value bet recommendations for 1X2 and Over/Under 2.5
- Confidence scores
- Pre-match forecast snapshots in `data/prediction_history.json`

### Evaluate Past Predictions
```bash
python evaluate_model.py
```
This compares saved pre-match forecasts with completed scores cached by `data_fetcher.py` and reports Brier scores, log loss, and reliability bins. Evaluation is only meaningful after forecasts and results have accumulated; it reports calibration quality but does not automatically alter the model.

### Run Dashboard
```bash
python app.py
```
Open http://localhost:5000 in browser

---

## 📊 Dashboard Preview

**Main View:**
- Match cards with predictions
- Probability bars for 1X2
- Over/Under meters
- Value bet highlighting

**Filters:**
- League selector (EPL/La Liga/Serie A/Bundesliga)
- Date range picker
- Value % threshold
- Minimum confidence

**Match Details:**
- xG Attack vs xGA Defense heatmap
- PPDA pressing metrics
- Injury impact analysis
- Odds movement tracker

---

## 🤖 AI Model Details

### Prediction Algorithm

1. **Base Model**: Bivariate Poisson Distribution
   - Uses team xG averages (last 5 matches)
   - Adjusts for home/away performance
   - Calculates all score probabilities 0-6 goals

2. **Adjustments**:
   - **PPDA Factor**: High press (< 9) → +5% attack boost
   - **Form Bonus**: Recent points → ±10% strength
   - **Injury Penalty**: Key players out → -15% attack
   - **Odds Calibration**: Aligns with market implied probability

3. **Value Bet Logic**:
   ```
   Value % = (Model Prob / Implied Prob - 1) × 100
   Bet Recommendation = Value > 5% AND Confidence > 65%
   ```

### Confidence Score
- 90%+: Historical accuracy >75% (based on xG model research)
- 70-89%: Good data quality, recent stats available
- <70%: Missing data (injuries unknown, odds stale)

---

## 🔄 Automated Updates

### Cron Setup (Linux/Mac)
```bash
crontab -e
```
Add:
```cron
# Daily at 8 AM
0 8 * * * cd /path/to/dashboard && python data_fetcher.py && python predictor.py
```

### Windows Task Scheduler
```powershell
schtasks /create /tn "FootballDashboard" /tr "python C:\path\data_fetcher.py" /sc daily /st 08:00
```

---

## 📁 Project Structure

```
football-ai-dashboard/
├── data/                    # Generated data files
│   ├── fixtures.json
│   ├── xg_stats.json
│   ├── odds.json
│   ├── injuries.json
│   ├── predictions.json
│   ├── prediction_history.json
│   └── results.json
├── data_fetcher.py          # Data scraping/API calls
├── predictor.py             # AI prediction model
├── evaluate_model.py        # Forecast calibration/evaluation report
├── app.py                   # Flask API server
├── dashboard.html           # Frontend UI
├── requirements.txt
└── README.md
```

---

## ⚠️ Disclaimer

This tool is for **educational and entertainment purposes only**. Sports betting involves risk:

- ⚠️ **No Guarantees**: Past performance ≠ future results
- 💸 **Bet Responsibly**: Only bet what you can afford to lose
- 📜 **Legal Compliance**: Check local gambling laws
- 🔞 **Age Restriction**: 18+ only

The model's accuracy depends on data quality and cannot account for:
- Last-minute lineup changes
- Referee bias
- Weather conditions
- Match-fixing

---

## 🛠️ Advanced Usage

### Custom Leagues
Edit `LEAGUES` dict in `data_fetcher.py`:
```python
LEAGUES['Ligue 1'] = {
    'fd_code': 'FL1',
    'understat': 'Ligue_1',
    'odds_key': 'soccer_france_ligue_one',
    'flag': '🇫🇷'
}
```

### Adjust Model Weights
In `predictor.py`, modify:
```python
PPDA_BOOST = 0.05        # Default: 5% for high press
INJURY_PENALTY = 0.15    # Default: 15% attack reduction
VALUE_THRESHOLD = 0.05   # Default: 5% edge required
```

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- [ ] Referee statistics API integration
- [ ] Weather data (wind, rain impact)
- [ ] ML model (XGBoost/LSTM) instead of Poisson
- [ ] Telegram bot notifications
- [ ] Multi-language support

---

## 📄 License

MIT License - see [LICENSE](LICENSE)

---

## 📚 Resources

- [Expected Goals Guide](https://understat.com/)
- [PPDA Explanation](https://statsbomb.com/articles/)
- [Poisson Betting Model](https://pinnacle.com/en/betting-articles/Soccer/how-to-calculate-poisson-distribution)
- [Value Betting Strategy](https://www.oddschecker.com/betting-guides/value-betting)

---

**Star ⭐ this repo if you found it useful!**
