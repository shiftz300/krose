"""Bounded metadata reads. These files contain names/order, never Python code."""
import json


def load_catalog(folder):
    def read(name):
        path = folder / name
        if path.is_symlink(): raise ValueError('Controller metadata symlink')
        with path.open('rb') as stream:
            data = stream.read(4 * 1024 * 1024 + 1)
        if len(data) > 4 * 1024 * 1024: raise ValueError('Controller catalog too large')
        try:
            return json.loads(data)
        except (ValueError, RecursionError) as error:
            raise ValueError('Invalid controller catalog') from error
    order, catalog = read('program_order.json'), read('programs.json')
    if not isinstance(catalog, list) or not 1 <= len(catalog) <= 32768:
        raise ValueError('Invalid controller catalog count')
    if any(not isinstance(row, list) or len(row) != 3 or
           any(not isinstance(value, str) or len(value) > 256 for value in row) for row in catalog):
        raise ValueError('Invalid controller catalog entry')
    if not isinstance(order, list) or len(order) != len(catalog) or any(type(i) is not int for i in order) or sorted(order) != list(range(len(catalog))):
        raise ValueError('Invalid controller program order')
    return order, catalog
