(()=> {
'use strict';
const $=id=>document.getElementById(id);
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const state={query:null,cursor:null,items:[],busy:false,view:'list',mapRenderId:0};
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
 const mapPanel=$('prospectingMapPanel');
 const mapToggle=$('prospectingMapToggle');
 const items=state.items;
 results.hidden=state.view==='map';
 mapPanel.hidden=state.view!=='map';
 mapToggle.disabled=!state.query||state.busy;
 mapToggle.textContent=state.view==='map'?'LISTA':'MAPA';
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
 if(state.view==='map')void renderMap(data);
 const count=items.length;
 $('prospectingSummary').textContent=count+' empresas · '+(data.identity_granularity||'identidade não informada');
 $('prospectingIdentityNote').textContent=data.identity_note||'A granularidade da identidade não foi informada pela fonte.';
 $('prospectingSourceNote').textContent='FONTE '+(data.source_id||'--')+' · COLETA '+(data.collected_at?new Date(data.collected_at).toLocaleString('pt-BR'):'--')+' · '+(data.scanned_rows??0)+' LINHAS EXAMINADAS';
}
function buildQuery(query,cursor,includeGeocoding=false){
 const params=new URLSearchParams();
 params.set('uf',query.uf);
 query.cnaePrefixes.forEach(value=>params.append('cnae_prefixes',value));
 query.municipalities.forEach(value=>params.append('municipalities',value));
 params.set('only_active',String(query.onlyActive));
 params.set('include_secondary_cnae',String(query.includeSecondaryCnae));
 params.set('limit',String(query.limit));
 if(includeGeocoding)params.set('include_geocoding','true');
 if(cursor)params.set('after_cnpj_basico',cursor);
 return '/api/prospecting/search?'+params.toString();
}
function renderMapSelection(cluster){
 const node=$('prospectingMapSelection');
 if(!node)return;
 if(cluster.count>1){
  node.replaceChildren();
  const heading=document.createElement('p');
  heading.textContent=cluster.count+' empresas agrupadas nesta localização. Selecione uma para consultar os dados:';
  node.appendChild(heading);
  const members=document.createElement('div');
  members.className='prospecting-map-members';
  cluster.members.forEach(marker=>{
   const button=document.createElement('button');
   button.type='button';
   button.className='prospecting-map-member';
   button.textContent=marker.name+(marker.cnpj?' · '+marker.cnpj:'');
   button.addEventListener('click',()=>renderMapSelection({count:1,members:[marker]}));
   members.appendChild(button);
  });
  node.appendChild(members);
  return;
 }
 const marker=cluster.members[0];
 const coordinate=marker.coordinate;
 const accuracy=coordinate.accuracy_m==null?'não informada':coordinate.accuracy_m+' m';
 node.textContent=[
  marker.name,
  marker.cnpj?'CNPJ '+marker.cnpj:'',
  [marker.city,marker.state].filter(Boolean).join(' / '),
  'PRECISÃO '+marker.precision+' · '+marker.status,
  'DESVIO ESTIMADO '+accuracy+' · '+coordinate.crs,
  marker.provider,
  marker.formattedAddress,
 ].filter(Boolean).join('\\n');
}
async function renderMap(data){
 const sequence=++state.mapRenderId;
 const summary=data.geocoding_summary||{};
 const mapped=state.items.filter(company=>{
  const item=company.geocoding;
  return item&&(item.status==='success'||item.status==='partial')&&item.coordinate;
 });
 const success=mapped.filter(company=>company.geocoding.status==='success').length;
 const partial=mapped.length-success;
 $('prospectingMapSummary').textContent=mapped.length+' / '+state.items.length+' COM COORDENADAS · '+success+' PRECISAS · '+partial+' PARCIAIS';
 $('prospectingMapNote').textContent=!summary.available
  ?'CACHE GEOGRÁFICO NÃO ENCONTRADO. Configure JARVIS_PROSPECTO_GEOCODING_DB ou execute uma campanha com --geocode no caminho padrão.'
  :mapped.length
   ?'PONTOS DO CACHE LOCAL · RESULTADOS PARCIAIS SÃO APROXIMADOS · CRS PRESERVADO POR REGISTRO · SEM GEOCODIFICAÇÃO SOB DEMANDA'
   :'Nenhuma coordenada em cache para esta página. Execute uma campanha com --geocode para preencher o cache; o mapa não chama provedores.';
 try{
  const renderer=window.JarvisProspectingMap;
  if(!renderer||typeof renderer.render!=='function')throw new Error('Módulo de mapa do Prospecto indisponível.');
  await renderer.render($('prospectingMapCanvas'),state.items,renderMapSelection);
  if(sequence!==state.mapRenderId)return;
 }catch(error){
  if(sequence!==state.mapRenderId)return;
  const canvas=$('prospectingMapCanvas');
  canvas.replaceChildren();
  const message=document.createElement('div');
  message.className='prospecting-map-empty';
  message.textContent=error.message;
  canvas.appendChild(message);
 }
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
  const data=await request(buildQuery(state.query,next?state.cursor:null,state.view==='map'));
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
  $('prospectingMapToggle').disabled=!state.query;
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
 $('prospectingMapToggle').addEventListener('click',()=>{
  if(state.busy||!state.query)return;
  state.view=state.view==='map'?'list':'map';
  state.cursor=null;
  state.items=[];
  state.mapRenderId+=1;
  $('prospectingMapSelection').textContent='Selecione um ponto para consultar a empresa e a precisão da coordenada.';
  search(false);
 });
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