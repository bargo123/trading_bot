"""Shared knowledge layer: book corpus manifest + verbatim passage retrieval.

The corpus is the trading-book library (docs/trading/books/*.md) indexed in
research/books_index.sqlite. Retrieval returns ORIGINAL passages verbatim so
council proposals can quote the books directly. Manifest presence is not an
implementation claim — it only records what the corpus contains.
"""
from __future__ import annotations