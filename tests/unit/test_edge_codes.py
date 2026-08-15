from terrasatch.edge.codes import generate_user_code, hash_device_code, normalize_user_code


def test_user_code_has_readable_shape() -> None:
    code = generate_user_code()
    assert len(code) == 9
    assert code[4] == "-"


def test_user_code_normalization() -> None:
    assert normalize_user_code("abcd1234") == "ABCD-1234"
    assert normalize_user_code("abcd-1234") == "ABCD-1234"


def test_device_code_hash_is_stable_and_not_plaintext() -> None:
    raw = "device-secret-example"
    digest = hash_device_code(raw)
    assert digest == hash_device_code(raw)
    assert raw not in digest
    assert len(digest) == 64
