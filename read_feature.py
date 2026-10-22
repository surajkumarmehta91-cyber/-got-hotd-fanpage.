import os
from functools import wraps
from contextlib import contextmanager
from flask import Blueprint, request, session, redirect, url_for, abort, render_template_string
import psycopg2
from psycopg2.extras import RealDictCursor

read_bp = Blueprint("read_feature", __name__)
SERIES = {"house-of-the-dragon": "House of the Dragon", "game-of-thrones": "Game of Thrones"}

@contextmanager
def _db():
    url = os.getenv("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable missing")
    conn = psycopg2.connect(url, sslmode="require", cursor_factory=RealDictCursor, connect_timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@read_bp.before_app_request
def _ensure_read_tables():
    # Safe, additive migration. Does not alter or drop existing site tables.
    if request.endpoint and request.endpoint.startswith("read_feature."):
        with _db() as db:
            with db.cursor() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS read_seasons (
                    id BIGSERIAL PRIMARY KEY,
                    series_slug TEXT NOT NULL CHECK (series_slug IN ('house-of-the-dragon','game-of-thrones')),
                    title TEXT NOT NULL,
                    season_number INTEGER NOT NULL DEFAULT 1,
                    description TEXT NOT NULL DEFAULT '',
                    cover_url TEXT NOT NULL DEFAULT '',
                    published BOOLEAN NOT NULL DEFAULT TRUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                c.execute("""CREATE TABLE IF NOT EXISTS read_episodes (
                    id BIGSERIAL PRIMARY KEY,
                    season_id BIGINT NOT NULL REFERENCES read_seasons(id) ON DELETE CASCADE,
                    title TEXT NOT NULL,
                    episode_number INTEGER NOT NULL DEFAULT 1,
                    description TEXT NOT NULL DEFAULT '',
                    thumbnail_url TEXT NOT NULL DEFAULT '',
                    video_url TEXT NOT NULL DEFAULT '',
                    published BOOLEAN NOT NULL DEFAULT TRUE,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
                c.execute("CREATE INDEX IF NOT EXISTS idx_read_seasons_series ON read_seasons(series_slug, sort_order, season_number)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_read_episodes_season ON read_episodes(season_id, sort_order, episode_number)")

def _admin():
    return bool(session.get("admin_logged_in"))

def _admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _admin():
            return redirect("/admin/login")
        return fn(*args, **kwargs)
    return wrapper

def _csrf_ok():
    import hmac
    return bool(session.get("csrf_token")) and hmac.compare_digest(
        request.form.get("csrf_token", ""), session.get("csrf_token", ""))

def _clean(name, limit):
    return (request.form.get(name, "") or "").strip()[:limit]

def _url(name, limit=2000):
    value = _clean(name, limit)
    return value if value.startswith(("https://", "http://")) else ""

@read_bp.get("/read")
def home():
    return render_template_string(PAGE, mode="home", series=SERIES, selected_series="", seasons=[], selected_season=None, episodes=[], episode=None, episode_list=[])

@read_bp.get("/read/<series_slug>")
def series_page(series_slug):
    if series_slug not in SERIES: abort(404)
    with _db() as db:
        with db.cursor() as c:
            c.execute("SELECT * FROM read_seasons WHERE series_slug=%s AND published=TRUE ORDER BY sort_order,season_number,id", (series_slug,))
            seasons = c.fetchall()
    return render_template_string(PAGE, mode="series", series=SERIES, selected_series=series_slug, seasons=seasons, selected_season=None, episodes=[], episode=None, episode_list=[])

@read_bp.get("/read/season/<int:season_id>")
def season_page(season_id):
    with _db() as db:
        with db.cursor() as c:
            c.execute("SELECT * FROM read_seasons WHERE id=%s AND published=TRUE", (season_id,))
            season = c.fetchone()
            if not season: abort(404)
            c.execute("SELECT * FROM read_episodes WHERE season_id=%s AND published=TRUE ORDER BY sort_order,episode_number,id", (season_id,))
            episodes = c.fetchall()
            c.execute("SELECT * FROM read_seasons WHERE series_slug=%s AND published=TRUE ORDER BY sort_order,season_number,id", (season["series_slug"],))
            seasons = c.fetchall()
    return render_template_string(PAGE, mode="season", series=SERIES, selected_series=season["series_slug"], seasons=seasons, selected_season=season, episodes=episodes, episode=None, episode_list=[])

@read_bp.get("/read/episode/<int:episode_id>")
def episode_page(episode_id):
    with _db() as db:
        with db.cursor() as c:
            c.execute("""SELECT e.*,s.title AS season_title,s.season_number,s.series_slug
                         FROM read_episodes e JOIN read_seasons s ON s.id=e.season_id
                         WHERE e.id=%s AND e.published=TRUE AND s.published=TRUE""", (episode_id,))
            episode = c.fetchone()
            if not episode: abort(404)
            c.execute("SELECT * FROM read_episodes WHERE season_id=(SELECT season_id FROM read_episodes WHERE id=%s) AND published=TRUE ORDER BY sort_order,episode_number,id", (episode_id,))
            episode_list = c.fetchall()
            c.execute("SELECT * FROM read_seasons WHERE series_slug=%s AND published=TRUE ORDER BY sort_order,season_number,id", (episode["series_slug"],))
            seasons = c.fetchall()
    return render_template_string(PAGE, mode="episode", series=SERIES, selected_series=episode["series_slug"], seasons=seasons, selected_season=None, episodes=[], episode=episode, episode_list=episode_list)

@read_bp.get("/admin/read")
@_admin_required
def admin_read():
    with _db() as db:
        with db.cursor() as c:
            c.execute("SELECT * FROM read_seasons ORDER BY series_slug,sort_order,season_number,id")
            seasons = c.fetchall()
            for s in seasons:
                c.execute("SELECT * FROM read_episodes WHERE season_id=%s ORDER BY sort_order,episode_number,id", (s["id"],))
                s["episodes"] = c.fetchall()
    return render_template_string(ADMIN_PAGE, seasons=seasons, token=session.get("csrf_token",""))

@read_bp.post("/admin/read/season/add")
@_admin_required
def add_season():
    if not _csrf_ok(): abort(400, "Page refresh karke dobara try karo.")
    slug, title = _clean("series_slug",50), _clean("title",160)
    if slug not in SERIES or not title: abort(400, "Series aur season title required.")
    with _db() as db:
        with db.cursor() as c:
            c.execute("""INSERT INTO read_seasons(series_slug,title,season_number,description,cover_url,published,sort_order)
                         VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (slug,title,max(1,int(request.form.get("season_number",1))),_clean("description",3000),
                 _url("cover_url",1000),"published" in request.form,int(request.form.get("sort_order",0))))
    return redirect("/admin/read")

@read_bp.post("/admin/read/season/<int:sid>/save")
@_admin_required
def save_season(sid):
    if not _csrf_ok(): abort(400, "Page refresh karke dobara try karo.")
    slug, title = _clean("series_slug",50), _clean("title",160)
    if slug not in SERIES or not title: abort(400, "Series aur title required.")
    with _db() as db:
        with db.cursor() as c:
            c.execute("""UPDATE read_seasons SET series_slug=%s,title=%s,season_number=%s,description=%s,cover_url=%s,published=%s,sort_order=%s WHERE id=%s""",
                (slug,title,max(1,int(request.form.get("season_number",1))),_clean("description",3000),_url("cover_url",1000),"published" in request.form,int(request.form.get("sort_order",0)),sid))
    return redirect("/admin/read")

@read_bp.post("/admin/read/season/<int:sid>/delete")
@_admin_required
def delete_season(sid):
    if not _csrf_ok(): abort(400, "Page refresh karke dobara try karo.")
    with _db() as db:
        with db.cursor() as c: c.execute("DELETE FROM read_seasons WHERE id=%s",(sid,))
    return redirect("/admin/read")

@read_bp.post("/admin/read/episode/add")
@_admin_required
def add_episode():
    if not _csrf_ok(): abort(400, "Page refresh karke dobara try karo.")
    title = _clean("title",180)
    if not title: abort(400,"Episode title required.")
    with _db() as db:
        with db.cursor() as c:
            c.execute("""INSERT INTO read_episodes(season_id,title,episode_number,description,thumbnail_url,video_url,published,sort_order)
                         SELECT id,%s,%s,%s,%s,%s,%s,%s FROM read_seasons WHERE id=%s""",
                (title,max(1,int(request.form.get("episode_number",1))),_clean("description",5000),_url("thumbnail_url",1000),_url("video_url"),"published" in request.form,int(request.form.get("sort_order",0)),int(request.form.get("season_id",0))))
            if c.rowcount == 0: abort(404,"Season not found")
    return redirect("/admin/read")

@read_bp.post("/admin/read/episode/<int:eid>/save")
@_admin_required
def save_episode(eid):
    if not _csrf_ok(): abort(400, "Page refresh karke dobara try karo.")
    title = _clean("title",180)
    if not title: abort(400,"Episode title required.")
    with _db() as db:
        with db.cursor() as c:
            c.execute("""UPDATE read_episodes SET title=%s,episode_number=%s,description=%s,thumbnail_url=%s,video_url=%s,published=%s,sort_order=%s WHERE id=%s""",
                (title,max(1,int(request.form.get("episode_number",1))),_clean("description",5000),_url("thumbnail_url",1000),_url("video_url"),"published" in request.form,int(request.form.get("sort_order",0)),eid))
    return redirect("/admin/read")

@read_bp.post("/admin/read/episode/<int:eid>/delete")
@_admin_required
def delete_episode(eid):
    if not _csrf_ok(): abort(400, "Page refresh karke dobara try karo.")
    with _db() as db:
        with db.cursor() as c: c.execute("DELETE FROM read_episodes WHERE id=%s",(eid,))
    return redirect("/admin/read")

ADMIN_PAGE = r"""<!doctype html><html lang="en"><meta name="viewport" content="width=device-width,initial-scale=1"><title>READ Manager</title>
<body style="background:#09070c;color:#f8f1e5;font-family:Arial,sans-serif;padding:20px;max-width:1100px;margin:auto">
<h1 style="color:#d7a642">READ — Seasons & Episodes</h1><p>Yeh existing admin login use karta hai. Existing messages/admin data alag aur safe hai.</p>
<p><a href="/admin" style="color:#e5b94d">← Existing admin / messages</a> · <a href="/" style="color:#e5b94d">Fanpage</a> · <a href="/read" style="color:#e5b94d">Public READ</a></p>
<section style="border:1px solid #6b4b27;border-radius:10px;padding:16px;margin:18px 0"><h2>Add Season</h2>
<form method="post" action="/admin/read/season/add"><input type="hidden" name="csrf_token" value="{{ token }}">
<label>Series</label><br><select name="series_slug"><option value="house-of-the-dragon">House of the Dragon</option><option value="game-of-thrones">Game of Thrones</option></select><br><br>
<label>Season title</label><br><input name="title" required maxlength="160" placeholder="Season 1"><br><br>
<label>Season number</label><br><input type="number" name="season_number" min="1" value="1" required><br><br>
<label>Description</label><br><textarea name="description" maxlength="3000" rows="3" style="width:min(700px,100%)"></textarea><br><br>
<label>Cover image URL</label><br><input type="url" name="cover_url" maxlength="1000" style="width:min(700px,100%)"><br><br>
<label>Display order</label> <input type="number" name="sort_order" value="0"><br><br><label><input type="checkbox" name="published" checked> Published</label><br><br><button>Add Season</button></form></section>
{% for s in seasons %}<section style="border:1px solid #6b4b27;border-radius:10px;padding:16px;margin:18px 0"><h2>{{ s['series_slug']|replace('-',' ')|title }} — {{ s['title'] }} (ID {{ s['id'] }})</h2>
<form method="post" action="/admin/read/season/{{ s['id'] }}/save"><input type="hidden" name="csrf_token" value="{{ token }}">
<select name="series_slug"><option value="house-of-the-dragon" {{ 'selected' if s['series_slug']=='house-of-the-dragon' else '' }}>House of the Dragon</option><option value="game-of-thrones" {{ 'selected' if s['series_slug']=='game-of-thrones' else '' }}>Game of Thrones</option></select>
<input name="title" required value="{{ s['title'] }}" maxlength="160"><label>Season #</label><input type="number" name="season_number" min="1" value="{{ s['season_number'] }}" style="width:75px"><label>Order</label><input type="number" name="sort_order" value="{{ s['sort_order'] }}" style="width:75px"><br><br>
<textarea name="description" rows="2" style="width:100%">{{ s['description'] }}</textarea><br><label>Cover URL</label><br><input type="url" name="cover_url" value="{{ s['cover_url'] }}" style="width:100%"><br><br>
<label><input type="checkbox" name="published" {{ 'checked' if s['published'] else '' }}> Published</label> <button>Save season</button></form>
<form method="post" action="/admin/read/season/{{ s['id'] }}/delete" onsubmit="return confirm('Season ke saare episodes bhi delete honge. Continue?')"><input type="hidden" name="csrf_token" value="{{ token }}"><button>Delete season + episodes</button></form>
<h3>Episodes</h3>{% for e in s['episodes'] %}<article style="border-top:1px solid #49331f;padding:12px 0"><form method="post" action="/admin/read/episode/{{ e['id'] }}/save"><input type="hidden" name="csrf_token" value="{{ token }}">
<label>Title</label><br><input name="title" required maxlength="180" value="{{ e['title'] }}" style="width:100%"><br><br>
<label>Episode #</label><input type="number" name="episode_number" min="1" value="{{ e['episode_number'] }}" style="width:75px"><label>Order</label><input type="number" name="sort_order" value="{{ e['sort_order'] }}" style="width:75px"><br><br>
<label>Description</label><br><textarea name="description" rows="2" style="width:100%">{{ e['description'] }}</textarea><br>
<label>Thumbnail URL</label><br><input type="url" name="thumbnail_url" value="{{ e['thumbnail_url'] }}" style="width:100%"><br>
<label>Video URL (YouTube, Vimeo player, or direct MP4/WebM)</label><br><input type="url" name="video_url" value="{{ e['video_url'] }}" style="width:100%"><br><br>
<label><input type="checkbox" name="published" {{ 'checked' if e['published'] else '' }}> Published</label> <button>Save episode</button></form>
<form method="post" action="/admin/read/episode/{{ e['id'] }}/delete" onsubmit="return confirm('Delete episode?')"><input type="hidden" name="csrf_token" value="{{ token }}"><button>Delete episode</button></form></article>{% else %}<p>No episodes yet.</p>{% endfor %}
<h3>Add episode to this season</h3><form method="post" action="/admin/read/episode/add"><input type="hidden" name="csrf_token" value="{{ token }}"><input type="hidden" name="season_id" value="{{ s['id'] }}">
<label>Episode title</label><br><input name="title" required maxlength="180" style="width:100%"><br><br><label>Episode number</label><br><input type="number" name="episode_number" min="1" value="1"><br><br>
<label>Description</label><br><textarea name="description" rows="3" style="width:100%"></textarea><br><label>Thumbnail URL</label><br><input type="url" name="thumbnail_url" style="width:100%"><br>
<label>Video URL</label><br><input type="url" name="video_url" style="width:100%"><br><br><label><input type="checkbox" name="published" checked> Published</label> <label>Order <input type="number" name="sort_order" value="0" style="width:75px"></label><br><br><button>Add episode</button></form>
</section>{% endfor %}</body></html>"""

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>READ THE REALM | The Dragon Realm</title>
<style>
:root{color-scheme:dark;--gold:#d7a642;--bg:#09070c;--line:#604421}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#2b1715,#09070c 55%);color:#f8f1e5;font-family:Georgia,serif}a{color:inherit;text-decoration:none}.top{padding:22px 5%;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:18px;align-items:center;flex-wrap:wrap}.brand{color:var(--gold);letter-spacing:3px;font-weight:bold}.wrap{width:min(1100px,92%);margin:35px auto 70px}h1{font-size:clamp(2rem,5vw,4rem);color:var(--gold);margin:0 0 10px}h2{color:var(--gold)}.muted{color:#c2b6a7;line-height:1.65}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:18px;margin-top:28px}.card{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:rgba(25,16,25,.92)}.card img{width:100%;height:160px;object-fit:cover;background:#21151b}.cardbody{padding:18px}.btn{display:inline-block;padding:10px 15px;border:1px solid var(--gold);border-radius:6px;color:var(--gold);margin:8px 8px 0 0}.primary{background:var(--gold);color:#160d08;font-weight:bold}.crumb{color:#c7a45d;margin-bottom:22px}.player{width:100%;aspect-ratio:16/9;background:#000;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:22px 0}.player iframe,.player video{width:100%;height:100%;border:0}.episode-row{padding:15px;border:1px solid var(--line);border-radius:8px;margin:10px 0;background:#150f16;display:block}.empty{border:1px dashed var(--line);padding:24px;border-radius:10px;color:#d4c3ad}
</style></head><body><header class="top"><a class="brand" href="/">THE DRAGON REALM</a><a class="btn" href="/">← BACK TO FANPAGE</a></header><main class="wrap">
{% if mode == 'home' %}<h1>READ THE REALM</h1><p class="muted">Choose a saga, then explore seasons and episodes. New content appears here after the admin publishes it.</p><div class="grid">
<a class="card" href="/read/house-of-the-dragon"><img src="https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1000&q=80" alt="Fantasy"><div class="cardbody"><h2>HOUSE OF THE DRAGON</h2><p class="muted">Fire, blood, and the Targaryen civil war.</p><span class="btn primary">EXPLORE SEASONS</span></div></a>
<a class="card" href="/read/game-of-thrones"><img src="https://images.unsplash.com/photo-1519681393784-d120267933ba?auto=format&fit=crop&w=1000&q=80" alt="Winter fantasy"><div class="cardbody"><h2>GAME OF THRONES</h2><p class="muted">The great houses fight for the Iron Throne.</p><span class="btn primary">EXPLORE SEASONS</span></div></a></div>
{% elif mode == 'series' %}<div class="crumb"><a href="/read">READ</a> / {{ series[selected_series] }}</div><h1>{{ series[selected_series] }}</h1><p class="muted">Select a season.</p><div class="grid">{% for s in seasons %}<a class="card" href="/read/season/{{ s['id'] }}">{% if s['cover_url'] %}<img src="{{ s['cover_url'] }}" alt="">{% else %}<div style="height:110px;background:linear-gradient(135deg,#321a20,#09070c)"></div>{% endif %}<div class="cardbody"><h2>{{ s['title'] }}</h2><p class="muted">{{ s['description'] }}</p><span class="btn">VIEW EPISODES</span></div></a>{% else %}<div class="empty">No seasons published yet. Add them in Admin → READ Manager.</div>{% endfor %}</div>
{% elif mode == 'season' %}<div class="crumb"><a href="/read">READ</a> / <a href="/read/{{ selected_series }}">{{ series[selected_series] }}</a> / {{ selected_season['title'] }}</div><h1>{{ selected_season['title'] }}</h1><p class="muted">{{ selected_season['description'] }}</p>{% for e in episodes %}<a class="episode-row" href="/read/episode/{{ e['id'] }}"><strong>EPISODE {{ e['episode_number'] }} — {{ e['title'] }}</strong><p class="muted">{{ e['description'] }}</p></a>{% else %}<div class="empty">No episodes published in this season yet.</div>{% endfor %}
{% else %}<div class="crumb"><a href="/read">READ</a> / <a href="/read/{{ selected_series }}">{{ series[selected_series] }}</a> / Season {{ episode['season_number'] }} / Episode {{ episode['episode_number'] }}</div><h1>{{ episode['title'] }}</h1><p class="muted">{{ episode['season_title'] }} · Episode {{ episode['episode_number'] }}</p><p class="muted">{{ episode['description'] }}</p>
{% set video = episode['video_url'] %}{% if video %}<div class="player">
{% if '.mp4' in video.lower() or '.webm' in video.lower() or '.ogg' in video.lower() %}<video controls preload="metadata" src="{{ video }}"></video>
{% elif 'youtube.com/embed/' in video or 'player.vimeo.com/video/' in video %}<iframe src="{{ video }}" title="{{ episode['title'] }}" allowfullscreen loading="lazy"></iframe>
{% elif 'youtu.be/' in video %}<iframe src="https://www.youtube-nocookie.com/embed/{{ video.split('youtu.be/')[1].split('?')[0] }}" title="{{ episode['title'] }}" allowfullscreen loading="lazy"></iframe>
{% elif 'youtube.com/watch' in video %}<iframe src="https://www.youtube-nocookie.com/embed/{{ video.split('v=')[1].split('&')[0] }}" title="{{ episode['title'] }}" allowfullscreen loading="lazy"></iframe>
{% else %}<div style="padding:28px"><p>This video link may not support embedding.</p><a class="btn primary" href="{{ video }}" target="_blank" rel="noopener">OPEN VIDEO</a></div>{% endif %}</div>{% else %}<div class="empty">Video not added yet. Admin can add a video URL.</div>{% endif %}
<h2>Episodes</h2>{% for e in episode_list %}<a class="episode-row" href="/read/episode/{{ e['id'] }}">Episode {{ e['episode_number'] }} — {{ e['title'] }}</a>{% endfor %}{% endif %}</main></body></html>"""
