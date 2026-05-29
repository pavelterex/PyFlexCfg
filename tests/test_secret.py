from pyflexcfg.components.misc import Secret

MASK = '********'
PLAINTEXT = 'super-secret-value'


def test_format_spec_is_masked():
    s = Secret(PLAINTEXT)
    formatted = f'{s:>20}'

    assert formatted == MASK, f'format-spec usage leaked plaintext: {formatted!r}'


def test_fstring_is_masked():
    """Regression: `str.__format__` would otherwise leak the underlying string."""
    s = Secret(PLAINTEXT)
    formatted = f'{s}'

    assert formatted == MASK, f'f-string leaked plaintext: {formatted!r}'


def test_repr_is_masked():
    s = Secret(PLAINTEXT)

    assert repr(s) == MASK, f'repr leaked plaintext: {repr(s)!r}'


def test_secret_equality():
    a = Secret('x')
    b = Secret('x')

    assert a == b, 'two Secrets wrapping equal strings must compare equal'


def test_str_is_masked():
    s = Secret(PLAINTEXT)

    assert str(s) == MASK, f'str leaked plaintext: {str(s)!r}'


def test_underlying_value_still_accessible_via_str_methods():
    """Secret is still a str subclass; explicit slicing returns the real data."""
    s = Secret(PLAINTEXT)

    assert s[:5] == 'super', 'slicing must expose the underlying string for caller use'
    assert s == PLAINTEXT, 'equality must compare the underlying value'
