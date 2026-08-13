"""Create and edit simple static websites by voice or text — 'create me a
site about X' then 'add a page about Y' / 'change the about page'.

Deliberately plain HTML/CSS with no build step, no JS framework, and no
external font/CDN dependency: every byte the browser needs is in the two
files it loads (an HTML page + one shared style.css), so pages render
instantly and nothing can break because a CDN went down or a dependency
stopped installing. Claude supplies each page's actual content as semantic
HTML; this module guarantees the surrounding structure (doctype, responsive
meta tag, consistent nav across every page, a tested-looking baseline
CSS with dark-mode support) so quality doesn't depend on getting the
boilerplate right from scratch every time.

Every page in a site links to every other page, so the nav has to be
correct on ALL of them whenever one page is added, edited, or removed —
handled by keeping each site's content in a small `_site.json` manifest and
regenerating every page's HTML from it on any change, rather than trying to
patch one page's file in place.

Sites are tracked by name in the Store (kind='website') the same way
presentations/documents are, so a follow-up command can find the right site
again without repeating its path. Local files only, for now — see the
Store's `path` field once this site is published (level 2, not built yet)
for where it actually lives online.
"""
from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

from core.attachments import push as push_attachment
from core.store import Store
from tools.base import Tool
from tools.document_utils import kind_collision_warning, slugify

WEBSITES_DIR = Path("outputs") / "websites"

_CSS_BASELINE = """:root {
  --bg: #ffffff;
  --fg: #1a1a1a;
  --muted: #6b7280;
  --accent: #2563eb;
  --border: #e5e7eb;
  --max-width: 860px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1115;
    --fg: #e5e7eb;
    --muted: #9ca3af;
    --accent: #60a5fa;
    --border: #262b36;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  line-height: 1.6;
}
.site-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border);
}
.site-header .brand {
  font-weight: 700;
  font-size: 1.25rem;
  color: var(--fg);
  text-decoration: none;
}
.site-header nav {
  display: flex;
  gap: 1.25rem;
  flex-wrap: wrap;
}
.site-header nav a {
  color: var(--muted);
  text-decoration: none;
  font-size: 0.95rem;
}
.site-header nav a:hover,
.site-header nav a.active {
  color: var(--accent);
}
main {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 2.5rem 1.5rem;
}
main h1 {
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  margin-bottom: 1rem;
}
main img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
}
.site-footer {
  text-align: center;
  padding: 2rem 1.5rem;
  color: var(--muted);
  font-size: 0.875rem;
  border-top: 1px solid var(--border);
}
"""


def _site_dir(site_name: str) -> Path:
    return WEBSITES_DIR / site_name


def _manifest_path(site_dir: Path) -> Path:
    return site_dir / "_site.json"


def _load_manifest(site_dir: Path) -> dict:
    return json.loads(_manifest_path(site_dir).read_text(encoding="utf-8"))


def _save_manifest(site_dir: Path, manifest: dict) -> None:
    _manifest_path(site_dir).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _page_filename(slug: str) -> str:
    return "index.html" if slug == "index" else f"{slug}.html"


def _render_nav(pages: list[dict], current_slug: str) -> str:
    links = []
    for page in pages:
        css_class = ' class="active"' if page["slug"] == current_slug else ""
        links.append(f'<a href="{_page_filename(page["slug"])}"{css_class}>{html.escape(page["title"])}</a>')
    return "\n    ".join(links)


def _render_page(manifest: dict, page: dict) -> str:
    nav = _render_nav(manifest["pages"], current_slug=page["slug"])
    return f"""<!doctype html>
<html lang="{manifest['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page['title'])} — {html.escape(manifest['title'])}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="site-header">
  <a class="brand" href="index.html">{html.escape(manifest['title'])}</a>
  <nav>
    {nav}
  </nav>
</header>
<main>
  <h1>{html.escape(page['title'])}</h1>
  {page['content_html']}
</main>
<footer class="site-footer">
  <p>{html.escape(manifest['footer_text'])}</p>
</footer>
</body>
</html>
"""


