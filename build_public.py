#!/usr/bin/env python3
"""Build script to assemble the deployable public directory for Netlify.
Ensures both root-relative (/styles.css) and prefix-relative (/static/styles.css)
links resolve cleanly, alongside all HTML views, assets, and design system tokens.
"""
from __future__ import annotations
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"

def main():
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True, exist_ok=True)

    # 1. Copy files from static/ to root of public/
    static_src = ROOT / "static"
    if static_src.exists():
        for item in static_src.iterdir():
            if item.is_file():
                shutil.copy2(item, PUBLIC / item.name)

    # 2. Also keep a public/static/ folder so /static/* links always work
    public_static = PUBLIC / "static"
    public_static.mkdir(parents=True, exist_ok=True)
    if static_src.exists():
        for item in static_src.iterdir():
            if item.is_file():
                shutil.copy2(item, public_static / item.name)

    # 2b. Sub-folders of static/ (e.g. static/samples) for both URL styles
    for item in static_src.iterdir() if static_src.exists() else []:
        if item.is_dir():
            shutil.copytree(item, PUBLIC / item.name, dirs_exist_ok=True)
            shutil.copytree(item, public_static / item.name, dirs_exist_ok=True)

    # 3. Copy Logo Design to public/Logo Design and public/static/Logo Design
    logo_src = ROOT / "Logo Design"
    if logo_src.exists():
        shutil.copytree(logo_src, PUBLIC / "Logo Design", dirs_exist_ok=True)
        shutil.copytree(logo_src, public_static / "Logo Design", dirs_exist_ok=True)

    # 4. Copy assets/
    assets_src = ROOT / "assets"
    if assets_src.exists():
        shutil.copytree(assets_src, PUBLIC / "assets", dirs_exist_ok=True)
        shutil.copytree(assets_src, public_static / "assets", dirs_exist_ok=True)

    # 5. Copy design tokens and DESIGN.md
    for f in ["DESIGN.md", "design-tokens.json"]:
        src_file = ROOT / f
        if src_file.exists():
            shutil.copy2(src_file, PUBLIC / f)
            shutil.copy2(src_file, public_static / f)

    # 6. Copy studio_v6/static to public/studio
    studio_src = ROOT / "studio_v6" / "static"
    if studio_src.exists():
        shutil.copytree(studio_src, PUBLIC / "studio", dirs_exist_ok=True)

    # 7. Copy auto_studio/static to public/auto
    auto_src = ROOT / "auto_studio" / "static"
    if auto_src.exists():
        shutil.copytree(auto_src, PUBLIC / "auto", dirs_exist_ok=True)

    # 8. Create Netlify _redirects file
    redirects_content = """# Netlify Clean URLs and Routing Rules
/landing        /landing.html       200
/community      /community.html     200
/admin          /admin.html         200
/donate         /donate.html        200
/updates        /updates.html       200
/dashboard      /index.html         200
/tokens         /tokens.css         200
/design-tokens  /design-tokens.json 200

# Fallback static routing
/static/*       /static/:splat      200
"""
    # Netlify cannot run the Python backend: proxy API traffic to it (e.g. Railway).
    # Set API_ORIGIN=https://<backend>.up.railway.app in Netlify build env, and PUBLIC_BASE_URL=<this Netlify URL> on the backend.
    import os
    api_origin = os.getenv("API_ORIGIN", "").strip().rstrip("/")
    if api_origin:
        if not api_origin.startswith("https://"):
            raise SystemExit("API_ORIGIN must start with https://")
        proxy = "\n".join(f"{path}  {api_origin}{target}  200!" for path, target in [
            ("/api/*", "/api/:splat"), ("/media/*", "/media/:splat"), ("/health", "/health"),
            ("/studio/*", "/studio/:splat"), ("/ws/*", "/ws/:splat")])
        # Proxy rules must come first so they win over static files.
        redirects_content = "# Backend proxy (API_ORIGIN)\n" + proxy + "\n/  /index.html  200\n\n" + redirects_content
    else:
        print("WARNING: API_ORIGIN not set - the dashboard will load but login/API calls will fail.")
    (PUBLIC / "_redirects").write_text(redirects_content, encoding="utf-8")

    # 9. Create Netlify _headers file
    headers_content = """/*
  X-Frame-Options: SAMEORIGIN
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin

/*.css
  Cache-Control: public, max-age=31536000, immutable

/*.js
  Cache-Control: public, max-age=31536000, immutable

/*.png
  Cache-Control: public, max-age=31536000, immutable

/*.html
  Cache-Control: public, max-age=0, must-revalidate
"""
    (PUBLIC / "_headers").write_text(headers_content, encoding="utf-8")

    # 10. Cache-bust: .js/.css are cached for a year (immutable), so every HTML reference
    # gets ?v=<content hash>. A changed file always gets a new URL; unchanged files stay cached.
    import hashlib, re as _re
    ref = _re.compile(r'((?:/static/|/)[\w./-]+\.(?:js|css))(?:\?v=[\w.-]*)?(?=["\'])')
    def _bust(m):
        path = m.group(1)
        f = PUBLIC / path.lstrip('/')
        if not f.is_file():
            return m.group(0)
        return f"{path}?v={hashlib.sha256(f.read_bytes()).hexdigest()[:10]}"
    busted = 0
    for html in PUBLIC.rglob('*.html'):
        text = html.read_text(encoding='utf-8')
        new = ref.sub(_bust, text)
        if new != text:
            html.write_text(new, encoding='utf-8'); busted += 1
    print(f"Cache-busted asset URLs in {busted} HTML files.")

    print(f"Public build directory ready at {PUBLIC} with {len(list(PUBLIC.rglob('*')))} files.")

if __name__ == "__main__":
    main()
