import { beforeEach, expect, it, vi } from 'vitest';
import { readResumeAnalysis, saveResumeAnalysis } from './resume-analysis-cache';
const data = new Map<string,string>();
beforeEach(()=>{data.clear();vi.stubGlobal('localStorage',{getItem:(k:string)=>data.get(k)??null,setItem:(k:string,v:string)=>data.set(k,v)});});
const analysis={keywords:['Engineer'],locations:['SF'],remote_likely:true,experience_level:null,suggested_job_boards:['indeed']};
it('reuses analysis only for the exact same resume without storing raw resume text',async()=>{
 await saveResumeAnalysis('private resume one',analysis);
 expect(await readResumeAnalysis('private resume one')).toEqual(analysis);
 expect(await readResumeAnalysis('private resume two')).toBeNull();
 expect(Array.from(data.keys()).join()).not.toContain('private resume');
 expect(Array.from(data.values()).join()).not.toContain('private resume');
});
it('tolerates blocked storage without preventing prompt-driven use',async()=>{
 vi.stubGlobal('localStorage',{getItem:()=>{throw new Error('blocked')},setItem:()=>{throw new Error('blocked')}});
 await expect(readResumeAnalysis('resume')).resolves.toBeNull();
 await expect(saveResumeAnalysis('resume',analysis)).resolves.toBeUndefined();
});