def _rebuild_all_pages(site_dir: Path, manifest: dict) -> None:
    """Every page's nav lists every other page, so any add/edit/delete has
    to regenerate all of them, not just the one that changed."""
    for page in manifest["pages"]:
        (site_dir / _page_filename(page["slug"])).write_text(_render_page(manifest, page), encoding="utf-8")


def _find_page(manifest: dict, slug: str) -> dict | None:
    return next((p for p in manifest["pages"] if p["slug"] == slug), None)


class CreateWebsiteTool(Tool):
    requires_network = False
    name = "create_website"
    description = (
        "Create a new static website (plain HTML/CSS, no build step) with one or more pages. "
        "Returns the site_name to use in later add_website_page/edit_website_page calls. Local "
        "files only for now — this doesn't publish the site online."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Site title, shown in the header/nav brand."},
            "pages": {
                "type": "array",
                "description": "At least one page. The first page's slug should be 'index' (the home page).",
                "items": {
                    "type": "object",
                    "properties": {
                        "slug": {"type": "string", "description": "URL-safe page id, e.g. 'index', 'about'."},
                        "title": {"type": "string"},
                        "content_html": {
                            "type": "string",
                            "description": "The page body as semantic HTML (p, h2, ul, img, etc.) — no <html>/<body> wrapper.",
                        },
                    },
                    "required": ["slug", "title", "content_html"],
                },
            },
            "footer_text": {"type": "string", "description": "Optional footer line. Default is empty."},
            "lang": {"type": "string", "description": "HTML lang attribute, e.g. 'en' or 'fr'. Default 'en'."},
            "site_name": {
                "type": "string",
                "description": "Optional stable name for this site. Derived from the title if omitted.",
            },
        },
        "required": ["title", "pages"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(
        self,
        title: str,
        pages: list[dict],
        footer_text: str = "",
        lang: str = "en",
        site_name: str | None = None,
    ) -> str:
        if not pages:
            return "A website needs at least one page."

        site_name = site_name or slugify(title)
        site_dir = _site_dir(site_name)
        site_dir.mkdir(parents=True, exist_ok=True)

        (site_dir / "style.css").write_text(_CSS_BASELINE, encoding="utf-8")
        manifest = {"title": title, "footer_text": footer_text, "lang": lang, "pages": pages}
        _save_manifest(site_dir, manifest)
        _rebuild_all_pages(site_dir, manifest)

        previous = self._store.register_document("website", site_name, str(site_dir))
        first_page = _find_page(manifest, "index") or pages[0]
        index_path = site_dir / _page_filename(first_page["slug"])
        push_attachment(str(index_path))
        return (
            f"Created website '{site_name}' with {len(pages)} page(s) at {site_dir}. "
            f"Open {index_path} in a browser to view it.{kind_collision_warning(previous, 'website')}"
        )


class AddWebsitePageTool(Tool):
    requires_network = False
    name = "add_website_page"
    description = "Add a new page to an existing website. Updates the nav on every page of the site."
    input_schema = {
        "type": "object",
        "properties": {
            "site_name": {"type": "string"},
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "content_html": {"type": "string"},
        },
        "required": ["site_name", "slug", "title", "content_html"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, site_name: str, slug: str, title: str, content_html: str) -> str:
        doc = self._store.get_document(site_name)
        if not doc or doc.kind != "website":
            return f"No website named '{site_name}'. Use create_website first."

        site_dir = Path(doc.path)
        manifest = _load_manifest(site_dir)
        if _find_page(manifest, slug) is not None:
            return f"'{site_name}' already has a page with slug '{slug}' — use edit_website_page instead."

        manifest["pages"].append({"slug": slug, "title": title, "content_html": content_html})
        _save_manifest(site_dir, manifest)
        _rebuild_all_pages(site_dir, manifest)
        self._store.touch_document(site_name)
        push_attachment(str(site_dir / _page_filename(slug)))
        return f"Added page '{title}' ({slug}) to '{site_name}' (now {len(manifest['pages'])} pages)."


class EditWebsitePageTool(Tool):
    requires_network = False
    name = "edit_website_page"
    description = "Edit an existing page's title and/or content. Omit a field to leave it unchanged."
    input_schema = {
        "type": "object",
        "properties": {
            "site_name": {"type": "string"},
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "content_html": {"type": "string"},
        },
        "required": ["site_name", "slug"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, site_name: str, slug: str, title: str | None = None, content_html: str | None = None) -> str:
        doc = self._store.get_document(site_name)
        if not doc or doc.kind != "website":
            return f"No website named '{site_name}'."

        site_dir = Path(doc.path)
        manifest = _load_manifest(site_dir)
        page = _find_page(manifest, slug)
        if page is None:
            return f"'{site_name}' has no page with slug '{slug}'."

        if title is not None:
            page["title"] = title
        if content_html is not None:
            page["content_html"] = content_html

        _save_manifest(site_dir, manifest)
        _rebuild_all_pages(site_dir, manifest)
        self._store.touch_document(site_name)
        push_attachment(str(site_dir / _page_filename(slug)))
        return f"Updated page '{slug}' in '{site_name}'."


class DeleteWebsitePageTool(Tool):
    requires_network = False
    name = "delete_website_page"
    description = "Delete a page from a website. Can't delete the last remaining page."
    input_schema = {
        "type": "object",
        "properties": {"site_name": {"type": "string"}, "slug": {"type": "string"}},
        "required": ["site_name", "slug"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, site_name: str, slug: str) -> str:
        doc = self._store.get_document(site_name)
        if not doc or doc.kind != "website":
            return f"No website named '{site_name}'."

        site_dir = Path(doc.path)
        manifest = _load_manifest(site_dir)
        page = _find_page(manifest, slug)
        if page is None:
            return f"'{site_name}' has no page with slug '{slug}'."
        if len(manifest["pages"]) == 1:
            return f"Can't delete '{slug}' — it's the only page left in '{site_name}'."

        manifest["pages"].remove(page)
        (site_dir / _page_filename(slug)).unlink(missing_ok=True)
        _save_manifest(site_dir, manifest)
        _rebuild_all_pages(site_dir, manifest)
        self._store.touch_document(site_name)
        return f"Deleted page '{slug}' from '{site_name}' ({len(manifest['pages'])} pages left)."


class AddWebsiteImageTool(Tool):
    requires_network = False
    name = "add_website_image"
    description = (
        "Copy an image (e.g. one made with generate_image or edit_image) into a website's "
        "'images' folder so it can be referenced from a page's content_html, e.g. "
        "<img src=\"images/photo.png\">. Returns the relative path to use."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "site_name": {"type": "string"},
            "image_path": {"type": "string", "description": "Path to the source image file."},
            "file_name": {
                "type": "string",
                "description": "Optional name to save it as. Derived from the source file name if omitted.",
            },
        },
        "required": ["site_name", "image_path"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, site_name: str, image_path: str, file_name: str | None = None) -> str:
        doc = self._store.get_document(site_name)
        if not doc or doc.kind != "website":
            return f"No website named '{site_name}'. Use create_website first."

        source = Path(image_path)
        if not source.is_file():
            return f"'{image_path}' is not a file."

        images_dir = Path(doc.path) / "images"
        images_dir.mkdir(exist_ok=True)
        dest_name = file_name or source.name
        dest = images_dir / dest_name
        shutil.copyfile(source, dest)

        self._store.touch_document(site_name)
        return f"Copied '{image_path}' into '{site_name}' — reference it as images/{dest_name} in a page's content_html."


class ListWebsitePagesTool(Tool):
    requires_network = False
    name = "list_website_pages"
    description = "List the pages in a website (slug and title)."
    input_schema = {
        "type": "object",
        "properties": {"site_name": {"type": "string"}},
        "required": ["site_name"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, site_name: str) -> str:
        doc = self._store.get_document(site_name)
        if not doc or doc.kind != "website":
            return f"No website named '{site_name}'."

        manifest = _load_manifest(Path(doc.path))
        return "\n".join(f"- {p['slug']}: {p['title']}" for p in manifest["pages"])


class ListWebsitesTool(Tool):
    requires_network = False
    name = "list_websites"
    description = "List all websites Orion has created."
    input_schema = {"type": "object", "properties": {}}

    def __init__(self, store: Store):
        self._store = store

    def run(self) -> str:
        docs = self._store.list_documents(kind="website")
        if not docs:
            return "No websites yet."
        return "\n".join(f"- {d.name} ({d.path})" for d in docs)
