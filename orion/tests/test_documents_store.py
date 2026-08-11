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


def test_register_document_returns_previous_record(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    assert store.register_document("pptx", "budget", "/outputs/budget.pptx") is None

    previous = store.register_document("xlsx", "budget", "/outputs/budget.xlsx")
    assert previous.kind == "pptx"
    assert previous.path == "/outputs/budget.pptx"


def test_register_document_never_leaves_mismatched_kind_and_path(tmp_path):
    store = Store(db_path=str(tmp_path / "test.db"))
    store.register_document("pptx", "budget", "/outputs/budget.pptx")
    store.register_document("xlsx", "budget", "/outputs/budget.xlsx")

    doc = store.get_document("budget")
    assert doc.kind == "xlsx"
    assert doc.path == "/outputs/budget.xlsx"
