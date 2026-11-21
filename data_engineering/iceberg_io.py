from pathlib import Path
from urllib.request import url2pathname

from pyiceberg.io.pyarrow import PyArrowFileIO


class LocalFileIO(PyArrowFileIO):
    """Translate escaped file URIs into native paths before passing them to Arrow."""

    @staticmethod
    def parse_location(location, properties=None):
        scheme, authority, path = PyArrowFileIO.parse_location(location, properties or {})
        if location.startswith("file:") and scheme == "file" and not authority:
            path = Path(url2pathname(path)).as_posix()
        return scheme, authority, path
