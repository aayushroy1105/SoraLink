
"""SoraLink Flask application entry point."""

from __future__ import annotations

from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request
from flask_socketio import SocketIO, emit, join_room

import auth as auth_service
import broadcast_service
import classifier
import database
import requests_service
import voice
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

    # Preload the local intent classifier once at application startup.
    classifier.init_classifier()
    loaded_dir = classifier.get_loaded_model_dir()
    readiness = classifier.get_classifier_readiness()
    label_count = len(getattr(classifier._STATE, "labels", []) or classifier.REQUIRED_INTENT_IDS)
    app.logger.info(
        "Active intent classifier: framework=SetFit path=%s labels=%d readiness=%s",
        loaded_dir,
        label_count,
        readiness,
    )

    @app.get("/api/health")
    def health():
        return success({
            "service": "SoraLink",
            "status": "ok",
            "classifier": {
                "framework": "SetFit",
                "model_dir": classifier.get_loaded_model_dir(),
                "readiness": classifier.get_classifier_readiness(),
                "labels": len(getattr(classifier._STATE, "labels", []) or classifier.REQUIRED_INTENT_IDS),
            },
        })

    @app.get("/")
    def page_root():
        host = request.host or ""
        crew_port = str(app.config.get("CREW_PORT", 5002))
        passenger_port = str(app.config.get("PORT", 5001))
        if host.endswith(f":{crew_port}"):
            return redirect("/crew")
        if host.endswith(f":{passenger_port}"):
            return redirect("/passenger")
        return render_template("login.html")

    @app.get("/login")
    def page_login():
        return render_template("login.html")

    @app.get("/passenger")
    def page_passenger():
        return render_template("passenger.html")

    @app.get("/crew")
    def page_crew():
        return render_template("crew.html")

    # Role-specific cookie names to prevent mutual session overwrite when both
    # passenger and crew portals are open in the same browser.
    _ROLE_COOKIE = {
        "passenger": "soralink_passenger_session",
        "crew": "soralink_crew_session",
    }
    _LEGACY_COOKIE = "soralink_session"

    def _apply_session_cookie(response, token, role=None):
        ttl = app.config.get("SESSION_TTL_SECONDS", 8 * 3600)
        secure = app.config.get("SESSION_COOKIE_SECURE", False) or request.is_secure
        common = dict(max_age=ttl, httponly=True, samesite="Lax", secure=secure, path="/")
        # Set the legacy generic cookie FIRST so that test clients and browsers
        # that read only the first Set-Cookie header see soralink_session=.
        legacy_name = app.config.get("SESSION_COOKIE_NAME", _LEGACY_COOKIE)
        response.set_cookie(key=legacy_name, value=token, **common)
        # Also set role-specific cookie so passenger and crew sessions coexist
        # when both portals are open in the same browser.
        if role in _ROLE_COOKIE:
            response.set_cookie(key=_ROLE_COOKIE[role], value=token, **common)
        return response

    def _clear_session_cookie(response, role=None):
        secure = app.config.get("SESSION_COOKIE_SECURE", False) or request.is_secure
        common = dict(path="/", httponly=True, samesite="Lax", secure=secure)
        # Clear legacy cookie first (so tests find soralink_session= in the header).
        legacy_name = app.config.get("SESSION_COOKIE_NAME", _LEGACY_COOKIE)
        response.delete_cookie(key=legacy_name, **common)
        if role in _ROLE_COOKIE:
            response.delete_cookie(key=_ROLE_COOKIE[role], **common)
        return response

    def current_session(role=None):
        """Resolve the active session from cookies.

        When *role* is supplied (e.g. 'passenger' or 'crew'), the role-specific
        cookie is checked first so that simultaneous passenger and crew sessions
        in the same browser do not interfere with each other.  The legacy
        generic cookie is used as a fallback so that existing test clients that
        only set ``soralink_session`` continue to work unchanged.
        """
        if not role:
            role = request.args.get("role") or request.headers.get("X-SoraLink-Role")
            if role not in ("passenger", "crew"):
                role = None

        token = None
        # 1. Role-specific cookie (highest priority)
        if role and role in _ROLE_COOKIE:
            token = request.cookies.get(_ROLE_COOKIE[role])
        # 2. Infer role from URL path or referrer when no explicit role hint given
        if not token:
            path = request.path
            if path.startswith("/api/passenger") or path.startswith("/api/requests") or path.startswith("/api/voice_request"):
                token = request.cookies.get(_ROLE_COOKIE["passenger"])
            elif path.startswith("/api/crew"):
                token = request.cookies.get(_ROLE_COOKIE["crew"])
            elif request.referrer:
                if "/passenger" in request.referrer:
                    token = request.cookies.get(_ROLE_COOKIE["passenger"])
                elif "/crew" in request.referrer:
                    token = request.cookies.get(_ROLE_COOKIE["crew"])
        # 3. Legacy / generic cookie fallback (keeps existing tests green)
        if not token:
            legacy_name = app.config.get("SESSION_COOKIE_NAME", _LEGACY_COOKIE)
            token = request.cookies.get(legacy_name)
        if not token:
            token = request.cookies.get("soralink_session") or request.cookies.get("session_token")
        # 4. Fallback to surviving role cookie if legacy cookie was cleared by logout of the other role
        if not token and not role:
            token = request.cookies.get(_ROLE_COOKIE.get("passenger", "")) or request.cookies.get(_ROLE_COOKIE.get("crew", ""))
        if not token:
            raise auth_service.AuthenticationError("Missing session cookie")

        session = auth_service.get_session_by_token(token)
        if session is None:
            raise auth_service.AuthenticationError("Missing, invalid, expired, or revoked session")
        return session

    def authenticated(role=None):
        """Protect a route using the server-resolved session.

        Passes the *role* hint to ``current_session()`` so that the
        role-specific cookie is preferred over the legacy generic cookie,
        preventing cross-role session contamination.
        """
        def decorator(function):
            @wraps(function)
            def wrapper(*args, **kwargs):
                try:
                    session = current_session(role)
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
            return _apply_session_cookie(resp, result["token"], role="passenger"), status
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
            return _apply_session_cookie(resp, result["token"], role="crew"), status
        except auth_service.AuthenticationError as exc:
            return failure(str(exc), 401, "INVALID_CREDENTIALS")

    @app.get("/api/auth/me")
    def who_am_i():
        """Return the active session.

        Accepts an optional ``?role=passenger`` or ``?role=crew`` query
        parameter so that both tabs (passenger and crew) can independently
        verify their own session without interfering with each other.
        """
        role_hint = request.args.get("role") or request.headers.get("X-SoraLink-Role") or None
        if not role_hint and request.referrer:
            if "/crew" in request.referrer:
                role_hint = "crew"
            elif "/passenger" in request.referrer:
                role_hint = "passenger"
        if role_hint not in ("passenger", "crew", None):
            role_hint = None
        try:
            session = current_session(role_hint)
            if role_hint and session["role"] != role_hint:
                raise auth_service.AuthenticationError(f"No active session for role {role_hint}")
        except auth_service.AuthenticationError as exc:
            return failure(str(exc), 401, "UNAUTHENTICATED")

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
    def logout():
        """Revoke the current session.

        Accepts an optional ``?role=passenger`` or ``?role=crew`` query
        parameter (or JSON body ``{"role": "..."}``).  Only the matching
        role-specific cookie (and the legacy cookie) are cleared; the other
        role's session is left intact.
        """
        # Resolve role hint from query param, header, body, or Referer before looking up session.
        body = request.get_json(silent=True) or {}
        role_hint = (
            request.args.get("role")
            or request.headers.get("X-SoraLink-Role")
            or (body.get("role") if isinstance(body, dict) else None)
        )
        if not role_hint and request.referrer:
            if "/crew" in request.referrer:
                role_hint = "crew"
            elif "/passenger" in request.referrer:
                role_hint = "passenger"
        if role_hint not in ("passenger", "crew", None):
            role_hint = None
        try:
            session = current_session(role_hint)
        except auth_service.AuthenticationError as exc:
            return failure(str(exc), 401, "UNAUTHENTICATED")
        auth_service.revoke_session(session["id"])
        resp, status = success({"logged_out": True}, 200)
        return _clear_session_cookie(resp, role=session["role"]), status

    @app.get("/api/passenger/state")
    @authenticated("passenger")
    def passenger_state(session):
        return success({
            "seat_label": session.get("seat_label"),
            "session": session,
            "requests": requests_service.list_passenger_requests(session),
            "active_broadcasts": broadcast_service.list_active_broadcasts(),
        })

    @app.post("/api/requests")
    @authenticated("passenger")
    def create_request(session):
        if not request.is_json:
            return failure("Request body must be JSON", 400, "BAD_REQUEST")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return failure("Request body must be a JSON object", 400, "BAD_REQUEST")

        intent_id = body.get("intent_id")
        if not intent_id or not isinstance(intent_id, str):
            return failure("intent_id is required", 400, "INVALID_INTENT")

        client_request_id = (
            body.get("client_request_id")
            or body.get("idempotency_key")
            or request.headers.get("Idempotency-Key")
        )

        try:
            created = requests_service.create_request(
                session, intent_id, client_request_id=client_request_id
            )
        except requests_service.InvalidIntentError as exc:
            return failure(str(exc), 400, "INVALID_INTENT")
        except requests_service.IdempotencyConflictError as exc:
            return failure(str(exc), 409, "IDEMPOTENCY_CONFLICT")
        except requests_service.DuplicateActiveRequestError as exc:
            return failure(str(exc), 409, "DUPLICATE_ACTIVE_REQUEST")
        except PermissionError as exc:
            return failure(str(exc), 403, "FORBIDDEN")

        was_created = created.get("was_created", True)
        if was_created:
            # Emit Socket.IO notifications only after durable database commit
            socketio.emit(
                "request_created",
                {
                    "request": {
                        "request_id": created["id"],
                        "seat_label": created["seat_label"],
                        "intent_id": created["intent_id"],
                        "priority": created["priority"].upper(),
                        "status": created["status"],
                        "created_at": created["created_at_ms"],
                    }
                },
                to="crew:dashboard",
            )
            socketio.emit(
                "request_updated",
                {
                    "request_id": created["id"],
                    "seat_label": created["seat_label"],
                    "status": created["status"],
                    "updated_at": created["updated_at_ms"],
                },
                to=f"passenger:seat:{created['seat_label']}",
            )
            status_code = 201
        else:
            status_code = 200

        resp_data = {
            "request_id": created["id"],
            "id": created["id"],
            "seat_label": created["seat_label"],
            "intent_id": created["intent_id"],
            "status": created["status"],
            "priority": created["priority"].upper(),
            "created_at": created["created_at_ms"],
            "request": created,
        }
        return success(resp_data, status_code)

    @app.post("/api/voice_request")
    @authenticated("passenger")
    def voice_request(session):
        if "audio" not in request.files:
            return failure("audio file is required", 400, "BAD_REQUEST")

        audio_file = request.files["audio"]
        filename = (audio_file.filename or "").lower()
        content_type = audio_file.content_type or ""

        # Infer a supported MIME type only when the browser omits it.
        if not content_type or content_type == "application/octet-stream":
            extensions = {
                ".webm": "audio/webm",
                ".mp4": "audio/mp4",
                ".m4a": "audio/mp4",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".ogg": "audio/ogg",
            }
            content_type = next(
                (mime for ext, mime in extensions.items() if filename.endswith(ext)),
                content_type or "application/octet-stream",
            )

        audio_bytes = audio_file.read()

        try:
            result = voice.process_voice_preview(audio_bytes, content_type)
        except classifier.VoiceProcessingError as exc:
            return failure(exc.message, exc.http_status, exc.code)
        except Exception:
            app.logger.exception("Voice preview processing failed unexpectedly")
            return failure("Audio processing failed", 500, "INTERNAL_ERROR")

        transcript = result.get("transcript", "").strip()
        if not transcript:
            return failure(
                "No clear speech was recognized. Please try again or tap a request card.",
                422,
                "SILENCE_OR_NO_SPEECH",
            )

        outcome = result.get("outcome", "UNRELIABLE")
        suggested = result.get("suggested_intent")
        candidates = result.get("candidates") or []
        attributes = result.get("attributes") or {}
        requires_choice = bool(result.get("requires_choice", True))

        catalog = {
            item["id"]: item
            for item in classifier.load_intent_catalog()
        }

        alternatives = []
        for candidate in candidates:
            intent_id = candidate.get("intent_id")
            if not intent_id:
                continue
            item = catalog.get(intent_id, {})
            alternatives.append({
                "intent_id": intent_id,
                "label": item.get("label", intent_id),
                "priority": item.get("priority", "routine"),
                "confidence": float(candidate.get("score", 0.0)),
            })

        # Only an explicit SUGGESTED outcome may preselect an intent.
        intent_id = None
        confidence = alternatives[0]["confidence"] if alternatives else 0.0
        if outcome == "SUGGESTED" and suggested:
            proposed_id = suggested.get("intent_id")
            if proposed_id in catalog:
                intent_id = proposed_id
                confidence = float(suggested.get("score", confidence))
            else:
                outcome = "UNRELIABLE"
                requires_choice = True

        preview = voice.create_voice_preview(
            session_id=session["id"],
            transcript=transcript,
            intent_id=intent_id,
            confidence=confidence,
            alternatives=alternatives,
        )

        return success({
            "preview_id": preview["id"],
            "transcript": transcript,
            "language": result.get("language"),
            "intent_id": intent_id,
            "confidence": confidence,
            "needs_confirmation": True,
            "alternatives": alternatives[:3],
            "outcome": outcome,
            "attributes": attributes,
            "candidates": candidates,
            "requires_choice": requires_choice,
            "allow_none_of_these": intent_id is None,
        })

    @app.post("/api/voice_request/confirm")
    @authenticated("passenger")
    def confirm_voice_request(session):
        if not request.is_json:
            return failure("Request body must be JSON", 400, "BAD_REQUEST")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return failure("Request body must be a JSON object", 400, "BAD_REQUEST")

        preview_id = body.get("preview_id")
        intent_id = body.get("intent_id")

        if not preview_id or not isinstance(preview_id, str):
            return failure("preview_id is required", 400, "BAD_REQUEST")
        if not intent_id or not isinstance(intent_id, str):
            return failure("intent_id is required", 400, "BAD_REQUEST")

        preview = voice.get_voice_preview(preview_id)
        if preview is None:
            return failure("Voice preview not found", 404, "NOT_FOUND")

        # Session ownership check
        if preview["session_id"] != session["id"]:
            return failure("Preview does not belong to authenticated session", 403, "FORBIDDEN")

        # Expiry check
        if preview["expires_at_ms"] <= database.now_ms():
            return failure("Voice preview has expired", 410, "PREVIEW_EXPIRED")

                # Reject previously consumed previews, except for a valid idempotent retry.
        if preview["consumed_at_ms"] is not None:
            existing_req_id = preview.get("request_id")

            if existing_req_id == "REJECTED":
                return failure(
                    "Preview was previously rejected",
                    409,
                    "PREVIEW_REJECTED",
                )

            if existing_req_id:
                existing_req = requests_service.get_request_by_id(
                    existing_req_id
                )

                if existing_req is not None:
                    if existing_req["intent_id"] == intent_id:
                        return success({
                            "request_id": existing_req["id"],
                            "id": existing_req["id"],
                            "seat_label": existing_req["seat_label"],
                            "intent_id": existing_req["intent_id"],
                            "status": existing_req["status"],
                            "priority": existing_req["priority"].upper(),
                            "created_at": existing_req["created_at_ms"],
                            "request": existing_req,
                        }, 200)

                    return failure(
                        "Preview was already confirmed with a different intent",
                        409,
                        "PREVIEW_ALREADY_CONSUMED",
                    )

            return failure(
                "Preview has already been consumed",
                409,
                "PREVIEW_ALREADY_CONSUMED",
            )

        # Validate intent ID and create request
        try:
            created = requests_service.create_request(
                session, intent_id, client_request_id=f"preview-{preview_id}"
            )
        except requests_service.InvalidIntentError as exc:
            return failure(str(exc), 400, "INVALID_INTENT")
        except requests_service.IdempotencyConflictError as exc:
            return failure(str(exc), 409, "IDEMPOTENCY_CONFLICT")
        except PermissionError as exc:
            return failure(str(exc), 403, "FORBIDDEN")

        voice.consume_voice_preview(preview_id, created["id"])

        was_created = created.get("was_created", True)
        if was_created:
            socketio.emit(
                "request_created",
                {
                    "request": {
                        "request_id": created["id"],
                        "seat_label": created["seat_label"],
                        "intent_id": created["intent_id"],
                        "priority": created["priority"].upper(),
                        "status": created["status"],
                        "created_at": created["created_at_ms"],
                    }
                },
                to="crew:dashboard",
            )
            socketio.emit(
                "request_updated",
                {
                    "request_id": created["id"],
                    "seat_label": created["seat_label"],
                    "status": created["status"],
                    "updated_at": created["updated_at_ms"],
                },
                to=f"passenger:seat:{created['seat_label']}",
            )
            status_code = 201
        else:
            status_code = 200

        resp_data = {
            "request_id": created["id"],
            "id": created["id"],
            "seat_label": created["seat_label"],
            "intent_id": created["intent_id"],
            "status": created["status"],
            "priority": created["priority"].upper(),
            "created_at": created["created_at_ms"],
            "request": created,
        }
        return success(resp_data, status_code)

    @app.post("/api/voice_request/none_of_these")
    @authenticated("passenger")
    def reject_voice_request(session):
        if not request.is_json:
            return failure("Request body must be JSON", 400, "BAD_REQUEST")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return failure("Request body must be a JSON object", 400, "BAD_REQUEST")

        preview_id = body.get("preview_id")
        if not preview_id or not isinstance(preview_id, str):
            return failure("preview_id is required", 400, "BAD_REQUEST")

        preview = voice.get_voice_preview(preview_id)
        if preview is None:
            return failure("Voice preview not found", 404, "NOT_FOUND")

        # Session ownership check
        if preview["session_id"] != session["id"]:
            return failure("Preview does not belong to authenticated session", 403, "FORBIDDEN")

        # Expiry check
        if preview["expires_at_ms"] <= database.now_ms():
            return failure("Voice preview has expired", 410, "PREVIEW_EXPIRED")

        # A preview can only be rejected once.
        if preview["consumed_at_ms"] is not None:
            return failure(
                "Preview has already been consumed",
                409,
                "PREVIEW_ALREADY_CONSUMED",
            )
        voice.reject_voice_preview(preview_id)

        return success({
            "preview_id": preview_id,
            "needs_visual_fallback": True,
            "intents": classifier.load_intent_catalog(),
        })

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
        body = request.get_json(silent=True) or {}
        response_id = body.get("response_id") if isinstance(body, dict) else None

        try:
            item = requests_service.acknowledge_request(
                session, request_id, response_id=response_id
            )
        except requests_service.RequestNotFoundError as exc:
            return failure(str(exc), 404, "NOT_FOUND")
        except requests_service.InvalidTransitionError as exc:
            return failure(str(exc), 409, "INVALID_TRANSITION")
        except PermissionError as exc:
            return failure(str(exc), 403, "FORBIDDEN")

        was_updated = item.get("was_updated", True)
        if was_updated:
            socketio.emit(
                "request_updated",
                {
                    "request_id": item["id"],
                    "seat_label": item["seat_label"],
                    "status": "ACKNOWLEDGED",
                    "updated_at": item["updated_at_ms"],
                },
                to="crew:dashboard",
            )
            # Emit to the seat room so all connected clients for this seat
            # (including passengers who re-logged in with a new session ID)
            # receive real-time status updates.
            socketio.emit(
                "request_updated",
                {
                    "request_id": item["id"],
                    "seat_label": item["seat_label"],
                    "status": "ACKNOWLEDGED",
                    "updated_at": item["updated_at_ms"],
                },
                to=f"passenger:seat:{item['seat_label']}",
            )
            if response_id:
                crew_responses = requests_service.load_crew_responses()
                response_data = crew_responses.get(response_id)
                if response_data:
                    reply_payload = {
                        "request_id": item["id"],
                        "response_id": response_id,
                        "labels": response_data.get("messages", {}),
                        "created_at": item["updated_at_ms"],
                    }
                    socketio.emit(
                        "crew_reply",
                        reply_payload,
                        to=f"passenger:seat:{item['seat_label']}",
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

        was_updated = item.get("was_updated", True)
        if was_updated:
            socketio.emit(
                "request_updated",
                {
                    "request_id": item["id"],
                    "seat_label": item["seat_label"],
                    "status": "COMPLETED",
                    "updated_at": item["updated_at_ms"],
                },
                to="crew:dashboard",
            )
            socketio.emit(
                "request_updated",
                {
                    "request_id": item["id"],
                    "seat_label": item["seat_label"],
                    "status": "COMPLETED",
                    "updated_at": item["updated_at_ms"],
                },
                to=f"passenger:seat:{item['seat_label']}",
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
    def pa_cards(session):
        cards = list(broadcast_service.load_pa_cards().values())
        return success({"cards": cards})

    @app.get("/api/content/pa_cards")
    def content_pa_cards():
        cards = list(broadcast_service.load_pa_cards().values())
        return success({"cards": cards})

    @app.get("/api/content/catalog")
    def content_catalog():
        intents = classifier.load_intent_catalog()
        crew_responses = requests_service.load_crew_responses()
        return success({
            "intents": intents,
            "crew_responses": crew_responses,
        })

    @app.get("/api/passenger/replies")
    @authenticated("passenger")
    def passenger_replies(session):
        requests = requests_service.list_passenger_requests(session)
        crew_responses = requests_service.load_crew_responses()
        return success({
            "requests": requests,
            "crew_responses": crew_responses,
        })

    @app.get("/api/passenger/broadcasts")
    @app.get("/api/pa/active")
    @authenticated("passenger")
    def passenger_broadcasts(session):
        items = broadcast_service.list_active_broadcasts()
        return success({
            "broadcasts": items,
            "active_broadcasts": items,
        })

    @app.get("/api/crew/pa/broadcasts")
    @app.get("/api/crew/broadcasts")
    @authenticated("crew")
    def crew_broadcasts(session):
        include_inactive = (
            request.args.get("include_inactive", "").lower()
            in {"1", "true", "yes"}
        )
        items = broadcast_service.list_crew_broadcasts(
            session, include_inactive=include_inactive
        )
        return success({"broadcasts": items})

    @app.post("/api/crew/pa/broadcast")
    @app.post("/api/crew/broadcasts")
    @authenticated("crew")
    def create_broadcast(session):
        if not request.is_json:
            return failure("Request body must be JSON", 400, "BAD_REQUEST")
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return failure("Request body must be a JSON object", 400, "BAD_REQUEST")

        # Reject client-supplied announcement text and spoofed metadata
        if any(k in body for k in ("text", "body", "title", "custom_text")):
            return failure(
                "Client-supplied announcement text is not permitted; reference an approved pa_card_id",
                400,
                "INVALID_BROADCAST",
            )

        if any(k in body for k in ("created_by", "created_at", "created_at_ms", "expires_at", "expires_at_ms", "ended_at", "ended_at_ms", "active_status", "role")):
            return failure(
                "Client-supplied metadata is not permitted",
                400,
                "INVALID_METADATA",
            )

        pa_card_id = body.get("pa_card_id") or body.get("card_id")
        if not pa_card_id or not isinstance(pa_card_id, str):
            return failure("pa_card_id is required", 400, "INVALID_CARD")

        duration_seconds = body.get("duration_seconds")
        if duration_seconds is None:
            duration_seconds = body.get("ttl_seconds")
        if duration_seconds is not None:
            if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int):
                return failure("duration_seconds must be an integer", 400, "BAD_REQUEST")

        try:
            item = broadcast_service.create_broadcast(
                session,
                pa_card_id=pa_card_id,
                duration_seconds=duration_seconds,
            )
        except broadcast_service.InvalidBroadcastError as exc:
            return failure(str(exc), 400, "INVALID_BROADCAST")
        except broadcast_service.BroadcastAuthorizationError as exc:
            return failure(str(exc), 403, "FORBIDDEN")
        except Exception as exc:
            app.logger.exception("Failed to persist broadcast")
            return failure("Failed to persist broadcast", 500, "INTERNAL_ERROR")

        # Emit Socket.IO notification only after successful database commit
        socketio.emit("pa_broadcast_created", item)

        resp_data = {
            "broadcast_id": item["id"],
            "id": item["id"],
            "pa_card_id": item["pa_card_id"],
            "title": item["title"],
            "body": item["body"],
            "category": item["category"],
            "active_status": True,
            "created_at": item["created_at_ms"],
            "created_at_ms": item["created_at_ms"],
            "expires_at": item["expires_at_ms"],
            "expires_at_ms": item["expires_at_ms"],
            "broadcast": item,
        }
        return success(resp_data, 201)

    @app.post("/api/crew/pa/end")
    @app.patch("/api/crew/pa/broadcast/<broadcast_id>")
    @authenticated("crew")
    def end_broadcast(session, broadcast_id=None):
        if broadcast_id is None:
            body = request.get_json(silent=True) or {}
            if isinstance(body, dict):
                broadcast_id = body.get("broadcast_id") or body.get("id")

        if not broadcast_id or not isinstance(broadcast_id, str):
            return failure("broadcast_id is required", 400, "BAD_REQUEST")

        try:
            item = broadcast_service.end_broadcast(session, broadcast_id)
        except broadcast_service.BroadcastNotFoundError as exc:
            return failure(str(exc), 404, "NOT_FOUND")
        except broadcast_service.BroadcastAuthorizationError as exc:
            return failure(str(exc), 403, "FORBIDDEN")
        except broadcast_service.BroadcastServiceError as exc:
            return failure(str(exc), 400, "INVALID_BROADCAST")
        except Exception as exc:
            app.logger.exception("Failed to end broadcast")
            return failure("Failed to end broadcast", 500, "INTERNAL_ERROR")

        event_data = {
            "broadcast_id": item["id"],
            "id": item["id"],
            "ended_at": item["ended_at_ms"],
            "ended_at_ms": item["ended_at_ms"],
        }
        socketio.emit("pa_broadcast_ended", event_data)

        return success({"broadcast": item, "broadcast_id": item["id"], "ended_at": item["ended_at_ms"]})

    @socketio.on("connect")
    def socket_connect(auth_data=None):
        role_hint = request.args.get("role") or request.headers.get("X-SoraLink-Role")
        if not role_hint and isinstance(auth_data, dict):
            role_hint = auth_data.get("role")
        if not role_hint and request.referrer:
            if "/passenger" in request.referrer:
                role_hint = "passenger"
            elif "/crew" in request.referrer:
                role_hint = "crew"
        if role_hint not in ("passenger", "crew", None):
            role_hint = None

        token = None
        if role_hint and role_hint in _ROLE_COOKIE:
            token = request.cookies.get(_ROLE_COOKIE[role_hint])
        if not token and isinstance(auth_data, dict):
            token = auth_data.get("token")
        if not token:
            cookie_name = app.config.get("SESSION_COOKIE_NAME", _LEGACY_COOKIE)
            token = request.cookies.get(cookie_name)
        if not token:
            token = request.cookies.get("soralink_session") or request.cookies.get("session_token")
        if not token:
            token = request.cookies.get(_ROLE_COOKIE.get("passenger", "")) or request.cookies.get(_ROLE_COOKIE.get("crew", ""))

        session = auth_service.get_session_by_token(token or "") if token else None
        if session is None:
            return False
        if role_hint and session["role"] != role_hint:
            return False

        if session["role"] == "crew":
            join_room("crew:dashboard")
        elif session["role"] == "passenger":
            join_room(f"passenger:{session['id']}")
            join_room("passengers:all")
            # Join the seat room so events reach the passenger even after a
            # session rotation (re-login generates a new session ID but the
            # seat label stays constant for the duration of the flight).
            if session.get("seat_label"):
                join_room(f"passenger:seat:{session['seat_label']}")

        payload = {
            "session_id": session["id"],
            "role": session["role"],
            "server_time": database.now_ms(),
        }
        if session["role"] == "passenger":
            payload["seat_label"] = session.get("seat_label")
        elif session["role"] == "crew":
            payload["crew_id"] = session.get("id")

        emit("connection_ready", payload)

        reconnect_flag = False
        if request.args.get("reconnect") in ("1", "true", "yes"):
            reconnect_flag = True
        elif isinstance(auth_data, dict) and auth_data.get("reconnect"):
            reconnect_flag = True

        if reconnect_flag:
            emit("state_resync_required", {"reason": "reconnect_or_state_mismatch"})

    @socketio.on("request_resync")
    def handle_request_resync(data=None):
        role_hint = None
        if isinstance(data, dict):
            role_hint = data.get("role")
        if not role_hint:
            role_hint = request.args.get("role") or request.headers.get("X-SoraLink-Role")
        if not role_hint and request.referrer:
            if "/passenger" in request.referrer:
                role_hint = "passenger"
            elif "/crew" in request.referrer:
                role_hint = "crew"
        if role_hint not in ("passenger", "crew", None):
            role_hint = None

        token = None
        if role_hint and role_hint in _ROLE_COOKIE:
            token = request.cookies.get(_ROLE_COOKIE[role_hint])
        if not token:
            token = (
                request.cookies.get(app.config.get("SESSION_COOKIE_NAME", _LEGACY_COOKIE))
                or request.cookies.get("soralink_session")
                or request.cookies.get("session_token")
                or request.cookies.get(_ROLE_COOKIE.get("passenger", ""))
                or request.cookies.get(_ROLE_COOKIE.get("crew", ""))
            )
        session = auth_service.get_session_by_token(token or "") if token else None
        if session is None:
            return False
        if role_hint and session["role"] != role_hint:
            return False
        emit("state_resync_required", {"reason": "reconnect_or_state_mismatch"})

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
    import threading

    host = app.config["HOST"]
    passenger_port = app.config["PORT"]
    crew_port = app.config.get("CREW_PORT", 5002)
    dual_port = app.config.get("DUAL_PORT", True)
    debug = app.config["DEBUG"]

    if dual_port and passenger_port != crew_port:
        print(f" * SoraLink starting in dual-portal mode on {host}:")
        print(f" *   -> Passenger Portal: http://{host}:{passenger_port}/ (or http://localhost:{passenger_port}/)")
        print(f" *   -> Crew Portal:      http://{host}:{crew_port}/ (or http://localhost:{crew_port}/)")

        # Run crew portal in background thread sharing in-memory socketio and app
        crew_thread = threading.Thread(
            target=socketio.run,
            args=(app,),
            kwargs={
                "host": host,
                "port": crew_port,
                "debug": False,
                "allow_unsafe_werkzeug": True,
            },
            daemon=True,
        )
        crew_thread.start()

        # Run passenger portal on main thread
        socketio.run(
            app,
            host=host,
            port=passenger_port,
            debug=debug,
            allow_unsafe_werkzeug=True,
        )
    else:
        socketio.run(
            app,
            host=host,
            port=passenger_port,
            debug=debug,
            allow_unsafe_werkzeug=True,
        )

