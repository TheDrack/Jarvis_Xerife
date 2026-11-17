(()=> {
'use strict';
const $=id=>document.getElementById(id);
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const state={query:null,cursor:null,items:[],busy:false};
const token=()=>sessionStorage.getItem('jarvis_local_access')||'';
async function request(path){
 const headers={'Accept':'application/json'};
 const current=token();
 if(current)headers.Authorization='Bearer '+current;
 const response=await fetch(path,{headers,cache:'no-store'});
 const payload=await response.json().catch(()=>({detail:'Resposta inválida do núcleo local.'}));
 if(!response.ok)throw new Error(payload.detail||('HTTP '+response.status));
 return payload;
}
function setStatus(message,error=false){
 const node=$('prospectingStatus');
 if(!node)return;
 node.textContent=message;
 node.classList.toggle('error',Boolean(error));
}
function render(data){
 const results=$('prospectingResults');
 const items=state.items;
 if(!items.length){
  results.innerHTML='<div class="prospecting-empty">Nenhuma empresa encontrada para este recorte.</div>';
 }else{
  results.innerHTML=items.map(company=>{
   const name=company.company_name||company.legal_name||'Empresa sem nome disponível';
   const location=[company.city,company.state].filter(Boolean).join('/');
   const sector=company.industry||company.segment||'Atividade não informada';
   const evidence=Array.isArray(company.evidence)?company.evidence[0]:null;
   const source=evidence&&evidence.source_name?evidence.source_name:'Fonte não informada';
   return '<article class="prospecting-company"><div><b>'+escapeHtml(name)+'</b><small>'+escapeHtml(company.cnpj||'CNPJ não informado')+' · '+escapeHtml(location||'Localização não informada')+'</small><small>'+escapeHtml(sector)+'</small><small>FONTE · '+escapeHtml(source)+'</small></div><button class="mini" type="button" data-copy-cnpj="'+escapeHtml(company.cnpj||'')+'" '+(company.cnpj?'':'disabled')+'>COPIAR CNPJ</button></article>';
  }).join('');
 }
 $('prospectingNext').hidden=!(data.truncated&&data.next_cursor);
 $('prospectingNext').disabled=false;
 const count=items.length;
 $('prospectingSummary').textContent=count+' empresas · '+(data.identity_granularity||'identidade não informada');
 $('prospectingIdentityNote').textContent=data.identity_note||'A granularidade da identidade não foi informada pela fonte.';
 $('prospectingSourceNote').textContent='FONTE '+(data.source_id||'--')+' · COLETA '+(data.collected_at?new Date(data.collected_at).toLocaleString('pt-BR'):'--')+' · '+(data.scanned_rows??0)+' LINHAS EXAMINADAS';
}
function buildQuery(query,cursor){
 const params=new URLSearchParams();
 params.set('uf',query.uf);
 query.cnaePrefixes.forEach(value=>params.append('cnae_prefixes',value));
 query.municipalities.forEach(value=>params.append('municipalities',value));
 params.set('only_active',String(query.onlyActive));
 params.set('include_secondary_cnae',String(query.includeSecondaryCnae));
 params.set('limit',String(query.limit));
 if(cursor)params.set('after_cnpj_basico',cursor);
 return '/api/prospecting/search?'+params.toString();
}
async function search(next=false){
 if(state.busy)return;
 if(!next){
  const uf=($('prospectingUf').value||'').trim().toUpperCase();
  const cnaePrefixes=($('prospectingCnae').value||'').split(/[;,\s]+/).map(v=>v.trim()).filter(Boolean);
  const municipalities=($('prospectingMunicipalities').value||'').split(/[;,]+/).map(v=>v.trim()).filter(Boolean);
  if(!/^[A-Z]{2}$/.test(uf)){setStatus('Informe uma UF com duas letras.',true);return;}
  if(!cnaePrefixes.length){setStatus('Informe ao menos um prefixo CNAE.',true);return;}
  state.query={uf,cnaePrefixes,municipalities,onlyActive:$('prospectingOnlyActive').checked,includeSecondaryCnae:$('prospectingSecondary').checked,limit:50};
  state.cursor=null;
  state.items=[];
 }
 if(!state.query)return;
 state.busy=true;
 $('prospectingSearch').disabled=true;
 $('prospectingNext').disabled=true;
 setStatus(next?'Carregando próxima página…':'Consultando a base oficial…');
 try{
  const data=await request(buildQuery(state.query,next?state.cursor:null));
  state.items=next?state.items.concat(data.companies||[]):(data.companies||[]);
  state.cursor=data.next_cursor||null;
  render(data);
  setStatus((data.companies||[]).length+' resultados nesta página · '+state.items.length+' acumulados.');
 }catch(error){
  setStatus(error.message,true);
  if(!next){state.items=[];state.cursor=null;render({companies:[]});}
 }finally{
  state.busy=false;
  $('prospectingSearch').disabled=false;
  $('prospectingNext').disabled=false;
 }
}
function wire(){
 const button=$('prospectingButton');
 const windowNode=$('prospectingWindow');
 if(!button||!windowNode)return;
 button.addEventListener('click',()=>{
  windowNode.classList.add('show');
  $('prospectingUf').focus();
 });
 $('prospectingClose').addEventListener('click',()=>windowNode.classList.remove('show'));
 windowNode.addEventListener('click',event=>{if(event.target===windowNode)windowNode.classList.remove('show');});
 $('prospectingForm').addEventListener('submit',event=>{event.preventDefault();search(false);});
 $('prospectingNext').addEventListener('click',()=>search(true));
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&windowNode.classList.contains('show'))windowNode.classList.remove('show');});
 $('prospectingResults').addEventListener('click',async event=>{
  const button=event.target.closest('[data-copy-cnpj]');
  if(!button)return;
  const value=button.getAttribute('data-copy-cnpj')||'';
  if(!value)return;
  try{
   await navigator.clipboard.writeText(value);
   setStatus('CNPJ copiado.');
  }catch(_){
   setStatus('Não foi possível acessar a área de transferência.',true);
  }
 });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',wire,{once:true});
else wire();
})();