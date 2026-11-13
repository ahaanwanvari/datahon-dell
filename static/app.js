'use strict';
const $=id=>document.getElementById(id);
let state={images:[],events:[]}, selectedLocation=null, selectedEvent=null, current=null, polling=false;
let imageById=new Map(), initialCollection=true;
let texasPoint={lat:29.76,lon:-95.37}, texasRequest=0;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(s){$('toast').textContent=s;$('toast').style.display='block';setTimeout(()=>$('toast').style.display='none',7000);}
async function api(url,body){const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const v=await r.json();if(!r.ok)throw Error(v.error||'Request failed');return v;}
function images(){return state.images.filter(i=>i.collection===$('collection').value);}
function matches(e){const a=imageById.get(e.after_id);if(!a||a.collection!==$('collection').value)return false;const q=$('query').value.toLowerCase().trim();const text=[e.summary,e.evidence,e.kind,a.name,e.note].join(' ').toLowerCase().replaceAll('_',' ');const synonyms={flood:'water',expanding:'expand',receding:'recede'};const terms=q.split(/\s+/).filter(Boolean).map(x=>synonyms[x]||x);return terms.every(t=>text.includes(t))&&($('kind').value==='all'||e.kind===$('kind').value)&&e.rarity>=Number($('rarity').value)&&(!$('from').value||a.date>=$('from').value)&&(!$('to').value||a.date<=$('to').value)&&($('rejected').checked||e.review!=='rejected');}
function groups(){
 const events=state.events.filter(matches), places=new Map();
 for(const i of images()){if(!places.has(i.location_id))places.set(i.location_id,{...i,events:[],images:[]});places.get(i.location_id).images.push(i);}
 for(const e of events){const i=imageById.get(e.after_id);places.get(i.location_id).events.push(e);}
 const browsing=!$('query').value.trim()&&$('kind').value==='all'&&Number($('rarity').value)===0;
 const analyzed=new Set(state.events.map(e=>imageById.get(e.after_id)?.location_id));
 return [...places.values()].filter(p=>p.events.length||(browsing&&!analyzed.has(p.location_id)&&p.images.some(i=>(!$('from').value||i.date>=$('from').value)&&(!$('to').value||i.date<=$('to').value))))
 .sort((a,b)=>Math.max(-1,...b.events.map(e=>e.strength))-Math.max(-1,...a.events.map(e=>e.strength)));
}
function render(){const ims=images(), ids=new Set(ims.map(i=>i.id)), gs=groups();$('imageCount').textContent=ims.length;$('placeCount').textContent=new Set(ims.map(i=>i.location_id)).size;$('eventCount').textContent=state.events.filter(e=>ids.has(e.after_id)).length;$('rarityValue').textContent=$('rarity').value;$('notice').textContent=$('collection').value==='demo'?'DEMONSTRATION · Synthetic imagery and prewritten observations. Import real imagery to run Qwen.':'AI OBSERVATIONS · Automatically generated, with optional review. Rarity is a relative magnitude rank, not flood probability.';$('resultCount').textContent=`${gs.length} locations · ${gs.reduce((n,p)=>n+p.events.length,0)} matching observations`;
if(!gs.some(p=>p.location_id===selectedLocation)){selectedLocation=gs[0]?.location_id;selectedEvent=null;}
$('locations').innerHTML=gs.map(p=>{const top=[...p.events].sort((a,b)=>b.strength-a.strength)[0];return `<button class="location ${p.location_id===selectedLocation?'active':''}" data-location="${esc(p.location_id)}"><strong>${esc(p.name)}</strong><p>${esc(top?.summary||(p.images.length>1?'Ready for automatic comparison':'Single observation · no before/after pair'))}</p><div class="meta"><span>${p.images.length} dates · ${p.events.length} matches</span><span class="score">${top?'Rarity '+top.rarity+'/100':'Not analyzed'}</span></div></button>`}).join('')||'<div class="empty">No matches. Adjust filters, or import imagery and run discovery.</div>';
$('locations').querySelectorAll('button').forEach(b=>b.onclick=()=>{selectedLocation=b.dataset.location;selectedEvent=null;render()});drawMap(gs);
const place=gs.find(p=>p.location_id===selectedLocation);$('detail').style.display=place?'block':'none';if(!place)return;
const placeIds=new Set(place.images.map(i=>i.id));const timeline=state.events.filter(e=>placeIds.has(e.after_id)).sort((a,b)=>imageById.get(a.after_id).date.localeCompare(imageById.get(b.after_id).date));
if(!timeline.some(e=>e.id===selectedEvent))selectedEvent=[...place.events].sort((a,b)=>b.strength-a.strength)[0]?.id;
$('placeName').textContent=place.name;$('placeLabel').textContent=Number.isFinite(place.lat)&&Number.isFinite(place.lon)?`${place.lat.toFixed(4)}° / ${place.lon.toFixed(4)}°`:'CAPTION LOCATION · PRECISE COORDINATES UNAVAILABLE';$('mapLink').style.display=Number.isFinite(place.lat)?'':'none';$('mapLink').href=`https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lon}#map=13/${place.lat}/${place.lon}`;
if(!timeline.length){showPending(place);return;}
document.querySelector('.review').style.display='';$('timeline').innerHTML=timeline.map(e=>{const i=imageById.get(e.after_id);return `<button class="timeline-item ${e.id===selectedEvent?'active':''}" data-event="${esc(e.id)}">${esc(i.date)}<span>${esc(e.kind.replaceAll('_',' '))}</span><span>${esc(e.review)}${matches(e)?' · matches filters':''}</span></button>`}).join('');$('timeline').querySelectorAll('button').forEach(b=>b.onclick=()=>{selectedEvent=b.dataset.event;render()});showEvent(timeline.find(e=>e.id===selectedEvent));}
function pairImages(a,b){
 $('beforeImage').src='/api/image?id='+encodeURIComponent(a.id);$('afterImage').src='/api/image?id='+encodeURIComponent(b.id);
 $('beforeDate').textContent=(a.id===b.id?'OBSERVATION':'BEFORE')+' · '+a.date;$('afterDate').textContent=(a.id===b.id?'OBSERVATION':'AFTER')+' · '+b.date;
 $('beforeSource').href=a.source_url||$('beforeImage').src;$('afterSource').href=b.source_url||$('afterImage').src;$('sensor').textContent=b.sensor;
}
function showPending(place){
 current=null;document.querySelector('.review').style.display='none';
 const dated=[...place.images].sort((a,b)=>a.date.localeCompare(b.date));const a=dated[0],b=dated[dated.length-1];pairImages(a,b);
 $('timeline').innerHTML=dated.map(i=>`<div class="timeline-item">${esc(i.date)}<span>${esc(i.provenance?.original_image_id||i.id)}</span><span>Source observation</span></div>`).join('');
 $('observation').innerHTML=`<span class="badge">${dated.length>1?'Awaiting AI analysis':'Standalone image'}</span><h3>${dated.length>1?'Imagery is ready. Automatic discovery will add a change description here.':'One dated observation is available for this location.'}</h3><p>${dated.length>1?'Open Manage imagery to follow indexing progress.':'This image is available for inspection. A change timeline requires a matching observation from another date.'}</p><p><b>Source</b> ${esc(b.provenance?.original_image_id||b.id)} · ${esc(b.sensor)}</p><p><b>Attribution</b> ${esc(b.provenance?.attribution||'See source image link.')}</p><p><b>Dataset</b> ${esc(b.provenance?.dataset_repo||b.collection)}</p>`;
}
function showEvent(e){if(!e)return;current=e;const a=imageById.get(e.before_id),b=imageById.get(e.after_id);$('beforeImage').src='/api/image?id='+encodeURIComponent(a.id);$('afterImage').src='/api/image?id='+encodeURIComponent(b.id);$('beforeDate').textContent='BEFORE · '+a.date;$('afterDate').textContent='AFTER · '+b.date;$('beforeSource').href=a.source_url||$('beforeImage').src;$('afterSource').href=b.source_url||$('afterImage').src;$('sensor').textContent=b.sensor;$('observation').innerHTML=`<span class="badge">${esc(e.kind.replaceAll('_',' '))}</span> <span class="badge">${esc(e.review)}</span><h3>${esc(e.summary)}</h3><p><b>Observation window</b> ${esc(a.date)} → ${esc(b.date)}</p><p><b>Evidence</b> ${esc(e.evidence)}</p><p><b>Uncertainty</b> ${esc(e.uncertainty)}</p><p><b>Provenance</b> ${esc(e.model)} · magnitude ${e.strength.toFixed(2)} · rarity ${e.rarity}/100 · ${esc(e.created)}</p><p><b>Source IDs</b> ${esc(a.provenance?.original_image_id||a.id)} → ${esc(b.provenance?.original_image_id||b.id)}<br><b>SHA-256 (after)</b> <span style="overflow-wrap:anywhere">${esc(b.sha)}</span></p>`;$('note').value=e.note;$('review').value=e.review;$('saved').textContent='';}
function drawMap(gs){gs=gs.filter(p=>Number.isFinite(p.lat)&&Number.isFinite(p.lon));const svg=$('map');if(!gs.length){svg.innerHTML='';return;}let minX=Math.min(...gs.map(p=>p.lon)),maxX=Math.max(...gs.map(p=>p.lon)),minY=Math.min(...gs.map(p=>p.lat)),maxY=Math.max(...gs.map(p=>p.lat));const cos=Math.max(.1,Math.cos((minY+maxY)/2*Math.PI/180));const span=Math.max((maxX-minX)*cos,(maxY-minY)*2,.03);const cx=(minX+maxX)/2,cy=(minY+maxY)/2;svg.innerHTML=`<defs><pattern id="grid" width="40" height="38" patternUnits="userSpaceOnUse"><path d="M40 0H0V38" fill="none" stroke="#dce2dd" stroke-width=".5"/></pattern></defs><rect width="400" height="190" fill="url(#grid)"/><text x="12" y="20" fill="#8aa5ac" font-size="10">N ↑</text>`+gs.map(p=>{const x=200+(p.lon-cx)*cos/span*310,y=95-(p.lat-cy)/span*310;return `<g class="pin" tabindex="0" role="button" aria-label="${esc(p.name)}" data-location="${esc(p.location_id)}"><circle cx="${x}" cy="${y}" r="${p.location_id===selectedLocation?8:gs.length>30?3:5}" fill="${p.location_id===selectedLocation?'#245a4e':'#728078'}"/>${gs.length<12||p.location_id===selectedLocation?`<text x="${x+11}" y="${y+4}" fill="#34423b" font-size="10">${esc(p.name.slice(0,20))}</text>`:""}</g>`}).join('');svg.querySelectorAll('.pin').forEach(p=>{const choose=()=>{selectedLocation=p.dataset.location;selectedEvent=null;render()};p.onclick=choose;p.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose()}}});}
function jobUI(){const j=state.job;$('indexStatus').textContent=j.running?`Comparing images · ${j.done} / ${j.total} pairs processed · results appear as they finish.`:(state.images.some(i=>i.collection==='local')?`Imported imagery available · ${state.events.filter(e=>imageById.get(e.after_id)?.collection==='local').length} comparisons saved. Use Import images to add a collection or run comparisons.`:'');$('progress').max=j.total||1;$('progress').value=j.done;$('jobMessage').textContent=j.message+ (j.running?` (${j.done}/${j.total})`:'');$('jobErrors').textContent=j.errors.join('\n');$('indexBtn').disabled=j.running;$('importBtn').disabled=j.running;$('modelInfo').textContent=`Model: ${state.model} · ${state.endpoint}. Magnitude and rarity are exploratory model outputs, not calibrated flood likelihoods.`;}
function escapeText(s){return esc(s)}
async function loadTexas(){const run=++texasRequest;$('texasStatus').textContent='Looking up this Texas location and loading public context layers…';$('texasLayers').innerHTML='';try{const place=await api('/api/geocode',{query:$('texasPlace').value});if(run!==texasRequest)return;texasPoint={lat:place.lat,lon:place.lon};$('texasPlace').value=place.label;$('texasMap').innerHTML=`<iframe title="OpenStreetMap view of ${escapeText(place.label)}" src="https://www.openstreetmap.org/export/embed.html?bbox=${place.lon-.12}%2C${place.lat-.09}%2C${place.lon+.12}%2C${place.lat+.09}&layer=mapnik&marker=${place.lat}%2C${place.lon}"></iframe>`;$('texasStatus').textContent=`Area centered at ${place.lat.toFixed(4)}, ${place.lon.toFixed(4)} · loading nearby data; unavailable sources will be identified below.`;const c=await api(`/api/texas-context?lat=${place.lat}&lon=${place.lon}`);if(run!==texasRequest)return;const specs=[['alerts','NWS active alerts','Official active watches/warnings/advisories for the point; an empty result is not a guarantee of safety.','https://api.weather.gov/alerts/active'],['gauges','NOAA river gauges','Gauge sites with official stage/flow data; gauges do not cover all waterways or street flooding.','https://api.water.noaa.gov/nwps/v1/docs/'],['road_conditions','TxDOT road conditions','Reported conditions on maintained TxDOT roads; not every local street. Zero reports is not an all-clear.','https://api.drivetexas.org/'],['flood_hazards','FEMA mapped flood hazards','Mapped regulatory hazard areas; not a live flood forecast.','https://msc.fema.gov/portal/home']];$('texasLayers').innerHTML=specs.map(([key,title,desc,href])=>{const l=c.layers[key];const n=key==='alerts'?c.alerts.length:key==='gauges'?c.gauges.length:key==='road_conditions'?c.road_conditions.length:c.flood_hazards.length;return `<article class="layer-card"><strong>${title}<span class="${l?.available?'layer-ok':'layer-error'}">${l?.available?`${n} records returned`:'unavailable'}</span></strong><p>${desc}</p>${l?.as_of?`<p>Feed timestamp: ${escapeText(l.as_of)}</p>`:''}${l?.error?`<p>${escapeText(l.error)}</p>`:''}<a target="_blank" rel="noopener" href="${href}">Open source ↗</a></article>`}).join('');const alerts=c.alerts.slice(0,8).map(f=>{const p=f.properties||{};return `<div class="data-row"><b>${escapeText(p.event||'NWS alert')}</b><span>${escapeText(p.headline||p.description||'Active alert')}</span><small>${escapeText(p.effective||'Effective time unavailable')} · expires ${escapeText(p.expires||'unknown')}</small></div>`}).join('');const gauges=c.gauges.slice(0,8).map(g=>{const s=g.status?.observed||{},value=s.primary>-900?`${s.primary} ${s.primaryUnit||''}`:'No current observation',cat=String(s.floodCategory||'unknown').replaceAll('_',' ');return `<div class="data-row"><b>${escapeText(g.name||g.lid)}</b><span>${escapeText(value)} · ${escapeText(cat)}</span><small>${escapeText(s.validTime||'Time unavailable')}</small></div>`}).join('');const roads=c.road_conditions.slice(0,8).map(f=>{const p=f.properties||{};return `<div class="data-row"><b>${escapeText(p.FULLNAME||p.ROUTE_NAME||'TxDOT roadway')}</b><span>${escapeText(p.CONDITION_DESC||p.CNSTRCT_TYPE_CD||p.TYPE||'Reported condition')}</span></div>`}).join('');const zones=c.flood_hazards.slice(0,8).map(f=>{const p=f.properties||{};return `<div class="data-row"><b>FEMA zone ${escapeText(p.FLD_ZONE||'unknown')}</b><span>${escapeText(p.ZONE_SUBTY||'Mapped hazard area')}</span></div>`}).join('');$('texasDetails').innerHTML=`<h3>National Weather Service active alerts · ${c.alerts.length}</h3>${alerts||'<div class="data-row"><span>No active alert returned at this point. This is not an all-clear.</span></div>'}`+(gauges?`<h3>Nearby gauge observations</h3>${gauges}`:'')+(roads?`<h3>Nearby TxDOT reports</h3>${roads}`:'')+(zones?`<h3>Nearby mapped FEMA zones</h3>${zones}`:'')||'<p class="helper">No details returned for this point. That does not mean there is no flood or road hazard.</p>';$('texasSources').textContent='Map tiles © OpenStreetMap contributors (ODbL). Public feeds may be delayed or incomplete. Texas road conditions are restricted to TxDOT-maintained roads and API terms apply.';$('texasStatus').textContent='Context check finished. Counts reflect source records returned near the selected point, not proof of safety or complete coverage.'}catch(e){if(run===texasRequest)$('texasStatus').textContent=e.message}}
function useSelectedTexas(){const p=groups().find(x=>x.location_id===selectedLocation);if(!p||!Number.isFinite(p.lat)||!Number.isFinite(p.lon)){toast('Select an imported image location with coordinates first.');return;}$('texasPlace').value=`${p.lat}, ${p.lon}`;loadTexas()}
async function routeRequest(){try{$('routeResults').textContent='Finding routes and screening them against available Texas hazard/report layers…';const a=await api('/api/geocode',{query:$('routeStart').value}),b=await api('/api/geocode',{query:$('routeEnd').value});const r=await api(`/api/route?olat=${a.lat}&olon=${a.lon}&dlat=${b.lat}&dlon=${b.lon}`);$('routeResults').innerHTML=`<p class="helper">${escapeText(r.road_source)} · ${escapeText(r.ranking)}</p>`+r.options.map(o=>`<article class="route-option ${o.txdot_hazards?.length?'route-hazard':''}"><strong>Risk-screen rank ${o.rank} · ${o.distance_km} km · about ${o.duration_min} min · screen score ${o.risk_score===null?'unknown':o.risk_score+'/100'}</strong><p class="risk-note">${escapeText(o.risk_level)}</p><p>Sampled FEMA zone exposure: ${o.fema_zone_sample_fraction===null?'unavailable':Math.round(o.fema_zone_sample_fraction*100)+'% of route samples'} · matched TxDOT hazard reports: ${o.txdot_hazards?.length||0}</p>${o.txdot_hazards?.length?`<p class="risk-note">${o.txdot_hazards.map(h=>`${escapeText(h.road)}: ${escapeText(h.description)}`).join(' · ')}</p>`:''}<p>${o.roads.map(escapeText).join(' → ')||'Road names unavailable'}</p><details><summary>Risk inputs and limitations</summary><p>${escapeText(o.method)}</p><pre>${escapeText(JSON.stringify(o.sources,null,2))}</pre></details><a target="_blank" rel="noopener" href="https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${a.lat}%2C${a.lon}%3B${b.lat}%2C${b.lon}">Open route in OSM ↗</a></article>`).join('')}catch(e){$('routeResults').textContent=e.message}}
function facilities(){try{return JSON.parse(localStorage.getItem('texasFloodFacilities')||'[]')}catch{return []}}
function renderFacilities(){const fs=facilities();$('facilityList').innerHTML=fs.map((f,i)=>`<div class="facility-item"><div><strong>${escapeText(f.name)}</strong><p>${escapeText(f.type)} · ${f.lat.toFixed(5)}, ${f.lon.toFixed(5)} · ${escapeText(f.added)}</p></div><button data-remove-facility="${i}">Remove</button></div>`).join('')||'<p class="helper">No local facility notes yet.</p>';document.querySelectorAll('[data-remove-facility]').forEach(b=>b.onclick=()=>{const f=facilities();f.splice(Number(b.dataset.removeFacility),1);localStorage.setItem('texasFloodFacilities',JSON.stringify(f));renderFacilities()})}
function addFacility(){try{const coords=$('facilityCoords').value.split(',').map(Number);if(coords.length!==2||!Number.isFinite(coords[0])||!Number.isFinite(coords[1])||coords[0]<25.8||coords[0]>36.6||coords[1]<-106.7||coords[1]>-93.4)throw Error('Enter Texas coordinates as latitude, longitude.');const name=$('facilityName').value.trim();if(!name)throw Error('Enter a facility or check-location label.');const f=facilities();f.push({name,type:$('facilityType').value,lat:coords[0],lon:coords[1],added:new Date().toISOString()});localStorage.setItem('texasFloodFacilities',JSON.stringify(f));$('facilityName').value='';renderFacilities()}catch(e){toast(e.message)}}
function damageScenario(){const count=Math.max(0,Number($('damageCount').value)||0),low=Math.max(0,Number($('damageLow').value)||0),high=Math.max(low,Number($('damageHigh').value)||0);return {assumed_buildings:count,repair_cost_per_building_usd:{low,high},total_usd:{low:count*low,high:count*high},source:'User-entered scenario assumptions; not derived from imagery or official damage assessment.'}}
function renderDamage(){const d=damageScenario();$('damageEstimate').textContent=`Scenario total: $${d.total_usd.low.toLocaleString()} – $${d.total_usd.high.toLocaleString()} · based only on user-entered assumptions.`}
function exportBrief(){const brief={title:'Texas flood planning brief',created:new Date().toISOString(),notice:'Planning aid only. Not an evacuation order, safe-route certification, or dispatch instruction.',area:$('texasPlace').value,damage_scenario:damageScenario(),facilities:facilities(),observations:state.events.filter(e=>imageById.get(e.after_id)?.collection===$('collection').value).map(e=>({summary:e.summary,kind:e.kind,review:e.review,observation_window:[imageById.get(e.before_id)?.date,imageById.get(e.after_id)?.date],location:imageById.get(e.after_id)?.name,uncertainty:e.uncertainty})),sources:['NOAA NWPS','TxDOT DriveTexas','FEMA NFHL','OpenStreetMap / OSRM']};const blob=new Blob([JSON.stringify(brief,null,2)],{type:'application/json'}),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='texas-flood-planning-brief.json';a.click();URL.revokeObjectURL(a.href)}
async function refresh(full=true){state=await api('/api/state');imageById=new Map(state.images.map(i=>[i.id,i]));if(initialCollection){if(state.images.some(i=>i.collection==='local'))$('collection').value='local';initialCollection=false;}jobUI();if(full)render();}
for(const id of ['query','collection','kind','rarity','from','to','rejected'])$(id).addEventListener('input',render);
$('swipe').oninput=()=>{$('beforeClip').style.clipPath=`inset(0 ${100-$('swipe').value}% 0 0)`;$('swipeLine').style.left=$('swipe').value+'%'};
$('dataBtn').onclick=()=>$('dataDialog').showModal();$('closeDialog').onclick=()=>$('dataDialog').close();
$('importBtn').onclick=async()=>{try{const v=await api('/api/import',{path:$('manifest').value});$('collection').value='local';await refresh();toast(`Imported ${v.count} images. Use Compare images to create a timeline.`)}catch(e){toast(e.message)}};
$('indexBtn').onclick=async()=>{try{await api('/api/index',{});await refresh(false)}catch(e){toast(e.message)}};
$('saveReview').onclick=async()=>{if(!current)return;try{await api('/api/review',{id:current.id,review:$('review').value,note:$('note').value});await refresh();$('saved').textContent='Saved locally'}catch(e){toast(e.message)}};
refresh().catch(e=>toast(e.message));setInterval(async()=>{if(polling)return;polling=true;try{const was=state.job?.running,oldCount=state.events.length;await refresh(false);if(oldCount!==state.events.length&&document.activeElement!==$('note'))render();if(was&&!state.job.running){render();toast('Comparisons saved.')}}catch(e){$('jobMessage').textContent='Connection lost. Retrying…'}finally{polling=false}},2500);
$('loadTexas').onclick=loadTexas;$('texasPlace').addEventListener('keydown',e=>{if(e.key==='Enter')loadTexas()});$('useSelected').onclick=useSelectedTexas;$('routeBtn').onclick=routeRequest;$('addFacility').onclick=addFacility;$('exportBrief').onclick=exportBrief;for(const id of ['damageCount','damageLow','damageHigh'])$(id).addEventListener('input',renderDamage);renderDamage();renderFacilities();

