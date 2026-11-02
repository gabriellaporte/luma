import importlib
import pkgutil

import pytest

import luma

MODULES = [
    module.name
    for module in pkgutil.walk_packages(luma.__path__, prefix="luma.")
    if not module.name.endswith("__main__")
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name, qapp):
    importlib.import_module(name)
