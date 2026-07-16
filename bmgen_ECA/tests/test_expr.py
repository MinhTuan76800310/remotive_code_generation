from bmgen_eca.expr import (
    Lit,
    StateRef,
    ParamRef,
    SignalRef,
    Compare,
    Call,
    parse_expr,
    free_refs,
    lower_expr,
)


def test_parse_true():
    e, d = parse_expr("true")
    assert not d and isinstance(e, Lit) and e.value is True


def test_parse_false():
    e, d = parse_expr("false")
    assert not d and isinstance(e, Lit) and e.value is False


def test_parse_state_ref():
    e, d = parse_expr("$state.target_pos")
    assert not d
    assert isinstance(e, StateRef) and e.name == "target_pos"


def test_parse_param_ref():
    e, d = parse_expr("$para.move_step")
    assert not d
    assert isinstance(e, ParamRef) and e.name == "move_step"


def test_bare_ident():
    e, d = parse_expr("$target_pos")
    assert e is None
    assert any(x.code == "E_BARE_IDENT" for x in d)


def test_unknown_fn():
    e, d = parse_expr("clamp(1, 2)")
    assert any(x.code == "E_UNKNOWN_FUNCTION" for x in d)


def test_lower_clamp_payload():
    text = "max($para.min_pos, min($para.max_pos, $[BodyCAN]DoorStatus.TargetPosition))"
    e, d = parse_expr(text)
    assert not d
    src = lower_expr(e)
    assert "np.maximum.reduce" in src
    assert "np.minimum.reduce" in src
    assert "self.min_pos" in src
    assert "self.max_pos" in src
    assert "target_position" in src  # leaf local


def test_lower_move_step():
    text = (
        "$state.current_pos + max(0 - $para.move_step, "
        "min($para.move_step, $state.target_pos - $state.current_pos))"
    )
    e, d = parse_expr(text)
    assert not d
    src = lower_expr(e)
    assert "self.current_pos" in src and "self.move_step" in src


def test_abs_and_compare():
    text = "abs($state.target_pos - $state.current_pos) > $para.pos_tolerance"
    e, d = parse_expr(text)
    assert not d
    assert isinstance(e, Compare)
    src = lower_expr(e)
    assert "np.abs" in src
    assert "self.target_pos" in src
    assert "self.current_pos" in src
    assert "self.pos_tolerance" in src
    assert ">" in src


def test_free_refs():
    text = "max($para.min_pos, min($para.max_pos, $[BodyCAN]DoorStatus.TargetPosition))"
    e, d = parse_expr(text)
    assert not d
    refs = free_refs(e)
    kinds = {k for k, _ in refs}
    assert "para" in kinds
    assert "rx" in kinds
    assert ("para", "min_pos") in refs
    assert ("para", "max_pos") in refs
    assert ("rx", "[BodyCAN]DoorStatus.TargetPosition") in refs


def test_signal_ref_with_locals():
    text = "$[BodyCAN]DoorStatus.TargetPosition"
    e, d = parse_expr(text)
    assert not d
    assert isinstance(e, SignalRef)
    src = lower_expr(e, signal_locals={e.signal.raw: "tp"})
    assert src == "tp"


def test_and_or_bool():
    e, d = parse_expr("true and false or true")
    assert not d
    src = lower_expr(e)
    assert "and" in src and "or" in src
    assert "True" in src and "False" in src


def test_bad_expr_unbalanced():
    e, d = parse_expr("(1 + 2")
    assert e is None or d
    assert any(x.code == "E_BAD_EXPR" for x in d)
