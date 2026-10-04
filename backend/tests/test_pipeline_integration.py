"""Real graph, agents, applier, grounding and SQL; only provider transports are fakes.

Run through ../run_duplicate_tests.py: never against a personal/production DB.
"""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from backend.shared.config import settings
from backend.shared.db import get_connection
from backend.shared.models.schemas import CoachOutput, ResumeScore, SearchConfig
from backend.orchestrator.pipeline import graph as pipeline
from backend.orchestrator.agents import intake, career_coach, scoring, application, verification, qa, reporting
from backend.browser import application_answers
from backend.browser.tools import indeed_discovery, indeed_hydration
from backend.browser.tools import cover_letter
from backend.browser.tools.appliers.indeed import NextStep

pytestmark = pytest.mark.requires_postgres
RESUME = 'Test Applicant\ntest@applicant.invalid\nSan Francisco, CA\nBuilt production Python LLM applications.'
PDF = b'%PDF-1.4\nCanonical synthetic resume fixture\n%%EOF'


@pytest_asyncio.fixture
async def real_identity(monkeypatch):
    from alembic import command
    from alembic.config import Config
    from backend.shared import application_store, resume_store
    from backend.shared.resume_crypto import _get_fernet
    from backend.shared.billing_store import get_or_create_user, ensure_billing_tables
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / 'alembic.ini'))
    cfg.set_main_option('script_location', str(root / 'alembic'))
    command.upgrade(cfg, 'head')
    await application_store.ensure_table()
    await ensure_billing_tables()
    user = get_or_create_user(f'{uuid4().hex}@fixture.invalid')
    sid = str(uuid4())
    with get_connection() as conn:
        conn.execute("INSERT INTO sessions (id,user_id,status) VALUES (%s,%s,'intake')", (sid,user['id']))
        conn.commit()
    resume_store.save_resume(sid, _get_fernet().encrypt(PDF), owner_user_id=user['id'])
    return sid, user['id']


class ProviderModel:
    """Deterministic provider responses; production parsing/retry wrappers stay real."""
    def __init__(self, calls, schema=None):
        self.calls, self.schema = calls, schema
    def with_structured_output(self, schema):
        return ProviderModel(self.calls, schema)
    async def ainvoke(self, messages):
        name = self.schema.__name__ if self.schema else 'CoverLetter'
        self.calls.append((name, messages))
        if name in ('SearchConfig', '_PromptSearchConfig'):
            payload = dict(keywords=['AI Engineer'], locations=['San Francisco, CA'], work_arrangements=['remote','hybrid'])
            if name == '_PromptSearchConfig': payload['primary_role'] = 'AI Engineer'
        elif name == 'CoachOutput':
            payload = dict(rewritten_resume=RESUME, cover_letter_template='Dear team,', confidence_message='Ready.',
                           resume_score=ResumeScore(overall=80,keyword_density=80,impact_metrics=80,ats_compatibility=80,readability=80,formatting=80))
        elif name == 'ScoringBatchResult':
            ids = [line.removeprefix('- ID: ').strip() for line in messages[-1].content.splitlines() if line.startswith('- ID: ')]
            payload = {'scores':[dict(job_id=jid, score=90, eligibility_status='met', eligibility_reasons=['Fixture requirements match original resume.'], score_breakdown=dict(keyword_match=90,experience_match=90,location_match=90,salary_match=90),reasons=['Relevant Python role']) for jid in ids]}
        elif name == 'AnswerCheck':
            payload = dict(supported=True, reason='Resume demonstrates Python experience.', question='')
        elif name == 'VerificationResult':
            payload = dict(verified_count=1, failed_count=0, details=[], summary='Receipt confirmed by application adapter.')
        elif name == 'QADecision':
            payload = dict(decision='continue', reasoning='One verified application.')
        elif name == 'NextStepsResult':
            payload = dict(next_steps=['Review the verified application.'])
        else:
            assert self.schema is None, name
            return SimpleNamespace(content='Dear team, I build production Python LLM applications. Submitted via JobHunter Agent.')
        return self.schema.model_validate(payload)


