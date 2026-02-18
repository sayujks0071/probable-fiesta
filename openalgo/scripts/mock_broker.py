import sys
from flask import Flask, jsonify

app = Flask(__name__)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5000

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "up"}), 200

@app.route('/api/v1/positions', methods=['GET'])
def positions():
    if PORT == 5001:
        # Kite: Matches StrategyA and StrategyB
        data = [
            {"symbol": "TestStrategyA", "quantity": 50, "average_price": 100.0},
            {"symbol": "TestStrategyB", "quantity": -20, "average_price": 200.0}
        ]
    elif PORT == 5002:
        # Dhan: Returns RiskyStrategy but with mismatch (900 vs 1000)
        data = [
            {"symbol": "RiskyStrategy", "quantity": 900, "average_price": 500.0}
        ]
    else:
        data = []

    return jsonify({"status": "success", "data": data})

if __name__ == "__main__":
    print(f"Starting mock broker on port {PORT}")
    app.run(port=PORT)
