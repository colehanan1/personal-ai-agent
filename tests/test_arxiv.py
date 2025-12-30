# quick test
from integrations.arxiv_api import ArxivAPI

api = ArxivAPI()
papers = api.search_papers("cat:q-bio.NC AND dopamine", max_results=3)
for p in papers:
    print(p["published"], "–", p["title"])