async function askImageData(file){
  if(!file || !['image/jpeg','image/png','image/webp'].includes(file.type))throw Error('Choose a JPEG, PNG or WebP photo.');
  if(file.size>30*1024*1024)throw Error('Choose an image smaller than 30 MB.');
  const image=await createImageBitmap(file);
  try{const scale=Math.min(1,448/Math.max(image.width,image.height));
    const canvas=document.createElement('canvas');canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale));
    canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
    return canvas.toDataURL('image/jpeg',.9);
  }finally{image.close();}
}
$('askSubmit').onclick=async()=>{
  const button=$('askSubmit');button.disabled=true;$('askAnswer').textContent='';
  try{
    const first=$('askImage').files[0], second=$('askSecondImage').files[0];
    const prompt=$('askPrompt').value.trim();if(!prompt)throw Error('Enter your question.');
    const images=[await askImageData(first)];if(second)images.push(await askImageData(second));
    $('askPreviews').replaceChildren(...images.map((src,i)=>{const img=document.createElement('img');img.src=src;img.alt=images.length===1?'Selected image':i===0?'Before image':'After image';return img;}));
    $('askStatus').textContent='Checking your image…';
    const result=await api('/api/ask',{prompt,images});$('askAnswer').textContent=result.answer;
    $('askStatus').textContent='Done';
  }catch(e){$('askStatus').textContent=e.message;}finally{button.disabled=false;}
};

