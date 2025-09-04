#!/usr/bin/env python3
import argparse, os, re, sys, difflib
from pathlib import Path

VALID_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".avif")
ATTR_RE = re.compile(r'(?P<attr>src|srcset|href)\s*=\s*([\'"])(?P<val>[^\'"]+)\2', re.IGNORECASE)
CSS_URL_RE = re.compile(r'url\(\s*([\'"]?)(?P<val>[^\'")]+)\1\s*\)', re.IGNORECASE)
FIRST_EXT_RE = re.compile(r'\.(jpg|jpeg|png|webp|gif|svg|avif)\b', re.IGNORECASE)

def slug(s: str) -> str:
    s = s.lower()
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'[^a-z0-9\-]+', '', s)
    s = re.sub(r'-{2,}', '-', s).strip('-')
    return s

def find_images_root(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.is_dir():
            return p
        print(f"[!] --images-dir '{explicit}' not found.", file=sys.stderr)
        sys.exit(1)
    for cand in ("images", "public/images", "static/images", "assets/images"):
        p = Path(cand)
        if p.is_dir():
            return p
    print("[!] Could not find an images directory (tried images/, public/images/, static/images/, assets/images/).", file=sys.stderr)
    sys.exit(1)

def build_catalog(images_dir: Path):
    files = []
    for f in images_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in VALID_EXTS:
            files.append(f)
    basenames = {f.name for f in files}
    # map slug(stem) -> basename (first seen wins)
    slug_map = {}
    for f in files:
        s = slug(f.stem)
        slug_map.setdefault(s, f.name)
    return files, basenames, slug_map

def truncate_after_first_ext(name: str) -> str | None:
    m = FIRST_EXT_RE.search(name)
    if not m:
        return None
    return name[: m.end()]

def normalize_url(url: str, make_relative: bool) -> str:
    # strip query/fragment
    url = url.split("?", 1)[0].split("#", 1)[0]
    if make_relative and url.startswith("/"):
        url = url[1:]
    return url

def maybe_fix_url(url: str, images_dir: Path, basenames: set[str], slug_map: dict[str,str],
                  images_web_root: str, make_relative: bool) -> str | None:
    # ignore external/data/mail
    if url.startswith(("http:", "https:", "data:", "mailto:", "#")):
        return None
    norm = normalize_url(url, make_relative)
    # Extract filename
    fname = Path(norm).name
    # If it's already a valid image path pointing to an existing file, keep as-is (but normalize to images_web_root)
    if fname in basenames:
        new_url = f"{images_web_root}{fname}"
        return new_url if new_url != url else None

    # Try truncating to first valid extension (fixes ...jpgxresdefault.jpg... etc.)
    cut = truncate_after_first_ext(fname)
    if cut and cut in basenames:
        return f"{images_web_root}{cut}"

    # Fuzzy match by slug
    s = slug(Path(fname).stem)
    s = re.sub(r'(xresdefault)+', '', s)  # clean repeated tokens
    cand = difflib.get_close_matches(s, slug_map.keys(), n=1, cutoff=0.6)
    if cand:
        return f"{images_web_root}{slug_map[cand[0]]}"

    # If caller referenced a bare name like "minneapolis.webp" and it exists
    if norm == fname and fname in basenames:
        return f"{images_web_root}{fname}"

    return None

def fix_srcset(val: str, **kwargs) -> str:
    parts = [p.strip() for p in val.split(",")]
    out = []
    for part in parts:
        if not part:
            continue
        tokens = part.split()
        url = tokens[0]
        rest = " ".join(tokens[1:]) if len(tokens) > 1 else ""
        new_url = maybe_fix_url(url, **kwargs)
        out.append(((new_url or url) + (" " + rest if rest else "")).strip())
    return ", ".join(out)

def process_html(path: Path, images_dir: Path, basenames: set[str], slug_map: dict[str,str],
                 make_relative: bool, write: bool) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    changed = 0

    images_web_root = ("images/" if make_relative else "/images/")

    # Replace src, href, srcset
    def repl_attr(m):
        nonlocal changed
        attr = m.group("attr").lower()
        val = m.group("val")
        new_val = None
        if attr == "srcset":
            new_val = fix_srcset(val,
                                 images_dir=images_dir,
                                 basenames=basenames,
                                 slug_map=slug_map,
                                 images_web_root=images_web_root,
                                 make_relative=make_relative)
        else:
            # only touch images or obvious image file endings
            if "/images/" in val or val.lower().endswith(VALID_EXTS):
                new_val = maybe_fix_url(val,
                                        images_dir=images_dir,
                                        basenames=basenames,
                                        slug_map=slug_map,
                                        images_web_root=images_web_root,
                                        make_relative=make_relative)
        if new_val and new_val != val:
            changed += 1
            return f'{m.group(1)}="{new_val}"' if m.group(1) else f'{attr}="{new_val}"'
        return m.group(0)

    # Because m.group(1) above is not set, rebuild safely:
    def repl_attr_safe(m):
        nonlocal changed
        attr = m.group("attr")
        quote = '"' if m.group(0).find('"') != -1 else "'"
        val = m.group("val")
        new_val = None
        if attr.lower() == "srcset":
            new_val = fix_srcset(val,
                                 images_dir=images_dir,
                                 basenames=basenames,
                                 slug_map=slug_map,
                                 images_web_root=("images/" if make_relative else "/images/"),
                                 make_relative=make_relative)
        else:
            if "/images/" in val or val.lower().endswith(VALID_EXTS):
                new_val = maybe_fix_url(val,
                                        images_dir=images_dir,
                                        basenames=basenames,
                                        slug_map=slug_map,
                                        images_web_root=("images/" if make_relative else "/images/"),
                                        make_relative=make_relative)
        if new_val and new_val != val:
            changed += 1
            return f'{attr}={quote}{new_val}{quote}'
        return m.group(0)

    new_text = ATTR_RE.sub(repl_attr_safe, text)

    # Replace CSS url(...)
    def repl_css(m):
        nonlocal changed
        val = m.group("val")
        if "/images/" in val or val.lower().endswith(VALID_EXTS):
            new_val = maybe_fix_url(val,
                                    images_dir=images_dir,
                                    basenames=basenames,
                                    slug_map=slug_map,
                                    images_web_root=("images/" if make_relative else "/images/"),
                                    make_relative=make_relative)
            if new_val and new_val != val:
                changed += 1
                return f'url("{new_val}")'
        return m.group(0)

    new_text = CSS_URL_RE.sub(repl_css, new_text)

    if changed and write:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(text, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
    return changed

def main():
    ap = argparse.ArgumentParser(description="Fix broken image links in HTML files.")
    ap.add_argument("--images-dir", help="Path to images directory (default: auto-detect)")
    ap.add_argument("--make-paths-relative", action="store_true",
                    help="Rewrite /images/... to images/... (useful for GitHub Pages subpaths)")
    ap.add_argument("--dry-run", action="store_true", help="Scan and print changes without writing")
    ap.add_argument("--root", default=".", help="Project root to scan (default: .)")
    args = ap.parse_args()

    images_dir = find_images_root(args.images-dir if hasattr(args, "images-dir") else args.images_dir)
    files, basenames, slug_map = build_catalog(images_dir)

    html_files = list(Path(args.root).rglob("*.html"))
    total_changes = 0
    for f in html_files:
        changed = process_html(f, images_dir, basenames, slug_map, args.make_paths_relative, write=not args.dry_run)
        if changed:
            print(f"[fix] {f}  (+{changed} change{'s' if changed!=1 else ''})")
            total_changes += changed

    if total_changes == 0:
        print("No changes needed.")
    else:
        print(f"Done. {total_changes} replacement(s) made.")
        if not args.dry_run:
            print("Backups written alongside files as *.bak")

if __name__ == "__main__":
    main()
