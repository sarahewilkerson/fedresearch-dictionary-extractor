from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fedresearch-dictionary-extractor")
except PackageNotFoundError:
    __version__ = "0.3.0"

SCHEMA_VERSION = "1"