let conditionsLoaded=false;
for(const button of document.querySelectorAll('[data-view]')){
  button.addEventListener('click',()=>{
    for(const tab of document.querySelectorAll('[data-view]')){
      const active=tab===button;
      if(active)tab.setAttribute('aria-current','page');else tab.removeAttribute('aria-current');
      $('view-'+tab.dataset.view).hidden=!active;
    }
    if(button.dataset.view==='conditions'&&!conditionsLoaded){conditionsLoaded=true;loadTexas();}
  });
}

let activeScenario=null,scenarioPoll=null,scenarioBusy=false;
function scenarioButtons(busy){scenarioBusy=busy;$('scenarioGenerate').disabled=busy;$('scenarioPlan').disabled=busy||!locationConfirmed;$('askImage').disabled=busy;$('scenarioSeverity').disabled=busy;}
function resetScenario(){
  if(scenarioPoll)clearTimeout(scenarioPoll);scenarioPoll=null;activeScenario=null;
  $('scenarioResult').hidden=true;$('scenarioPlanResults').replaceChildren();$('scenarioStatus').textContent='';$('scenarioLocation').value='';$('scenarioPlanStatus').textContent='';localStorage.removeItem('floodAtlasScenario');resetLocationUI();clearPhotoAnalysis();$('askAnswer').textContent='';$('askPreviews').replaceChildren();$('askStatus').textContent='';$('askSecondImage').value='';
}
$('askImage').addEventListener('change',()=>{if(!scenarioBusy)resetScenario();});
function rawPhoto(file){
  return new Promise((resolve,reject)=>{
    if(!file||!['image/jpeg','image/png','image/webp'].includes(file.type))return reject(Error('Choose a JPEG, PNG or WebP photo.'));
    if(file.size>16*1024*1024)return reject(Error('Choose a photo smaller than 16 MB.'));
    const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('The photo could not be read.'));reader.readAsDataURL(file);
  });
}
function renderScenarioPlan(plan){
  const selected=plan.candidates.find(p=>p.id===plan.assessment.candidate_id);
  const title=selected?'Planning option to contact first':'No confirmed destination';
  const origin=plan.origin;
  $('scenarioPlanResults').innerHTML=`<div class="plan-summary"><h3>${esc(title)}</h3><p>${esc(plan.assessment.reason)}</p><p class="helper">Location: ${esc(origin.label)}${Number.isFinite(origin.elevation_m)?' · terrain elevation '+esc(origin.elevation_m)+' m':''}</p></div>`+
    plan.candidates.map(p=>`<article class="destination-option"><h3>${esc(p.name)}</h3><p>${esc(p.address)} · ${esc(p.distance_km)} km away</p><p>${esc(p.status)}</p><p class="helper">Coordinates: ${Number(p.lat).toFixed(6)}, ${Number(p.lon).toFixed(6)}</p>${Number.isFinite(p.higher_by_m)?`<p class="helper">Approximate terrain: ${esc(p.elevation_m)} m · ${p.higher_by_m>0?'+':''}${esc(p.higher_by_m)} m relative to the photo location</p>`:''}${p.phone?`<p>Contact: ${esc(p.phone)}</p>`:''}${p.route_note?`<p class="helper">${esc(p.route_note)}</p>`:''}${p.route_error?`<p class="helper">Route information unavailable: ${esc(p.route_error)}</p>`:''}<a href="https://www.openstreetmap.org/?mlat=${Number(p.lat)}&mlon=${Number(p.lon)}#map=16/${Number(p.lat)}/${Number(p.lon)}" target="_blank" rel="noopener">View location</a>${p.route_usable?` · <a href="https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${Number(origin.lat)}%2C${Number(origin.lon)}%3B${Number(p.lat)}%2C${Number(p.lon)}" target="_blank" rel="noopener">Review route</a><p class="helper">No matching hazards in available sampled layers. This is not a guarantee of passability.</p>`:''}</article>`).join('')+
    (!plan.candidates.length?'<p>No nearby shelter records were returned. This does not mean there are no shelters or higher places.</p>':'')+
    `<p class="helper">${esc(plan.scope)} ${esc(plan.terrain_limit)}</p><p><a href="${esc(plan.shelter_directory)}" target="_blank" rel="noopener">Official shelter directory</a> · <a href="${esc(plan.official_guidance)}" target="_blank" rel="noopener">Flood safety guidance</a></p>`+
    `<details class="extra-tool"><summary>Sources and missing information</summary><p class="helper">Checked ${esc(plan.checked_at)}</p>${plan.sources.map(source=>`<p><a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.name)}</a></p>`).join('')}${plan.errors.map(error=>`<p class="helper">${esc(error)}</p>`).join('')}</details>`;
}
async function pollScenario(){
  if(!activeScenario)return;
  try{
    const record=await api('/api/scenarios/'+activeScenario);
    if(['failed','interrupted'].includes(record.state))throw Error(record.error||'The scenario was interrupted. Please try again.');
    const generating=['queued','analyzing_and_generating'].includes(record.state),planning=record.state==='finding_destinations';
    if(generating){$('scenarioStatus').textContent=record.stage==='reviewing_generated_photo'?'Qwen is analyzing the generated flooded view…':'Generating the flooded view…';renderPhotoAnalysis(record);}
    if(record.generated_url){
      if($('scenarioAfter').getAttribute('src')!==record.generated_url){
        $('scenarioAfter').onload=()=>{$('scenarioComparison').style.aspectRatio=$('scenarioAfter').naturalWidth+'/'+$('scenarioAfter').naturalHeight;};
        $('scenarioBefore').src=record.original_url;$('scenarioAfter').src=record.generated_url;
        $('scenarioSwipe').value=50;updateScenarioSwipe();

      }
      $('scenarioResult').hidden=false;restorePhotoLocation(record);renderPhotoAnalysis(record);$('scenarioStatus').textContent=generating?'Flood illustration ready. Qwen is analyzing the generated flooded view…':'Flood illustration ready. Drag the slider to compare.';
    }
    if(planning){const stages={searching_shelters:'Finding nearby shelter records…',checking_terrain:'Nearby records found. Checking terrain…',checking_access:'Checking available access information…',reviewing_options:'Comparing eligible options…'};$('scenarioPlanStatus').textContent=stages[record.plan_stage]||'Starting destination lookup…';if(record.plan)renderScenarioPlan(record.plan);}
    if(record.plan_error)$('scenarioPlanStatus').textContent=record.plan_error;
    if(record.state==='planned'){$('scenarioPlanStatus').textContent='Location check complete.';renderScenarioPlan(record.plan);}
    scenarioButtons(generating||planning);
    if(generating||planning)scenarioPoll=setTimeout(pollScenario,2000);
    else localStorage.setItem('floodAtlasScenario',activeScenario);
  }catch(e){scenarioButtons(false);$('scenarioStatus').textContent=e.message;}
}
function updateScenarioSwipe(){const value=$('scenarioSwipe').value;$('scenarioBeforeClip').style.clipPath=`inset(0 ${100-value}% 0 0)`;$('scenarioLine').style.left=value+'%';$('sceneMarkers').style.clipPath=`inset(0 0 0 ${value}%)`;}
$('scenarioSwipe').oninput=updateScenarioSwipe;
$('scenarioGenerate').onclick=async()=>{
  if(scenarioBusy)return;scenarioButtons(true);
  try{
    const image=await rawPhoto($('askImage').files[0]);resetScenario();scenarioButtons(true);
    $('scenarioStatus').textContent='Uploading your photo…';
    const result=await api('/api/scenarios',{image,severity:$('scenarioSeverity').value});activeScenario=result.id;localStorage.setItem('floodAtlasScenario',activeScenario);pollScenario();
  }catch(e){scenarioButtons(false);$('scenarioStatus').textContent=e.message;}
};
$('scenarioPlan').onclick=async()=>{
  try{if(!activeScenario)throw Error('Generate a flooded view first.');if(!locationConfirmed)throw Error('Confirm the photo location on the map first.');
    scenarioButtons(true);$('scenarioPlanResults').replaceChildren();await api('/api/scenarios/'+activeScenario+'/plan',{});pollScenario();
  }catch(e){scenarioButtons(false);$('scenarioPlanStatus').textContent=e.message;}
};
const savedScenario=localStorage.getItem('floodAtlasScenario');if(savedScenario&&/^[0-9a-f]{32}$/.test(savedScenario)){activeScenario=savedScenario;pollScenario();}

