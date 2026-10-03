from backend.shared.models.schemas import SearchConfig,JobListing,JobBoard
from backend.browser.tools.job_boards.indeed import matches_search

def job(title='Applied AI Engineer',company='Example',location='Hybrid work in San Francisco, CA'):
 return JobListing(id='1',title=title,company=company,location=location,url='https://www.indeed.com/viewjob?jk=123',board=JobBoard.INDEED)

def test_prompt_exclusions_and_arrangements():
 search=SearchConfig(keywords=['Applied AI Engineer'],locations=['San Francisco'],work_arrangements=['hybrid','remote'],exclude_title_keywords=['AI Trainer','Data Annotation'])
 assert matches_search(job(),search)
 assert not matches_search(job(title='Application Engineer - AI Trainer'),search)
 assert not matches_search(job(location='San Francisco, CA'),search)
 assert matches_search(job(location='Remote in San Francisco, CA'),search)


def test_card_snapshot_normalizes_job_key_and_rejects_external_link():
 from backend.browser.tools.job_boards.indeed import _parse_indeed_card
 card = {'title': 'Applied AI Engineer', 'company': 'Example', 'location': 'Hybrid in San Francisco',
         'job_key': 'abc123', 'href': '/rc/clk?tracking=1', 'is_easy_apply': True}
 parsed = _parse_indeed_card(card)
 assert parsed.url == 'https://www.indeed.com/viewjob?jk=abc123'
 assert parsed.is_easy_apply
 assert parsed.location == 'Hybrid in San Francisco'
 assert _parse_indeed_card({**card, 'job_key': None, 'href': 'https://external.example/apply'}) is None
 assert _parse_indeed_card({**card, 'title': None}) is None
