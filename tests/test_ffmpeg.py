import pytest

from exporter import ffmpeg

MPD_WITH_OFFSET = """<?xml version="1.0" encoding="utf-8"?>
<MPD mediaPresentationDuration="PT6.0S">
    <Period id="0" start="PT26M10.568S">
        <AdaptationSet contentType="video">
            <Representation id="0" mimeType="video/mp4">
                <SegmentTemplate timescale="1000000" duration="3000000"
                    initialization="init-stream$RepresentationID$.m4s"
                    media="chunk-stream$RepresentationID$-$Number%05d$.m4s"/>
            </Representation>
        </AdaptationSet>
    </Period>
</MPD>
"""


def test_mpd_start_offset_minutes_format(tmp_path):
    path = tmp_path / "session.mpd"
    path.write_text(MPD_WITH_OFFSET, encoding="utf-8")
    assert ffmpeg.mpd_start_offset(str(path)) == pytest.approx(1570.568)


def test_mpd_start_offset_absent(tmp_path):
    path = tmp_path / "session.mpd"
    path.write_text('<MPD><Period id="0" start="PT0S"/></MPD>', encoding="utf-8")
    assert ffmpeg.mpd_start_offset(str(path)) == 0.0


def test_mpd_start_offset_missing_file(tmp_path):
    assert ffmpeg.mpd_start_offset(str(tmp_path / "nope.mpd")) == 0.0


def test_fix_mpd_resets_period_and_strips_nul(tmp_path):
    source = tmp_path / "session.mpd"
    raw = MPD_WITH_OFFSET.replace("PT26M10.568S", "PT26M10.568S").encode("utf-8")
    raw = raw + b"\x00\x00"
    source.write_bytes(raw)
    out = tmp_path / "fixed.mpd"
    result = ffmpeg.fix_mpd(str(source), str(out))
    assert result == str(out)
    text = out.read_text(encoding="utf-8")
    assert 'start="PT0S"' in text
    assert "\x00" not in text


def test_fix_mpd_rewrites_segment_paths_to_absolute(tmp_path):
    source = tmp_path / "session.mpd"
    source.write_text(MPD_WITH_OFFSET, encoding="utf-8")
    out = tmp_path / "fixed.mpd"
    ffmpeg.fix_mpd(str(source), str(out))
    text = out.read_text(encoding="utf-8")
    expected = str(tmp_path)
    assert 'initialization="%s/' % expected in text
    assert 'media="%s/' % expected in text
    assert 'initialization="init-stream' not in text
    assert 'media="chunk-stream' not in text
