"""
Flask Web Portal – application factory.
"""
from __future__ import annotations

import logging

from flask import Flask

import config

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates")
    app.secret_key = config.FLASK_SECRET_KEY

    from portal.routes import bp
    app.register_blueprint(bp)

    return app
