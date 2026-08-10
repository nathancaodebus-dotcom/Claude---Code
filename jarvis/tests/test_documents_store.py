from core.store import Store


def test_register_and_get_document(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.register_document("pptx", "my-deck", "/outputs/my-deck.pptx")

    doc = store.get_document("my-deck")
    assert doc.kind == "pptx"
    assert doc.path == "/outputs/my-deck.pptx"


def test_get_document_missing_returns_none(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    assert store.get_document("nope") is None


def test_register_document_upserts_on_name_conflict(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.register_document("pptx", "my-deck", "/outputs/v1.pptx")
    store.register_document("pptx", "my-deck", "/outputs/v2.pptx")

    doc = store.get_document("my-deck")
    assert doc.path == "/outputs/v2.pptx"


def test_list_documents_filtered_by_kind(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.register_document("pptx", "deck", "/outputs/deck.pptx")
    store.register_document("docx", "report", "/outputs/report.docx")

    assert [d.name for d in store.list_documents(kind="pptx")] == ["deck"]
    assert {d.name for d in store.list_documents()} == {"deck", "report"}
