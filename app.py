from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

app = Flask(__name__, static_folder='.')
CORS(app)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / 'data'
refresh_lock = threading.Lock()

@app.route('/')
def index():
    return send_from_directory(APP_DIR, 'dashboard.html')

@app.route('/api/predictions')
def get_predictions():
    try:
        pred_file = DATA_DIR / 'predictions.json'
        if os.path.exists(pred_file):
            with open(pred_file, 'r', encoding='utf-8') as f:
                predictions = json.load(f)
            now = datetime.now(timezone.utc)
            upcoming_predictions = []
            for prediction in predictions:
                try:
                    kickoff = datetime.fromisoformat(
                        f"{prediction['date']}T{prediction['time']}:00+00:00"
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                if kickoff > now:
                    upcoming_predictions.append(prediction)
            return jsonify({
                'success': True,
                'data': upcoming_predictions,
                'updated': datetime.fromtimestamp(os.path.getmtime(pred_file)).isoformat(),
                'count': len(upcoming_predictions)
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No predictions available. Add API keys to .env, then run data_fetcher.py and predictor.py.'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/refresh', methods=['POST'])
def refresh_data():
    """Fetch current data and regenerate predictions from the updated files."""
    if not refresh_lock.acquire(blocking=False):
        return jsonify({'success': False, 'error': 'A data refresh is already running.'}), 409

    try:
        for script in ('data_fetcher.py', 'predictor.py'):
            subprocess.run(
                [sys.executable, str(APP_DIR / script)],
                cwd=APP_DIR,
                capture_output=True,
                text=True,
                timeout=180,
                check=True,
            )
        return jsonify({'success': True, 'message': 'Fixtures and predictions updated.'})
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Data refresh timed out. Please try again.'}), 504
    except subprocess.CalledProcessError as e:
        details = (e.stderr or e.stdout or '').strip()
        return jsonify({
            'success': False,
            'error': f'Data refresh failed: {details[-1000:] or "see server output"}',
        }), 500
    finally:
        refresh_lock.release()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
