import threading
from flask import Flask, jsonify, request
import logging

# Disable Flask logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

def run_kite_mock():
    app = Flask("KiteMock")

    @app.before_request
    def log_request():
        print(f"KiteMock received request: {request.path}")

    @app.route('/health')
    def health():
        return "OK", 200

    @app.route('/api/v1/positions')
    def positions():
        return jsonify({
            "status": "success",
            "data": [
                {"symbol": "INFY", "quantity": 50, "average_price": 1500, "product": "MIS"},
            ]
        })

    app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)

def run_dhan_mock():
    app = Flask("DhanMock")

    @app.before_request
    def log_request():
        print(f"DhanMock received request: {request.path}")

    @app.route('/health')
    def health():
        return "OK", 200

    @app.route('/api/v1/positions')
    def positions():
        return jsonify({
            "status": "success",
            "data": [
                {"symbol": "RELIANCE", "quantity": 10, "average_price": 2500, "product": "INTRADAY"},
                {"symbol": "GHOST_POS", "quantity": 100, "average_price": 50, "product": "INTRADAY"}
            ]
        })

    app.run(host='0.0.0.0', port=5002, debug=False, use_reloader=False)

if __name__ == "__main__":
    t1 = threading.Thread(target=run_kite_mock)
    t2 = threading.Thread(target=run_dhan_mock)

    t1.daemon = True
    t2.daemon = True

    t1.start()
    t2.start()

    print("Mock Brokers running on ports 5001 (Kite) and 5002 (Dhan)")

    # Keep main thread alive
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping Mock Brokers")
