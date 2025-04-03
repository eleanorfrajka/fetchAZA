from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("fetchaza")
except PackageNotFoundError:
    __version__ = "unknown"
