import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedBlock:
    content: str
    location: str


@dataclass
class Chunk:
    chunk_id: str
    content: str
    location: str


def parse_document(path: Path) -> list[ParsedBlock]:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8-sig")
        blocks = []
        for index, part in enumerate(re.split(r"\n\s*\n", text)):
            clean = re.sub(r"[ \t]+", " ", part).strip()
            if clean:
                blocks.append(ParsedBlock(clean, f"段落 {index + 1}"))
        return blocks
    if suffix == ".pdf":
        from pypdf import PdfReader
        blocks = [ParsedBlock((page.extract_text() or "").strip(), f"第 {i + 1} 页") for i, page in enumerate(PdfReader(str(path)).pages)]
        if not any(block.content for block in blocks):
            raise ValueError("扫描版 PDF 无可提取文本，需要 OCR，当前版本不支持")
        return [block for block in blocks if block.content]
    if suffix == ".docx":
        from docx import Document
        result, heading = [], "正文"
        for index, paragraph in enumerate(Document(str(path)).paragraphs):
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.style and paragraph.style.name.startswith("Heading"):
                heading = text
            result.append(ParsedBlock(text, f"{heading} / 段落 {index + 1}"))
        return result
    raise ValueError("仅支持 PDF、DOCX、TXT、Markdown")


def split_blocks(blocks: list[ParsedBlock], source_id: str, chunk_size: int = 500, overlap: int = 60) -> list[Chunk]:
    chunks: list[Chunk] = []
    for block in blocks:
        start = 0
        while start < len(block.content):
            content = block.content[start:start + chunk_size].strip()
            if content:
                digest = hashlib.sha256(f"{source_id}:{block.location}:{start}:{content}".encode()).hexdigest()[:24]
                chunks.append(Chunk(digest, content, block.location))
            if start + chunk_size >= len(block.content):
                break
            start += max(1, chunk_size - overlap)
    if not chunks:
        raise ValueError("资料没有可索引的文本")
    return chunks

