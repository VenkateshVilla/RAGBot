"""
search_bot.py - tag-based keyword search engine.

How it works
------------
1. A keyword is routed to a folder by its prefix (ROUTES below).
2. Every .txt / .md / .docx file in that folder is scanned once for
   <keyword> ... </keyword> blocks and stored in an in-memory dict.
   Results include the opening and closing tags (include_tags=True).
3. Lookups are O(1) dict reads, so 1000+ keywords cost nothing.
4. The index rebuilds itself automatically when files are added/edited.

To add a new knowledge area, add ONE line to ROUTES and create the folder.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote

BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR / "documents"
INTENTS_FILE = BASE_DIR / "intents.json"

NOT_FOUND = "Keyword not found."

# keyword prefix -> folder name inside documents/
ROUTES = {
    "play": "Playwright",
    "sel": "Selenium",
    "api": "API",
}

SUPPORTED = {".txt", ".md", ".docx"}

# Images: embedded .docx pictures are extracted here; every image in an answer is
# turned into a [[IMAGE:<path-or-url>]] marker that the UI renders as a picture.
IMAGE_CACHE = BASE_DIR / ".image_cache"
IMAGE_EXTS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}
IMG_MD = re.compile(r'!\[([^\]]*)\]\(\s*<?([^)>"]+?)>?\s*(?:"[^"]*")?\s*\)')   # ![alt](path)
IMG_HTML = re.compile(r'<img\b[^>]*?\bsrc=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)  # <img src="path">
IMAGE_TOKEN = re.compile(r"\[\[IMAGE:(.+?)\]\]")

# <tag> ... </tag>; the closing tag must match the opening one (case-insensitive)
TAG_RE = re.compile(r"<([A-Za-z][\w-]*)>(.*?)</\1>", re.DOTALL | re.IGNORECASE)


# --------------------------------------------------------------------------
# File reading
# --------------------------------------------------------------------------
def _save_image(blob: bytes, ext: str) -> str:
    """Cache an image embedded in a .docx and return its marker."""
    ext = ext.lower()
    if ext not in IMAGE_EXTS:
        return f"[unsupported image format: .{ext}]"
    IMAGE_CACHE.mkdir(exist_ok=True)
    target = IMAGE_CACHE / f"{hashlib.sha1(blob).hexdigest()[:16]}.{ext}"
    if not target.exists():
        target.write_bytes(blob)
    return f"[[IMAGE:{target}]]"


def _resolve_image(src: str, base: Path) -> str:
    src = src.strip()
    if src.lower().startswith(("http://", "https://")):
        return src
    return str((base / unquote(src.replace("\\", "/"))).resolve())


def _mark_images(text: str, base: Path) -> str:
    """Rewrite ![alt](path) and <img src="path"> into [[IMAGE:absolute-path]]."""
    repl = lambda m: f"[[IMAGE:{_resolve_image(m.group(m.lastindex), base)}]]"
    return IMG_HTML.sub(repl, IMG_MD.sub(repl, text))


# ---- plain-text / markdown / ASCII table detection ---------------------------------
SEP_ROW = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")  # |---|:--:|
GRID_BORDER = re.compile(r"^\s*\+[-=+:]+\+\s*$")                             # +----+----+
PIPE_ROW = re.compile(r"^\s*\|.*\|\s*$")                                     # | a | b |


def _cells(row: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<!\\)\|", row.strip().strip("|"))]


def _md_table(rows: list[str]) -> str:
    """Pipe rows (first row = header) -> a markdown table."""
    cells = [_cells(r) for r in rows]
    out = ["| " + " | ".join(cells[0]) + " |", "| " + " | ".join(["---"] * len(cells[0])) + " |"]
    return "\n".join(out + ["| " + " | ".join(c) + " |" for c in cells[1:]])


def _split_tables(text: str) -> list[tuple[str, str]]:
    """Split text into ("text", ...) and ("table", markdown) parts."""
    lines, out, buf, i = text.split("\n"), [], [], 0

    def flush():
        if "".join(buf).strip():
            out.append(("text", "\n".join(buf).strip("\n")))
        buf.clear()

    while i < len(lines):
        line, nxt = lines[i], (lines[i + 1] if i + 1 < len(lines) else "")
        if "|" in line and "|" in nxt and SEP_ROW.match(nxt):       # standard markdown table
            j = i + 2
            while j < len(lines) and "|" in lines[j]:
                j += 1
            flush(); out.append(("table", "\n".join(lines[i:j]))); i = j
            continue
        if PIPE_ROW.match(line) or GRID_BORDER.match(line):         # plain-text / ASCII table
            j = i
            while j < len(lines) and (PIPE_ROW.match(lines[j]) or GRID_BORDER.match(lines[j])):
                j += 1
            block = lines[i:j]
            rows = [l for l in block if PIPE_ROW.match(l) and not SEP_ROW.match(l)]
            if len(rows) >= 2 or (rows and any(GRID_BORDER.match(l) for l in block)):
                flush(); out.append(("table", _md_table(rows))); i = j
                continue
        buf.append(line); i += 1
    flush()
    return out


# ---- file reading ------------------------------------------------------------------
def _read_docx(path: Path) -> str:
    try:
        from docx import Document  # pip install python-docx
        from docx.oxml.ns import qn
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:
        print(f"[warn] python-docx not installed, skipping {path.name}")
        return ""
    doc = Document(str(path))
    body = doc._body

    def para_images(para) -> list[str]:
        found = []
        for rid in para._element.xpath(".//a:blip/@r:embed"):
            part = doc.part.related_parts.get(rid)
            if part is not None:
                found.append(_save_image(part.blob, str(part.partname).rsplit(".", 1)[-1]))
        return found

    def table_lines(table) -> list[str]:
        rows, images = [], []
        for row in table.rows:
            seen, cells = set(), []
            for cell in row.cells:
                if cell._tc in seen:                      # merged cells repeat; show once
                    cells.append("")
                    continue
                seen.add(cell._tc)
                texts = [p.text.strip() for p in cell.paragraphs if p.text.strip()]
                for p in cell.paragraphs:
                    images += para_images(p)
                cells.append(" / ".join(texts).replace("|", "\\|"))
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
        return ["", _md_table(rows), ""] + images if rows else []

    lines = []
    for child in body._body.iterchildren():               # paragraphs and tables, in order
        if child.tag == qn("w:p"):
            para = Paragraph(child, body)
            lines += [para.text] + para_images(para)
        elif child.tag == qn("w:tbl"):
            lines += table_lines(Table(child, body))
    return "\n".join(lines)


def read_file(path: Path) -> str:
    """Return the text of a .txt / .md / .docx file (images become [[IMAGE:...]] markers)."""
    if path.suffix.lower() == ".docx":
        return _read_docx(path)
    return _mark_images(path.read_text(encoding="utf-8-sig", errors="replace"), path.parent)


def split_parts(result: str) -> list[tuple[str, str]]:
    """Split an answer into ordered ("text" | "table" | "image", value) parts."""
    parts, pos = [], 0
    for m in IMAGE_TOKEN.finditer(result):
        parts += _split_tables(result[pos:m.start()])
        parts.append(("image", m.group(1)))
        pos = m.end()
    return parts + _split_tables(result[pos:])


def list_files(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith("~$")
    )


def signature(files: list[Path]) -> tuple:
    """Cheap fingerprint used to detect added/changed/removed files."""
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files)


# --------------------------------------------------------------------------
# Search engine
# --------------------------------------------------------------------------
class SearchBot:
    def __init__(self, docs_dir: Path = DOCS_DIR, intents_file: Path = INTENTS_FILE,
                 include_tags: bool = True):
        self.docs_dir = Path(docs_dir)
        self.intents_file = Path(intents_file)
        self.include_tags = include_tags  # False -> return only the text between the tags
        self._indexes: dict[str, tuple[tuple, dict[str, str]]] = {}  # folder -> (sig, {kw: text})
        self._aliases: dict[str, str] = {}
        self._intents_mtime = None

    # ---- indexing --------------------------------------------------------
    def _index(self, folder_name: str) -> dict[str, str]:
        folder = self.docs_dir / folder_name
        if not folder.is_dir():
            return {}
        files = list_files(folder)
        sig = signature(files)
        cached = self._indexes.get(folder_name)
        if cached and cached[0] == sig:
            return cached[1]

        entries: dict[str, str] = {}
        for f in files:
            for m in TAG_RE.finditer(read_file(f)):
                entries.setdefault(m.group(1).lower(), m.group(0).strip())  # first wins
        self._indexes[folder_name] = (sig, entries)
        return entries

    # ---- intents / aliases ----------------------------------------------
    @staticmethod
    def _tokens(text: str) -> list[str]:
        return re.sub(r"[^\w\s-]", " ", text.lower()).split()

    def _load_aliases(self) -> dict[str, str]:
        if not self.intents_file.exists():
            self._aliases, self._intents_mtime = {}, None
            return self._aliases
        mtime = self.intents_file.stat().st_mtime_ns
        if mtime != self._intents_mtime:
            data = json.loads(self.intents_file.read_text(encoding="utf-8"))
            self._aliases = {
                " ".join(self._tokens(alias)): keyword.lower()
                for keyword, aliases in data.items() if not keyword.startswith("_")
                for alias in aliases
            }
            self._intents_mtime = mtime
        return self._aliases

    # ---- routing + lookup -----------------------------------------------
    @staticmethod
    def route(keyword: str) -> str | None:
        for prefix in sorted(ROUTES, key=len, reverse=True):
            if keyword.startswith(prefix):
                return ROUTES[prefix]
        return None

    def _lookup(self, keyword: str) -> str | None:
        folder = self.route(keyword)
        block = self._index(folder).get(keyword) if folder else None
        if block is None or self.include_tags:
            return block
        return TAG_RE.match(block).group(2).strip()

    # ---- public API --------------------------------------------------------
    def search(self, query: str) -> str:
        """Return the full <keyword> ... </keyword> block, or NOT_FOUND."""
        raw = query.strip().strip("<>/ ").lower()
        tokens = self._tokens(query)
        text = " ".join(tokens)
        aliases = self._load_aliases()

        candidates: list[str] = [raw, "".join(tokens)]       # "play arc" -> "playarc"
        if text in aliases:                                    # exact alias
            candidates.append(aliases[text])
        padded = f" {text} "                                   # alias inside a sentence
        candidates += [aliases[a] for a in sorted(aliases, key=len, reverse=True)
                       if f" {a} " in padded]
        candidates += tokens                                   # "show me playarc"

        for kw in candidates:
            content = self._lookup(kw)
            if content is not None:
                return content
        return NOT_FOUND

    def all_keywords(self) -> list[str]:
        """Flat list of every keyword (grouped by folder), used for autosuggest."""
        return [k for words in self.keywords().values() for k in words]

    def keywords(self) -> dict[str, list[str]]:
        """All known keywords, grouped by folder (for the UI)."""
        return {folder: sorted(self._index(folder)) for folder in ROUTES.values()}


if __name__ == "__main__":
    bot = SearchBot()
    print("Knowledge bot. Type a keyword (Ctrl+C to quit).")
    while True:
        try:
            print("\n" + bot.search(input("> ")))
        except (KeyboardInterrupt, EOFError):
            break
