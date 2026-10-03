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
