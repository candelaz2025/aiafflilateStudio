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

    print(f"Public build directory ready at {PUBLIC} with {len(list(PUBLIC.rglob('*')))} files.")

if __name__ == "__main__":
    main()
