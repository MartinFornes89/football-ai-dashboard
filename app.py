from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import json
import os
from datetime import datetime

app = Flask(__name__, static_folder='.')
CORS(app)

DATA_DIR = 'data'

@app.route('/')
def index():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/predictions')
def get_predictions():
    try:
        pred_file = os.path.join(DATA_DIR, 'predictions.json')
        if os.path.exists(pred_file):
            with open(pred_file, 'r') as f:
                predictions = json.load(f)
            return jsonify({
                'success': True,
                'data': predictions,
                'updated': datetime.fromtimestamp(os.path.getmtime(pred_file)).isoformat(),
                'count': len(predictions)
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
