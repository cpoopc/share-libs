from cptools_kibana.cli import build_search_query, format_id_query


def test_format_id_query_session_id():
    query, smart = format_id_query("s-abc123")
    assert query == 'sessionId:"s-abc123"'
    assert smart is True


def test_build_search_query_uuid_conversation_id():
    query, smart = build_search_query("10791a9b-0afc-4ab5-acad-fbe0ef3f781c")
    assert query == 'conversationId:"10791a9b-0afc-4ab5-acad-fbe0ef3f781c"'
    assert smart is True


def test_build_search_query_predefined_name():
    query, smart = build_search_query("recent_errors")
    assert "ERROR" in query
    assert smart is False
