
"""SoraLink Flask application entry point."""

from __future__ import annotations

from functools import wraps

from flask import Flask, jsonify, request
from flask_socketio import SocketIO, emit, join_room

import auth as auth_service
import broadcast_service
import requests_service
from config import get_config
from database import init_db


socketio = SocketIO()


def success(data=None, status=200):
    return jsonify({"ok": True, "data": data or {}}), status


def failure(message, status=400, code="BAD_REQUEST"):
    return jsonify({
        "ok": False,
        "error": {"code": code, "message": message},
    }), status


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        cors_allowed_origins=None,
    )

    # Create tables and indexes if they do not already exist.
    init_db()

    @app.get("/api/health")
    def health():
        return success({"service": "SoraLink", "status": "ok"})

    def _apply_session_cookie(response, token):
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "soralink_session")
        ttl = app.config.get("SESSION_TTL_SECONDS", 8 * 3600)
        secure = app.config.get("SESSION_COOKIE_SECURE", False) or request.is_secure
        response.set_cookie(
            key=cookie_name,
            value=token,
            max_age=ttl,
            httponly=True,
            samesite="Lax",
            secure=secure,
            path="/",
        )
        return response

    def _clear_session_cookie(response):
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "soralink_session")
        secure = app.config.get("SESSION_COOKIE_SECURE", False) or request.is_secure
        response.delete_cookie(
            key=cookie_name,
            path="/",
            httponly=True,
            samesite="Lax",
            secure=secure,
        )
        return response

    def current_session():
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "soralink_session")
        token = request.cookies.get(cookie_name)
        if not token:
            token = request.cookies.get("soralink_session") or request.cookies.get("session_token")
        if not token:
            raise auth_service.AuthenticationError("Missing session cookie")

        session = auth_service.get_session_by_token(token)
        if session is None:
            raise auth_service.AuthenticationError("Missing, invalid, expired, or revoked session")
        return session

    def authenticated(role=None):
        """Protect a route using the server-resolved session."""
        def decorator(function):
            @wraps(function)
            def wrapper(*args, **kwargs):
                try:
                    session = current_session()
                    if role:
                        auth_service.require_role(session, role)
                    return function(session, *args, **kwargs)
                except auth_service.AuthenticationError as exc:
                    return failure(str(exc), 401, "UNAUTHENTICATED")
                except auth_service.AuthorizationError as exc:
                    return failure(str(exc), 403, "FORBIDDEN")
            return wrapper
        return decorator

    @app.post("/api/auth/passenger")
    def passenger_login():
        if not request.is_json:
            return failure("Request body must be JSON", 400, "BAD_REQUEST")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return failure("Request body must be a JSON object", 400, "BAD_REQUEST")

        seat_label = body.get("seat_label")
        demo_code = body.get("demo_code") or body.get("invite_code")

        if not seat_label or not demo_code or not isinstance(seat_label, str) or not isinstance(demo_code, str):
            return failure("seat_label and demo_code are required strings", 400, "BAD_REQUEST")

        try:
            result = auth_service.authenticate_passenger(seat_label, demo_code)
            resp, status = success({
                "role": "passenger",
                "seat_label": result["session"]["seat_label"],
                "session_id": result["session"]["id"],
            }, 200)
            return _apply_session_cookie(resp, result["token"]), status
        except auth_service.AuthenticationError as exc:
            return failure(str(exc), 401, "INVALID_CREDENTIALS")

    @app.post("/api/auth/crew")
    def crew_login():
        if not request.is_json:
            return failure("Request body must be JSON", 400, "BAD_REQUEST")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return failure("Request body must be a JSON object", 400, "BAD_REQUEST")

        username = body.get("username")
        password = body.get("password") or body.get("crew_code") or body.get("crew_pin")

        if not password or (username is None and not body.get("crew_code") and not body.get("crew_pin")):
            return failure("username and password are required", 400, "BAD_REQUEST")

        if not username:
            username = "crew_demo"

        if not isinstance(username, str) or not isinstance(password, str):
            return failure("username and password must be strings", 400, "BAD_REQUEST")

        try:
            result = auth_service.authenticate_crew(username, password)
            resp, status = success({
                "role": "crew",
                "crew_id": result["session"]["id"],
                "session_id": result["session"]["id"],
            }, 200)
            return _apply_session_cookie(resp, result["token"]), status
        except auth_service.AuthenticationError as exc:
            return failure(str(exc), 401, "INVALID_CREDENTIALS")

    @app.get("/api/auth/me")
    @authenticated()
    def who_am_i(session):
        data = {
            "role": session["role"],
            "session_id": session["id"],
            "session": {
                "id": session["id"],
                "role": session["role"],
                "seat_label": session.get("seat_label"),
                "created_at_ms": session.get("created_at_ms"),
                "expires_at_ms": session.get("expires_at_ms"),
            },
        }
        if session["role"] == "passenger":
            data["seat_label"] = session.get("seat_label")
        elif session["role"] == "crew":
            data["crew_id"] = session["id"]

        return success(data)

    @app.post("/api/auth/logout")
    @authenticated()
    def logout(session):
        auth_service.revoke_session(session["id"])
        resp, status = success({"logged_out": True}, 200)
        return _clear_session_cookie(resp), status

    @app.get("/api/passenger/state")
    @authenticated("passenger")
    def passenger_state(session):
        return success({
            "session": session,
            "requests": requests_service.list_passenger_requests(session),
            "active_broadcasts": broadcast_service.list_active_broadcasts(),
        })

    @app.post("/api/requests")
    @authenticated("passenger")
    def create_request(session):
        body = request.get_json(silent=True) or {}
        intent_id = body.get("intent_id")

        try:
            created = requests_service.create_request(session, intent_id)
        except requests_service.InvalidIntentError as exc:
            return failure(str(exc), 400, "INVALID_INTENT")
        except requests_service.DuplicateActiveRequestError as exc:
            return failure(str(exc), 409, "DUPLICATE_ACTIVE_REQUEST")
        except PermissionError as exc:
            return failure(str(exc), 403, "FORBIDDEN")

        # The service returns only after the database transaction commits.
        socketio.emit("request_created", created, to="crew:dashboard")
        socketio.emit(
            "request_updated",
            created,
            to=f"passenger:{session['id']}",
        )
        return success({"request": created}, 201)

    @app.get("/api/crew/requests")
    @authenticated("crew")
    def crew_requests(session):
        include_completed = (
            request.args.get("include_completed", "").lower()
            in {"1", "true", "yes"}
        )
        items = requests_service.list_crew_requests(
            session, include_completed=include_completed
        )
        return success({"requests": items})

    @app.post("/api/crew/requests/<request_id>/acknowledge")
    @authenticated("crew")
    def acknowledge_request(session, request_id):
        try:
            item = requests_service.acknowledge_request(session, request_id)
        except requests_service.RequestNotFoundError as exc:
            return failure(str(exc), 404, "NOT_FOUND")
        except requests_service.InvalidTransitionError as exc:
            return failure(str(exc), 409, "INVALID_TRANSITION")
        except PermissionError as exc:
            return failure(str(exc), 403, "FORBIDDEN")

        socketio.emit("request_updated", item, to="crew:dashboard")
        socketio.emit(
            "request_updated",
            item,
            to=f"passenger:{item['session_id']}",
        )
        return success({"request": item})

    @app.post("/api/crew/requests/<request_id>/complete")
    @authenticated("crew")
    def complete_request(session, request_id):
        try:
            item = requests_service.complete_request(session, request_id)
        except requests_service.RequestNotFoundError as exc:
            return failure(str(exc), 404, "NOT_FOUND")
        except requests_service.InvalidTransitionError as exc:
            return failure(str(exc), 409, "INVALID_TRANSITION")
        except PermissionError as exc:
            return failure(str(exc), 403, "FORBIDDEN")

        socketio.emit("request_updated", item, to="crew:dashboard")
        socketio.emit(
            "request_updated",
            item,
            to=f"passenger:{item['session_id']}",
        )
        return success({"request": item})

    @app.post("/api/crew/requests/<request_id>/follow_up")
    @authenticated("passenger")
    def follow_up(session, request_id):
        body = request.get_json(silent=True) or {}
        try:
            item = requests_service.request_follow_up(
                session, request_id, body.get("message", "")
            )
        except requests_service.RequestNotFoundError as exc:
            return failure(str(exc), 404, "NOT_FOUND")
        except requests_service.InvalidTransitionError as exc:
            return failure(str(exc), 409, "INVALID_TRANSITION")
        except (ValueError, PermissionError) as exc:
            return failure(str(exc), 400, "INVALID_FOLLOW_UP")

        socketio.emit("follow_up_requested", {
            "request_id": request_id,
            "session_id": session["id"],
        }, to="crew:dashboard")
        return success({"request": item})

    @app.get("/api/crew/pa/cards")
    @authenticated("crew")
    def pa_cards():
        # Reviewed, fixed cards are loaded from the repository data directory.
        from pathlib import Path
        import json

        cards_path = Path(app.root_path) / "data" / "pa_cards.json"
        try:
            cards = json.loads(cards_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return failure("PA card data is unavailable", 500, "CONTENT_ERROR")
        return success({"cards": cards})

    @app.get("/api/passenger/broadcasts")
    @authenticated("passenger")
    def passenger_broadcasts(session):
        return success({
            "broadcasts": broadcast_service.list_active_broadcasts()
        })

    @app.post("/api/crew/pa/broadcast")
    @authenticated("crew")
    def create_broadcast(session):
        body = request.get_json(silent=True) or {}
        try:
            item = broadcast_service.create_broadcast(
                session,
                title=body.get("title"),
                body=body.get("body"),
                category=body.get("category", "general"),
                ttl_seconds=body.get("ttl_seconds", 120),
            )
        except broadcast_service.BroadcastServiceError as exc:
            return failure(str(exc), 400, "INVALID_BROADCAST")

        socketio.emit("pa_broadcast_created", item, broadcast=True)
        return success({"broadcast": item}, 201)

    @app.post("/api/crew/pa/end")
    @authenticated("crew")
    def end_broadcast(session):
        body = request.get_json(silent=True) or {}
        broadcast_id = body.get("broadcast_id", "")

        try:
            item = broadcast_service.end_broadcast(session, broadcast_id)
        except broadcast_service.BroadcastNotFoundError as exc:
            return failure(str(exc), 404, "NOT_FOUND")
        except broadcast_service.BroadcastServiceError as exc:
            return failure(str(exc), 400, "INVALID_BROADCAST")

        socketio.emit("pa_broadcast_ended", {
            "id": item["id"],
            "ended_at_ms": item["ended_at_ms"],
        }, broadcast=True)
        return success({"broadcast": item})

    @socketio.on("connect")
    def socket_connect(auth_data=None):
        cookie_name = app.config.get("SESSION_COOKIE_NAME", "soralink_session")
        token = request.cookies.get(cookie_name)
        if not token:
            token = request.cookies.get("soralink_session") or request.cookies.get("session_token")

        if not token and isinstance(auth_data, dict):
            token = auth_data.get("token")

        session = auth_service.get_session_by_token(token or "") if token else None
        if session is None:
            return False

        if session["role"] == "crew":
            join_room("crew:dashboard")
        elif session["role"] == "passenger":
            join_room(f"passenger:{session['id']}")

        emit("connection_ready", {
            "session_id": session["id"],
            "role": session["role"],
        })

    @socketio.on("disconnect")
    def socket_disconnect():
        # The server manages room membership; clients cannot choose rooms.
        pass

    @app.errorhandler(404)
    def not_found(_error):
        return failure("Endpoint not found", 404, "NOT_FOUND")

    @app.errorhandler(413)
    def upload_too_large(_error):
        return failure("Request payload is too large", 413, "PAYLOAD_TOO_LARGE")

    @app.errorhandler(500)
    def internal_error(_error):
        app.logger.exception("Unhandled SoraLink application error")
        return failure("Internal server error", 500, "INTERNAL_ERROR")

    return app


app = create_app()


if __name__ == "__main__":
    socketio.run(
        app,
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=app.config["DEBUG"],
        allow_unsafe_werkzeug=app.config["DEBUG"],
    )
