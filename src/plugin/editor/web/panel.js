
function kroseLcdBitmap(view){
 const W=240,H=64,bits=new Uint8Array(W*H);
 const glyphs={
 ' ':[0,0,0,0,0],'!':[0,0,95,0,0],'%':[35,19,8,100,98],'+':[8,8,62,8,8],'-':[8,8,8,8,8],'.':[0,96,96,0,0],':':[0,54,54,0,0],'/':[32,16,8,4,2],'_':[64,64,64,64,64],'>':[0,65,34,20,8],'<':[8,20,34,65,0],
 '0':[62,81,73,69,62],'1':[0,66,127,64,0],'2':[66,97,81,73,70],'3':[33,65,69,75,49],'4':[24,20,18,127,16],'5':[39,69,69,69,57],'6':[60,74,73,73,48],'7':[1,113,9,5,3],'8':[54,73,73,73,54],'9':[6,73,73,41,30],
 A:[126,17,17,17,126],B:[127,73,73,73,54],C:[62,65,65,65,34],D:[127,65,65,34,28],E:[127,73,73,73,65],F:[127,9,9,9,1],G:[62,65,73,73,122],H:[127,8,8,8,127],I:[0,65,127,65,0],J:[32,64,65,63,1],K:[127,8,20,34,65],L:[127,64,64,64,64],M:[127,2,12,2,127],N:[127,4,8,16,127],O:[62,65,65,65,62],P:[127,9,9,9,6],Q:[62,65,81,33,94],R:[127,9,25,41,70],S:[70,73,73,73,49],T:[1,1,127,1,1],U:[63,64,64,64,63],V:[31,32,64,32,31],W:[63,64,56,64,63],X:[99,20,8,20,99],Y:[7,8,112,8,7],Z:[97,81,73,69,67],
 a:[32,84,84,84,120],b:[127,72,68,68,56],c:[56,68,68,68,32],d:[56,68,68,72,127],e:[56,84,84,84,24],f:[8,126,9,1,2],g:[12,82,82,82,62],h:[127,8,4,4,120],i:[0,68,125,64,0],j:[32,64,68,61,0],k:[127,16,40,68,0],l:[0,65,127,64,0],m:[124,4,24,4,120],n:[124,8,4,4,120],o:[56,68,68,68,56],p:[124,20,20,20,8],q:[8,20,20,24,124],r:[124,8,4,4,8],s:[72,84,84,84,32],t:[4,63,68,64,32],u:[60,64,64,32,124],v:[28,32,64,32,28],w:[60,64,48,64,60],x:[68,40,16,40,68],y:[12,80,80,80,60],z:[68,100,84,76,68]
 };
 const px=(x,y)=>{if(x>=0&&y>=0&&x<W&&y<H)bits[y*W+x]=1;};
 /* Large main-name glyphs: 18 rows rather than the seven-row parameter font.
  * Proportional lowercase and curved shoulders follow the supplied MAIN photo.
  */
 const rows={
 C:'0011111100|0110000110|1100000011|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000011|0110000110|0011111100',
 G:'0011111100|0110000110|1100000011|1100000000|1100000000|1100000000|1100000000|1100000000|1100011111|1100000011|1100000011|1100000011|1100000011|1100000011|1100000011|1100000011|0110000111|0011111011',
 S:'0011111100|0110000110|1100000011|1100000000|1100000000|0110000000|0011000000|0001100000|0000110000|0000011000|0000001100|0000000110|0000000011|0000000011|0000000011|1100000011|0110000110|0011111100',
 E:'1111111111|1111111111|1100000000|1100000000|1100000000|1100000000|1100000000|1111111100|1111111100|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1100000000|1111111111|1111111111',
 W:'11000000011|11000000011|11000000011|11000000011|11000000011|11000000011|11000000011|11000000011|11000100011|11001110011|11001110011|11011011011|11011011011|11110001111|11110001111|11100000111|11000000011|11000000011',
 o:'001111100|011000110|110000011|110000011|110000011|110000011|110000011|110000011|110000011|110000011|011000110|001111100',
 n:'110111100|111000110|110000011|110000011|110000011|110000011|110000011|110000011|110000011|110000011|110000011|110000011',
 c:'001111100|011000110|110000011|110000000|110000000|110000000|110000000|110000000|110000000|110000011|011000110|001111100',
 e:'001111100|011000110|110000011|110000011|111111111|110000000|110000000|110000000|110000000|110000011|011000110|001111100',
 r:'1101110|1110011|1100000|1100000|1100000|1100000|1100000|1100000|1100000|1100000|1100000|1100000',
 t:'0011000|0011000|0011000|0011000|1111111|1111111|0011000|0011000|0011000|0011000|0011000|0011000|0011000|0011000|0011000|0011011|0001110|0001100',
 a:'001111100|011000110|000000011|000000011|001111111|011000011|110000011|110000011|110000011|110000111|011001111|001110011',
 d:'000000011|000000011|000000011|000000011|000000011|000000011|001111011|011000111|110000011|110000011|110000011|110000011|110000011|110000011|110000011|110000011|011000111|001111011',
 i:'11|11|00|00|00|00|11|11|11|11|11|11|11|11|11|11|11|11',
 m:'110110110|111001001|110001001|110001001|110001001|110001001|110001001|110001001|110001001|110001001|110001001|110001001'
 };
 const large=ch=>{if(ch===' ')return Array(18).fill('00000');if(rows[ch]){const r=rows[ch].split('|');return [...Array(18-r.length).fill('0'.repeat(r[0].length)),...r];}const g=glyphs[ch]||glyphs[ch.toUpperCase()]||glyphs[' '];return Array.from({length:18},(_,y)=>Array.from({length:10},(_,x)=>(g[Math.floor(x/2)]&(1<<Math.min(6,Math.floor(y*7/18))))?'1':'0').join(''));};
 const name=view.name||'Kross Grand Piano 1';
 const letters=[...name].map(large),textWidth=letters.reduce((sum,r)=>sum+r[0].length+2,0)-2;
 let x=Math.max(8,Math.floor((W-textWidth)/2));const start=x,y=22;
 for(const r of letters){for(let j=0;j<18;j++)for(let i=0;i<r[j].length;i++)if(r[j][i]==='1')px(x+i,y+j);x+=r[0].length+2;}
 const small=(str,x,y)=>{for(const ch of str){const g=glyphs[ch]||glyphs[' '];for(let col=0;col<5;col++)for(let row=0;row<7;row++)if(g[col]&(1<<row))px(x+col,y+row);x+=6;}};
 small('PROG',2,1);small('MAIN',109,1);small('TONE',143,1);small('FX',180,1);small('ARP',209,1);
 for(let x=0;x<240;x++)px(x,9);
 small((view.category||'PIANO')+':000 ('+(view.code||'A000')+')',31,12);
 small('120.00',193,12);
 for(let x=3;x<237;x++)px(x,47);
 small('SW1:Octave Down',3,54);small('SW2:Octave Up',142,54);
 return {width:W,height:H,bits,title:name,titleBounds:{x:start,y,width:textWidth,height:18}};
}
function krosePaintLcd(canvas,view){
 const bitmap=kroseLcdBitmap(view),ctx=canvas.getContext('2d'),pitch=6;canvas.width=bitmap.width*pitch;canvas.height=bitmap.height*pitch;
 const glow=ctx.createLinearGradient(0,0,0,canvas.height);glow.addColorStop(0,'#e4ecda');glow.addColorStop(.5,'#dbe5d3');glow.addColorStop(1,'#d6e2d0');ctx.fillStyle=glow;ctx.fillRect(0,0,canvas.width,canvas.height);
 for(let y=0;y<bitmap.height;y++)for(let x=0;x<bitmap.width;x++){ctx.fillStyle=bitmap.bits[y*bitmap.width+x]?'#3c5294':'#77977b13';ctx.fillRect(x*pitch,y*pitch,5,5);}
 canvas.setAttribute('aria-label',bitmap.title+'，大字点阵主界面');
}
(()=>{
const root=document.getElementById('krose-fixed-ui');
const $=s=>root.querySelector(s), $$=s=>[...root.querySelectorAll(s)];
const native=window.kroseNative;
const presets=native?.presets||[['A000','Kross GrandPiano 1','PIANO',0],['A061','Celesta','PIANO',61],['B097','DWGS Bells 1','BELL',5],['C001','Stereo Strings 1','STRINGS',0]];
const presetOrder=native?.browser.order||presets.map((_,i)=>i);
const lcdResources={"source":"KROSS2 v1.2.4 KROSSAPP.bin","row_encoding":"Each integer is one row, most significant visible bit at left.","symbols":{"PIANO":{"offset":"0x38e219","width":14,"height":12,"rows":[4064,8176,8188,16383,16383,16383,16383,10837,10837,8193,16383,4290]},"E.PIANO":{"offset":"0x38e231","width":14,"height":12,"rows":[8190,16383,12291,16383,10837,10837,8193,16383,8190,2052,4098,8193]},"ORGAN":{"offset":"0x38e249","width":14,"height":12,"rows":[16383,10927,11007,16383,10837,10837,8193,16383,10837,10837,8193,16383]},"BELL":{"offset":"0x38e261","width":14,"height":12,"rows":[6,11,255,270,524,7180,4872,4504,4784,2656,3168,992]},"STRINGS":{"offset":"0x38e279","width":14,"height":12,"rows":[1804,2192,5728,8896,8496,12872,7784,1840,2488,4349,8199,11]},"BRASS":{"offset":"0x38e291","width":14,"height":12,"rows":[0,8192,8360,12288,14504,16383,14764,12970,8874,8706,508,0]},"SYNTH":{"offset":"0x38e2a9","width":14,"height":12,"rows":[16383,12125,16383,11093,16383,16213,11263,16383,11093,11093,16129,16383]},"SYNTH_ALT":{"offset":"0x38e2c1","width":14,"height":12,"rows":[16383,16383,16383,11221,15999,10837,16383,16383,10837,10837,8193,16383]},"GUITAR":{"offset":"0x38e2d9","width":14,"height":12,"rows":[14,30,60,1904,1120,6528,8608,10272,11360,9920,4288,3968]},"BASS":{"offset":"0x38e2f1","width":14,"height":12,"rows":[7,398,600,560,7272,8396,8460,9228,11832,7216,6192,10176]},"DRUM/SFX":{"offset":"0x38e309","width":14,"height":12,"rows":[4100,14350,4100,6004,6014,4574,4654,5140,5140,5140,14894,10698]},"AC":{"offset":"0x38e209","width":13,"height":8,"rows":[2040,4088,3279,6840,6328,2767,4088,2040]}},"aliases":{"SYNTH LEAD":"SYNTH","SYNTH PAD":"SYNTH"},"font":{"offset":"0x394f84","stride":10,"glyphs":{" ":[3,0,0,0,0,0,0,0,0,0],"(":[6,16,32,64,64,64,64,64,32,16],")":[6,64,32,16,16,16,16,16,32,64],":":[4,0,0,0,64,0,0,0,64,0],".":[4,0,0,0,0,0,0,0,64,0],"0":[6,0,112,136,152,168,200,136,112,0],"1":[6,0,32,96,32,32,32,32,32,0],"2":[6,0,112,136,136,16,32,64,248,0],"3":[6,0,112,136,8,48,8,136,112,0],"4":[6,0,16,48,80,144,248,16,16,0],"5":[6,0,248,128,240,8,8,136,112,0],"6":[6,0,112,128,240,136,136,136,112,0],"7":[6,0,248,8,16,32,32,32,32,0],"8":[6,0,112,136,136,112,136,136,112,0],"9":[6,0,112,136,136,136,120,8,112,0],"A":[6,0,32,80,80,136,248,136,136,0],"B":[6,0,240,136,136,240,136,136,240,0],"C":[6,0,112,136,128,128,128,136,112,0],"D":[6,0,240,136,136,136,136,136,240,0],"E":[6,0,248,128,128,240,128,128,248,0],"F":[6,0,248,128,128,240,128,128,128,0],"G":[6,0,120,128,128,152,136,136,120,0],"H":[6,0,136,136,136,248,136,136,136,0],"I":[2,0,128,128,128,128,128,128,128,0],"J":[5,0,16,16,16,16,16,144,96,0],"K":[6,0,136,144,160,192,160,144,136,0],"L":[6,0,128,128,128,128,128,128,248,0],"M":[8,0,130,198,170,170,146,146,130,0],"N":[6,0,136,200,200,168,152,152,136,0],"O":[6,0,112,136,136,136,136,136,112,0],"P":[6,0,240,136,136,240,128,128,128,0],"Q":[6,0,112,136,136,136,168,144,104,0],"R":[6,0,240,136,136,240,160,144,136,0],"S":[6,0,112,136,128,112,8,136,112,0],"T":[6,0,248,32,32,32,32,32,32,0],"U":[6,0,136,136,136,136,136,136,120,0],"V":[6,0,136,136,80,80,80,32,32,0],"W":[8,0,130,146,84,84,84,40,40,0],"X":[6,0,136,136,80,32,80,136,136,0],"Y":[6,0,136,136,80,32,32,32,32,0],"Z":[6,0,248,8,16,32,64,128,248,0],"/":[5,0,16,16,32,32,64,64,128,128]}},"tempoReference":{"origin":"User MAIN status-row photo","bpm":"125.00","sprites":{"[":[6,4,4,4,4,4,4,4,6],"]":[6,2,2,2,2,2,2,2,6],"note":[1,1,1,1,1,7,15,14],"=":[31,0,31],"1":[7,3,3,3,3],"2":[63,3,63,48,63],"5":[63,48,63,3,63],".":[3],"0":[30,51,51,51,30]}}};
function drawProgramRow(p){
 const [code,,category,index]=p;
 const displayCode=code.toUpperCase().replace(/^EXPCM00([124]):/,'E$1-');
 const label=category.replace('SYNTH ','')+':'+String(index).padStart(3,'0')+' ('+displayCode+')';
 const canvas=$('#kf-program-row'),ctx=canvas.getContext('2d');
 ctx.clearRect(0,0,240,12);ctx.fillStyle=getComputedStyle($('.lcd')).getPropertyValue('--ink').trim();
 function stamp(rows,width,x,y){
  rows.forEach((bits,j)=>{for(let i=0;i<width;i++)if(bits&(1<<(width-1-i)))ctx.fillRect(x+i,y+j,1,1);});
 }
 const symbols=lcdResources.symbols,icon=symbols[lcdResources.aliases[category]||category];
 if(icon)stamp(icon.rows,icon.width,10,0);
 const letters=[...label].map(ch=>lcdResources.font.glyphs[ch]||(ch==='-'?[6,0,0,0,248,0,0,0,0,0]:lcdResources.font.glyphs[' ']));
 let x=Math.min(59,154-letters.reduce((n,g)=>n+g[0],0));
 for(const [advance,...rows] of letters){stamp(rows,8,x,2);x+=advance;}
 const sample=lcdResources.tempoReference.sprites;
 for(const [ch,width,dx,y] of [['[',3,0,1],['note',4,5,2],['=',5,12,4],['1',3,20,3],['2',6,27,3],['5',6,35,3],['.',2,43,7],['0',6,49,3],['0',6,57,3],[']',3,65,1]]){
  stamp(sample[ch],width,157+dx,y);
 }
 stamp(symbols.AC.rows,symbols.AC.width,227,2);
 canvas.setAttribute('aria-label',label+' · 125.00 BPM · AC');
}
const defaults={output:-6,cutoff:0,resonance:0,velocity:1,pan:0,glide:0,gate:80,swing:0};
const keyGeometry={whitePitch:34,whiteLength:216,blackWidth:20.4,blackLength:134};
let state={version:1,values:{...defaults},toggles:{arp:true,latch:false,host:true,sustain:false,sw1:false,sw2:false},fx:{insert:true,master:true},fxEdits:{},fxFolded:false,eg:'amp',envelopes:{amp:{attack:0,decay:0,sustain:0,release:0},filter:{attack:0,decay:0,sustain:0,release:0}},voice:'poly',preset:0,page:'main',octave:0,rate:'1/16',pattern:'UP',wheels:{pitch:0,mod:0}};
let compare=null;
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));
const signed=n=>(n>=0?'+':'−')+String(Math.abs(n)).padStart(2,'0');
function feedback(t){$('#kf-feedback').textContent=t;}
function persist(){const fn=window.openai?.setWidgetState;if(fn)Promise.resolve(fn({modelContent:{kroseFixedUI:compare?{...state,...compare}:state}})).catch(()=>{});}
function loadShared(s){const incoming=s?.modelContent?.kroseFixedUI;if(!incoming||incoming.version!==1)return;state={...state,...incoming,values:{...defaults,...incoming.values},toggles:{...state.toggles,...incoming.toggles},envelopes:{amp:{...state.envelopes.amp,...incoming.envelopes?.amp},filter:{...state.envelopes.filter,...incoming.envelopes?.filter}},wheels:{pitch:0,mod:0,...incoming.wheels}};state.preset=clamp(Number(state.preset)||0,0,presets.length-1);state.eg=state.eg==='filter'?'filter':'amp';state.page=['main','tone','fx','arp'].includes(state.page)?state.page:'main';state.octave=clamp(Number(state.octave)||0,-2,2);}
loadShared(window.openai?.widgetState);
if(native)state.toggles.arp=false;
state.fx={insert:true,master:true,...state.fx};
const categoryGroups=new Map();
presetOrder.forEach(i=>{
 const p=presets[i],option=document.createElement('option');option.value=String(i);option.textContent=p[0]+'  '+p[1];
 let parent=$('#kf-program');
 if(native){if(!categoryGroups.has(p[2])){const group=document.createElement('optgroup');group.label=p[2];parent.append(group);categoryGroups.set(p[2],group);}parent=categoryGroups.get(p[2]);}
 parent.append(option);
});
$$('[data-control]').forEach(c=>{
const key=c.dataset.control,label=c.dataset.label,min=+c.dataset.min,max=+c.dataset.max,step=+(c.dataset.step||1);
const caption=document.createElement('label');caption.className='caption';caption.textContent=label;caption.htmlFor='kf-value-'+key;
const knob=document.createElement('button');knob.type='button';knob.className='knob cursor-interaction';knob.role='slider';knob.setAttribute('aria-label',label);knob.setAttribute('aria-valuemin',min);knob.setAttribute('aria-valuemax',max);const pointer=document.createElement('span');pointer.className='pointer';knob.append(pointer);
const input=document.createElement('input');input.id='kf-value-'+key;input.type='text';input.inputMode='decimal';input.className='readout';input.setAttribute('aria-label',label+' value');c.append(caption,knob,input);
const hostName=c.dataset.label==='VOLUME'?'Output':label[0]+label.slice(1).toLowerCase();
const set=n=>{state.values[key]=Math.round(clamp(n,min,max)/step)*step;paintKnob(c);native?.set(hostName,state.values[key]);};
input.addEventListener('change',()=>{const n=parseFloat(input.value.replace('−','-'));if(Number.isFinite(n))set(n);else paintKnob(c);persist();});
let start=null;knob.addEventListener('pointerdown',e=>{native?.begin(hostName);start={y:e.clientY,value:state.values[key]};knob.setPointerCapture(e.pointerId);e.preventDefault();});
knob.addEventListener('pointermove',e=>{if(!start)return;const scale=$('.instrument').getBoundingClientRect().width/$('.instrument').offsetWidth;set(start.value+(start.y-e.clientY)/scale*(max-min)/160*(e.shiftKey?.1:1));});
const end=()=>{if(start){start=null;native?.end(hostName);persist();}};knob.addEventListener('pointerup',end);knob.addEventListener('pointercancel',end);
knob.addEventListener('dblclick',()=>{set(+c.dataset.default);persist();});
knob.addEventListener('keydown',e=>{if(!['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home'].includes(e.key))return;e.preventDefault();set(e.key==='Home'?+c.dataset.default:state.values[key]+(['ArrowUp','ArrowRight'].includes(e.key)?step:-step));persist();});
});
function paintKnob(c){const key=c.dataset.control,min=+c.dataset.min,max=+c.dataset.max;const v=clamp(Number(state.values[key])||0,min,max);state.values[key]=v;c.querySelector('.knob').style.setProperty('--angle',(-135+270*(v-min)/(max-min))+'deg');c.querySelector('.knob').setAttribute('aria-valuenow',v);let text=key==='output'?v.toFixed(1)+' dB':key==='velocity'?v.toFixed(2)+'×':['cutoff','resonance'].includes(key)?signed(Math.round(v)):key==='pan'?(v===0?'C':(v<0?'L':'R')+Math.abs(Math.round(v))):Math.round(v)+c.dataset.unit;c.querySelector('input').value=text;}
// A single dot matrix keeps adjacent shoulders on the same pixels.
// Enabled slots and initial values from the four factory Program records.
const programEffects={
 "A000":[{"slot":"IFX1","name":"EQ","bands":[{"hz":80,"gain":6.0,"q":0.5,"increment":10},{"hz":630,"gain":1.5,"q":2.1,"increment":10},{"hz":1800,"gain":4.0,"q":0.8,"increment":100},{"hz":4500,"gain":3.0,"q":0.7,"increment":100}]},
  {"slot":"IFX2","name":"M.Lim","values":{"threshold10":-1.3,"ceiling":-0.3,"releaseIndex":20}},
  {"slot":"IFX5","name":"Lim","values":{"ratio":30,"attack":60,"release":50,"threshold":-15}},
  {"slot":"MFX2","name":"Hall","values":{"damp":62,"mix":16}}],
 "A061":[{"slot":"IFX1","name":"M.Lim","values":{"threshold10":-8.6,"ceiling":0.0,"releaseIndex":20}},
  {"slot":"MFX2","name":"Plate","values":{"damp":60,"mix":10}}],
 "B097":[{"slot":"IFX1","name":"Exciter","values":{"blend":30,"mix":100}},
  {"slot":"MFX1","name":"Chorus","values":{"depth":60,"chorusMix":40}},
  {"slot":"MFX2","name":"Plate","values":{"damp":26,"mix":38}}],
 "C001":[{"slot":"IFX1","name":"EQ","bands":[{"hz":80,"gain":3.0,"q":0.6,"increment":10},{"hz":580,"gain":3.0,"q":0.8,"increment":10},{"hz":1200,"gain":1.5,"q":1.1,"increment":100},{"hz":11300,"gain":11.0,"q":null,"increment":100}]},
  {"slot":"IFX2","name":"EQ","bands":[{"hz":490,"gain":0.0,"q":1.0,"increment":10},{"hz":6080,"gain":-2.5,"q":5.5,"increment":10},{"hz":5000,"gain":-2.0,"q":0.8,"increment":100},{"hz":6100,"gain":1.5,"q":0.5,"increment":100}]},
  {"slot":"IFX5","name":"Lim","values":{"ratio":25,"attack":20,"release":50,"threshold":-25}},
  {"slot":"MFX2","name":"Hall","values":{"damp":30,"mix":36}}]
};
const fxRanges={
 threshold:['Thresh dB',-40,0,1],threshold10:['Thresh dB',-30,0,0.1],ceiling:['Ceiling dB',-30,0,0.1],
 attack:['Attack',1,100,1],release:['Release',1,100,1],blend:['Blend',-100,100,1],
 depth:['Depth',0,100,1],chorusMix:['Wet/Dry',-100,100,1],mix:['Wet/Dry',0,100,1],damp:['Hi Damp %',0,100,1]
};
if(native){for(const [code] of presets)programEffects[code]??=[];}
let selectedSlot=0,selectedBand=0;
const scopeStyles={
 EQ:['#73decf','PARAMETRIC EQ'],Lim:['#f2b777','STEREO LIMITER'],
 'M.Lim':['#f3958b','MASTERING LIMITER'],Hall:['#b5a0ff','HALL'],
 Plate:['#dfa6e0','PLATE'],Chorus:['#7fc6ff','STEREO CHORUS'],Exciter:['#e9d57e','STEREO EXCITER']
};
// Paint loss, components and glass occupy separate planes on the same chassis.
// Cache the stone grain. Effect edits only redraw the instruments and the glass.
const fxLayout={arpX:69.5,glideX:173,knobPitch:78,unitScale:1.12,half:30};
const fxRowY=30+fxLayout.unitScale*fxLayout.half;
function marbleInlay(){
 const stone=document.createElement('canvas');stone.width=428;stone.height=332;
 const ctx=stone.getContext('2d'),pixels=ctx.createImageData(stone.width,stone.height);
 function lattice(x,y){
  let h=Math.imul(x,374761393)+Math.imul(y,668265263);
  h=Math.imul(h^(h>>>13),1274126177);return ((h^(h>>>16))>>>0)/4294967296;
 }
 function noise(x,y){
  const i=Math.floor(x),j=Math.floor(y);let a=x-i,b=y-j;
  a*=a*(3-2*a);b*=b*(3-2*b);
  return (1-b)*((1-a)*lattice(i,j)+a*lattice(i+1,j))+b*((1-a)*lattice(i,j+1)+a*lattice(i+1,j+1));
 }
 for(let y=0;y<stone.height;y++)for(let x=0;x<stone.width;x++){
  const cloud=noise(x/84+2,y/67+5),grain=noise(x/21,y/18);
  const fold=x*.52-y*.92+cloud*97+grain*11+noise(x/5,y/7)*2.6;
  // Warm mineral base sampled from the reference, with split umber veins.
  const vein=Math.sin(fold*.071),branch=Math.sin(fold*.117+grain*2.3+cloud*4);
  const broad=Math.exp(-vein*vein*12),core=Math.exp(-vein*vein*210);
  const fine=Math.exp(-branch*branch*95)*(.35+.65*grain);
  const umber=Math.min(1,.44*broad+.73*core+.62*fine);
  const variation=(cloud-.5)*14+(grain-.5)*9+(lattice(x,y)-.5)*6;
  const k=4*(y*stone.width+x);
  pixels.data[k]=229+variation-umber*39+core*3;
  pixels.data[k+1]=211+variation-umber*60+core*4;
  pixels.data[k+2]=200+variation-umber*70+core*5;
  pixels.data[k+3]=255;
 }
 ctx.putImageData(pixels,0,0);
 // Translucent printed rails sit under the modules and continue into exposed scratches.
 function track(x,y,length,vertical){
  ctx.save();ctx.translate(x,y);if(vertical)ctx.rotate(Math.PI/2);
  ctx.fillStyle='rgba(182,81,76,.15)';ctx.fillRect(0,-8,length,16);
  for(let offset=-7;offset<8;offset+=2){
   ctx.fillStyle='rgba(152,71,70,.10)';ctx.fillRect(0,offset,length,.5);
  }
  ctx.fillStyle='rgba(255,225,215,.28)';ctx.fillRect(0,-8,length,.7);
  ctx.restore();
 }
 track(0,fxRowY,stone.width,false);track(fxLayout.arpX,0,stone.height,true);
 return stone;
}
const stoneInlay=marbleInlay();
// Sample bare stone away from the two printed FX tracks.
const logoTile=document.createElement('canvas');
logoTile.width=logoTile.height=96;
logoTile.getContext('2d').drawImage(stoneInlay,112,90,96,96,0,0,96,96);
$('#kf-logo-marble image').setAttribute('href',logoTile.toDataURL());
// Short tapered paint remnants run across the edge and share the stone/glass mask.
function marbleCutout(){
 const guide=document.createElementNS('http://www.w3.org/2000/svg','path');
 guide.setAttribute('d','M400 0 C399 18 391 33 391 45 S390 68 383 79 C378 88 380 98 370 104 S359 109 351 112 C341 116 337 112 327 115 S308 112 300 114 C286 118 278 113 268 114 S248 112 241 116 C229 122 223 113 213 123 C201 137 195 139 186 153 S172 169 167 179 C157 196 144 193 136 203 S115 214 103 218 C90 226 79 220 69 229 S49 234 41 240 C27 249 21 244 12 255 Q5 262 0 264');
 const length=guide.getTotalLength(),point=d=>{
  const p=guide.getPointAtLength(Math.min(length,Math.max(0,d)));
  // Ease the upper-right edge outward and keep the wear registered farther down.
  p.x+=25*Math.max(0,1-p.y/116)**1.25;
  return p;
 };
 // Overlapping abrasions have worn shoulders and blunt ends. A few narrow
 // cuts cross each worn patch, leaving the intervening enamel intact.
 const wear=[
  [26,8,-1.8],[32,3.2,2.4],[35,1.2,3.1],[72,10,2.5],[77,2.3,2.8],
  [111,5,-2],[118,3.2,3.3],[124,1.5,2.2],[155,8,2.3],[161,2.4,-2.5],
  [207,7,-1.8],[213,2.8,2.8],[217,1.1,3.4],[250,4,1.8],
  [285,9,-2],[291,2.7,3.1],[296,1.6,2.4],[325,6,1.9],
  [361,8,2.6],[366,2.7,-2.2],[391,4.2,-1.6],[427,6,2.1],[430,1.6,2.7],
  [465,8,-1.8],[471,3,2.9],[474,1.2,1.8],[509,5,2]
 ];
 const cut=new Path2D();cut.moveTo(0,0);cut.lineTo(425,0);
 for(let d=.5;d<length;d+=.5){
  const p=point(d),a=point(d-.5),b=point(d+.5);
  const dx=b.x-a.x,dy=b.y-a.y,n=Math.hypot(dx,dy)||1;
  let depth=.42*Math.sin(d*.76+.8*Math.sin(d*.23))+.31*Math.sin(d*1.29);
  for(const [at,radius,amount] of wear){
   const u=(d-at)/radius;
   if(Math.abs(u)<1)depth+=amount*(1-u*u)**2;
  }
  cut.lineTo(p.x-dy/n*depth,p.y+dx/n*depth);
 }
 cut.lineTo(0,264);cut.closePath();return cut;
}
const marbleCut=marbleCutout();
function paintFxToggle(folded,x,y){
 const button=$('.fx-lettering'),c=button.querySelector('canvas').getContext('2d');
 root.style.setProperty('--fx-x',x+'px');root.style.setProperty('--fx-y',y+'px');
 button.setAttribute('aria-expanded',String(!folded));
 button.setAttribute('aria-label',folded?'展开 FX 展示':'收起 FX 展示');
 c.setTransform(2,0,0,2,0,0);c.clearRect(0,0,66,54);
 c.font='bold 30px Georgia, "Times New Roman", serif';
 const m=c.measureText('FX');
 const baseline=27+(m.actualBoundingBoxAscent-m.actualBoundingBoxDescent)/2;
 const left=33+(m.actualBoundingBoxLeft-m.actualBoundingBoxRight)/2;
 if(folded){
  const marble=c.createPattern(stoneInlay,'no-repeat');
  marble.setTransform(new DOMMatrix().translate(33-x,27-y));c.fillStyle=marble;
 }else c.fillStyle='#614239';
 c.fillText('FX',left,baseline);
 return {right:x-33+left+m.actualBoundingBoxRight,bottom:y-27+baseline+m.actualBoundingBoxDescent};
}
$('.fx-lettering').addEventListener('click',()=>{
 state.fxFolded=!state.fxFolded;paintEffectView();persist();
});
function paintEffectView(){
 const program=presets[state.preset][0],slots=programEffects[program];
 root.toggleAttribute('data-fx-folded',state.fxFolded);
 const hitLayer=$('.fx-hit-layer');
 hitLayer.hidden=!!state.fxFolded;
 $('#kf-effect-view').setAttribute('aria-hidden',String(!!state.fxFolded));
 const glyph=paintFxToggle(!!state.fxFolded,fxLayout.arpX,fxRowY);
 const canvas=$('#kf-effect-view'),c=canvas.getContext('2d');
 c.setTransform(2,0,0,2,0,0);c.clearRect(0,0,stoneInlay.width,stoneInlay.height);
 function stroke(x,y,u,v,color,width=1){
  c.beginPath();c.moveTo(x,y);c.lineTo(u,v);c.strokeStyle=color;c.lineWidth=width;c.stroke();
 }
 function dot(x,y,r,color){
  c.beginPath();c.arc(x,y,r,0,2*Math.PI);c.fillStyle=color;c.fill();
 }
 function metal(x,y,w,h,colors){
  const g=c.createLinearGradient(x,y,x,y+h);
  colors.forEach((color,i)=>g.addColorStop(i/(colors.length-1),color));
  c.fillStyle=g;c.fillRect(x,y,w,h);
 }
 c.save();c.clip(marbleCut);c.drawImage(stoneInlay,0,0);c.restore();
 // Canvas origin is 33 px above the upper-control origin.
 const {unitScale,half,glideX,knobPitch}=fxLayout;
 const placement=slots.map((_,i)=>i===0?[fxLayout.arpX,179]:[glideX+(i-1)*knobPitch,fxRowY]);
 const layer=hitLayer;
 if(layer.dataset.program!==program){
  layer.replaceChildren();layer.dataset.program=program;
  slots.forEach((slot,i)=>{
   const [x,y]=placement[i],size=unitScale*half*2,hit=document.createElement('span');
   hit.className='fx-hit';hit.tabIndex=0;hit.setAttribute('role','img');
   hit.setAttribute('aria-label',slot.slot+' · '+scopeStyles[slot.name][1]);
   Object.assign(hit.style,{left:(x-size/2)+'px',top:(y-size/2)+'px',width:size+'px',height:size+'px'});
   layer.append(hit);
  });
 }
 // Route enters FX from below and exits to the right, 15 px from the ink.
 const gap=15,arrowTop=glyph.bottom+gap,arrowLeft=glyph.right+gap;
 c.fillStyle='#805e49';c.beginPath();
 c.moveTo(fxLayout.arpX,arrowTop);c.lineTo(fxLayout.arpX+5,arrowTop+9);
 c.lineTo(fxLayout.arpX-5,arrowTop+9);c.closePath();
 c.moveTo(arrowLeft,fxRowY-5);c.lineTo(arrowLeft+9,fxRowY);
 c.lineTo(arrowLeft,fxRowY+5);c.closePath();c.fill();
 slots.forEach((slot,i)=>{
  const [cx,cy]=placement[i];
  c.save();c.translate(cx,cy);c.scale(unitScale,unitScale);c.translate(-cx,-41);
  const edits=state.fxEdits[program+'/'+slot.slot]||{},v={...slot.values,...edits};
  const on=edits.enabled!==false&&state.fx[slot.slot.startsWith('I')?'insert':'master'];
  const ink=on?scopeStyles[slot.name][0]:'#69716e';
  const isVU=slot.name.endsWith('Lim'),width=2*half;
  const inset=6,faceX=cx-half+inset,faceY=11+inset,faceSize=width-2*inset;
  // The warm ceramic rim has a lit shoulder and a recessed inner lip.
  c.save();c.shadowColor='rgba(35,27,23,.33)';c.shadowBlur=6;c.shadowOffsetX=4;c.shadowOffsetY=6;
  c.fillStyle='#ada299';c.fillRect(cx-half,11,width,width);c.restore();
  c.fillStyle='#ece3dc';c.fillRect(cx-half,11,width-1.2,width-1.2);
  c.fillStyle='#d7cdc4';c.fillRect(cx-half+1.5,12.5,width-3,width-3);
  c.fillStyle='#c3b9af';c.fillRect(faceX-1.2,faceY-1.2,faceSize+2.4,faceSize+2.4);
  stroke(faceX-1,faceY-1,faceX+faceSize,faceY-1,'#b4aaa1',.8);
  stroke(faceX+faceSize,faceY+faceSize,faceX-1,faceY+faceSize,'#e2d9d1',.8);
  const faceColors=isVU?(slot.name==='M.Lim'?['#a99c70','#e5d59b','#c9bc90']:['#999b9c','#d6d7d6','#afafb0']):['#23322e','#34453e','#273832'];
  metal(faceX,faceY,faceSize,faceSize,faceColors);
  c.save();c.beginPath();c.rect(faceX,faceY,faceSize,faceSize);c.clip();
  const halo=c.createRadialGradient(cx,12,1,cx,12,19);
  halo.addColorStop(0,on?'#ffffff80':'#99999915');halo.addColorStop(.32,on?'#eeeeee46':'#90909009');halo.addColorStop(1,'#eeeeee00');
  c.fillStyle=halo;c.fillRect(cx-half+5,16,width-10,width-10);
  c.restore();
  c.fillStyle=on?getComputedStyle(canvas).getPropertyValue('--fx-lamp').trim():'#898989';c.fillRect(cx-9,11,18,2.5);
  c.save();c.beginPath();c.rect(cx-half+6,isVU?19:26,width-12,isVU?45:37);c.clip();
  if(slot.bands){
   const w=width-8,x0=cx-w/2;
   for(let j=1;j<6;j++)stroke(x0+w*j/6,25,x0+w*j/6,57,'#58606060',.5);
   for(const y of [31,41,51])stroke(x0,y,x0+w,y,'#6d79785c',.5);
   const bands=slot.bands.map((b,j)=>({f:edits['b'+j+'hz']??b.hz,g:edits['b'+j+'gain']??b.gain,q:edits['b'+j+'q']??b.q}));
   function response(t){
    const sum=bands.reduce((total,b,j)=>{
     const oct=Math.log2(20*1000**t/b.f);
     const weight=b.q===null?1/(1+Math.exp((j===0?1:-1)*oct*3)):Math.exp(-.5*(oct*Math.max(.65,b.q))**2);
     return total+b.g*weight;
    },0);return 42-(on?clamp(sum,-16,18)*.82:0);
   }
   c.beginPath();for(let j=0;j<=w;j++){const y=response(j/w);if(j)c.lineTo(x0+j,y);else c.moveTo(x0,y);}
   c.strokeStyle=ink;c.lineWidth=1.3;c.stroke();
   for(const b of bands){const t=Math.log10(b.f/20)/3;dot(x0+t*w,response(t),1.3,ink);}
  }else if(isVU){
   const master=slot.name==='M.Lim';
   const scale='#393733';
   const px=cx,py=61,r=23;
   function arc(radius,a,b,color,weight){
    c.beginPath();c.arc(px,py,radius,a,b);c.strokeStyle=color;c.lineWidth=weight;c.stroke();
   }
   arc(r,-2.47,-1.38,scale,.85);arc(r,-1.38,-.67,'#a14336',1);
   c.textAlign='center';c.font='4.8px Arial,sans-serif';
   for(let j=0;j<9;j++){
    const a=-2.47+j*.225,dx=Math.cos(a),dy=Math.sin(a);
    stroke(px+dx*r,py+dy*r,px+dx*(r+2.8),py+dy*(r+2.8),j>5?'#a14336':scale,.85);
    c.fillStyle=j>5?'#a14336':scale;c.fillText(['-20','','-7','','-3','0','1','2','3'][j],px+dx*(r+5.2),py+dy*(r+5.2));
   }
   const level=master?1+v.threshold10/30:1+v.threshold/40;
   const a=-2.47+1.8*(on?clamp(level,0,1):0);
   stroke(px+1,py,px+Math.cos(a)*28+1,py+Math.sin(a)*28+1,'#302b252e',1.2);
   stroke(px,py,px+Math.cos(a)*28,py+Math.sin(a)*28,'#aa3832',1);
  }else if(slot.name==='Hall'||slot.name==='Plate'){
   // An obliquely projected stack of closed contours previews a 3D reverb volume.
   const plate=slot.name==='Plate',slices=18;
   for(let j=0;j<slices;j++){
    const t=j/(slices-1),z=2*t-1,rad=Math.sqrt(Math.max(.025,1-z*z));
    const rx=rad*(plate?18:15)*(1+v.mix/400),ry=rad*(plate?4.1:6.3);
    c.beginPath();
    for(let k=0;k<=72;k++){
     const a=k*Math.PI/36,fold=1+.12*Math.sin(3*a+2.8*t)+.07*Math.cos(5*a-2*t);
     const x=cx+z*6+rx*fold*Math.cos(a),y=41-z*(plate?9:11)+ry*fold*Math.sin(a)-rx*Math.cos(a)*.17;
     if(k)c.lineTo(x,y);else c.moveTo(x,y);
    }
    c.closePath();c.fillStyle=ink+'11';c.fill();c.strokeStyle=ink+(j%4===0?'df':'88');c.lineWidth=j%4===0?.8:.48;c.stroke();
   }
  }else if(slot.name==='Exciter'){
   const lit=Math.round(Math.abs(v.blend)/100*9);
   for(let j=0;j<9;j++){const x=cx-23+j*5.5,h=9+j*1.8;metal(x,53-h,3.4,h,['#292a26',on&&j<lit?ink:'#54554f','#222426']);}
  }else{
   for(const phase of [0,1.55]){
    c.beginPath();for(let j=0;j<50;j++){const y=41+Math.sin(j*.16+phase)*v.depth*.12;if(j)c.lineTo(cx-25+j,y);else c.moveTo(cx-25,y);}
    c.strokeStyle=phase?ink:ink+'88';c.lineWidth=1;c.stroke();
   }
  }
  c.restore();
  c.restore();
 });
 c.textAlign='left';
 c.save();c.clip(marbleCut);
 // Light grazing the facets is continuous across the single triangular cover.
 const reflection=c.createLinearGradient(10,5,244,165);
 [[0,'#eedee921'],[.28,'#ece2f109'],[.46,'#ffffff00'],[.56,'#d1beee17'],[.57,'#eff1ff08'],[1,'#ffffff00']].forEach(([at,col])=>reflection.addColorStop(at,col));
 c.fillStyle=reflection;c.fillRect(0,0,stoneInlay.width,stoneInlay.height);
 c.restore();
 canvas.setAttribute('aria-label',slots.map(s=>s.slot+' '+scopeStyles[s.name][1]).join(', '));
}
function renderEffects(){
 paintEffectView();
 const program=presets[state.preset][0], slots=programEffects[program];
 const slot=slots[selectedSlot]||slots[0];
 const strip=$('#kf-fx-slots'), fields=$('#kf-fx-fields');
 strip.replaceChildren();fields.replaceChildren();
 if(!slot){fields.textContent='—';$('#kf-slot-on').disabled=true;return;}
 const key=program+'/'+slot.slot;
 slots.forEach((item,i)=>{
  const button=document.createElement('button');
  button.type='button';button.textContent=item.slot.replace('FX','')+' '+item.name;
  button.setAttribute('aria-label',item.slot+' '+item.name);
  button.setAttribute('aria-pressed',String(item===slot));
  button.onclick=()=>{selectedSlot=i;selectedBand=0;renderEffects();strip.children[i].focus();};
  strip.append(button);
 });
 function addField(title,control){
  const label=document.createElement('label');if(native)control.disabled=true;label.append(title,control);fields.append(label);
 }
 function options(items,current,change){
  const select=document.createElement('select');
  for(const [value,title] of items)select.add(new Option(title,value));
  select.value=current;select.onchange=()=>change(Number(select.value));return select;
 }
 function save(field,value){
  state.fxEdits[key]??={};state.fxEdits[key][field]=value;paintEffectView();persist();
 }
 function number(field,initial,[title,min,max,step]){
  const input=document.createElement('input');input.type='number';input.min=min;input.max=max;input.step=step;
  input.value=state.fxEdits[key]?.[field]??initial;
  input.onchange=()=>{
   if(input.value===''||!input.validity.valid){input.value=state.fxEdits[key]?.[field]??initial;return;}
   save(field,input.valueAsNumber);
  };
  addField(title,input);
 }
 const enabled=$('#kf-slot-on');enabled.disabled=!!native;enabled.checked=state.fxEdits[key]?.enabled!==false;
 enabled.onchange=()=>save('enabled',enabled.checked);
 if(slot.bands){
  const band=slot.bands[selectedBand], prefix='b'+selectedBand;
  addField('Band',options(slot.bands.map((b,i)=>[i,'B'+(i+1)+(b.q===null?' Shelf':' Peak')]),selectedBand,i=>{
   selectedBand=i;renderEffects();fields.querySelector('select').focus();
  }));
  const min=[20,50,300,500][selectedBand],maxIndex=[98,995,97,195][selectedBand];
  number(prefix+'hz',band.hz,['Freq Hz',min,min+band.increment*maxIndex,band.increment]);
  number(prefix+'gain',band.gain,['Gain dB',-18,18,0.5]);
  if(band.q!==null)number(prefix+'q',band.q,['Q',0.5,10,0.1]);
 }else{
  for(const [field,value] of Object.entries(slot.values)){
   if(field==='ratio'||field==='releaseIndex'){
    const ratio=field==='ratio', items=[];
    for(let i=ratio?0:10;i<=(ratio?131:290);i++){
     const display=ratio?(i===131?'Inf':(i<=90?(i+10)/10:i-80)+':1'):
      (i<20?i*0.05:i<110?(i-10)/10:i<200?i-100:10*i-1900).toFixed(i<20?2:i<110?1:0);
     items.push([i,display]);
    }
    addField(ratio?'Ratio':'Rel ms',options(items,state.fxEdits[key]?.[field]??value,n=>save(field,n)));
   }else number(field,value,fxRanges[field]);
  }
 }
}
function paintPageStrip(){
 const canvas=$('.lcd-tab-outline'), tabs=$$('.lcd-tab'), height=9;
 const width=canvas.clientWidth;
 if(!width)return;
 canvas.width=width;canvas.height=canvas.clientHeight;
 const ctx=canvas.getContext('2d');
 // Square two-pixel dots give both shoulders the same 45-degree staircase.
 ctx.setTransform(2,0,0,2,0,1);
 ctx.fillStyle=getComputedStyle(canvas).getPropertyValue('--ink');
 const step=tabs[0].offsetWidth/2, first=Math.floor(width/2)-step*tabs.length-5;
 for(let y=0;y<height;y++){
  const left=height-1-y, edge=first+4-y;
  ctx.fillRect(left,y,edge-left+1,1);
  tabs.forEach((tab,i)=>{
   const start=first+i*step, end=start+step;
   const active=tab.dataset.page===state.page;
   const nextActive=tabs[i+1]?.dataset.page===state.page;
   if(y===0)ctx.fillRect(start+4,0,step-7,1);
   if(i>0&&(active||y<=4))ctx.fillRect(start+4-y,y,1,1);
   if(!nextActive||y<=4)ctx.fillRect(end-4+y,y,1,1);
   if(y===8&&!active){
    const x=i===0?start-4:start+4;
    const right=nextActive?end-4:end+4;
    ctx.fillRect(x,y,right-x+1,1);
   }
  });
 }
}
function render(){
$$('[data-control]').forEach(paintKnob);
$$('[data-toggle]').forEach(b=>{const on=!!state.toggles[b.dataset.toggle];b.setAttribute('aria-pressed',on);});
$$('[data-eg]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.eg===state.eg));
$$('[data-voice]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.voice===state.voice));
$$('[data-fader]').forEach(f=>{const v=clamp(+state.envelopes[state.eg][f.dataset.fader]||0,-99,99);f.querySelector('input').value=v;f.querySelector('output').textContent=signed(v);});
const p=presets[state.preset];if(state.page==='main')drawProgramRow(p);$('#kf-preset').textContent=p[1];$('#kf-edit-name').textContent=p[1];$('#kf-source').textContent=p[2]+' ('+p[0]+')';$('#kf-status').textContent=p[5]||'Voice: '+state.voice.toUpperCase();$('#kf-source').title=p[5]||p[1];
paintPageStrip();
$('.instrument').dataset.page=state.page;$('.lcd').dataset.page=state.page;$('#kf-program').value=String(state.preset);
$$('[data-bind]').forEach(input=>{input.value=state.values[input.dataset.bind];});
$$('[data-fx]').forEach(input=>{input.checked=state.fx[input.dataset.fx]!==false;});
if(state.page==='fx')renderEffects();else paintEffectView();
$$('.lcd-tab[data-page]').forEach(b=>{const on=b.dataset.page===state.page;b.setAttribute('aria-selected',on);$('#kf-'+b.dataset.page).hidden=!on;});
$('#kf-route').hidden=state.page!=='main';$('#kf-routing').textContent=programEffects[p[0]].map(slot=>slot.slot.replace('FX','')+' '+slot.name).join(' / ');
$('#kf-arp-state').textContent='ARP '+(state.toggles.arp?'ON':'OFF')+' · LATCH '+(state.toggles.latch?'ON':'OFF');$('#kf-tempo').textContent=(state.toggles.host?'HOST':'INT')+' 125.00';$('#kf-tempo').title=$('#kf-tempo').textContent;$('#kf-octave').textContent='OCT'+(state.octave<0?'−':state.octave>0?'+':' ')+Math.abs(state.octave);$('#kf-rate').value=state.rate;$('#kf-pattern').value=state.pattern;
['pitch','mod'].forEach(k=>{const b=$('#kf-'+k),v=state.wheels[k];b.setAttribute('aria-valuenow',v);b.style.setProperty('--wheel',(k==='pitch'?50-v/8192*42:92-v/127*84)+'%');});
$('#kf-compare').setAttribute('aria-pressed',!!compare);
}
$$('[data-toggle]').forEach(b=>b.addEventListener('click',()=>{state.toggles[b.dataset.toggle]=!state.toggles[b.dataset.toggle];render();persist();}));
$$('[data-eg]').forEach(b=>b.addEventListener('click',()=>{state.eg=b.dataset.eg;render();persist();}));
$$('[data-voice]').forEach(b=>b.addEventListener('click',()=>{state.voice=b.dataset.voice;render();persist();}));
$$('.lcd-tab[data-page]').forEach(b=>b.addEventListener('click',()=>{state.page=b.dataset.page;render();persist();}));
$$('[data-open-page]').forEach(b=>b.addEventListener('click',()=>{state.page=b.dataset.openPage;render();persist();}));
$('#kf-value').addEventListener('click',()=>stepPreset(1));
$('#kf-program').addEventListener('change',e=>selectPreset(+e.target.value));
$$('[data-bind]').forEach(input=>input.addEventListener('change',()=>{const v=Number(input.value);if(Number.isFinite(v))state.values[input.dataset.bind]=clamp(v,+input.min,+input.max);render();persist();}));
$$('[data-fx]').forEach(input=>input.addEventListener('change',()=>{state.fx[input.dataset.fx]=input.checked;paintEffectView();persist();}));
$$('[data-fader]').forEach(f=>{const input=f.querySelector('input');input.addEventListener('input',()=>{state.envelopes[state.eg][f.dataset.fader]=+input.value;f.querySelector('output').textContent=signed(+input.value);});input.addEventListener('change',persist);input.addEventListener('dblclick',()=>{state.envelopes[state.eg][f.dataset.fader]=0;render();persist();});});
$('#kf-rate').addEventListener('change',e=>{state.rate=e.target.value;render();persist();});$('#kf-pattern').addEventListener('change',e=>{state.pattern=e.target.value;persist();});
function stepPreset(delta){selectPreset(presetOrder[(presetOrder.indexOf(state.preset)+delta+presetOrder.length)%presetOrder.length]);}
function selectPreset(n){if(compare){state.fxEdits=compare.fxEdits;state.fx=compare.fx;}selectedSlot=0;selectedBand=0;state.preset=(n+presets.length)%presets.length;state.page='main';if(native)native.set('Program',state.preset);else {state.values={...defaults};state.envelopes={amp:{attack:0,decay:0,sustain:0,release:0},filter:{attack:0,decay:0,sustain:0,release:0}};}compare=null;render();persist();}
$('#kf-prev').addEventListener('click',()=>stepPreset(-1));$('#kf-next').addEventListener('click',()=>stepPreset(1));
$('#kf-browse').addEventListener('click',()=>{if(native){native.openBrowser(root);return;}const select=$('#kf-program');select.focus();if(typeof select.showPicker==='function'){try{select.showPicker();}catch{}}});
$('#kf-save').addEventListener('click',()=>{persist();feedback('UI SNAPSHOT SAVED · '+presets[state.preset][0]);});
$('#kf-compare').addEventListener('click',()=>{if(compare){state.values=compare.values;state.envelopes=compare.envelopes;state.fx=compare.fx;state.fxEdits=compare.fxEdits;compare=null;}else{compare={values:structuredClone(state.values),envelopes:structuredClone(state.envelopes),fx:{...state.fx},fxEdits:structuredClone(state.fxEdits)};state.fx={insert:true,master:true};state.fxEdits={...state.fxEdits};for(const slot of programEffects[presets[state.preset][0]])delete state.fxEdits[presets[state.preset][0]+'/'+slot.slot];state.values={...defaults};state.envelopes={amp:{attack:0,decay:0,sustain:0,release:0},filter:{attack:0,decay:0,sustain:0,release:0}};}render();});
const held=new Set();function releaseKey(b){b.classList.remove('is-down');held.delete(b);}
function panic(){held.forEach(releaseKey);$$('.is-down').forEach(releaseKey);state.toggles.sustain=false;state.wheels.pitch=0;render();feedback('ALL NOTES STOPPED');persist();}
$('#kf-panic').addEventListener('click',panic);
function buildKeyboard(){const kb=$('#kf-keyboard');kb.replaceChildren();let whiteIndex=0;for(let i=0;i<61;i++){const note=36+i+12*state.octave,pc=i%12,black=[1,3,6,8,10].includes(pc);const b=document.createElement('button');b.type='button';b.className=(black?'black-key':'white-key')+' cursor-interaction';b.dataset.midi=note;b.setAttribute('aria-label','MIDI note '+note);if(black)b.style.left=(whiteIndex*keyGeometry.whitePitch-keyGeometry.blackWidth/2)+'px';else{if(pc===0)b.textContent='C'+(Math.floor(note/12)-1);whiteIndex++;}b.addEventListener('pointerdown',e=>{b.setPointerCapture(e.pointerId);b.classList.add('is-down');held.add(b);feedback('NOTE '+note+' · VELOCITY 100');});b.addEventListener('pointerup',()=>{if(!state.toggles.sustain)releaseKey(b);});b.addEventListener('pointercancel',()=>releaseKey(b));b.addEventListener('keydown',e=>{if(e.key===' '||e.key==='Enter'){b.classList.add('is-down');held.add(b);}});b.addEventListener('keyup',()=>{if(!state.toggles.sustain)releaseKey(b);});kb.append(b);}$('#kf-notes').textContent='C'+(2+state.octave)+' — C'+(7+state.octave);}
$('#kf-oct-down').addEventListener('click',()=>{state.octave=clamp(state.octave-1,-2,2);held.clear();buildKeyboard();render();persist();});$('#kf-oct-up').addEventListener('click',()=>{state.octave=clamp(state.octave+1,-2,2);held.clear();buildKeyboard();render();persist();});
$$('[data-toggle="sustain"]').forEach(b=>b.addEventListener('click',()=>{if(!state.toggles.sustain)held.forEach(releaseKey);}));
['pitch','mod'].forEach(k=>{const b=$('#kf-'+k);let drag=null;const set=v=>{state.wheels[k]=Math.round(clamp(v,k==='pitch'?-8192:0,k==='pitch'?8191:127));render();};b.addEventListener('pointerdown',e=>{drag={y:e.clientY,v:state.wheels[k]};b.setPointerCapture(e.pointerId);});b.addEventListener('pointermove',e=>{if(!drag)return;const scale=$('.instrument').getBoundingClientRect().width/$('.instrument').offsetWidth;set(drag.v+(drag.y-e.clientY)/scale*(k==='pitch'?160:1.3));});const end=()=>{drag=null;if(k==='pitch')set(0);persist();};b.addEventListener('pointerup',end);b.addEventListener('pointercancel',end);b.addEventListener('keydown',e=>{if(['ArrowUp','ArrowDown','Home'].includes(e.key)){e.preventDefault();set(e.key==='Home'?0:state.wheels[k]+(e.key==='ArrowUp'?1:-1)*(k==='pitch'?128:1));persist();}});});
window.addEventListener('blur',()=>{held.forEach(releaseKey);state.wheels.pitch=0;render();});
window.addEventListener('openai:set_globals',e=>{loadShared(e.detail?.globals?.widgetState);render();buildKeyboard();});
function fit(){const scale=Math.min(1,root.clientWidth/$('.instrument').offsetWidth);$('.instrument').style.transform='scale('+scale+')';$('.viewport').style.height=($('.instrument').offsetHeight*scale)+'px';}
if(native){
 native.mount(root,state,render);
}
new ResizeObserver(fit).observe(root);render();buildKeyboard();fit();
if(native)root.setAttribute('data-ready','');
else document.fonts.ready.then(()=>requestAnimationFrame(()=>root.setAttribute('data-ready','')));
})();
