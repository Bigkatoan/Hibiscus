"""mkdocs hooks for the Hibiscus docs site (referenced from mkdocs.yml).

The site reuses assets that live outside ``docs/`` instead of copying them into it:

* ``assets/brand/*``            -> ``assets/brand/``  (banners, logo, favicons; rendered by
  ``tools/brand.py`` from the synced hibiscus-assets sprites)
* ``frontend/public/fonts/*``   -> ``assets/fonts/``  (self-hosted Nunito woff2 +
  its OFL licence, the same files the web UI ships)

Files are registered in ``on_files`` so ``mkdocs build --strict`` validates links to them and
``mkdocs serve`` picks them up.

Relative Markdown links that leave ``docs/`` (for example ``../../worker/train/log_patterns.py``
from a spec) point at source files, not pages: ``on_page_markdown`` rewrites them to the file on
GitHub so they work on the site and still work when browsing the repository.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path
from typing import Any

from mkdocs.structure.files import File, Files

REPO_BLOB = "https://github.com/Bigkatoan/Hibiscus/blob/main/"
REPO_TREE = "https://github.com/Bigkatoan/Hibiscus/tree/main/"
_LINK = re.compile(r"(\]\()(\.\./[^)\s#]+)(#[^)\s]*)?(\))")

_SOURCES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("assets/brand", "assets/brand", ("*.png", "*.svg", "*.ico")),
    ("frontend/public/fonts", "assets/fonts", ("nunito-*.woff2", "OFL-Nunito.txt")),
)


def on_files(files: Files, config: Any) -> Files:
    root = Path(config.config_file_path).resolve().parent
    for src_dir, dest_dir, patterns in _SOURCES:
        base = root / src_dir
        for pattern in patterns:
            for path in sorted(base.glob(pattern)):
                uri = f"{dest_dir}/{path.name}"
                if files.get_file_from_path(uri) is None:
                    files.append(File.generated(config, uri, abs_src_path=str(path)))
    return files


def on_page_markdown(markdown: str, page: Any, config: Any, files: Files) -> str:
    root = Path(config.config_file_path).resolve().parent
    docs = Path(config.docs_dir).resolve()
    page_dir = posixpath.dirname(page.file.src_uri)

    def fix(m: re.Match[str]) -> str:
        target = (docs / page_dir / m.group(2)).resolve()
        try:
            target.relative_to(docs)
            return m.group(0)  # stays inside docs/: mkdocs validates it
        except ValueError:
            pass
        try:
            rel = target.relative_to(root).as_posix()
        except ValueError:
            return m.group(0)
        base = REPO_TREE if target.is_dir() else REPO_BLOB
        return f"{m.group(1)}{base}{rel}{m.group(3) or ''}{m.group(4)}"

    return _LINK.sub(fix, markdown)