let locationChoice=null,locationConfirmed=false,locationForScenario=null,locationMapCenter=null,locationMapZoom=16,locationBounds=null;
function resetLocationUI(){
  locationChoice=null;locationConfirmed=false;locationForScenario=null;locationBounds=null;
  $('photoMatchStatus').textContent='';$('photoMatchCandidates').replaceChildren();$('locationMapPanel').hidden=true;
  $('locationConfirmation').textContent='';$('scenarioPlan').disabled=true;
}
function projectLocation(lat,lon){const size=256*2**locationMapZoom,sine=Math.sin(Math.max(-85,Math.min(85,lat))*Math.PI/180);return {x:(lon+180)/360*size,y:(.5-Math.log((1+sine)/(1-sine))/(4*Math.PI))*size};}
function unprojectLocation(x,y){const size=256*2**locationMapZoom;return {lat:Math.atan(Math.sinh(Math.PI*(1-2*y/size)))*180/Math.PI,lon:((x/size*360+180)%360+360)%360-180};}
function drawLocationMap(){
  if(!locationChoice||!locationMapCenter||$('locationMapPanel').hidden)return;
  const map=$('scenarioLocationMap'),width=map.clientWidth,height=map.clientHeight,center=projectLocation(locationMapCenter.lat,locationMapCenter.lon);
  if(!width||!height)return;
  const left=center.x-width/2,top=center.y-height/2,world=2**locationMapZoom;
  const tiles=document.createDocumentFragment();
  for(let x=Math.floor(left/256);x<=Math.floor((left+width)/256);x++)for(let y=Math.floor(top/256);y<=Math.floor((top+height)/256);y++){
    if(y<0||y>=world)continue;const tile=document.createElement('img');tile.alt='';tile.draggable=false;
    tile.src=`https://tile.openstreetmap.org/${locationMapZoom}/${((x%world)+world)%world}/${y}.png`;
    tile.style.cssText=`left:${x*256-left}px;top:${y*256-top}px;width:256px;height:256px;`;tiles.append(tile);
  }
  if(locationBounds){const nw=projectLocation(locationBounds.north,locationBounds.west),se=projectLocation(locationBounds.south,locationBounds.east),box=document.createElement('div');box.className='photo-footprint';box.style.cssText=`left:${nw.x-left}px;top:${nw.y-top}px;width:${se.x-nw.x}px;height:${se.y-nw.y}px;`;tiles.append(box);}
  const pin=projectLocation(locationChoice.lat,locationChoice.lon),marker=document.createElement('span');marker.className='location-pin';marker.style.cssText=`left:${pin.x-left}px;top:${pin.y-top}px;`;marker.setAttribute('aria-hidden','true');tiles.append(marker);
  const attribution=document.createElement('a');attribution.className='map-attribution';attribution.href='https://www.openstreetmap.org/copyright';attribution.target='_blank';attribution.rel='noopener';attribution.textContent='© OpenStreetMap contributors';attribution.onclick=event=>event.stopPropagation();tiles.append(attribution);
  map.replaceChildren(tiles);$('locationPinCoordinates').textContent=`Selected pin: ${locationChoice.lat.toFixed(6)}, ${locationChoice.lon.toFixed(6)}`;
}
function choosePhotoLocation(place,bounds=null,confirmed=false){
  locationChoice={lat:Number(place.lat),lon:Number(place.lon)};locationConfirmed=confirmed;
  locationMapCenter={...locationChoice};locationBounds=bounds;$('scenarioLocation').value=locationChoice.lat.toFixed(6)+', '+locationChoice.lon.toFixed(6);
  $('locationMapPanel').hidden=false;$('locationConfirmation').textContent=confirmed?'Photo location confirmed.':'Check the pin, then confirm this is where the photo was taken.';
  $('scenarioPlan').disabled=scenarioBusy||!confirmed;requestAnimationFrame(drawLocationMap);
}
function renderDetectedLocation(match){
  locationChoice=null;locationConfirmed=false;$('locationMapPanel').hidden=true;$('scenarioPlan').disabled=true;
  const labels={exact_file:'Exact match to a registered photo',exact_pixels:'Exact image-content match',visual_copy:'Likely match to a resized or recompressed photo',possible:'Possible visual match — not verified',photo_gps:'GPS metadata found',address_search:'Address search result',none:'No reliable photo match'};
  $('photoMatchStatus').textContent=(labels[match.method]||'Location suggestion')+'. '+(match.note||'');
  const candidates=$('photoMatchCandidates');candidates.replaceChildren();
  for(const candidate of match.candidates||[]){
    const button=document.createElement('button');button.className='location-candidate';
    if(candidate.image_id){const image=document.createElement('img');image.src='/api/location-reference?id='+encodeURIComponent(candidate.image_id);image.alt='Registered reference photo';button.append(image);}
    const label=document.createElement('span');label.textContent=(candidate.locality||candidate.label||'Location suggestion')+(candidate.acquisition_date?' · '+candidate.acquisition_date:'')+' · '+Number(candidate.lat).toFixed(5)+', '+Number(candidate.lon).toFixed(5);button.append(label);
    button.onclick=()=>choosePhotoLocation(candidate,candidate.bounds||null);candidates.append(button);
  }
  if(match.suggested)choosePhotoLocation(match.suggested,match.suggested.bounds||null);
}
function restorePhotoLocation(record){
  if(locationForScenario===record.id)return;locationForScenario=record.id;
  if(record.location_match)renderDetectedLocation(record.location_match);
  else if(record.gps)renderDetectedLocation({method:'photo_gps',suggested:record.gps,candidates:[{...record.gps,label:'Photo GPS metadata'}],note:'Verify these coordinates on the map.'});
  else $('photoMatchStatus').textContent='Choose Locate from photo to look for a registered image match, or enter an address.';
  if(record.confirmed_location)choosePhotoLocation(record.confirmed_location,null,true);
}
$('scenarioLocate').onclick=async()=>{
  try{if(!activeScenario)throw Error('Generate a preview first.');$('photoMatchStatus').textContent='Checking the registered photo collection…';const match=await api('/api/scenarios/'+activeScenario+'/locate',{});locationConfirmed=false;$('scenarioPlan').disabled=true;renderDetectedLocation(match);}
  catch(e){$('photoMatchStatus').textContent=e.message;}
};
$('scenarioResolve').onclick=async()=>{
  try{if(!activeScenario)throw Error('Generate a preview first.');const query=$('scenarioLocation').value.trim();if(!query)throw Error('Enter an address or coordinates.');const match=await api('/api/scenarios/'+activeScenario+'/locate',{query});locationConfirmed=false;renderDetectedLocation(match);}
  catch(e){$('locationConfirmation').textContent=e.message;}
};
$('scenarioLocation').addEventListener('input',()=>{locationChoice=null;locationConfirmed=false;$('locationMapPanel').hidden=true;$('scenarioPlan').disabled=true;$('locationConfirmation').textContent='Location edited. Choose Show on map, then confirm the pin.';});
$('scenarioLocationMap').onclick=event=>{
  if(scenarioBusy||!locationMapCenter)return;const rect=$('scenarioLocationMap').getBoundingClientRect(),center=projectLocation(locationMapCenter.lat,locationMapCenter.lon);
  locationChoice=unprojectLocation(center.x+event.clientX-rect.left-rect.width/2,center.y+event.clientY-rect.top-rect.height/2);locationConfirmed=false;
  $('scenarioLocation').value=locationChoice.lat.toFixed(6)+', '+locationChoice.lon.toFixed(6);$('scenarioPlan').disabled=true;$('locationConfirmation').textContent='Pin moved. Confirm this is the photo location.';drawLocationMap();
};
$('scenarioLocationMap').onkeydown=event=>{
  const moves={ArrowLeft:[-12,0],ArrowRight:[12,0],ArrowUp:[0,-12],ArrowDown:[0,12]};
  if(!moves[event.key]||!locationChoice||scenarioBusy)return;event.preventDefault();const pixel=projectLocation(locationChoice.lat,locationChoice.lon),move=moves[event.key];locationChoice=unprojectLocation(pixel.x+move[0],pixel.y+move[1]);locationMapCenter={...locationChoice};locationConfirmed=false;$('scenarioPlan').disabled=true;$('scenarioLocation').value=locationChoice.lat.toFixed(6)+', '+locationChoice.lon.toFixed(6);$('locationConfirmation').textContent='Pin moved. Confirm this is the photo location.';drawLocationMap();
};
for(const [id,delta] of [['locationZoomIn',1],['locationZoomOut',-1]])$(id).onclick=()=>{locationMapZoom=Math.max(4,Math.min(19,locationMapZoom+delta));if(locationChoice)locationMapCenter={...locationChoice};drawLocationMap();};
$('scenarioConfirmLocation').onclick=async()=>{
  try{if(!activeScenario||!locationChoice)throw Error('Choose a location on the map first.');const confirmed=await api('/api/scenarios/'+activeScenario+'/confirm-location',locationChoice);locationConfirmed=true;$('locationConfirmation').textContent='Photo location confirmed.';$('scenarioPlan').disabled=scenarioBusy;}
  catch(e){locationConfirmed=false;$('scenarioPlan').disabled=true;$('locationConfirmation').textContent=e.message;}
};
$('scenarioUseLocation').onclick=()=>{
  if(!navigator.geolocation){$('scenarioPlanStatus').textContent='Location access is unavailable. Enter an address or coordinates.';return;}
  navigator.geolocation.getCurrentPosition(position=>{choosePhotoLocation({lat:position.coords.latitude,lon:position.coords.longitude});$('locationConfirmation').textContent='Device location added. Confirm the photo was taken here.';},()=>{$('scenarioPlanStatus').textContent='Location access was unavailable. Enter the photo location manually.';},{timeout:10000});
};
new ResizeObserver(()=>{if(locationChoice)drawLocationMap();}).observe($('scenarioLocationMap'));

