import os
import socket

import pytest

from integrations.arxiv_api import ArxivAPI

pytestmark = pytest.mark.integration


def _dns_available(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 80)
        return True
    except OSError:
        return False


def test_arxiv_search_smoke():
    if not os.environ.get("RUN_INTEGRATION"):
        pytest.skip("Set RUN_INTEGRATION=1 to run live arXiv lookup.")

    if not _dns_available("export.arxiv.org"):
        pytest.skip("DNS unavailable for export.arxiv.org; skipping live arXiv lookup.")

    api = ArxivAPI()
    papers = api.search_papers("cat:q-bio.NC AND dopamine", max_results=3)

    assert len(papers) > 0
    assert "title" in papers[0]
