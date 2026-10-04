import { expect, it } from 'vitest';
import { applicationOutcomeCounts } from './application-outcomes';
import { buildLedger, runOutcome } from './run';
it('separates uncertain submissions in old snapshots and summaries',()=>{
 const failures=[{error_category:'submission_uncertain'},{error_category:'validation'}];
 expect(applicationOutcomeCounts(failures,{total_failed:2})).toEqual({failed:1,uncertain:1});
 expect(applicationOutcomeCounts(failures)).toEqual({failed:1,uncertain:1});
});
it('does not subtract uncertainty twice from the new summary',()=>{
 expect(applicationOutcomeCounts([{error_category:'submission_uncertain'}],{total_failed:0,total_uncertain:1})).toEqual({failed:0,uncertain:1});
});
it('never reports nothing sent or every failure for an uncertain terminal run',()=>{
 for(const status of ['completed','failed']) expect(runOutcome({status,submitted:0,failed:0,uncertain:1})).toEqual({tone:'needs',label:'Confirmation pending—check before retrying'});
 const ledger=buildLedger({status:'completed',found:1,shortlisted:1,attempted:1,submitted:0,failed:0,uncertain:1});
 expect(ledger.phases.find(p=>p.key==='report')?.reason).toBe('Confirmation pending—check before retrying');
});
