from app.adapters.edge.portas_midia import MediaCaptureEngine, is_media_request, UmpReader


def test_is_media_request_requires_response_declared_media_type():
    assert is_media_request("https://example.com/videoplayback?id=1") is False
    assert is_media_request("https://example.com/playlist.m3u8") is False
    assert is_media_request("https://example.com/manifest.mpd") is False
    assert is_media_request("https://example.com/api/foo", "video/mp4") is True
    assert is_media_request("https://example.com/api/foo", "application/vnd.apple.mpegurl") is True
    assert is_media_request("https://example.com/api/foo", "application/octet-stream") is False
    assert is_media_request("https://example.com/api/foo", "application/json") is False


def test_media_stream_status_redacts_query_values():
    engine = MediaCaptureEngine()
    engine.enable()
    engine.open_stream(
        "https://video.example/videoplayback?token=secret-token&expire=123",
        content_type="video/mp4",
    )
    status = engine.streams()[0]

    assert status["url"] == (
        "https://video.example/videoplayback?token=%5BREDACTED%5D&expire=%5BREDACTED%5D"
    )
    assert "secret-token" not in str(status)


def test_hls_manifest_metadata_redacts_signed_segment_urls():
    engine = MediaCaptureEngine()
    engine.enable()
    sid = engine.open_stream(
        "https://video.example/master.m3u8?token=manifest-secret",
        content_type="application/vnd.apple.mpegurl",
        adapter="hls",
    )
    stream = engine.get(sid)
    stream.hls_playlist = {
        "segments": [
            {"uri": "https://video.example/segment.ts?token=segment-secret&part=1"}
        ]
    }

    result = engine.hls_playlist(sid)
    assert result["success"] is True
    assert "segment-secret" not in str(result)
    assert "manifest-secret" not in str(result)
    assert "%5BREDACTED%5D" in str(result)


def test_manifest_bytes_are_not_exposed_by_read_bytes():
    engine = MediaCaptureEngine()
    engine.enable()
    sid = engine.open_stream(
        "https://video.example/master.m3u8?token=manifest-secret",
        content_type="application/vnd.apple.mpegurl",
        adapter="hls",
    )
    engine.append(sid, b"#EXTM3U\\nhttps://video.example/segment.ts?token=segment-secret")

    result = engine.read_bytes(sid)
    assert result["success"] is False
    assert "segment-secret" not in str(result)


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
