from kb.retriever import load_kb, retrieve, tokenize


def test_kb_loads_all_entries():
    docs = load_kb()
    assert len(docs) >= 30
    ids = [d["id"] for d in docs]
    assert len(ids) == len(set(ids))


def test_kb_entries_have_required_fields():
    for d in load_kb():
        assert {"id", "category", "title", "content", "source", "applies_to"} <= set(d)
        assert d["content"].strip()
        assert isinstance(d["applies_to"], list) and d["applies_to"]
        assert isinstance(d["verified"], bool)


def test_verified_entries_with_url_are_http():
    for d in load_kb():
        if d.get("source_url"):
            assert d["source_url"].startswith("http")


def test_retrieve_hits_category():
    r = retrieve("风速 高处作业 降水 清洗窗口", applies_to="weather", top_k=2)
    assert r
    assert r[0]["id"].startswith("KB-A")
    assert r[0]["score"] > 0


def test_retrieve_respects_applies_to():
    r = retrieve("污损 积灰 损失率", applies_to="soiling", top_k=3)
    assert r
    for item in r:
        doc = next(d for d in load_kb() if d["id"] == item["id"])
        assert "soiling" in doc["applies_to"]


def test_retrieve_returns_empty_for_blank():
    assert retrieve("") == []
    assert retrieve("   ") == []


def test_retrieve_returns_expected_shape():
    r = retrieve("净收益 回本周期 清洗成本", applies_to="economics", top_k=2)
    assert r
    for item in r:
        assert {"id", "title", "category", "snippet", "source", "verified", "score"} <= set(item)


def test_tokenize_chinese_bigrams():
    tokens = tokenize("光伏清洗")
    assert "光伏" in tokens and "伏清" in tokens and "清洗" in tokens