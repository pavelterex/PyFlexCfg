import pytest

from pyflexcfg.components.misc import AttrDict


def test_as_dict_does_not_mutate_source():
    inner = AttrDict({'k': 'v'})
    outer = AttrDict({'i': inner})
    _ = outer.as_dict()

    assert isinstance(outer['i'], AttrDict), 'as_dict must not mutate the source'


def test_as_dict_handles_lists_tuples_sets():
    d = AttrDict(
        {
            'lst': [AttrDict({'x': 1}), 2],
            'tpl': (AttrDict({'y': 2}), 3),
            'st': {4, 5},
        },
    )
    result = d.as_dict()

    assert result['lst'] == [{'x': 1}, 2], f'list unwrap failed: {result["lst"]}'
    assert result['tpl'] == ({'y': 2}, 3), f'tuple unwrap failed: {result["tpl"]}'
    assert result['st'] == {4, 5}, f'set unwrap failed: {result["st"]}'


def test_as_dict_unwraps_nested_attrdict():
    inner = AttrDict({'k': 'v'})
    outer = AttrDict({'i': inner, 'n': 1})
    result = outer.as_dict()

    assert type(result) is dict, f'top-level type must be plain dict, got {type(result).__name__}'
    assert type(result['i']) is dict, f'nested type must be plain dict, got {type(result["i"]).__name__}'
    assert result == {'i': {'k': 'v'}, 'n': 1}, f'unexpected as_dict output: {result}'


def test_attribute_get_set():
    d = AttrDict()
    d.foo = 'bar'

    assert d['foo'] == 'bar', 'attribute write must show through dict access'
    assert d.foo == 'bar', 'attribute read must mirror dict value'


def test_init_from_mapping_preserves_values():
    d = AttrDict({'a': 1, 'b': 2})

    assert d.a == 1, f'a mismatch: {dict(d)}'
    assert d.b == 2, f'b mismatch: {dict(d)}'


def test_missing_attribute_raises_attribute_error():
    d = AttrDict()

    with pytest.raises(AttributeError, match='missing'):
        _ = d.missing
