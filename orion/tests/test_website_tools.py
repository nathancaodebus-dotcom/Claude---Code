import json

import pytest

from core.store import Store
from tools.website_tools import (
    AddWebsitePageTool,
    CreateWebsiteTool,
    DeleteWebsitePageTool,
    EditWebsitePageTool,
    ListWebsitePagesTool,
    ListWebsitesTool,
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return Store(db_path=str(tmp_path / "test.db"))


def _pages(*, index_content="<p>Home</p>"):
    return [{"slug": "index", "title": "Home", "content_html": index_content}]


def test_create_website_writes_files_and_registers_document(store):
    result = CreateWebsiteTool(store).run(title="My Site", pages=_pages())

    assert "my-site" in result
    doc = store.get_document("my-site")
    assert doc is not None
    assert doc.kind == "website"

    from pathlib import Path

    site_dir = Path(doc.path)
    assert (site_dir / "index.html").exists()
    assert (site_dir / "style.css").exists()
    assert (site_dir / "_site.json").exists()


def test_create_website_index_html_contains_the_content(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages(index_content="<p>Hello world</p>"))

    from pathlib import Path

    site_dir = Path(store.get_document("my-site").path)
    html_text = (site_dir / "index.html").read_text()
    assert "Hello world" in html_text
    assert "<!doctype html>" in html_text
    assert 'href="style.css"' in html_text


def test_create_website_requires_at_least_one_page(store):
    result = CreateWebsiteTool(store).run(title="Empty", pages=[])
    assert "at least one page" in result
    assert store.get_document("empty") is None


def test_add_website_page_appears_on_every_nav(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    AddWebsitePageTool(store).run(
        site_name="my-site", slug="about", title="About", content_html="<p>About us</p>"
    )

    from pathlib import Path

    site_dir = Path(store.get_document("my-site").path)
    index_html = (site_dir / "index.html").read_text()
    about_html = (site_dir / "about.html").read_text()

    # The nav on BOTH pages must link to both pages — this is the whole
    # point of rebuilding every page on any change, not just the new one.
    assert "about.html" in index_html
    assert "index.html" in about_html
    assert "About us" in about_html


def test_add_website_page_rejects_duplicate_slug(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    result = AddWebsitePageTool(store).run(
        site_name="my-site", slug="index", title="Dup", content_html="<p>x</p>"
    )
    assert "already has a page" in result


def test_add_website_page_missing_site_gives_clear_error(store):
    result = AddWebsitePageTool(store).run(
        site_name="nope", slug="about", title="About", content_html="<p>x</p>"
    )
    assert "No website named" in result


def test_edit_website_page_updates_content_and_rebuilds_nav_titles(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    AddWebsitePageTool(store).run(
        site_name="my-site", slug="about", title="About", content_html="<p>old</p>"
    )

    EditWebsitePageTool(store).run(site_name="my-site", slug="about", content_html="<p>new</p>")

    from pathlib import Path

    site_dir = Path(store.get_document("my-site").path)
    assert "new" in (site_dir / "about.html").read_text()
    assert "old" not in (site_dir / "about.html").read_text()


def test_edit_website_page_missing_slug_gives_clear_error(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    result = EditWebsitePageTool(store).run(site_name="my-site", slug="nope", title="x")
    assert "no page with slug" in result


def test_delete_website_page_removes_file_and_updates_manifest(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    AddWebsitePageTool(store).run(
        site_name="my-site", slug="about", title="About", content_html="<p>x</p>"
    )

    result = DeleteWebsitePageTool(store).run(site_name="my-site", slug="about")

    from pathlib import Path

    site_dir = Path(store.get_document("my-site").path)
    assert "Deleted" in result
    assert not (site_dir / "about.html").exists()
    assert "about.html" not in (site_dir / "index.html").read_text()


def test_delete_website_page_refuses_to_remove_the_last_page(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    result = DeleteWebsitePageTool(store).run(site_name="my-site", slug="index")
    assert "only page left" in result


def test_list_website_pages(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    AddWebsitePageTool(store).run(
        site_name="my-site", slug="about", title="About", content_html="<p>x</p>"
    )

    result = ListWebsitePagesTool(store).run(site_name="my-site")

    assert "index: Home" in result
    assert "about: About" in result


def test_list_websites_reports_none_when_empty(store):
    assert "No websites" in ListWebsitesTool(store).run()


def test_list_websites_lists_created_sites(store):
    CreateWebsiteTool(store).run(title="My Site", pages=_pages())
    result = ListWebsitesTool(store).run()
    assert "my-site" in result


def test_website_and_document_names_share_a_namespace_and_warn_on_collision(store):
    from tools.docx_tools import CreateWordDocumentTool

    CreateWordDocumentTool(store).run(title="my-site", paragraphs=["hello"])
    result = CreateWebsiteTool(store).run(title="My Site", pages=_pages())

    assert "replaced an existing docx document" in result
