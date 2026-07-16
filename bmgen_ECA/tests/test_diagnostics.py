from bmgen_eca.diagnostics import ERROR_CATALOG, Severity, all_codes

REQUIRED = {
    "E_PARSE", "E_MISSING_ECU_NAME", "E_BAD_SIGNAL_ID", "E_DUP_SYMBOL",
    "E_BARE_IDENT", "E_UNRESOLVED_IDENT", "E_UNKNOWN_FUNCTION",
    "E_TRIGGER_TARGET", "E_TX_TARGET_NOT_IN_CAN_TX", "E_SET_STATE_UNKNOWN",
    "E_BAD_EXPR", "E_BAD_ACTION", "E_BAD_TRIGGER_TYPE",
    "E_MISSING_INIT", "E_BAD_TIMER_INTERVAL", "E_MULTI_BUS_UNSUPPORTED",
    "W_UNUSED_PARAM", "W_UNUSED_STATE", "W_UNUSED_TIMER", "W_SOMEIP_IGNORED",
}

def test_catalog_contains_all_frozen_codes():
    codes = all_codes()
    assert REQUIRED <= codes

def test_codes_are_stable_strings():
    for code, meta in ERROR_CATALOG.items():
        assert code == meta["code"]
        assert meta["severity"] in (Severity.ERROR, Severity.WARNING)
        assert meta["help"]
