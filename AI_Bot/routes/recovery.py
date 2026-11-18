"""Public forgot-password flow."""

import time

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from services import accounts, recovery

bp = Blueprint("recovery", __name__)

USER_KEY = "rx_recovery_user"
SENT_AT_KEY = "rx_recovery_sent_at"
RESEND_SECONDS = 60


def _recovery_user():
    user_id = session.get(USER_KEY)

    return accounts.get_user(user_id) if user_id else None


@bp.route("/forgot-password", methods=["GET"])
def forgot_page():
    step = request.args.get("step", "phone")

    return render_template(
        "forgot_password.html",
        step=step,
        phone=session.get("rx_recovery_phone", ""),
        error=None,
    )


@bp.route("/forgot-password/send", methods=["POST"])
def send_code():
    """Look up the phone, issue an OTP and try to deliver it."""

    phone = accounts.normalize_phone(request.form.get("phone", ""))
    user = accounts.find_by_phone(phone)

    if user is not None:
        last = session.get(SENT_AT_KEY, 0)

        if time.time() - last < RESEND_SECONDS:
            flash("Please wait a minute before requesting another code.", "error")
        else:
            code = recovery.create_otp(user)
            channel = recovery.send_otp(user, code)

            session[USER_KEY] = user.id
            session["rx_recovery_phone"] = phone
            session[SENT_AT_KEY] = time.time()

            if channel:
                flash(f"Code sent to your {channel}.", "success")
            else:
                flash(
                    "Could not deliver the code. Ask the administrator to "
                    "check the WhatsApp link and SMS settings.",
                    "error",
                )

    else:
        # Do not disclose which phone numbers are registered.
        flash("If that number is registered, a code has been sent.", "success")

    return redirect(url_for("recovery.forgot_page", step="verify"))


@bp.route("/forgot-password/verify", methods=["POST"])
def verify_code():
    """Turn a correct OTP into a one-time reset link."""

    user = _recovery_user()

    if user is None:
        session.clear()
        flash("Start the recovery again.", "error")
        return redirect(url_for("recovery.forgot_page"))

    code = request.form.get("code", "")
    ok, reason = recovery.verify_otp(user, code)

    if not ok:
        flash(reason, "error")
        return redirect(url_for("recovery.forgot_page", step="verify"))

    link = recovery.create_reset_link(user)
    channel = recovery.send_reset_link(user, link)

    session.pop(USER_KEY, None)
    session.pop(SENT_AT_KEY, None)

    if channel:
        flash(f"Username and reset link sent to your {channel}.", "success")
    else:
        flash(
            "Could not deliver the reset link. Ask the administrator to "
            "check the WhatsApp link and SMS settings.",
            "error",
        )

    return redirect(url_for("recovery.forgot_page", step="sent"))


@bp.route("/reset-password", methods=["GET"])
def reset_page():
    token = request.args.get("token", "")
    user = recovery.reset_user_for_token(token)

    return render_template(
        "reset_password.html", token=token, valid=user is not None, username=user.username if user else ""
    )


@bp.route("/reset-password", methods=["POST"])
def reset_submit():
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    user = recovery.reset_user_for_token(token)

    if user is None:
        flash("That link is invalid or has expired.", "error")
        return redirect(url_for("recovery.reset_page"))

    if len(password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("recovery.reset_page", token=token))

    if password != confirm:
        flash("The two passwords do not match.", "error")
        return redirect(url_for("recovery.reset_page", token=token))

    if not accounts.set_password(user.id, password):
        flash("Could not set the password. Try again.", "error")
        return redirect(url_for("recovery.reset_page", token=token))

    recovery.consume_token_for_user(user.id)
    session.clear()
    flash("Password set. Sign in with your username and new password.", "success")

    return redirect(url_for("auth.login"))
