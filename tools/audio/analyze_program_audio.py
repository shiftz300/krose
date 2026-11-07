"""Analyze audit-program-audio float windows; candidates require human review.

NumPy is an optional offline developer dependency. Noise, chords, organ drawbars,
intentional detuning and pitch envelopes must never be corrected automatically.
"""
import argparse
from pathlib import Path
import numpy as np,csv,math,json
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('prefixes',nargs='+',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
allrows=[]
for path in args.prefixes:
 prefix=str(path)
 rows=list(csv.DictReader(open(prefix+'.tsv'),delimiter='\t'))
 data=np.memmap(prefix+'.f32',dtype='<f4',mode='r').reshape(-1,2,4096)
 for r in rows:
  if int(r['drum']):continue
  expected=440*2**((int(r['note'])-69)/12)
  observations=[]
  for x in data[int(r['snippet'])]:
   x=x.astype(float);x-=x.mean()
   e=np.dot(x,x)
   if e<1e-8:observations.append((0,0));continue
   spec=np.fft.rfft(x,n=8192);acf=np.fft.irfft(abs(spec)**2,n=8192)[:4096]
   sq=np.r_[0,np.cumsum(x*x)]
   lag=np.arange(4096);norm=np.sqrt(np.maximum(1e-30,sq[4096-lag]*(sq[-1]-sq[lag])))
   acf=acf/norm
   lo=max(3,int(12000/(expected*2.1)));hi=min(1500,int(12000/(expected/2.1)))
   peaks=np.where((acf[lo:hi]>acf[lo-1:hi-1])&(acf[lo:hi]>=acf[lo+1:hi+1]))[0]+lo
   if not len(peaks):observations.append((0,0));continue
   best=max(acf[peaks]);peaks=peaks[acf[peaks]>=max(.75,best*.94)]
   if not len(peaks):observations.append((0,float(best)));continue
   at=min(peaks,key=lambda v:abs(math.log2((12000/v)/expected)))
   delta=.5*(acf[at-1]-acf[at+1])/(acf[at-1]-2*acf[at]+acf[at+1])
   hz=12000/(at+delta);cents=1200*math.log2(hz/expected)
   observations.append((float(cents),float(acf[at])))
  for k,(c,q) in enumerate(observations):r['cents'+str(k)]=round(c,3);r['confidence'+str(k)]=round(q,4)
  allrows.append(r)
with args.output.with_suffix('.pitch.tsv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=allrows[0].keys(),delimiter='\t');w.writeheader();w.writerows(allrows)
# Flag coherent errors across pitches/velocities, never noise or just an onset.
groups={}
for r in allrows:
 if float(r['confidence1'])>.9:groups.setdefault(r['id'],[]).append(r)
sus=[]
for id,rows in groups.items():
 v=np.array([float(r['cents1']) for r in rows]);pc=(v+600)%1200-600;v=pc
 med=float(np.median(v));mad=float(np.median(abs(v-med)))
 if len(rows)>=5 and abs(med)>20 and mad<25:sus.append((id,rows[0]['name'],len(rows),round(med,1),round(mad,1)))
summary={'pitched_conditions':len(allrows),
         'reliable_held_windows':sum(float(r['confidence1'])>.9 for r in allrows),
         'candidate_rules':{'confidence':.9,'minimum_conditions':5,'median_absolute_cents':20,'maximum_MAD_cents':25},
         'pitch_candidates':sorted(sus,key=lambda x:-abs(x[3])),
         'boundary':'Candidates are not diagnoses; no audio or tuning is modified.'}
args.output.with_suffix('.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