let renderedPhotoAnalysis=null,activePhotoFeature=null;
function clearPhotoAnalysis(){renderedPhotoAnalysis=null;activePhotoFeature=null;$('sceneMarkers').replaceChildren();$('sceneTooltip').hidden=true;$('analysisExplanation').replaceChildren();$('analysisFeatures').replaceChildren();$('analysisStatus').textContent='Qwen’s review will appear here automatically.';}
function closePhotoFeature(){
  $('sceneTooltip').hidden=true;activePhotoFeature=null;
  for(const marker of $('sceneMarkers').querySelectorAll('button'))marker.setAttribute('aria-expanded','false');
}
function showPhotoFeature(feature,index,marker){
  activePhotoFeature=index;
  for(const button of $('sceneMarkers').querySelectorAll('button'))button.setAttribute('aria-expanded',String(button===marker));
  const panel=$('sceneTooltip');panel.replaceChildren();
  const heading=document.createElement('strong');heading.textContent=feature.title;
  const close=document.createElement('button');close.textContent='×';close.className='tooltip-close';close.setAttribute('aria-label','Close feature details');close.onclick=closePhotoFeature;
  const label=document.createElement('p');label.className='helper';label.textContent=feature.kind==='hazard'?'Visible hazard to check':'Unverified photo feature';
  panel.append(close,heading,label);
  for(const [title,key] of [['Visible evidence','visible_evidence'],['Why it matters','why_it_matters'],['Access checks','access_checks']]){
    const paragraph=document.createElement('p'),bold=document.createElement('b');bold.textContent=title+': ';paragraph.append(bold,document.createTextNode(feature[key]));panel.append(paragraph);
  }
  const access=document.createElement('button');access.textContent='Check location and mapped access';access.onclick=()=>{closePhotoFeature();document.querySelector('.scenario-destinations').scrollIntoView({behavior:'smooth',block:'start'});$('scenarioLocation').focus({preventScroll:true});};panel.append(access);
  panel.hidden=false;
  const viewer=$('sceneViewer'),markerRect=marker.getBoundingClientRect(),viewerRect=viewer.getBoundingClientRect();
  const width=Math.min(330,viewer.clientWidth-16);panel.style.width=width+'px';
  panel.style.left=Math.max(8,Math.min(viewer.clientWidth-width-8,markerRect.left-viewerRect.left-30))+'px';
  panel.style.top=Math.max(8,Math.min(viewer.clientHeight-panel.offsetHeight-8,markerRect.bottom-viewerRect.top+10))+'px';
}
function renderPhotoAnalysis(record){
  const analysis=record.photo_analysis,key=record.id+':'+(analysis?.status||record.stage||'pending');
  if(renderedPhotoAnalysis===key)return;renderedPhotoAnalysis=key;closePhotoFeature();
  $('sceneMarkers').replaceChildren();$('analysisExplanation').replaceChildren();$('analysisFeatures').replaceChildren();
  if(!analysis){$('analysisStatus').textContent=record.generated_url?'This older preview has no automatic photo review. Generate a new preview to include it.':'Waiting for analysis of the generated flooded view…';return;}
  if(analysis.status!=='ready'){$('analysisStatus').textContent='The automatic photo review could not be completed: '+(analysis.error||'No structured response.');return;}
  if(analysis.basis!=='generated_flood_image'){$('analysisStatus').textContent='This saved review used the original photo. Generate a new flooded view to analyze its simulated flooding.';return;}
  $('analysisStatus').textContent='Automatic analysis of the generated flood image · simulated impacts and visible structures';
  for(const [title,text] of [['',analysis.summary],['Flood scenario',analysis.explanation],['What remains unknown',analysis.limitations]]){
    const paragraph=document.createElement('p');if(title){const bold=document.createElement('b');bold.textContent=title+': ';paragraph.append(bold);}paragraph.append(document.createTextNode(text));$('analysisExplanation').append(paragraph);
  }
  if(!analysis.features.length){const note=document.createElement('p');note.className='helper';note.textContent='Qwen could not identify a specific feature to annotate reliably. No markers have been added.';$('analysisFeatures').append(note);}
  analysis.features.forEach((feature,index)=>{
    const marker=document.createElement('button');marker.type='button';marker.className='scene-marker'+(feature.kind==='hazard'?' hazard-marker':'');marker.textContent='i';marker.style.left=(feature.x*100)+'%';marker.style.top=(feature.y*100)+'%';marker.setAttribute('aria-label','Photo feature '+(index+1)+': '+feature.title);marker.setAttribute('aria-expanded','false');marker.setAttribute('aria-controls','sceneTooltip');marker.tabIndex=feature.x*100>=Number($('scenarioSwipe').value)?0:-1;
    marker.onmouseenter=()=>showPhotoFeature(feature,index,marker);marker.onfocus=()=>showPhotoFeature(feature,index,marker);marker.onclick=()=>showPhotoFeature(feature,index,marker);$('sceneMarkers').append(marker);
    const card=document.createElement('article');card.className='photo-feature';const title=document.createElement('h3');title.textContent=(index+1)+'. '+feature.title;card.append(title);
    for(const [label,key] of [['Observed','visible_evidence'],['Relevance','why_it_matters'],['Access to verify','access_checks']]){const p=document.createElement('p'),b=document.createElement('b');b.textContent=label+': ';p.append(b,document.createTextNode(feature[key]));card.append(p);}$('analysisFeatures').append(card);
  });
}
$('sceneViewer').addEventListener('keydown',event=>{if(event.key==='Escape')closePhotoFeature();});
$('sceneViewer').addEventListener('mouseleave',()=>{if(!document.activeElement?.classList.contains('scene-marker'))closePhotoFeature();});
$('scenarioSwipe').addEventListener('input',()=>{closePhotoFeature();for(const marker of $('sceneMarkers').querySelectorAll('button'))marker.tabIndex=parseFloat(marker.style.left)>=Number($('scenarioSwipe').value)?0:-1;});
window.addEventListener('resize',closePhotoFeature);