class ProviderBrowser:
    """Fake remote browser/Stagehand SDK boundary; no application logic replaced."""
    def __init__(self, calls):
        self.calls = calls
        self.url = 'https://www.indeed.com/viewjob?jk=fixture123'
        self.phase = 'listing'
        self.uploads = []
        self.actions = []
        self.context = SimpleNamespace(pages=[self], _jobhunter_external_redirect=None)
        self.context.new_page = AsyncMock(return_value=self)
        self.stage_page = SimpleNamespace(url=self.active_url, snapshot=self.snapshot, locator=self.locator)
        self.stagehand = SimpleNamespace(browser=SimpleNamespace(context=SimpleNamespace(active_page=AsyncMock(return_value=self.stage_page))),
                                        extract=self.extract, observe=self.observe, _jobhunter_captcha_monitor=None)
    async def active_url(self): return self.url
    async def goto(self, url, **kwargs): self.url = url
    async def wait_for_function(self, *args, **kwargs): pass
    async def wait_for_timeout(self, *args): pass
    async def wait_for_selector(self, *args, **kwargs): pass
    async def close(self): pass
    def is_closed(self): return False
    async def screenshot(self, **kwargs): return b'fixture'
    async def evaluate(self, script, *args):
        if 'cards.map' in script:
            return [dict(title='AI Engineer', company='Fixture Company', location='Remote in San Francisco, CA',job_key='fixture123',is_easy_apply=True,description_snippet='Build Python LLM applications. $250,000 base.')]
        if 'selectors =>' in script: return False
        return 'AI Engineer at Fixture Company. Apply now. Build Python LLM applications.'
    async def query_selector(self, *args): return None
    async def query_selector_all(self, *args): return []
    def locator(self, selector):
        if selector == 'input[type="file"]':
            return SimpleNamespace(count=AsyncMock(return_value=1 if self.phase == 'resume' else 0),set_input_files=self.upload)
        return SimpleNamespace(count=AsyncMock(return_value=1),is_visible=AsyncMock(return_value=True),
                               click=lambda:self.advance('Click Submit application' if self.phase=='review' else 'Click Apply now'),
                               fill=lambda value:self.advance('Fill Python experience with '+value))
    async def observe(self, instruction, **kwargs):
        choices={'listing':('xpath=/apply','click',[]),'questions':('xpath=/experience','fill',['Built production Python LLM applications']),
                 'review':('xpath=/submit','click',[])}
        selector,method,arguments=choices[self.phase]
        return SimpleNamespace(data=[SimpleNamespace(selector=selector,method=method,arguments=arguments)])
    async def upload(self, payload):
        self.uploads.append(payload)
        assert payload.buffer == PDF
        self.phase = 'questions'
    async def snapshot(self, **kwargs):
        assert kwargs.get('include_iframes') is True
        texts = {'listing':'[1] button: Apply now','resume':'[2] button: Upload resume',
                 'questions':'[3] textbox: Python experience','review':'[4] heading: Review application\n[5] text: Python experience: Built production Python LLM applications\n[6] button: Submit application',
                 'receipt':'[7] heading: Your application has been submitted'}
        return SimpleNamespace(formatted_tree=texts[self.phase],xpath_map={"1":"/apply","3":"/experience","6":"/submit"})
    async def extract(self, prompt, schema, **kwargs):
        self.calls.append(('StagehandPlan', prompt))
        if schema is indeed_hydration.IndeedListing:
            return SimpleNamespace(data=schema(title='AI Engineer',company='Fixture Company',location='San Francisco, CA',
                description='Build Python LLM applications. $250,000 base.',is_remote=True,can_apply_on_indeed=True,expired=False,blocked=False))
        steps={'listing':('act','Click Apply now'), 'questions':('act','Fill Python experience with Built production Python LLM applications'), 'review':('submit','Click Submit application')}
        kind,instruction=steps[self.phase]
        return SimpleNamespace(data=NextStep(kind=kind,instruction=instruction,reason='Proceed using supplied facts.'))
    async def advance(self, instruction, **kwargs):
        self.actions.append(instruction)
        if self.phase=='listing':
            self.phase='resume'; self.url='https://smartapply.indeed.com/beta/indeedapply/form/resume-selection'
        elif self.phase=='questions':
            self.phase='review'; self.url='https://smartapply.indeed.com/beta/indeedapply/form/review'
        elif self.phase=='review':
            self.phase='receipt'; self.url='https://smartapply.indeed.com/beta/indeedapply/form/confirmation'
        else: raise AssertionError(self.phase)
        return SimpleNamespace(data=SimpleNamespace(success=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", ["search", "quick_apply", "autopilot"])
async def test_real_pipeline_reviews_uploads_submits_receipt_and_restart_deduplicates(monkeypatch, real_identity, entrypoint):
    sid, uid = real_identity
    calls=[]
    browser=ProviderBrowser(calls)
    monkeypatch.setattr(settings,'INDEED_ONLY',True)
    monkeypatch.setattr(settings,'INDEED_EASY_APPLY_ONLY',True)
    monkeypatch.setattr(settings,'BROWSER_MODE','browserbase')
    monkeypatch.setattr(settings,'BROWSERBASE_CONTEXT_USER_ID',uid)
    monkeypatch.setattr(settings,'BROWSERBASE_API_KEY','fixture-key')
    monkeypatch.setattr(settings,'BROWSERBASE_PROJECT_ID','fixture-project')
    monkeypatch.setattr(settings,'BROWSERBASE_CONTEXT_IDS','indeed=fixture-context')
    # Shared external Redis/Neo4j/event transport and remote model calls only.
    monkeypatch.setattr('backend.shared.event_bus.emit_agent_event',AsyncMock())
    for module in (intake,career_coach,scoring,application,verification,qa,reporting,pipeline,indeed_discovery):
        monkeypatch.setattr(module,'emit_agent_event',AsyncMock(),raising=False)
    monkeypatch.setattr('backend.browser.tools.appliers.base.emit_agent_event',AsyncMock())
    for module in (intake,career_coach,scoring,cover_letter,application_answers):
        monkeypatch.setattr(module,'build_llm',lambda **kwargs:ProviderModel(calls))
    for module in (verification,qa):
        monkeypatch.setattr(module,'_shared_build_llm',lambda **kwargs:ProviderModel(calls))
    monkeypatch.setattr(reporting,'_build_llm',lambda:ProviderModel(calls))
    monkeypatch.setattr('backend.shared.llm.build_llm',lambda **kwargs:ProviderModel(calls))
    monkeypatch.setattr('backend.moltbook.strategies.get_strategy_manager',lambda:SimpleNamespace(get_state=lambda:SimpleNamespace(board_priorities={},human_review_needed=False)))
    monkeypatch.setattr('backend.moltbook.strategies.get_strategy_patches',lambda:'')
    # Neo4j learning is external and not needed to establish submission correctness.
    monkeypatch.setattr(application,'_record_result_to_neo4j',AsyncMock())
    class Manager:
        stagehand=browser.stagehand
        live_view_url=None
        browserbase_session_id='fixture-session'
        async def start_for_task(self,**kwargs):
            assert kwargs['user_id']==uid
        async def new_context(self): return 'fixture-context',browser.context
        async def stop(self): pass
    monkeypatch.setattr(application,'BrowserManager',Manager)
    monkeypatch.setattr(indeed_discovery,'BrowserManager',Manager)
    monkeypatch.setattr(indeed_hydration,'BrowserManager',Manager)
    monkeypatch.setattr(indeed_hydration,'emit_agent_event',AsyncMock())
    from backend.shared.model_access import model_user_scope
    from backend.shared.application_store import check_already_applied
    with model_user_scope(uid):
        graph=pipeline.build_graph(MemorySaver())
        config={'configurable':{'thread_id':sid},'recursion_limit':100}
        state={'session_id':sid,'user_id':uid,'resume_text':RESUME,'keywords':['AI Engineer'],
               'locations':['San Francisco, CA'],'preferences':{},
               'session_config':{'max_jobs':1,'generate_cover_letters':True}, 'status':'intake'}
        if entrypoint == 'quick_apply':
            state['job_urls']=['https://www.indeed.com/viewjob?jk=fixture123']
            state['session_config']['discovery_mode']='manual_urls'
            state['preferences']['_skip_coach_review']=True
        elif entrypoint == 'autopilot':
            state['preferences']['_autopilot_auto_approve']=True
        result=await graph.ainvoke(state,config)
        if entrypoint == 'search':
            assert result['__interrupt__'][0].value['stage']=='coach_review'
            assert browser.actions==[]
            result=await graph.ainvoke(Command(resume={'approved':True,'use_original':True}),config)
        if entrypoint == 'search':
            assert result['__interrupt__'][0].value['stage']=='shortlist_review'
            assert browser.actions==[]
            jid=result['scored_jobs'][0].job.id
            result=await graph.ainvoke(Command(resume={'approved_job_ids':[jid]}),config)
        jid=result['scored_jobs'][0].job.id
        assert result['status']=='completed',result.get('errors')
        assert len(result['applications_submitted'])==1, (result.get('applications_failed'),result.get('applications_skipped'),result.get('errors'),result.get('application_queue'))
        assert len(browser.uploads)==1
        assert browser.actions.count('Click Submit application')==1
        assert result['session_summary'].total_applied==1
        audits=[json.loads(m[-1].content) for name,m in calls if name=='AnswerCheck']
        assert any(a['mode']=='final_review' and 'Python experience' in a['review_text'] for a in audits)
        assert any(name=='CoverLetter' for name,_ in calls)
        prior=check_already_applied(jid,user_id=uid,job_url=result['discovered_jobs'][0].url)
        assert prior['status']=='submitted'
        # Rebuild graph like a worker restart: completed checkpoint must not replay browser actions.
        restarted=pipeline.build_graph(graph.checkpointer)
        await restarted.ainvoke(None,config)
        assert browser.actions.count('Click Submit application')==1
