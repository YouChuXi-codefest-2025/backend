from flask import Flask, jsonify
from db import SessionLocal
from routes.districts import bp as districts_bp
from routes.cooling_sites import bp as cooling_sites_bp
from routes.heat import bp as heat_forecast_bp

def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return {"ok": True}

    app.register_blueprint(districts_bp)
    app.register_blueprint(cooling_sites_bp)
    app.register_blueprint(heat_forecast_bp)

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify(error=str(getattr(e, "description", e))), 400

    @app.errorhandler(500)
    def internal_error(_e):
        return jsonify(error="internal server error"), 500

    @app.teardown_appcontext
    def remove_session(_exc):
        try:
            SessionLocal.remove()
        except Exception:
            pass

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
