from flask import session, redirect, url_for

def logout_user():
    session.clear()
    return redirect(url_for("login"))