import csv
import io
import os
from datetime import datetime, timedelta
from urllib.parse import urljoin
from flask import session, g
from hmac import compare_digest as safe_str_cmp
from flask import session, redirect, url_for, request, render_template
from functools import wraps


from flask import (
    Flask, request, render_template, redirect, url_for, jsonify,
    send_file, Response, abort
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, or_
import hmac

from config import Config
from utils.geo import geolocate_ip
from utils.qrcode_utils import generate_qr_png_bytes

app = Flask(__name__)
app.config.from_object(Config)
db = SQLAlchemy(app)

# ---------- Modèles ----------
class Link(db.Model):
    __tablename__ = "links"
    id = db.Column(db.String(36), primary_key=True)        # UUID string
    file_name = db.Column(db.String(255), nullable=False)
    campaign = db.Column(db.String(80), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    clicks = db.relationship("Click", backref="link", lazy=True, cascade="all, delete-orphan")

class Click(db.Model):
    __tablename__ = "clicks"
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    link_id = db.Column(db.String(36), db.ForeignKey("links.id"), nullable=False, index=True)
    ts = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ip = db.Column(db.String(64), nullable=True, index=True)
    user_agent = db.Column(db.Text, nullable=True)
    referer = db.Column(db.Text, nullable=True)
    path = db.Column(db.String(255), nullable=True)

    # géo optionnelle
    country = db.Column(db.String(64))
    region = db.Column(db.String(64))
    city = db.Column(db.String(64))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)

# ---------- Helpers ----------
def require_dashboard_auth():
    if session.get('is_qr_user'):
        # l’utilisateur QR n’a pas accès
        abort(403)

    u = app.config.get("DASHBOARD_USERNAME")
    p = app.config.get("DASHBOARD_PASSWORD")
    if not u or not p:
        return None
    auth = request.authorization
    if not auth or not (safe_str_cmp(auth.username, u) and safe_str_cmp(auth.password, p)):
        return Response(
            "Auth requise", 401,
            {"WWW-Authenticate": 'Basic realm="Honeypot Dashboard"'}
        )
    return None

def ensure_db():
    with app.app_context():
        db.create_all()
        os.makedirs("export", exist_ok=True)

# ---------- Routes UI ----------
@app.route("/")
def index():
    # Derniers liens pour affichage
    latest_links = Link.query.order_by(Link.created_at.desc()).limit(20).all()
    return render_template("index.html", links=latest_links)

@app.route("/generate", methods=["POST"])
def generate():
    """
    Génère 1..N liens pour un nom de fichier et une campagne optionnelle.
    """
    from uuid import uuid4

    file_name = (request.form.get("file") or "rapport_salaire_2025.pdf").strip()
    campaign = (request.form.get("campaign") or "").strip() or None
    count = max(1, min(int(request.form.get("count") or "1"), 50))

    created = []
    for _ in range(count):
        link_id = str(uuid4())
        link = Link(id=link_id, file_name=file_name, campaign=campaign)
        db.session.add(link)
        created.append(link)
    db.session.commit()

    return redirect(url_for("index"))

@app.route("/click/<link_id>")
def click(link_id):
    link = Link.query.get(link_id)
    if not link:
        return render_template("not_found.html"), 404

    # Vérification du token QR
    token = request.args.get("t")
    if token != app.config.get("QR_SECRET_TOKEN"):
        return "Bu sayfaya erişemezsiniz.", 403

    # Marquer l'utilisateur comme QR-only dans la session
    session['is_qr_user'] = True

    # Récupérer les infos du click
    ip = request.headers.get("X-Forwarded-For", request.remote_addr)
    ua = request.headers.get("User-Agent", "")
    ref = request.headers.get("Referer", "")
    path = request.path

    country = region = city = None
    lat = lon = None
    if app.config.get("ENABLE_IP_GEO"):
        geo = geolocate_ip(ip, provider=app.config.get("GEO_PROVIDER"), token=app.config.get("GEO_IPINFO_TOKEN"))
        country = geo.get("country")
        region = geo.get("region")
        city = geo.get("city")
        lat = geo.get("lat")
        lon = geo.get("lon")

    # Sauvegarder le click dans la DB
    c = Click(
        link_id=link.id,
        ip=ip,
        user_agent=ua,
        referer=ref,
        path=path,
        country=country,
        region=region,
        city=city,
        lat=lat,
        lon=lon
    )
    db.session.add(c)
    db.session.commit()

    # Force le rôle normal pour les templates si besoin
    g.is_admin = False

    # Afficher la page QR
    return render_template("alert.html", file_name=link.file_name, link=link, qr_only=True)





@app.route("/qr/<link_id>.png")
def qr(link_id):
    link = Link.query.get(link_id)
    if not link:
        abort(404)
    absolute = urljoin(
        request.host_url,
        url_for("click", link_id=link.id) + f"?t={app.config.get('QR_SECRET_TOKEN')}"
    )
    png = generate_qr_png_bytes(absolute)
    return send_file(io.BytesIO(png), mimetype="image/png")


@app.route("/logs")
def logs_page():
    auth = require_dashboard_auth()
    if auth: return auth  # basic auth si configurée
    # Filtres passés côté template (fetch via /api/logs)
    return render_template("logs.html")

@app.route("/campaigns")
def campaigns_page():
    auth = require_dashboard_auth()
    if auth: return auth
    # Stats par campagne
    stats = (
        db.session.query(
            Link.campaign,
            func.count(Link.id).label("links"),
            func.count(Click.id).label("clicks")
        )
        .outerjoin(Click, Click.link_id == Link.id)
        .group_by(Link.campaign)
        .order_by(func.count(Click.id).desc())
        .all()
    )
    # calc CTR (~ clics / liens)
    campaigns = []
    for c, links, clicks in stats:
        ctr = (clicks / links) if links else 0
        campaigns.append({"campaign": c or "(sans campagne)", "links": links, "clicks": clicks, "ctr": ctr})
    return render_template("campaigns.html", campaigns=campaigns)

# ---------- API ----------
@app.route("/api/generate", methods=["POST"])
def api_generate():
    from uuid import uuid4
    data = request.get_json(force=True, silent=True) or {}
    file_name = (data.get("file") or "rapport.pdf").strip()
    campaign = (data.get("campaign") or "").strip() or None
    count = max(1, min(int(data.get("count") or 1), 100))

    ids = []
    for _ in range(count):
        link_id = str(uuid4())
        link = Link(id=link_id, file_name=file_name, campaign=campaign)
        db.session.add(link)
        ids.append(link_id)
    db.session.commit()

    urls = [urljoin(request.host_url, url_for("click", link_id=i)) for i in ids]
    return jsonify({"ok": True, "ids": ids, "urls": urls})

@app.route("/api/links")
def api_links():
    q = Link.query.order_by(Link.created_at.desc()).limit(200).all()
    out = [{
        "id": l.id,
        "file_name": l.file_name,
        "campaign": l.campaign,
        "created_at": l.created_at.isoformat()
    } for l in q]
    return jsonify(out)

@app.route("/api/logs")
def api_logs():
    # Filtres
    page = max(1, int(request.args.get("page", 1)))
    per_page = max(1, min(int(request.args.get("per_page", 25)), 200))
    ip = request.args.get("ip")
    campaign = request.args.get("campaign")
    file_name = request.args.get("file")
    search = request.args.get("q")
    days = request.args.get("days")

    q = db.session.query(Click, Link).join(Link, Click.link_id == Link.id)

    if ip:
        q = q.filter(Click.ip == ip)
    if campaign:
        q = q.filter(Link.campaign == campaign)
    if file_name:
        q = q.filter(Link.file_name.ilike(f"%{file_name}%"))
    if search:
        like = f"%{search}%"
        q = q.filter(or_(Click.user_agent.ilike(like), Click.referer.ilike(like), Link.file_name.ilike(like)))
    if days:
        try:
            d = int(days)
            since = datetime.utcnow() - timedelta(days=d)
            q = q.filter(Click.ts >= since)
        except ValueError:
            pass

    q = q.order_by(Click.ts.desc())
    total = q.count()
    items = q.offset((page-1)*per_page).limit(per_page).all()

    data = []
    for c, l in items:
        data.append({
            "id": c.id,
            "ts": c.ts.isoformat(timespec="seconds"),
            "ip": c.ip,
            "user_agent": c.user_agent,
            "referer": c.referer,
            "path": c.path,
            "file_name": l.file_name,
            "campaign": l.campaign,
            "country": c.country, "region": c.region, "city": c.city,
            "lat": c.lat, "lon": c.lon,
            "link_id": l.id,
            "click_url": urljoin(request.host_url, url_for("click", link_id=l.id)),
            "qr_url": urljoin(request.host_url, url_for("qr", link_id=l.id)),
        })

    return jsonify({
        "page": page, "per_page": per_page, "total": total,
        "items": data
    })

@app.route("/logs/export")
def export_logs():
    fmt = (request.args.get("format") or "csv").lower()
    q = db.session.query(Click, Link).join(Link, Click.link_id == Link.id).order_by(Click.ts.desc())

    if fmt == "json":
        items = []
        for c, l in q.all():
            items.append({
                "ts": c.ts.isoformat(timespec="seconds"),
                "ip": c.ip, "ua": c.user_agent, "referer": c.referer, "path": c.path,
                "file_name": l.file_name, "campaign": l.campaign,
                "country": c.country, "region": c.region, "city": c.city,
                "lat": c.lat, "lon": c.lon, "link_id": l.id
            })
        buf = io.BytesIO()
        data = (str(items)).encode("utf-8")
        buf.write(data); buf.seek(0)
        return send_file(buf, mimetype="application/json", download_name="logs.json", as_attachment=True)

    # CSV par défaut
    si = io.StringIO()
    w = csv.writer(si)
    w.writerow(["timestamp","ip","user_agent","referer","path","file_name","campaign","country","region","city","lat","lon","link_id"])
    for c, l in q.all():
        w.writerow([c.ts, c.ip, c.user_agent, c.referer, c.path, l.file_name, l.campaign, c.country, c.region, c.city, c.lat, c.lon, l.id])
    buf = io.BytesIO(si.getvalue().encode("utf-8"))
    return send_file(buf, mimetype="text/csv", download_name="logs.csv", as_attachment=True)

# ---------- Commandes utilitaires ----------
@app.cli.command("init-db")
def init_db():
    """flask init-db : crée les tables"""
    ensure_db()
    print("Base initialisée.")

# ---------- Hooks ----------
@app.before_request
def load_user():
    g.is_admin = False
    # Si Basic Auth pour dashboard
    auth = request.authorization
    u = app.config.get("DASHBOARD_USERNAME")
    p = app.config.get("DASHBOARD_PASSWORD")
    if auth and u and p and safe_str_cmp(auth.username, u) and safe_str_cmp(auth.password, p):
        g.is_admin = True


@app.route("/campaigns/delete/<campaign_name>", methods=["POST"])
def delete_campaign(campaign_name):
    auth = require_dashboard_auth()
    if auth:
        return auth

    if campaign_name == "(sans campagne)":
        return jsonify({"ok": False, "error": "Bu kampanya silinemez."})

    # Récupérer tous les liens de la campagne
    links_to_delete = Link.query.filter(Link.campaign == campaign_name).all()
    deleted_count = len(links_to_delete)

    for link in links_to_delete:
        db.session.delete(link)  # supprime le lien et tous les clicks associés
    db.session.commit()

    return jsonify({"ok": True, "deleted_links": deleted_count})

# Configurer un identifiant admin
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "supersecret"  # Tu peux aussi hasher le mot de passe pour plus de sécurité

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("dashboard"))
        else:
            error = "Kullanıcı adı veya şifre yanlış"
    return render_template("login.html", error=error)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)  # Interdit l'accès si ce n'est pas un admin
        return f(*args, **kwargs)
    return decorated_function

@app.route("/dashboard")
@admin_required
def dashboard():
    # Ici tu affiches les logs ou campagnes
    return render_template("dashboard.html")

@app.route("/delete_link/<string:link_id>", methods=["POST"], endpoint="delete_link_post")
def delete_link_post(link_id):
    link = Link.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()

    # Si c'est une requête Ajax, on renvoie juste un statut
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return '', 204

    return redirect(url_for('index'))


@app.route("/delete_link/<string:link_id>", methods=["DELETE"], endpoint="delete_link_delete")
def delete_link_delete(link_id):
    link = Link.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()
    return "", 200

@app.route("/delete_link/<string:link_id>", methods=["POST", "DELETE"])
def delete_link(link_id):
    link = Link.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()

    if request.method == "POST":
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return '', 204
        return redirect(url_for('index'))

    return '', 200


if __name__ == "__main__":
    ensure_db()
    app.run(host="0.0.0.0", port=5000, debug=True)