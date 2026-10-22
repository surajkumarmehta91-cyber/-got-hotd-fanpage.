THE DRAGON REALM — READ FEATURE
================================
Use these files to add the READ section while keeping the existing homepage, gallery,
videos, messages, and admin login. This uses the existing admin login/session and the
same Neon DATABASE_URL. It adds only read_seasons and read_episodes tables.

Deploy steps:
1. Back up your current GitHub files.
2. Replace app.py, index.html, style.css, script.js, requirements.txt with the matching files.
3. Add read_feature.py to the same folder as app.py.
4. Do NOT upload .env or secrets.
5. Commit and push; wait for Render to redeploy.
6. Open /admin and log in as usual. Then open /admin/read to manage seasons and episodes.
7. Public READ pages: /read, /read/house-of-the-dragon, /read/game-of-thrones.

Admin supports add/edit/delete seasons and episodes, display order, published/draft status,
descriptions, cover/thumbnail URLs, and video URLs. Existing tables are not dropped or changed.
Video is linked/embedded, not uploaded. Use YouTube URLs, Vimeo player URLs, or direct MP4/WebM URLs.
