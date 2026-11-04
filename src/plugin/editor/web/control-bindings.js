window.kroseNative.mount = function(root,state,render) {
  const bridge=this, q=s=>root.querySelector(s);
  const lcd=q('#kf-tone .lcd-fields');
  const legacy={};
  for(const [name,min,max,step] of [['Tone',0,2,1],['Release',30,2000,1],['Space',0,200,1]]){
    const label=document.createElement('label');
    const input=document.createElement(name==='Tone'?'select':'input');
    label.append(name+' ',input);
    if(name==='Tone'){
      for(const [i,s] of ['Concert','Warm','Wide'].entries()) input.add(new Option(s,i));
    }else{
      Object.assign(input,{type:'number',min,max,step});
    }
    input.onchange=()=>{if(input.value!=='' && input.validity.valid) bridge.set(name,+input.value);};
    legacy[name]=input;
    lcd.append(label);
  }
  // Only expose actions that are connected to the processor in this phase.
  for(const el of root.querySelectorAll('[data-toggle=arp],[data-toggle=latch],[data-toggle=sw1],[data-toggle=sw2],[data-toggle=host],[data-bind=gate],[data-bind=swing],[data-fx],#kf-pan,#kf-save,#kf-compare,#kf-mod,#kf-pattern,#kf-rate')){
    el.disabled=true;
  }
  for(const el of root.querySelectorAll('[data-voice]'))
    el.addEventListener('click',()=>bridge.set('Voice Mode',['poly','mono','legato'].indexOf(state.voice)));
  const notes=new Map();
  const keyFor=e=>e.target.closest('[data-midi]');
  function start(key){
    if(!key || notes.has(key)) return;
    const n=+key.dataset.midi;
    notes.set(key,n);bridge.midi(0x90,n,100);
  }
  function stop(key){
    if(!notes.has(key)) return;
    bridge.midi(0x80,notes.get(key),0);notes.delete(key);
  }
  function release(){for(const key of notes.keys()) stop(key);}
  root.addEventListener('pointerdown',e=>start(keyFor(e)),true);
  for(const type of ['pointerup','pointercancel','lostpointercapture'])
    root.addEventListener(type,e=>stop(keyFor(e)),true);
  root.addEventListener('keydown',e=>{if(e.key===' '||e.key==='Enter')start(keyFor(e));},true);
  root.addEventListener('keyup',e=>stop(keyFor(e)),true);
  window.addEventListener('blur',release);
  for(const id of ['#kf-oct-up','#kf-oct-down'])q(id).addEventListener('click',release,true);
  q('[data-toggle=sustain]').addEventListener('click',()=>bridge.midi(0xb0,64,state.toggles.sustain?127:0));
  q('#kf-panic').addEventListener('click',()=>{
    release();
    for(let ch=0;ch<16;ch++){bridge.midi(0xb0+ch,64,0);bridge.midi(0xb0+ch,120,0);}
    bridge.midi(0xe0,0,64);
  });
  function wheel(){
    const bend=state.wheels.pitch+8192;
    bridge.midi(0xe0,bend&127,bend>>7);
  }
  for(const event of ['pointermove','pointerup','pointercancel','keydown'])
    q('#kf-pitch').addEventListener(event,wheel);
  window.addEventListener('blur',wheel);
  const title=s=>s[0].toUpperCase()+s.slice(1);
  for(const input of root.querySelectorAll('#kf-tone [data-bind]')){
    const key=input.dataset.bind;
    input.addEventListener('change',()=>bridge.set(title(key),state.values[key]));
  }
  for(const group of root.querySelectorAll('[data-fader]')){
    const input=group.querySelector('input');
    const name=()=>title(state.eg)+' '+title(group.dataset.fader);
    let active;
    input.addEventListener('pointerdown',()=>{active=name();bridge.begin(active);});
    input.addEventListener('input',()=>bridge.set(active||name(),+input.value));
    for(const type of ['pointerup','pointercancel','lostpointercapture'])
      input.addEventListener(type,()=>{if(active)bridge.end(active);active=null;});
    input.addEventListener('dblclick',()=>bridge.set(name(),0));
  }
  bridge.connect((name,value)=>{
    if(legacy[name]) legacy[name].value=value;
    else if(name==='Program'){
      state.preset=value;
      legacy.Tone.disabled=value!==0;
    }else if(name==='Output') state.values.output=value;
    else if(name==='Voice Mode') state.voice=['poly','mono','legato'][value];
    else if(['Velocity','Pan','Cutoff','Resonance','Glide'].includes(name)) state.values[name.toLowerCase()]=value;
    else if(name.includes(' ')){
      const [eg,stage]=name.toLowerCase().split(' ');
      if(state.envelopes[eg] && stage in state.envelopes[eg])state.envelopes[eg][stage]=value;
    }
    render();
  });
};
