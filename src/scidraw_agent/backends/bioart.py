"""NIH BIOART Source (human/clinical-anatomy backend) — public-domain vector SVGs.

NIH BIOART Source (https://bioart.niaid.nih.gov, NIAID) publishes 2,000+ public-domain
science / biomedical illustrations as editable vector SVG. It is the human/clinical
neuroanatomy that SciDraw (rodent / systems-neuro) is thin on — exactly the coverage gap
the brief calls out — so it sits between Zenodo (primary) and the generic bioicons fallback.

Why a curated index instead of a live search: BIOART exposes **no stable, documented API**.
Discovery and the multi-format download dialog both run through per-deploy Next.js *server
actions* (action ids baked into the JS bundle, rotated every release), and the asset S3
bucket is not list-able. Replaying those would be brittle and would violate the project's
"wrap, cache, test with mocks" conventions. What **is** stable and verified is the file
proxy ``/api/bioarts/{id}/files/{file_id}`` (a plain GET that streams the asset). So this
backend matches a query against a small curated index shipped with the package
(``bioart_index.json``: id, the resolved **SVG** file_id, title, keywords) and downloads the
chosen SVG over that stable endpoint. Misses return nothing and the fetcher degrades
gracefully to the next backend / a labelled placeholder.

Everything in BIOART is Public Domain, so the license gate always passes (recorded as
``public-domain`` for the manifest's provenance trail).

Extending the index: open the item page on bioart.niaid.nih.gov, tick the **.svg** format
and click Download; the request carries ``["{id}",[[{file_id}]]]`` — add
``{"id", "file_id", "title", "keywords"}`` to ``bioart_index.json``.
"""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import TYPE_CHECKING

from ..models import AssetRecord

if TYPE_CHECKING:
    from ..fetch import HttpClient

FILE_API = "https://bioart.niaid.nih.gov/api/bioarts/{id}/files/{file_id}"
ITEM_PAGE = "https://bioart.niaid.nih.gov/bioart/{id}"
# Whole library is Public Domain (https://bioart.niaid.nih.gov/faqs).
LICENSE = "public-domain"
CREATOR = "NIH BIOART Source (NIAID)"

_INDEX_RESOURCE = "bioart_index.json"


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\W+", text.lower()) if t]


class BioartBackend:
    name = "bioart"

    def __init__(self, index: list[dict] | None = None) -> None:
        # ``index`` is injectable for tests; otherwise the packaged catalog is loaded once.
        self._index = index

    def _load_index(self) -> list[dict]:
        if self._index is None:
            raw = resources.files(__package__).joinpath(_INDEX_RESOURCE).read_text(encoding="utf-8")
            self._index = json.loads(raw)
        return self._index

    def search(self, term: str, size: int, http: HttpClient) -> list[AssetRecord]:
        # Offline keyword match: every token of the query must appear in title+keywords
        # (order-independent, so "mouse brain" matches "Mouse Brain Coronal").
        needle = _tokens(term)
        if not needle:
            return []
        out: list[AssetRecord] = []
        for entry in self._load_index():
            hay = (entry["title"] + " " + " ".join(entry.get("keywords", []))).lower()
            if all(tok in hay for tok in needle):
                out.append(
                    AssetRecord(
                        query=term,
                        title=entry["title"],
                        backend=self.name,
                        doi=None,
                        license=LICENSE,
                        source_url=FILE_API.format(id=entry["id"], file_id=entry["file_id"]),
                        creators=[CREATOR],
                    )
                )
            if len(out) >= size:
                break
        return out
