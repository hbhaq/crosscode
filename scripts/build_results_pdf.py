"""Create a read-only, data-grounded report for the completed hard-50 run."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
import csv
import json
import sqlite3
import hashlib
import math
import os
import statistics
from collections import Counter
from datetime import datetime, timezone, timedelta
from xml.sax.saxutils import escape
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/pdfs/matplotlib-cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

RUN=ROOT/'runs/docker-hard-fifty-fixed'
REPORT=RUN/'report'
OUT=ROOT/'output/pdf'
TMP=ROOT/'tmp/pdfs'
OUT.mkdir(parents=True,exist_ok=True)
TMP.mkdir(parents=True,exist_ok=True)
PDF=OUT/'Crosscode_50_Hard_Tasks_Report.pdf'
def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def rows(name,pop='reliability-inclusive'):
    with (REPORT/pop/(name+'.csv')).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))
manifest=read(RUN/'manifest.json')
config=read(RUN/'config.json')
results=read(REPORT/'results.json')
records=results['records']
metadata=results['metadata']
db=sqlite3.connect((RUN/'checkpoint.sqlite').as_uri()+'?mode=ro',uri=True)
try:
    stages={key:json.loads(value) for key,value in db.execute('SELECT key,record FROM stages')}
    evaluations={key:json.loads(value) for key,value in db.execute('SELECT key,record FROM evaluations')}
    db.row_factory=sqlite3.Row
    attempts=[dict(row) for row in db.execute('SELECT * FROM attempts ORDER BY id')]
finally: db.close()
assert len(stages)==500 and len(records)==300 and len(evaluations)==498
assert sum(a['cost'] or 0 for a in attempts)==metadata['ledger']['actual_usd']
assert all(a['state']=='settled' for a in attempts)
metrics=rows('all_metrics')
table2=rows('table2')
cc=rows('table2','complete-case')
transitions=rows('review_transitions')
comparisons=rows('table4')
all_comparisons=rows('all_pairwise')
conditions=['A','O','AO','OA','AA','OO']
M={r['condition']:r for r in metrics}
R={(r['task_id'],r['condition']):r for r in records}
assert all(int(M[c]['denominator'])==50 for c in conditions)
assert sum(int(M[c]['passed']) for c in conditions)==211
assert len({r['task_id'] for r in records})==50
for r in records:
    assert r['final_key'] in stages
    if r['valid']:
        assert evaluations[r['final_key']]['passed']==r['outcome']
def f(value,d=2): return f'{float(value):.{d}f}'
def pct(value,d=0): return f'{100*float(value):.{d}f}%'
def quantile(values,q):
    values=sorted(values); x=(len(values)-1)*q; lo=int(x)
    return values[lo]+(values[min(lo+1,len(values)-1)]-values[lo])*(x-lo)
provider=[]
for model,name in [('A','Claude Opus 5.5'),('O','GPT-6.1 Sol')]:
    group=[x for x in stages.values() if x['model']==model]
    valid=[x for x in group if x['status']=='valid']
    usage=Counter()
    for x in valid:
        u=x['usage']
        usage['input']+=u.get('input_tokens',0)
        usage['output']+=u.get('output_tokens',0)
        if model=='A':
            usage['cache_read']+=u.get('cache_read_input_tokens',0)
            usage['cache_write']+=u.get('cache_creation_input_tokens',0)
        else:
            usage['cache_read']+=(u.get('input_tokens_details') or {}).get('cached_tokens',0)
            usage['cache_write']+=(u.get('input_tokens_details') or {}).get('cache_write_tokens',0)
    ids={x['attempt_id'] for x in group}
    provider.append({'model':name,'stages':len(group),'valid':len(valid),'cost':sum(a['cost'] or 0 for a in attempts if a['id'] in ids),'usage':dict(usage)})
latencies={c:[r['workflow_latency'] for r in records if r['condition']==c and r['workflow_latency'] is not None] for c in conditions}
timestamp_values=[x['timestamp'] for x in stages.values() if isinstance(x.get('timestamp'),(float,int))]
tz=timezone(timedelta(hours=5))
start=datetime.fromtimestamp(min(timestamp_values),tz)
end=datetime.fromtimestamp(max(x['timestamp']+x.get('latency',0) for x in stages.values() if isinstance(x.get('timestamp'),(int,float))),tz)
libraries=Counter(lib for t in manifest['tasks'] for lib in t['libs'])
summary={'run_id':RUN.name,'configuration_hash':manifest['config_hash'],'ledger':metadata['ledger'],
         'stage_statuses':dict(Counter(x['status'] for x in stages.values())),
         'evaluation_statuses':dict(Counter(x['status'] for x in evaluations.values())),
         'providers':provider,'first_saved_call_start':start.isoformat(),'last_saved_call_end':end.isoformat(),
         'summed_api_latency_seconds':sum(r['workflow_latency'] or 0 for r in records),
         'metrics':metrics,'true_transitions':transitions,
         'latency_percentiles':{c:{'median':statistics.median(v),'p90':quantile(v,.9)} for c,v in latencies.items()},
         'library_task_counts':dict(libraries)}
(OUT/'Crosscode_50_Hard_Tasks_Report.data.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')

# New explanatory charts supplement the existing Figure 2, never replace its data.
plt.rcParams.update({'font.size':11,'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False})
palette=['#2676a5','#c65b42','#2676a5','#c65b42','#2676a5','#c65b42']
fig,ax=plt.subplots(figsize=(9,3.5))
vals=[100*float(M[c]['pass_rate']) for c in conditions]
lo=[v-100*float(M[c]['ci_low']) for c,v in zip(conditions,vals)]
hi=[100*float(M[c]['ci_high'])-v for c,v in zip(conditions,vals)]
ax.bar(conditions,vals,color=palette,width=.62,alpha=.9)
ax.errorbar(conditions,vals,yerr=[lo,hi],fmt='none',ecolor='#243648',capsize=5,lw=1.4)
for i,v in enumerate(vals): ax.text(i,5,f'{int(v)}%',ha='center',color='white',fontweight='bold',fontsize=12)
ax.set_ylim(0,105); ax.set_ylabel('Benchmark pass rate (%)'); ax.grid(axis='y',alpha=.15); ax.set_axisbelow(True)
fig.tight_layout(); fig.savefig(TMP/'figure1_accuracy.png',dpi=200); plt.close(fig)
fig,ax=plt.subplots(figsize=(9,3.4))
writer=[float(M[c]['mean_writer_latency_s']) for c in conditions]
review=[float(M[c]['mean_reviewer_latency_s']) for c in conditions]
ax.barh(conditions,writer,color='#2676a5',label='Writer API time')
ax.barh(conditions,review,left=writer,color='#e5a14a',label='Reviewer API time')
for i,(a,b) in enumerate(zip(writer,review)): ax.text(a+b+.35,i,f'{a+b:.1f}s',va='center',fontsize=10)
ax.invert_yaxis(); ax.set_xlim(0,35); ax.set_xlabel('Mean API latency per task (seconds)'); ax.legend(loc='lower right',frameon=False)
ax.grid(axis='x',alpha=.15); ax.set_axisbelow(True); fig.tight_layout()
fig.savefig(TMP/'figure3_latency.png',dpi=200); plt.close(fig)

FONT=Path('C:/Windows/Fonts')
pdfmetrics.registerFont(TTFont('Report',str(FONT/'segoeui.ttf')))
pdfmetrics.registerFont(TTFont('ReportBold',str(FONT/'segoeuib.ttf')))
pdfmetrics.registerFontFamily('Report',normal='Report',bold='ReportBold',italic='Report',boldItalic='ReportBold')
NAVY=colors.HexColor('#17324d'); TEAL=colors.HexColor('#137b87'); MUTED=colors.HexColor('#526577'); LIGHT=colors.HexColor('#edf3f7')
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyX',fontName='Report',fontSize=10,leading=14.6,textColor=NAVY,spaceAfter=9))
styles.add(ParagraphStyle(name='SmallX',parent=styles['BodyX'],fontSize=8.3,leading=11.3,textColor=MUTED,spaceAfter=7))
styles.add(ParagraphStyle(name='H1X',fontName='ReportBold',fontSize=22,leading=27,textColor=NAVY,spaceAfter=15))
styles.add(ParagraphStyle(name='H2X',fontName='ReportBold',fontSize=12,leading=16,textColor=TEAL,spaceBefore=10,spaceAfter=7))
styles.add(ParagraphStyle(name='TitleX',fontName='ReportBold',fontSize=37,leading=43,textColor=NAVY,spaceAfter=20))
styles.add(ParagraphStyle(name='CellX',fontName='Report',fontSize=8.5,leading=11.3,textColor=NAVY))
styles.add(ParagraphStyle(name='CellSmall',parent=styles['CellX'],fontSize=7.5,leading=9.6))
styles.add(ParagraphStyle(name='HeadCell',parent=styles['CellX'],fontName='ReportBold',textColor=colors.white))
W=A4[0]-88
story=[]
def p(text,style='BodyX'):
    story.append(Paragraph(text,styles[style]))
def h(text): p(text,'H2X')
def page(title,kicker):
    if story: story.append(PageBreak())
    p(kicker.upper(),'SmallX'); p(title,'H1X')
def caption(text): p(text,'SmallX')
def table(headers,data,widths=None,small=False):
    cellstyle=styles['CellSmall' if small else 'CellX']
    content=[[Paragraph(escape(str(v)),styles['HeadCell']) for v in headers]]
    content.extend([[Paragraph(escape(str(v)),cellstyle) for v in row] for row in data])
    t=Table(content,colWidths=widths or [W/len(headers)]*len(headers),repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
                          ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                          ('TOPPADDING',(0,0),(-1,-1),3 if small else 6),('BOTTOMPADDING',(0,0),(-1,-1),3 if small else 6),
                          ('LINEBELOW',(0,0),(-1,0),.6,NAVY),('LINEBELOW',(0,-1),(-1,-1),.4,colors.HexColor('#cbd7e0'))]))
    story.append(t); story.append(Spacer(1,8))
def picture(path,width=W):
    from PIL import Image as PILImage
    with PILImage.open(path) as im: w,h_=im.size
    story.append(Image(str(path),width=width,height=width*h_/w)); story.append(Spacer(1,6))
def note(text):
    t=Table([[Paragraph(text,styles['BodyX'])]],colWidths=[W])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#cfdee8')),
                          ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.append(t); story.append(Spacer(1,10))

p('EXPERIMENT REPORT  |  26 OCTOBER 2026','SmallX')
p('Crosscode','TitleX')
p('What happens when one model reviews another model\'s code?','H1X')
p('A first-reader guide to the tool, its data and the completed 50-task BigCodeBench-Hard experiment. Real API responses, official evaluator tests, transparent cost accounting.','BodyX')
note('<b>Headline:</b> Claude solo passed 45/50 tasks (90%). GPT solo passed 20/50 (40%). Claude reviewing GPT drafts reached 47/50 (94%); GPT reviewing Claude drafts reached 33/50 (66%). Review direction mattered in this sample.')
table(['Run at a glance','Observed result'],[
    ['Selected problems','50 of 148 hard tasks; one repetition; six workflows per task'],
    ['Saved generation stages','500 total: 498 valid programs, 2 terminal API failures'],
    ['Final workflow outcomes','300 attempted; 211 passes, 87 test failures, 2 API failures'],
    ['Recorded API spending',f"${metadata['ledger']['actual_usd']:.6f}; no unresolved reservations"],
    ['Highest observed pass rate','Claude self-review (AA): 48/50, or 96%'],
    ['Fastest / cheapest workflow','Fastest mean: Claude solo (11.1s). Cheapest: GPT solo ($0.007962/task).'],
],[140,W-140])
p('<b>The essential qualification:</b> AA already had 48/50 passing drafts before review and produced no pass/fail fixes. Its 96% final rate must not be described as evidence that self-review improved those drafts. The detailed before/after analysis is on page 6.')
p('Accuracy here means passing the benchmark\'s supplied tests. It does not measure every requirement, code maintainability, security, or performance at repository scale. Some inspected tasks contain ambiguities between written requirements and test expectations.')
caption('Source: completed run docker-hard-fifty-fixed [S1-S4]. All dollar figures are USD. This is a 50-task pilot, not a full 148-task hard-subset result. No inference was purchased to prepare this document.')

page('What the tool does','01 / Purpose and workflow')
p('Crosscode is a controlled experiment runner for comparing code-writing and one-pass code-review workflows. It asks two models to solve the same Python problems, optionally asks a second model to inspect each draft, and evaluates the resulting programs against the official BigCodeBench tests.')
h('One task, six workflows')
table(['Code','Writer','Reviewer','Meaning','Calls / 50 tasks'],[
    ['A','Claude','None','Claude solo','1 / 50'],['O','GPT','None','GPT solo','1 / 50'],
    ['AO','Claude','GPT','Cross-model review','2 / 100'],['OA','GPT','Claude','Cross-model review','2 / 100'],
    ['AA','Claude','Claude','Self-review','2 / 100'],['OO','GPT','GPT','Self-review','2 / 100'],
],[38,70,70,180,W-358])
caption('Table 1. A = Claude Opus 5.5; O = GPT-6.1 Sol. Letters are read left to right: writer, then reviewer. The design uses ten generation stages per task, or 500 across 50 tasks. [S1, S4]')
h('How a program moves through the system')
for title,text in [
    ('1. Freeze the experiment','Pin dataset revisions, selected task records, model IDs, prompts, settings and evaluator images. Run every selected reference solution in Docker before paid generation.'),
    ('2. Write a draft','Send only the problem statement and allowed starter interface. Ask for a complete Python program inside solution tags, plus a short confidence statement.'),
    ('3. Review once, where requested','Send the problem and the actual parsed draft to a reviewer. The reviewer is told not to run or test code and returns a final program. It receives no hidden tests, canonical answer or evaluator feedback.'),
    ('4. Evaluate and report','Score valid drafts and final programs in Docker. Save exact prompts/responses, programs, usage, costs, latency, test evidence and diffs. Generate tables, figures and a task audit.'),
]:
    h(title); p(text)
note('<b>Independent drafts:</b> the Claude solo draft, the AO draft and the AA draft are separate model calls. The GPT solo, OA and OO drafts are also separate. Arrows from solo to reviewed conditions compare pipelines; only a reviewer\'s actual input and output establish a same-draft fix or regression.')

page('The data and experimental setup','02 / What was tested')
p('The pinned BigCodeBench v0.1.4 snapshot contains 1,140 library-dependent Python function tasks. The separately pinned hard subset identifies 148 of those tasks. This run selects 50 hard-task IDs from a stable seed-42 ordering, with no library filters. It covers 33.8% of the hard pool, not all of BigCodeBench. [S1, S5]')
table(['Setting','Value'],[
    ['Task format','instruct: natural-language requirements plus required task_func interface/imports'],
    ['Models requested and returned','claude-opus-5-5 and gpt-6.1-sol'],
    ['Design / repetitions','paper-independent; all six conditions; one repetition'],
    ['Effort / output limit','medium for both; 16,384 output tokens per call'],
    ['Timeouts / retries','300 seconds API and evaluator; configured maximum retries = 0'],
    ['Selection / controls','hard; seed 42; 50 tasks; $40 total / $4 per task; sequential worker'],
    ['Evaluator readiness','All 50 selected canonical/reference solutions passed preflight'],
],[145,W-145])
h('The tasks are practical function exercises')
p('Examples include parsing dates from filenames, working with DataFrames, training small statistical models, drawing plots, processing audio, reading spreadsheets and extracting tables from HTML. These are function-level tasks with library dependencies, not end-to-end software projects.')
p('<b>Declared library coverage:</b> pandas and numpy each appear in 26/50 tasks, matplotlib in 21, os in 14, re in 8, datetime in 7, sklearn in 6 and scipy in 4. These overlapping counts come from declared library fields; official tests can import additional dependencies. [S1]')
h('What data goes to models, and what stays with evaluation')
p('Models receive the task\'s allowed instruction text and starter code; a reviewer additionally sees its actual writer program. Hidden tests and canonical solutions remain evaluation-only. The task manifest preserves the exact selected records and content hashes. Passing preflight verifies the environment can run the reference solutions; it does not tell the models what to write.')
p('The environment adds dependencies needed by this selection. Task 590 alone receives the authorized Wikibooks-only HTTPS transport, with a descriptive urllib User-Agent; other tasks remain offline. Tests and model programs were not rewritten. This adaptation and its image IDs are part of the recorded configuration. [S6]')

page('Accuracy across the six workflows','03 / Main result')
table(['Condition','Passed','Pass rate','95% bootstrap interval','Mean USD / task','Mean API seconds'],[
    [r['condition'],f"{r['passed']}/50",pct(r['pass_rate']),f"{pct(r['ci_low'])} - {pct(r['ci_high'])}",f(float(r['mean_workflow_cost_usd']),6),f(r['mean_workflow_latency_s'],1)] for r in table2
],[57,55,62,120,108,W-402])
caption('Table 2. Reliability-inclusive results: 50 terminal attempted workflows per condition. A and O each include one API failure as a failure; their valid-program evaluation counts are 49. All reviewed final workflows were valid and evaluated. Intervals use the saved 2,000 task-cluster bootstrap resamples. [S2]')
picture(TMP/'figure1_accuracy.png')
caption('Figure 1. Pass rates with saved 95% bootstrap intervals. Blue denotes a Claude writer; orange denotes a GPT writer. These intervals describe this experimental sample and protocol, not universal model capability.')
h('How to interpret the ranking')
p('<b>Claude solo:</b> 90% pass rate at about 2.31 cents per task and 11.1 seconds mean API latency. It was both more accurate and faster on average than GPT solo in this run, while GPT solo was cheaper.')
p('<b>Claude as reviewer:</b> OA reached 94%, and AA reached 96%. OA fixed many of its actual input drafts. AA\'s higher final rate versus solo reflects different drafts; no actual AA pass/fail fixes occurred.')
p('<b>GPT as reviewer:</b> AO finished at 66%, below Claude solo; OO finished at 36%, below GPT solo. The before/after evidence shows 15 AO regressions and no OO pass/fail changes. Reasons require task-specific inspection; aggregate rates alone do not explain them.')

page('Accuracy, cost and speed together','04 / Existing experiment figure')
picture(REPORT/'reliability-inclusive/figure2.png')
caption('Figure 2. Original generated Figure 2, reproduced from the completed run. Left: mean workflow cost versus pass rate. Right: mean workflow API latency versus pass rate. Circles are solo workflows; diamonds include review. Colors identify the writer. Coordinates match Table 2 exactly. [S2]')
h('Reading the figure')
p('Higher is a larger test pass rate. Further left is cheaper in the left panel, or faster in the right panel. A workflow near the upper-left corner offers a better observed trade-off on those two axes. The arrows compare independently generated workflows; they are not before/after trajectories for the same program.')
h('The measured trade-offs')
p('<b>Cost versus pass rate:</b> GPT solo is cheapest. Claude solo buys a much higher pass rate at a higher price. OA buys another two final passes over Claude solo in this 50-task comparison, for roughly 1.99 extra cents per task. AA buys one further pass over OA, at roughly 0.37 extra cents per task. These are sample comparisons, not guaranteed improvements on another workload.')
p('<b>Latency versus pass rate:</b> Claude solo is the fastest mean workflow; AA is slower but has the highest observed rate. OA is the slowest mean workflow. AA is both faster and more accurate than OA in this sample, but costs more.')
p('<b>Observed inefficient choices:</b> AO costs more, takes longer and passes fewer tasks than A. OO costs more, takes longer and passes fewer than O. Those are descriptive comparisons of this run\'s averages, not claims about all tasks or future model versions.')
note('<b>A strong default from this pilot:</b> Claude solo is the clearest measured balance of accuracy, time and cost. If reviewing an existing GPT draft, Claude review showed substantial benchmark benefit. The extra cost of routine Claude self-review is not justified by a demonstrated same-draft pass/fail improvement in this run.')
p('The figure does not include Docker evaluation time, preflight, report rendering, user pauses or provider billing overhead. Costs are recorded token-based API charges, including known reconciled amounts, rather than the machine\'s electricity or a ChatGPT subscription.')

page('Did the reviewer actually help?','05 / Pipeline differences versus real transitions')
table(['Writer / solo rate','Claude reviewer','GPT reviewer'],[
    ['Claude / 90%','AA: 96% (+6 pp)','AO: 66% (-24 pp)'],
    ['GPT / 40%','OA: 94% (+54 pp)','OO: 36% (-4 pp)'],
],[165,170,W-335])
caption('Table 3. Original writer-by-reviewer matrix. Deltas compare each reviewed pipeline with an independently sampled solo pipeline. pp = percentage points. [S2]')
h('The actual before/after programs tell a different, more precise story')
table(['Review','Draft passed','Final passed','Fixes','Regressions','Kept pass / fail'],[
    [r['condition'],f"{int(r['kept_pass'])+int(r['reviewer_regressions'])}/50",f"{int(r['kept_pass'])+int(r['reviewer_fixes'])}/50",r['reviewer_fixes'],r['reviewer_regressions'],r['kept_pass']+' / '+r['kept_fail']] for r in transitions
],[55,83,83,55,90,W-366])
caption('Table 6. Genuine same-draft transitions, from review_transitions.csv. All 50 actual draft/final pairs per reviewed condition were scored. A fix is fail-to-pass; a regression is pass-to-fail under the official tests. [S2, S4]')
p('<b>AO:</b> 48 Claude drafts passed before GPT review; only 33 final programs passed. GPT review retained 33 passes and two failures, created 15 test regressions, and fixed none. That is a 30-point decline on the actual drafts, distinct from the 24-point decline versus Claude solo.')
p('<b>OA:</b> 22 GPT drafts passed initially; 47 passed after Claude review. Claude fixed 25 failures, preserved all 22 initial passes and left three failures. The actual-draft improvement is 50 points. The 54-point matrix delta includes a four-point difference in the separate GPT solo draft sample.')
p('<b>AA:</b> all 48 passing drafts remained passing; both failing drafts remained failing. The +6-point matrix delta comes from the AA writer having three more passing drafts than the separate A writer. No benchmark fix or regression was observed from AA review.')
p('<b>OO:</b> all 18 passing drafts and 32 failing drafts retained their outcome. Its -4-point matrix delta comes from two fewer passing initial drafts than the separate O baseline, not observed reviewer damage.')
note('A reviewer can change code without changing its pass/fail result. Zero transitions do not mean byte-identical outputs or prove the review was useless for every unmeasured property. Conversely, a benchmark regression is not automatically a violation of the written requirements; page 10 illustrates why.')

page('What it cost','06 / Historical price snapshot and actual ledger')
p(f"The recorded total is <b>${metadata['ledger']['actual_usd']:.6f}</b> (about $8.29), including inherited purchases. All 500 attempts are settled; 498 are billable in the ledger and two disconnected attempts were reconciled at zero. No reservations or unknown charges remain. The $40 limit was a guardrail, not a charge. [S1, S4]")
price=next(x['pricing'] for x in stages.values() if x.get('pricing'))
table(['USD per 1M tokens','GPT-6.1 Sol','Claude Opus 5.5'],[
    ['Uncached input',f(price['O']['input']),f(price['A']['input'])],
    ['Cached input read',f(price['O']['cached']),f(price['A']['cached'])],
    ['Cache write / longer write',f"{f(price['O']['cache_write'])} / {f(price['O']['cache_write_long'])}",f"{f(price['A']['cache_write'])} / {f(price['A']['cache_write_long'])}"],
    ['Output',f(price['O']['output']),f(price['A']['output'])],
],[220,140,W-360])
caption('Table 7. Frozen 24 October 2026 price snapshot stored with this run, not a current price quote. GPT write lifetimes are 30 minutes / 12 hours; Claude write lifetimes are 5 minutes / 1 hour in the runner. Output totals already include reasoning/thinking tokens. Different provider input/cache fields are normalized by the runner to avoid double charging. [S4, S7]')
table(['Provider','Saved stages','Valid responses','Recorded USD'],[
    [r['model'],r['stages'],r['valid'],f(r['cost'],6)] for r in provider
],[185,100,110,W-395])
caption('Each provider supplied 250 scheduled stages; one terminal disconnection occurred for each. The recorded costs are derived from attempts, not added a second time from the original run. [S4]')
caption('Valid-response usage: Claude returned 184,627 input and 283,275 output tokens, with no cache reads/writes. GPT returned 113,675 input and 165,402 output tokens; 8,773 input tokens were cache writes, with no cache reads. Output totals include reasoning; they are not all visible program text. [S4]')
table(['Workflow','Writer USD','Review USD','Total USD','USD / passed final'],[
    [c,f(M[c]['writing_cost_usd'],4),f(M[c]['reviewing_cost_usd'],4),f(M[c]['workflow_cost_usd'],4),f(float(M[c]['workflow_cost_usd'])/int(M[c]['passed']),4)] for c in conditions
],[80,100,100,100,W-380])
caption('Table 8. Actual workflow spending across 50 tasks per condition. USD/passed final = total condition spending divided by its passing finals; this is a retrospective efficiency ratio, not the expected price of solving an arbitrary new task. All 50 cost rows per condition are known. Totals across conditions sum to the ledger (up to rounding). [S2, S4]')
p('Cost is calculated from the usage returned by each provider using the frozen price snapshot; verified reconciliation handles missing usage. The ledger is an experiment accounting record, not a substitute for vendor invoices, tax or currency conversion. No current vendor prices were fetched for this report.')

page('How long the workflows took','07 / API latency, not elapsed benchmark runtime')
picture(TMP/'figure3_latency.png')
caption('Figure 3. Mean writer and reviewer API time per workflow, stacked. Values are recomputed from the saved all_metrics.csv. The two terminal disconnections contribute their measured API time; model review is a sequential second call. [S2-S4]')
table(['Condition','Mean seconds','Median seconds','90th percentile seconds'],[
    [c,f(M[c]['mean_workflow_latency_s'],1),f(statistics.median(latencies[c]),1),f(quantile(latencies[c],.9),1)] for c in conditions
],[85,125,125,W-335])
caption('New descriptive latency summary from the 50 saved workflow durations per condition; percentile uses linear interpolation. These are observed durations, not service-level guarantees. [S3]')
p('Claude solo averaged 11.1 seconds per task versus 15.0 seconds for GPT solo. AA averaged 19.5 seconds, AO 21.0, OO 23.3 and OA 28.8. Provider speed can depend on output length, reasoning behavior, account routing and load; this run does not isolate which factor caused the differences.')
p(f"Across all six workflows and 50 tasks, summed recorded API time is {summary['summed_api_latency_seconds']/60:.1f} minutes. This sums work, not an uninterrupted end-to-end runtime. Saved call timestamps span {start.strftime('%d %b %H:%M')} to {end.strftime('%d %b %H:%M')} Asia/Karachi; that interval includes pauses and other phases and must not be treated as generation time.")
note('Docker setup, canonical preflight, evaluation, report building and user interruptions are outside the plotted API latency. The two pre-resume network failures were retained rather than silently retried. No time-to-first-token or generated-program runtime benchmark is reported.')

page('How strong is the evidence?','08 / Paired statistics and sensitivity')
p('The unit of comparison is the same selected task under two workflows. Exact two-sided McNemar tests use only tasks where the two outcomes differ. The runner adjusts across all 15 pairwise comparisons using Benjamini-Hochberg (BH), separately within each population and repetition. The six original displayed comparisons follow. [S2]')
table(['Comparison','First only','Second only','Exact p','BH adjusted p'],[
    [r['comparison'],r['first_only'],r['second_only'],f"{float(r['p_value']):.3g}",f"{float(r['bh_adjusted']):.3g}"] for r in comparisons
],[150,70,80,90,W-390])
caption('Table 4. All rows have 50 paired tasks; the adjustment family has 15 comparisons. First-only means the first named condition passes and the second fails, and vice versa. These are pipeline comparisons, not necessarily actual reviewer fixes. [S2]')
p('Within this sample, OA versus O and AO versus A show strong paired differences after adjustment. AA versus A (adjusted p = 0.3125) and OO versus O (0.5769) do not provide clear evidence of a pipeline difference. A non-small p-value does not establish equality; the sample has only 50 tasks and one repetition.')
h('Does excluding the API failures change the picture?')
table(['Condition','Reliability-inclusive / 50','Complete-case / 48'],[
    [r['condition'],f"{M[r['condition']]['passed']}/50 ({pct(M[r['condition']]['pass_rate'])})",f"{r['passed']}/48 ({pct(r['pass_rate'],1)})"] for r in cc
],[95,205,W-300])
caption('Table 9. Complete-case analysis drops tasks 108 and 915 from every condition because their solo workflows had API failures. Its smaller paired population is 48 tasks. Reliability-inclusive analysis counts those terminal API errors as failures in their affected workflows. [S2]')
p('The qualitative pattern is similar in both populations. This report leads with reliability-inclusive results because they include the actual operational failures. Bootstrap intervals use 2,000 resamples of whole task clusters, seed 42; they do not capture all uncertainty from future tasks, model updates, prompt choice or repeated sampling.')

page('What went right or wrong in examples','09 / Table 5: inspected transitions and benchmark caveats')
p('The original generated Table 5 selects the first two task IDs per condition and true transition. Its causal descriptions were marked pending inspection. For this report, the following examples were checked against saved code diffs, supplied instructions, official tests and evaluator tracebacks. These observations explain only these cases; the run\'s annotation files were not changed. [S1, S4]')
table(['Task / workflow','Measured transition','Evidence-based observation'],[
    ['1057 / OA','Fail -> pass','Claude changed missing/default input handling and the default animal/food lists. The GPT draft returned a 0 x 0 frame for no arguments and 3 x 3 for a partial-default test; tests expected 10 x 7 and 3 x 7. The final program passed.'],
    ['1057 / AO','Pass -> fail','GPT normalized omitted arguments to empty lists and returned an empty DataFrame when both were absent. The official default-input test expected 10 x 7. The written instruction says both empty or not provided should return empty, creating a specification/test tension.'],
    ['1008 / AO','Pass -> fail','GPT wrapped a requests ConnectionError as HTTPError. The supplied prose asks for HTTPError on request failures, but test_network_error expects the original ConnectionError to propagate. The traceback identifies this exception-type mismatch.'],
],[87,90,W-177])
caption('Table 5. Task IDs are BigCodeBench IDs. The first example is a measured benchmark repair; the latter two are measured test regressions with instruction/test ambiguities. No tests were modified, excluded or supplied to the models.')
h('Why these examples matter')
p('A score change records agreement with this test suite. It does not by itself establish that the reviewer made the program less faithful to the natural-language request. In both inspected AO examples, the changed behavior can be read as aligning with part of the instruction while failing the official test. Calling all 15 AO regressions careless code review would go beyond the evidence.')
p('Task 1057 also leaves exact predefined lists underspecified in the shown instruction. Successful code supplies values matching the benchmark\'s expectations; this report cannot establish how a model obtained them. Benchmark contamination or memorization is a possibility, not a demonstrated cause.')
p('The generated selection also contains task 187 as an OA fix. Its outcome is verified in the saved evaluator evidence, but a full causal explanation is not asserted here. Exact model responses, parsed code, diffs and test details remain available in the task audit for every workflow.')
note('Interpret the headline as <b>benchmark test performance under this recorded protocol</b>. A requirements audit or independent test suite is needed before translating these figures into production-quality claims.')

page('Completion, reliability and visibility','10 / What was actually finished')
table(['Layer','Completion and outcomes'],[
    ['Problem selection','50 tasks x 6 final workflows = 300 attempted final workflows'],
    ['Generation','500 saved stages: 498 valid programs and 2 terminal API failures'],
    ['Program evaluation','498 valid programs evaluated: 347 pass, 151 fail, zero infrastructure failures'],
    ['Final workflow evaluation','298 valid finals: 211 pass, 87 fail; 2 API failures complete the 300 workflows'],
    ['Actual review draft evaluation','200 drafts from AO, OA, AA and OO were also evaluated; these are not extra final workflows'],
    ['Accounting','500 settled attempts; 498 billable attempts; zero unresolved/reserved USD'],
],[155,W-155])
caption('Stage-level 347/498 must not be presented as the final workflow accuracy. It includes intermediate drafts. Likewise, 500 saved stages means execution is complete, not that every task passed. [S1-S4]')
h('The two operational failures')
p('Claude solo on task 108 and GPT solo on task 915 recorded RemoteDisconnected API failures. Their responses are unavailable, and they were not silently regenerated. Billing was reconciled at zero; they are counted as failures in reliability-inclusive results. They are communication failures rather than evaluated incorrect programs.')
h('What a user can inspect')
p('The task audit records each task\'s full requirements and interface, every requested workflow and exact saved writer/reviewer text, prompts, parsed programs, provider response structures, usage, prices, elapsed time, attempts, diffs and evaluator evidence. It distinguishes unstarted, invalid, failed and passed work. Provider-private reasoning that was not returned cannot be recovered.')
p('Live PowerShell progress identifies task, condition, role, model and attempt ID, reports cache reuse and spending, and emits an elapsed-time heartbeat while waiting. Events are appended to progress.log. The log is for operational visibility; the audit provides the full program-level evidence.')
h('How progress and money are protected')
p('Saved stage identities bind the exact task, prompt, model/settings and parent draft. SQLite checkpoints preserve completed work. Conservative atomic reservations check total and per-task budgets before dispatch; unknown usage blocks further generation until reconciliation. Resuming compatible work reuses it. Limits are local guardrails, not provider-enforced invoice caps.')

page('What to conclude, and what to test next','11 / Scope and practical interpretation')
h('What this experiment supports')
p('For this 50-task sample, Claude solo delivered a much higher test pass rate than GPT solo, with lower mean API latency but higher cost. Claude review substantially improved its actual GPT input drafts. GPT review damaged test outcomes on some otherwise passing Claude drafts. Review direction therefore matters, and a second model call is not automatically beneficial.')
p('Claude self-review produced the highest observed final rate, but the same drafts had already achieved that rate. Its extra cost and latency purchased no measured fail-to-pass transitions in this run. A direct comparison with the separate solo pipeline cannot isolate self-review\'s causal effect.')
h('What it does not support')
p('This is not a general ranking of these model families. It uses 50 selected tasks from 148 hard tasks, one repetition, one prompt pair, one effort setting and a 16,384-token ceiling. Equal effort labels and caps do not equalize compute or reasoning. Model aliases can change; exact requested and returned identifiers are saved, but not all serving details are exposed.')
p('These tasks are library-dependent functions. They do not validate repository understanding, multi-file changes, deployment, security, human review utility or long-term maintenance. Test coverage and instruction/test disagreement limit what a pass means. Contamination may affect results. Evaluator dependency versions and the live Wikibooks page add reproducibility constraints.')
h('A sensible next experiment')
p('First inspect the remaining review regressions and failures and tag requirements/test disagreements separately from clear code defects. Then repeat generation on the same tasks to quantify sampling variation, while keeping prompts and evaluator settings fixed. To estimate review benefit directly, compare each reviewer\'s actual draft with its final program, rather than attributing independent-draft baseline differences to review.')
p('A broader evaluation could cover all 148 hard tasks after their canonical preflight passes, and add an independent test set or requirements audit. Dependency/network support for the other 98 tasks is not established by this run. Keep those changes as new configurations and disclose which model outputs were reused.')
h('Terms used in this report')
table(['Term','Meaning'],[
    ['Pass rate / accuracy','Fraction of workflow outcomes passing the supplied official tests'],
    ['pp / SID','Percentage-point difference from a solo baseline; a pipeline comparison'],
    ['Fix / regression','The same actual reviewer input changes from fail to pass / pass to fail'],
    ['Complete-case','Only tasks evaluated in every requested condition (48 here)'],
    ['Reliability-inclusive','Includes terminal invalid/API attempts as failures; excludes infrastructure-only and unstarted work'],
],[125,W-125])

# Compact per-task appendix, preserving frozen selection order.
for chunk in range(2):
    selected=manifest['tasks'][chunk*25:(chunk+1)*25]
    page(f'Task-level results ({chunk*25+1}-{chunk*25+25} of 50)','Appendix A / Selected tasks and final outcomes')
    caption('P = official tests passed; F = valid program failed tests; E = terminal API failure. No infrastructure failures occurred. Short task descriptions below are editorial summaries of the frozen instructions, not substitutes for their full requirements. [S1, S3]')
    data=[]
    for t in selected:
        text=t['instruct_prompt'].split('Note that:')[0].strip().split('\n')[0]
        # Bound length for a readable two-line task label; full text stays in audit.
        words=text[:90].rsplit(' ',1)[0] if len(text)>90 else text
        if len(text)>90: words+='...'
        outcomes=[]
        for c in conditions:
            r=R[(t['task_id'],c)]
            outcomes.append('E' if not r['valid'] else ('P' if r['outcome'] else 'F'))
        data.append([t['task_id'].split('/')[-1],words]+outcomes)
    table(['ID','Task requirement (abridged)']+conditions,data,[36,W-36-6*25]+[25]*6,small=True)
    caption('Selection order is the original frozen seed-42 prefix. All 50 reference solutions passed; P/F/E above refer to model workflows, not reference preflight. Full exact requirements and programs are in report/task-audit/index.md within the run.')

page('Sources, reproducibility and file guide','Appendix B / Audit trail')
p('This report was compiled from saved local evidence on 26 October 2026. It makes no new provider calls and does not change checkpoints, model outputs, annotations or evaluation results. Historical pricing is quoted from the run, without asserting current vendor tariffs.')
references=[
    ('S1','Frozen run configuration and manifest','runs/docker-hard-fifty-fixed/config.json; manifest.json. Exact task fields, selection, model settings and hashes.'),
    ('S2','Generated population tables and figure','report/reliability-inclusive/{table2,table3,table4,table5,all_metrics,review_transitions}.csv; figure2.png. Sensitivity: report/complete-case/table2.csv.'),
    ('S3','Saved workflow analysis','report/results.json, including metadata, cumulative ledger and 300 final workflow records. Supplementary latency percentiles in this PDF are calculated from these durations.'),
    ('S4','Original attempt and program evidence','checkpoint.sqlite: stages, attempts and evaluations; report/task-audit/index.md. Read-only queries verified totals, outcomes and code examples for this report.'),
    ('S5','Pinned benchmark and study sources','sources.lock.json. BigCodeBench full snapshot b74c0d0bf70d2c0bc459be537895cca163007f1a; hard snapshot 298d2cc7b96612e15e47313c3603ee124cee0c1f; v0.1.4.'),
    ('S6','Evaluator and continuation provenance','docker/wikibooks.image.lock.json; docs/EVALUATION.md; preflight.json; migration.json. Original 100 generation stages were inherited and saved programs rescored under the new evaluator.'),
    ('S7','Frozen pricing and accounting implementation','Per-stage pricing snapshot dated 2026-10-24, plus crosscode/providers.py and crosscode/store.py. Documentation links recorded with that snapshot are listed below.'),
]
for key,title,detail in references:
    p(f'<b>[{key}] {title}.</b> '+escape(detail),'SmallX')
caption('All relative paths above are under the CrossCode workspace unless they start with report/ or name a run-local file. Run-local files are under runs/docker-hard-fifty-fixed/.')
h('Primary project and data links')
for label,url in [
    ('BigCodeBench source','https://github.com/bigcode-project/bigcodebench'),
    ('Full dataset','https://huggingface.co/datasets/bigcode/bigcodebench'),
    ('Hard subset','https://huggingface.co/datasets/bigcode/bigcodebench-hard'),
    ('Cross-model review reference implementation','https://github.com/shawnzxiang/cross-model-review-code'),
    ('GPT pricing documentation recorded by the run',price['O']['source']),
    ('Claude pricing documentation recorded by the run',price['A']['source']),
]:
    p(f'<link href="{escape(url)}" color="#137b87">{escape(label)}</link>','SmallX')
h('Immutable configuration identity')
caption(manifest['config_hash'][:32]+'<br/>'+manifest['config_hash'][32:])
caption('Evaluator: afd0ca41f44b14dd7460a52cde246c49e0e4fff6dd84256e2643728917072c7f<br/>Proxy: 3304f6c216ff7e417f71a675773d5a1c939dfa4414423fb009e5404685a19ef9')
caption('Image values above are SHA256 IDs. Evaluator source commit: 09dd993f46c3fbf3a799465bb96d524edcb0b199. The continuation includes inherited purchases from docker-hard-five-check; do not add their overlapping ledgers. The associated .data.json file preserves the numerical report inputs and derived summaries.')

class NumberedCanvas(canvas.Canvas):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.saved=[]
    def showPage(self):
        self.saved.append(dict(self.__dict__)); self._startPage()
    def save(self):
        count=len(self.saved)
        for state in self.saved:
            self.__dict__.update(state)
            self.setStrokeColor(colors.HexColor('#d7e1e8')); self.line(44,39,A4[0]-44,39)
            self.setFont('Report',8); self.setFillColor(MUTED)
            self.drawString(44,26,'CROSSCODE  |  50 HARD TASKS  |  26 OCT 2026')
            self.drawRightString(A4[0]-44,26,f'{self._pageNumber} / {count}')
            if self._pageNumber>1:
                self.setFont('Report',8); self.drawString(44,A4[1]-28,'EXPERIMENT RESULTS  /  docker-hard-fifty-fixed')
            super().showPage()
        super().save()

doc=SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=44,leftMargin=44,topMargin=48,bottomMargin=53,
                      title='Crosscode - 50 Hard Tasks: Tool, Methods and Results',author='Crosscode experiment report',
                      subject='BigCodeBench-Hard accuracy, cross-model review, cost and latency')
doc.build(story,canvasmaker=NumberedCanvas)
sources=[RUN/'config.json',RUN/'manifest.json',REPORT/'results.json',REPORT/'reliability-inclusive/table2.csv',REPORT/'reliability-inclusive/figure2.png']
(OUT/'Crosscode_50_Hard_Tasks_Report.sources.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},indent=2)+'\n',encoding='utf-8')
print(PDF)
print(json.dumps({'provider_costs':provider,'summed_API_minutes':summary['summed_api_latency_seconds']/60,'timestamp_window':[start.isoformat(),end.isoformat()]},indent=2))
