"""
Document ingestion.

For this exercise we support plain text/markdown files (representative SOPs,
tickets, policy docs). In a real system you'd add a docx/pdf loader here — the
important design point for the interview is that ingestion is a SEPARATE stage
from extraction, so swapping in a PDF loader later doesn't touch the LLM logic.
"""
import os
from dataclasses import dataclass
from typing import List

from src.config import MAX_CHUNK_CHARS, CHUNK_OVERLAP_CHARS


@dataclass
class Document:
    doc_id: str
    source_path: str
    text: str


@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    text: str


def load_documents(directory: str) -> List[Document]:
    docs = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith((".txt", ".md")):
            continue
        path = os.path.join(directory, fname)
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        docs.append(Document(doc_id=fname, source_path=path, text=text))
    return docs


def chunk_document(doc: Document, max_chars: int = MAX_CHUNK_CHARS,
                    overlap: int = CHUNK_OVERLAP_CHARS) -> List[Chunk]:
    """Simple sliding-window chunker.

    Most SOPs/tickets in this exercise are short enough to be a single chunk —
    this exists so the pipeline doesn't break (or silently truncate) on a long
    policy document, and so the cost writeup can honestly say "we chunk long
    inputs" rather than "we just hope documents stay small."
    """
    text = doc.text
    if len(text) <= max_chars:
        return [Chunk(doc_id=doc.doc_id, chunk_index=0, text=text)]

    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(Chunk(doc_id=doc.doc_id, chunk_index=idx, text=text[start:end]))
        idx += 1
        start = end - overlap if end < len(text) else end
    return chunks
