// The browser is an overlay; the approved main panel geometry stays fixed.
window.kroseNative.openBrowser = function(root) {
  let dialog=root.querySelector('#krose-browser');
  if(!dialog){
    dialog=document.createElement('dialog');dialog.id='krose-browser';
    Object.assign(dialog.style,{width:'610px',height:'390px',padding:'20px',background:'#282b2d',color:'#e1e1dc',border:'1px solid #717579',borderRadius:'6px',font:'15px sans-serif'});
    const heading=document.createElement('div');heading.textContent='PRESETS · '+this.presets.length;
    heading.style.marginBottom='12px';
    const close=document.createElement('button');close.textContent='×';close.setAttribute('aria-label','关闭音色浏览');
    Object.assign(close.style,{float:'right',width:'25px',height:'26px',padding:'0',border:'0',borderRadius:'0',background:'transparent',boxShadow:'none',color:'#e1e1dc',font:'24px/26px Arial, sans-serif',cursor:'pointer'});
    close.onclick=()=>dialog.close();heading.append(close);
    const filters=document.createElement('div');Object.assign(filters.style,{display:'flex',gap:'8px',marginBottom:'12px'});
    const search=document.createElement('input');search.type='search';search.placeholder='名称或编号';search.setAttribute('aria-label','搜索音色');Object.assign(search.style,{flex:'1',background:'#232628',color:'#e1e1dc',border:'1px solid #767a7d',borderRadius:'2px',padding:'0 9px'});
    const bank=document.createElement('select');bank.setAttribute('aria-label','音色库');bank.add(new Option('全部音色库',''));
    for(const group of this.browser.groups) bank.add(new Option(group,group));

    const category=document.createElement('select');category.setAttribute('aria-label','音色类型');category.add(new Option('全部类型',''));
    for(const name of this.browser.categories)category.add(new Option(name,name));
    for(const e of [bank,category])Object.assign(e.style,{appearance:"none",border:"1px solid #767a7d",borderRadius:"0",backgroundColor:"#232628",backgroundImage:"url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='9' height='12' viewBox='0 0 9 12'%3E%3Cpath fill='%23e3e3e3' d='M4 0h1v1H4zm-1 1h3v1H3zM2 2h5v1H2zM1 3h7v1H1zm0 5h7v1H1zm1 1h5v1H2zm1 1h3v1H3zm1 1h1v1H4z'/%3E%3C/svg%3E\")",backgroundRepeat:"no-repeat",backgroundPosition:"right 7px center",color:"#e3e3e3",padding:"0 24px 0 7px"});
    filters.append(search,bank,category);
    const list=document.createElement('div');list.setAttribute('role','list');Object.assign(list.style,{overflowY:'auto',height:'292px',display:'flex',flexDirection:'column',gap:'2px'});
    const redraw=()=>{
      list.replaceChildren();const needle=search.value.toLowerCase().trim();
      this.browser.order.forEach(i=>{
        const p=this.presets[i];
        if(bank.value&&bank.value!==p[4]||category.value&&category.value!==p[2]||needle&&!`${p[0]} ${p[1]}`.toLowerCase().includes(needle))return;
        const button=document.createElement('button');button.type='button';button.dataset.program=i;
        button.textContent=`${p[0]}  ${p[1]} · ${p[2]}${p[5]?" · "+p[5]:""}`;
        Object.assign(button.style,{textAlign:'left',flexShrink:'0',padding:'7px 10px',color:'#e1e1dc',background:'#373b3d',border:'1px solid #45494b',borderRadius:'3px'});
        button.onclick=()=>{const select=root.querySelector('#kf-program');select.value=String(i);select.dispatchEvent(new Event('change'));dialog.close();};
        list.append(button);
      });
      if(!list.childElementCount)list.textContent='没有匹配的音色';
    };
    search.oninput=redraw;bank.onchange=category.onchange=redraw;
    dialog.append(heading,filters,list);root.append(dialog);redraw();
    dialog.addEventListener('close',()=>root.querySelector('#kf-browse').focus());
  }
  dialog.showModal();dialog.querySelector('input').focus();
};
