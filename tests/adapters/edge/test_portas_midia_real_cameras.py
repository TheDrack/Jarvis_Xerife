import base64
import tempfile
from pathlib import Path

import pytest

from app.adapters.edge.portas_midia import (
    MediaCaptureEngine,
    is_media_request,
    parse_hls_playlist,
    decode_stream,
)

MASTER_PLAYLIST = """#EXTM3U
#EXT-X-VERSION:4
#EXT-X-STREAM-INF:BANDWIDTH=644571,CODECS="avc1.4d401f",RESOLUTION=1280x720
chunklist_w1531763749.m3u8?t=vO80tcT3TXjV2dOxyPnvodfKg0mZjv0q0rkjhfT4H3x4BaUN52eShbkLpTL3Tox9&td=202611111205
"""

MEDIA_PLAYLIST = """#EXTM3U
#EXT-X-VERSION:4
#EXT-X-TARGETDURATION:7
#EXT-X-MEDIA-SEQUENCE:1284
#EXT-X-DISCONTINUITY-SEQUENCE:0
#EXTINF:6.14,
media_w1531763749_1284.ts?t=vO80tcT3TXjV2dOxyPnvodfKg0mZjv0q0rkjhfT4H3x4BaUN52eShbkLpTL3Tox9&td=202611111205
#EXTINF:6.139,
media_w1531763749_1285.ts?t=vO80tcT3TXjV2dOxyPnvodfKg0mZjv0q0rkjhfT4H3x4BaUN52eShbkLpTL3Tox9&td=202611111205
#EXTINF:6.14,
media_w1531763749_1286.ts?t=vO80tcT3TXjV2dOxyPnvodfKg0mZjv0q0rkjhfT4H3x4BaUN52eShbkLpTL3Tox9&td=202611111205
"""


def test_real_earthcam_master_playlist():
    parsed = parse_hls_playlist(MASTER_PLAYLIST, base_url="https://videos-3.earthcam.com/fecnetwork/28925.flv/")
    assert parsed["type"] == "master"
    assert len(parsed["variants"]) == 1
    v = parsed["variants"][0]
    assert "1280x720" in v["attributes"]
    assert v["uri"].endswith("chunklist_w1531763749.m3u8?t=vO80tcT3TXjV2dOxyPnvodfKg0mZjv0q0rkjhfT4H3x4BaUN52eShbkLpTL3Tox9&td=202611111205")


def test_real_earthcam_media_playlist():
    parsed = parse_hls_playlist(MEDIA_PLAYLIST, base_url="https://videos-3.earthcam.com/fecnetwork/28925.flv/")
    assert parsed["type"] == "media"
    assert parsed["target_duration"] == 7.0
    assert parsed["media_sequence"] == 1284
    segs = parsed["segments"]
    assert len(segs) == 3
    assert segs[0]["sequence"] == 1284
    assert segs[0]["duration"] == 6.14
    assert segs[0]["uri"].endswith("media_w1531763749_1284.ts?t=vO80tcT3TXjV2dOxyPnvodfKg0mZjv0q0rkjhfT4H3x4BaUN52eShbkLpTL3Tox9&td=202611111205")


def test_real_camera_url_is_media():
    url = "https://videos-3.earthcam.com/fecnetwork/28925.flv/playlist.m3u8?t=abc"
    assert is_media_request(url, "application/vnd.apple.mpegurl") is True
    url2 = "https://videos-3.earthcam.com/fecnetwork/28925.flv/media_w1531763749_1284.ts?t=abc"
    assert is_media_request(url2, "video/mp2t") is True


def test_real_ts_segment_decode():
    seg_path = Path(tempfile.gettempdir()) / "scratchpad" / "segment.ts"
    if not seg_path.exists():
        pytest.skip("segment.ts not captured")
    data = seg_path.read_bytes()
    assert data[:1] == b"\x47"  # MPEG-TS sync byte

    import app.adapters.edge.portas_midia as pm
    pm.engine.clear()
    pm.engine.enable()
    engine = pm.engine
    sid = engine.open_stream("https://videos-3.earthcam.com/fecnetwork/28925.flv/media_w1531763749_1284.ts", content_type="video/mp2t", adapter="raw")
    assert sid is not None
    assert engine.append(sid, data) is True
    engine.close_stream(sid)

    probe = decode_stream(sid, mode="probe")
    assert probe.get("success") is True, probe.get("error")
    # Should detect an mpegts stream
    ffprobe = probe.get("ffprobe", "")
    assert "mpegts" in ffprobe.lower() or "h264" in ffprobe.lower()


def test_hls_capture_and_parse_roundtrip():
    engine = MediaCaptureEngine()
    engine.enable()
    sid = engine.open_stream("https://videos-3.earthcam.com/fecnetwork/28925.flv/playlist.m3u8", content_type="application/vnd.apple.mpegurl", adapter="hls")
    assert sid is not None
    assert engine.append(sid, MEDIA_PLAYLIST.encode(), adapter_hint="hls") is True
    pl = engine.hls_playlist(sid)
    assert pl["success"] is True
    assert pl["playlist"]["type"] == "media"
    assert len(pl["playlist"]["segments"]) == 3
    assert engine.get(sid).hls_playlist is not None
