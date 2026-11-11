from app.adapters.edge.portas_midia import MediaCaptureEngine, is_media_request, UmpReader


def test_is_media_request_detects_patterns():
    assert is_media_request("https://example.com/videoplayback?id=1") is True
    assert is_media_request("https://example.com/playlist.m3u8") is True
    assert is_media_request("https://example.com/manifest.mpd") is True
    assert is_media_request("https://example.com/api/foo", "video/mp4") is True
    assert is_media_request("https://example.com/api/foo", "application/json") is False


def test_engine_disabled_by_default():
    engine = MediaCaptureEngine()
    assert engine.enabled is False
    sid = engine.open_stream("https://example.com/videoplayback")
    assert sid is None


def test_engine_captures_when_enabled():
    engine = MediaCaptureEngine(max_streams=4, max_bytes_per_stream=1024, max_total_bytes=4096)
    engine.enable()
    sid = engine.open_stream("https://example.com/videoplayback", content_type="video/mp4", adapter="ump")
    assert sid is not None
    assert engine.append(sid, b"hello") is True
    assert engine.append(sid, b"world") is True
    st = engine.streams()[0]
    assert st["total_bytes"] == 10
    assert st["chunks"] == 2
    assert st["adapter"] == "ump"


def test_backpressure_truncates_stream():
    engine = MediaCaptureEngine(max_bytes_per_stream=1024)
    engine.enable()
    sid = engine.open_stream("https://example.com/videoplayback")
    assert engine.append(sid, b"a" * 1024) is True
    assert engine.append(sid, b"x") is False
    assert engine.get(sid).truncated is True


def test_ump_reader_parses_parts():
    def varint(v):
        return bytes([v])

    buf = varint(20) + varint(3) + b"abc" + varint(21) + varint(4) + b"wxyz"
    r = UmpReader()
    parts = r.feed(buf)
    assert len(parts) == 2
    assert parts[0][0] == 20
    assert parts[1][0] == 21


def test_ump_reader_handles_split():
    def varint(v):
        return bytes([v])

    buf = varint(20) + varint(3) + b"abc" + varint(21) + varint(4) + b"wxyz"
    r = UmpReader()
    p1 = r.feed(buf[:5])
    p2 = r.feed(buf[5:])
    assert len(p1) + len(p2) == 2


def test_clear_resets():
    engine = MediaCaptureEngine()
    engine.enable()
    sid = engine.open_stream("https://example.com/videoplayback")
    engine.append(sid, b"abc")
    assert engine.clear()["removed"] == 1
    assert engine.streams() == []
