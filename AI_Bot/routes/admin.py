"""Account administration — available to the basic admin role only."""

import secrets
import string

from flask import Blueprint, flash, redirect, render_template, request, url_for

from routes.auth import admin_required
from services import accounts, recovery

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _temporary_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits

    return "".join(secrets.choice(alphabet) for _ in range(length))


@bp.route("/users")
@admin_required
def users():
    return render_template("admin_users.html", users=accounts.all_users())


@bp.route("/users/create", methods=["POST"])
@admin_required
def create():
    username = request.form.get("username", "")
    display_name = request.form.get("display_name", "")
    phone = request.form.get("phone", "")
    role = request.form.get("role", "user")

    password = request.form.get("password") or _temporary_password()

    try:
        user = accounts.create_user(
            username, password, display_name=display_name, phone=phone, role=role
        )
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("admin.users"))

    flash(
        f"Created {user.username}. Temporary password: {password}",
        "success",
    )
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/active", methods=["POST"])
@admin_required
def set_active(user_id: int):
    active = request.form.get("active") == "1"

    if accounts.set_active(user_id, active):
        flash("Account updated.", "success")
    else:
        flash("No such account.", "error")

    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete(user_id: int):
    if accounts.delete_user(user_id) is None:
        flash("Could not delete that account (the last admin stays).", "error")
    else:
        flash("Account and its data deleted.", "success")

    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/send-reset", methods=["POST"])
@admin_required
def send_reset(user_id: int):
    """Send a username + reset link to an account's registered number."""

    user = accounts.get_user(user_id)

    if user is None or not user.phone:
        flash("That account has no recovery phone number.", "error")
        return redirect(url_for("admin.users"))

    link = recovery.create_reset_link(user)
    channel = recovery.send_reset_link(user, link)

    if channel:
        flash(f"Username and reset link sent via {channel}.", "success")
    else:
        flash("Could not deliver the reset link. Check WhatsApp/SMS setup.", "error")

    return redirect(url_for("admin.users"))
