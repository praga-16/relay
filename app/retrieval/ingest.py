"""Strict corpus ingestion. Originals are never changed."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import fitz
import httpx
from app.settings import ROOT

PAPERS = [
    ("1706.03762", "v7", "Attention Is All You Need"),
    ("2410.00037", "v1", "Moshi: a speech-text foundation model for real-time dialogue"),
    ("2507.07955", "v2", "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling"),
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def inspect_pdf(path, identifier, version):
    with fitz.open(path) as doc:
        first = doc[0].get_text()
        if not re.search(re.escape(identifier + version) + r"\b", first):
            raise ValueError(f"Missing exact first-page version: {identifier}{version}")
        return len(doc)


def prepare(download=True):
    (ROOT / "papers").mkdir(exist_ok=True)
    manifest = []
    for identifier, version, title in PAPERS:
        name = identifier + version
        original = ROOT / "pdf" / (name + ".pdf")
        source = original if original.is_file() else ROOT / "papers" / (name + ".pdf")
        local = source.read_bytes()
        pages = inspect_pdf(source, identifier, version)
        url = f"https://arxiv.org/pdf/{name}"
        official_hash = None
        if download:
            response = httpx.get(url, follow_redirects=True, timeout=60)
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("Official response is not a PDF")
            official_hash = sha256(response.content)
            if official_hash != sha256(local):
                raise ValueError(f"Official/local SHA-256 mismatch: {name}; originals preserved")
        destination = ROOT / "papers" / (name + ".pdf")
        if destination.exists() and destination.read_bytes() != local:
            raise ValueError(f"Refusing to overwrite differing paper: {name}")
        if not destination.exists():
            destination.write_bytes(local)
        manifest.append(dict(title=title, arxiv_id=identifier, version=version, url=url,
                             sha256=sha256(local), official_sha256=official_hash,
                             page_count=pages, verification_status="official_sha256_match" if download
                             else "embedded_version_only", verified_at=datetime.now(timezone.utc).isoformat()))
    (ROOT / "paper_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def extract():
    out = ROOT / "data/extracted"
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "paper_manifest.json").read_text())
    rows, quality = [], []
    for paper in manifest:
        name = paper["arxiv_id"] + paper["version"]
        path = ROOT / "papers" / f"{name}.pdf"
        if sha256(path.read_bytes()) != paper["sha256"]:
            raise ValueError("Paper changed since manifest verification")
        section = "Front matter / abstract"
        with fitz.open(path) as doc:
            for page_no, page in enumerate(doc, 1):
                text = page.get_text(sort=True)
                blocks = page.get_text("dict", sort=True)["blocks"]
                page_rows = []
                for block in blocks:
                    if "lines" not in block:
                        continue
                    lines = ["".join(s["text"] for s in line["spans"]) for line in block["lines"]]
                    paragraph = "\n".join(lines).strip()
                    if not paragraph:
                        continue
                    for line_index, line in enumerate(lines):
                        fonts = [s['font'].lower() for s in block['lines'][line_index]['spans']]
                        heading_font = any(any(tag in f for tag in ('bold', 'medi', 'cmbx', 'cmcsc', 'libertinetb')) for f in fonts)
                        if heading_font and re.match(r"^(?:[1-9]|[A-Z])(?:\.\d+)*\.?\s+[A-Z]", line) and len(line) < 130:
                            section = line.strip()
                        elif heading_font and re.fullmatch(r'(?:[1-9]|[A-Z])(?:\.\d+)*\.?', line.strip()) and line_index + 1 < len(lines):
                            title_line = lines[line_index + 1].strip()
                            if re.match(r'^[A-Z][A-Za-z -]{3,100}$', title_line):
                                section = line.strip() + ' ' + title_line
                        elif line.strip() in {"References", "Acknowledgments", "Appendix"}:
                            section = line.strip()
                    row = dict(paper_title=paper["title"], arxiv_version=name, page=page_no,
                               section=section, paragraph=len(page_rows), text=paragraph,
                               bbox=block["bbox"])
                    page_rows.append(row)
                rows.extend(page_rows)
                quality.append(dict(arxiv_version=name, page=page_no, characters=len(text),
                                    replacements=text.count("\ufffd"), blocks=len(page_rows),
                                    note="equations/tables require visual comparison; blocks are layout approximations"))
    (out / "paragraphs.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (out / "quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    return rows
