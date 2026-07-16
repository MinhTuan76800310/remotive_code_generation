from bmgen_eca.signals import parse_signal_id


def test_parse_ok():
    sid, diag = parse_signal_id("[BodyCAN]DoorStatus.TargetPosition")
    assert diag is None
    assert sid is not None
    assert sid.bus == "BodyCAN"
    assert sid.frame == "DoorStatus"
    assert sid.signal == "TargetPosition"
    assert sid.raw == "[BodyCAN]DoorStatus.TargetPosition"


def test_parse_bad_no_brackets():
    sid, diag = parse_signal_id("DoorStatus.TargetPosition")
    assert sid is None
    assert diag is not None
    assert diag.code == "E_BAD_SIGNAL_ID"


def test_parse_bad_no_dot():
    sid, diag = parse_signal_id("[BodyCAN]DoorStatus")
    assert sid is None and diag.code == "E_BAD_SIGNAL_ID"
