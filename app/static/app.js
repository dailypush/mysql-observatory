const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const escapeHTML = (s) => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pretty = (obj) => JSON.stringify(obj, null, 2);
const state = {lab:'documents', mode:'modern', inspect:'sql', customer:null, last:null, request:null, epoch:0, search:'weekend outdoor adventure', benchmark:null};
let toastTimer;
function toast(message) { $('#toast').textContent = message; $('#toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').hidden=true,3500); }
function error(message) { $('#error-banner').textContent=message; $('#error-banner').hidden=!message; }
async function api(url, options={}) {
  const res = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}
async function health() {
  try {
    const info = await api('/api/health');
    $('#db-version').textContent=`MySQL ${info.version}`;
    $('#db-edition').textContent='Connected';
    $('#connection-dot').classList.add('connected');
    $('#customer-count').textContent=info.customers.toLocaleString();
    $('#order-count').textContent=info.orders.toLocaleString();
    $('#vector-count').textContent=info.products;
  } catch(e) {
    $('#db-version').textContent='Database unavailable';
    $('#db-edition').textContent='Retry with refresh';
    $('#connection-dot').classList.remove('connected');
    error(e.message);
  }
}
function record(data,url,method='GET',body=null) { state.last=data; state.request={method,path:url,...(body?{body}: {})}; renderInspector(); }
const changes = {
  documents:{before:['Fields and mapping','The frontend edits a form. The API maps a relational row to a document and issues a column-based UPDATE.'],after:['A document-shaped contract','The frontend edits JSON. A JSON duality view exposes relational fields as one document and translates a document UPDATE back to the underlying table.'],note:'Duality-view writes became available in Community in MySQL 9.7. This focused example uses one base table; duality views can also model related tables.',url:'https://dev.mysql.com/doc/refman/9.7/en/create-json-duality-view.html'},
  vectors:{before:['Exact phrase search','A LIKE query matches a literal phrase in product names or descriptions. A related idea may return no results.'],after:['Rank by shared features','MySQL stores typed VECTOR(6) values. The API reads them with VECTOR_TO_STRING and ranks products using cosine similarity in Python.'],note:'These are hand-authored feature vectors, not AI embeddings. Community does not include DISTANCE() or native vector indexing. No cloud or model API is called.',url:'https://dev.mysql.com/doc/refman/9.7/en/vector-functions.html'},
  optimizer:{before:['Classic join planning','The default classic optimizer chooses an execution plan for a three-table analytical query.'],after:['An alternative join planner','MySQL 9.7 brings the hypergraph optimizer to Community. We opt in per session and compare plans, results, and five measured runs.'],note:'Both paths run on the same MySQL 9.7 server. Faster is workload-dependent; no speedup is assumed. EXPLAIN ANALYZE has been available since MySQL 8.0.18.',url:'https://blogs.oracle.com/mysql/the-hypergraph-optimizer-is-now-available-in-mysql-9-7-community-edition'}
};
function renderInspector() {
  const panel=$('#inspector-content');
  if(state.inspect==='changes') {
    const c=changes[state.lab];
    panel.innerHTML=['before','after'].map(k=>`<div class="change-item"><span>${k.toUpperCase()}</span><h4>${c[k][0]}</h4><p>${c[k][1]}</p></div>`).join('')+`<div class="change-note">${c.note} <a href="${c.url}" target="_blank" rel="noreferrer">Read the docs ↗</a></div>`;
  } else if (!state.last) {
    panel.innerHTML='<div class="empty-state">Your next interaction will appear here.<br>Real SQL. Real responses.</div>';
  } else if(state.inspect==='api') {
    panel.innerHTML=`<div class="code-head"><span>${escapeHTML(state.request.method)} ${escapeHTML(state.request.path)}</span><span>200 OK</span></div>${state.request.body?`<div class="editor-label">Request body</div><pre class="code-block">${escapeHTML(pretty(state.request.body))}</pre>`:''}<div class="editor-label">Response data</div><pre class="code-block">${escapeHTML(pretty(state.last.data))}</pre>`;
  } else {
    panel.innerHTML=state.last.trace.map((t,i)=>`<div class="code-head"><span>${String(i+1).padStart(2,'0')} / MYSQL QUERY</span><span>${t.ms.toFixed(3)} ms</span></div><pre class="code-block">${escapeHTML(t.sql)}${t.params.length?'\n\n-- Bound parameters\n'+escapeHTML(pretty(t.params)):''}</pre>`).join('');
    // Keep long mutation traces scrollable while retaining the front-end context.
    panel.style.maxHeight='440px';panel.style.overflow='auto';
  }
  if(state.inspect!=='sql'){panel.style.maxHeight='440px';panel.style.overflow='auto';}
  const n=state.last?.trace?.length||0;
  $('#trace-status').textContent=n?`${n} SQL statement${n!==1?'s':''} · ${state.last.trace.reduce((sum,t)=>sum+t.ms,0).toFixed(2)} ms total · live execution`:'Waiting for your next interaction';
}
async function selectLab(lab, scroll=false) {
  state.lab=lab;state.last=null;state.customer=null;state.epoch++;error('');
  $$('.lab-card').forEach(b=>{b.classList.toggle('selected',b.dataset.lab===lab);b.setAttribute('aria-selected',String(b.dataset.lab===lab));});
  $$('.lab-nav').forEach(b=>b.classList.toggle('active',b.dataset.lab===lab));
  $('#lab-title').textContent={documents:'JSON duality lab',vectors:'Vector discovery lab',optimizer:'Query optimizer lab'}[lab];
  $('#mode-toggle').hidden=lab==='optimizer';
  renderInspector();
  if(lab==='documents') await loadCustomer();
  if(lab==='vectors'){renderSearch();await searchProducts();}
  if(lab==='optimizer') renderOptimizer();
  if(scroll) $('.playground').scrollIntoView({behavior:'smooth',block:'start'});
}
async function loadCustomer() {
  const epoch=state.epoch;
  $('#lab-content').innerHTML='<div class="loading"><span class="spinner"></span>Reading your customer from MySQL…</div>';
  const url=`/api/customers/1?mode=${state.mode}`;
  try {
    const result=await api(url);
    if(epoch!==state.epoch)return;
    state.customer=result.data;record(result,url);renderCustomer();
  } catch(e){if(epoch===state.epoch){error(e.message);$('#lab-content').innerHTML='<div class="empty-state">Unable to load the customer.<br><button class="text-button" id="retry-customer">Try again →</button></div>';$('#retry-customer').onclick=loadCustomer;}}
}
function renderCustomer() {
  const doc=state.customer.document;
  const editable=Object.fromEntries(Object.entries(doc).filter(([k])=>k!=='_metadata'));
  const initials=doc.name.split(' ').map(s=>s[0]).slice(0,2).join('').toUpperCase();
  $('#lab-content').innerHTML=`<div class="profile-heading"><div class="profile-avatar">${escapeHTML(initials)}</div><div><h3>${escapeHTML(doc.name)}</h3><p>Customer #${String(doc._id).padStart(4,'0')} · Customer profile</p></div><span class="tier-badge">${escapeHTML(doc.tier)}</span></div><p class="description">${state.mode==='modern'?'Edit the document below. MySQL writes your changes directly<br>to the relational table through a JSON duality view.':'Edit individual fields. The backend maps each field to a column<br>and writes a traditional SQL UPDATE.'}</p><form id="profile-form">${state.mode==='modern'?`<label class="editor-label" for="json-editor">customer.document <span>JSON · EDITABLE</span></label><textarea class="json-editor" id="json-editor" spellcheck="false" aria-label="Customer JSON document">${escapeHTML(pretty(editable))}</textarea>`:`<div class="field-grid">${['name','email','city'].map(k=>`<div class="field"><label for="field-${k}">${k[0].toUpperCase()+k.slice(1)}</label><input id="field-${k}" name="${k}" value="${escapeHTML(doc[k])}" required maxlength="${k==='email'?150:k==='city'?80:100}" ${k==='email'?'type="email"':''}></div>`).join('')}<div class="field"><label for="field-tier">Tier</label><select id="field-tier" name="tier">${['Explorer','Plus','Pro'].map(t=>`<option ${doc.tier===t?'selected':''}>${t}</option>`).join('')}</select></div></div>`}<div class="action-row"><button type="submit" class="primary" id="save-document">Save changes &nbsp; ↗</button><button type="button" class="text-button" id="reload-profile">↻ &nbsp; Reload</button><span class="save-hint">Changes persist in MySQL</span></div></form><div class="relational-proof"><div class="editor-label">RELATIONAL TABLE <span>customers · live row</span></div><table class="row-table"><thead><tr><th>id</th><th>name</th><th>city</th><th>tier</th></tr></thead><tbody><tr>${['id','name','city','tier'].map(k=>`<td>${escapeHTML(state.customer.row[k])}</td>`).join('')}</tr></tbody></table></div>`;
  $('#reload-profile').onclick=()=>{error('');loadCustomer();};
  $('#profile-form').onsubmit=saveCustomer;
}
async function saveCustomer(event) {
  event.preventDefault();error('');
  const epoch=state.epoch;
  let doc;
  try {doc=state.mode==='modern'?JSON.parse($('#json-editor').value):{_id:1,...Object.fromEntries(new FormData($('#profile-form')))};}catch(e){error('This document is not valid JSON. Check quotes, commas, and brackets.');return;}
  const button=$('#save-document');button.disabled=true;button.textContent='Saving…';
  const url=`/api/customers/1?mode=${state.mode}`;
  const body={document:doc,version:state.customer.version};
  try {
    const result=await api(url,{method:'PUT',body:pretty(body)});
    if(epoch!==state.epoch)return;
    state.customer=result.data;record(result,url,'PUT',body);renderCustomer();toast('Saved to MySQL. Relational row updated.');
  }catch(e){if(epoch===state.epoch)error(e.message);}finally{if(button.isConnected){button.disabled=false;button.textContent='Save changes ↗';}}
}
function renderSearch() {
  $('#lab-content').innerHTML=`<h3 class="section-title">A better way to discover.</h3><p class="description">${state.mode==='modern'?'Search a concept and explore products ranked by shared features.':'Search for an exact phrase in product names and descriptions.'}</p><label class="search-label" for="product-query">What are you looking for?</label><form class="search-form" id="search-form"><input class="search-input" id="product-query" value="${escapeHTML(state.search)}" maxlength="200" required placeholder="Try weekend outdoor adventure"><button class="primary" id="search-button">Search ↗</button></form><div class="suggestions">${['weekend outdoor adventure','focused creative workspace','cozy home coffee'].map(q=>`<button data-query="${q}">${q}</button>`).join('')}</div><div id="search-results"></div>`;
  $('#search-form').onsubmit=e=>{e.preventDefault();searchProducts();};
  $$('[data-query]').forEach(b=>b.onclick=()=>{$('#product-query').value=b.dataset.query;searchProducts();});
}
async function searchProducts() {
  const epoch=state.epoch;
  state.search=$('#product-query').value.trim();if(!state.search){error('Enter a search phrase.');return;}
  error('');const button=$('#search-button');button.disabled=true;
  $('#search-results').innerHTML='<div class="loading"><span class="spinner"></span>Querying your product catalog…</div>';
  const url=`/api/search?q=${encodeURIComponent(state.search)}&mode=${state.mode}`;
  // Search sequence guards against responses arriving out of order.
  const searchId=state.searchId=(state.searchId||0)+1;
  try {
    const result=await api(url);
    if(epoch!==state.epoch||searchId!==state.searchId)return;
    record(result,url);const products=result.data.products;
    $('#search-results').innerHTML=`<div class="result-meta">${products.length} results · ${state.mode==='modern'?'MySQL vector storage / Python similarity ranking':'SQL exact-phrase matching'}</div>${products.length?`<div class="product-list">${products.map(p=>`<article class="product"><div class="product-top"><span class="product-icon">${{Outdoors:'△',Technology:'⌘',Home:'⌂',Wellness:'◌'}[p.category]}</span><span>${escapeHTML(p.category)}</span></div><h4>${escapeHTML(p.name)}</h4><p>${escapeHTML(p.description)}</p><div class="product-footer"><span>$${Number(p.price).toFixed(0)}</span>${p.score!==undefined?`<span class="match">${p.score.toFixed(1)}% similarity</span>`:''}</div></article>`).join('')}</div>`:`<div class="empty-state">No matches for this phrase.<br>${state.mode==='classic'?'Switch to After to search by shared features.':'Try one of the suggested phrases. This demo uses a small concept vocabulary.'}</div>`}${state.mode==='modern'?`<div class="vector-strip">QUERY VECTOR &nbsp; ${escapeHTML(pretty(result.data.query_vector))}<br>6 hand-authored features · Not AI-generated embeddings</div>`:''}`;
  } catch(e){if(epoch===state.epoch&&searchId===state.searchId){error(e.message);$('#search-results').innerHTML='<div class="empty-state">Search could not be completed. Try again.</div>';}}
  finally {if(button.isConnected&&searchId===state.searchId)button.disabled=false;}
}
function renderOptimizer() {
  $('#lab-content').innerHTML='<h3 class="section-title">Let the plans do the talking.</h3><p class="description">Compare classic and hypergraph join planning on 30,000 orders.<br>Same SQL, same server, actual measured results.</p><div class="bench-controls"><div class="field"><label for="bench-city">Customer city</label><select id="bench-city" class="bench-select">'+['Portland','Austin','Brooklyn','Seattle','Denver'].map(c=>`<option>${c}</option>`).join('')+'</select></div><div class="field"><label for="bench-status">Order status</label><select id="bench-status" class="bench-select">'+['Delivered','Processing','Shipped'].map(c=>`<option>${c}</option>`).join('')+'</select></div></div><button class="primary" id="run-benchmark">Run comparison &nbsp; ↗</button><div id="benchmark-results"><div class="empty-state" style="margin-top:20px">Two optimizers. One result set.<br>Run a comparison to see their plans and timings.</div></div>';
  $('#run-benchmark').onclick=runBenchmark;
}
async function runBenchmark() {
  const epoch=state.epoch;error('');const button=$('#run-benchmark');button.disabled=true;button.textContent='Running 12 queries + 2 plans…';
  const body={city:$('#bench-city').value,status:$('#bench-status').value};
  try {
    const result=await api('/api/benchmark',{method:'POST',body:pretty(body)});
    if(epoch!==state.epoch)return;
    record(result,'/api/benchmark','POST',body);const data=result.data;const max=Math.max(data.classic.median_ms,data.hypergraph.median_ms,0.001);
    $('#benchmark-results').innerHTML=`<div class="benchmark-results">${['classic','hypergraph'].map(k=>`<div class="timing"><span>${k==='classic'?'Classic':'Hypergraph'}</span><div class="bar-track"><div class="bar ${k==='hypergraph'?'modern':''}" style="width:${data[k].median_ms/max*100}%"></div></div><strong>${data[k].median_ms.toFixed(2)} ms</strong></div>`).join('')}<p class="benchmark-caption">Median of 5 runs after warmup · ${data.same_results?'✓ Identical results':'⚠ Results differ'}<br>${data.hypergraph.median_ms < data.classic.median_ms?'Hypergraph was faster in this run.':'Classic was faster or tied in this run.'} Results vary with data, cache, and workload.</p><table class="row-table"><thead><tr><th>category</th><th>tier</th><th>orders</th><th>revenue</th></tr></thead><tbody>${data.classic.rows.map(r=>`<tr><td>${escapeHTML(r.category)}</td><td>${escapeHTML(r.tier)}</td><td>${r.order_count}</td><td>$${Number(r.revenue).toLocaleString()}</td></tr>`).join('')}</tbody></table>${['classic','hypergraph'].map(k=>`<details class="plan-detail"><summary>${k==='classic'?'Classic':'Hypergraph'} · EXPLAIN ANALYZE</summary><pre class="code-block">${escapeHTML(data[k].plan)}</pre><p class="benchmark-caption">Samples (ms): ${data[k].samples_ms.join(', ')}</p></details>`).join('')}<p class="benchmark-caption">${escapeHTML(data.method)}</p></div>`;
  }catch(e){if(epoch===state.epoch)error(e.message);}finally{if(button.isConnected){button.disabled=false;button.textContent='Run comparison ↗';}}
}
function showDialog(type) {
  const content=type==='architecture'?`<h2>Small stack. Real capabilities.</h2><p>One Compose command starts two containers connected through a private Docker network.</p><div class="architecture-flow"><div class="arch-box"><span>▦</span><strong>Browser</strong><p>HTML, CSS, JavaScript<br>Interactive frontend</p></div><span>→</span><div class="arch-box"><span>{ }</span><strong>Application container</strong><p>Flask + Gunicorn<br>JSON API · Port 8080</p></div><span>→</span><div class="arch-box"><span>▱</span><strong>MySQL container</strong><p>MySQL 9.7.2 Community<br>Persistent named volume</p></div></div><p><strong>Documents:</strong> the API reads and writes <code>customer_documents</code>, a real JSON duality view over the <code>customers</code> table. Version checks prevent stale edits.</p><p><strong>Discovery:</strong> products have native <code>VECTOR(6)</code> columns. A transparent feature mapping and Python cosine ranking keep this demo local.</p><p><strong>Optimizer:</strong> the API toggles <code>hypergraph_optimizer</code> on its own session. Both plans execute against the same dataset and transaction.</p><p>The app is bound to localhost. MySQL has no published host port. Your data survives container restarts.</p>`:`<h2>A five-minute tour.</h2><p>Keep the backend inspector open as you explore. Its SQL and API tabs update after every interaction.</p><ol><li><strong>A document becomes a row.</strong> In JSON duality, select Before to see the traditional form. Switch to After, change the city in the JSON document, and save. Watch the relational row update and inspect the actual duality-view UPDATE.</li><li><strong>An idea becomes a discovery.</strong> Open Vector discovery. Search “weekend outdoor adventure” in Before: exact-phrase matching returns no matches. Switch to After to rank related products by shared features. Explain the native MySQL storage and application-side ranking.</li><li><strong>A query gets another plan.</strong> Open Query optimizer and run a comparison. Inspect both EXPLAIN ANALYZE trees. Change the city or status and rerun. A new optimizer can choose a different plan; it is not guaranteed to be faster.</li></ol><p><strong>Use “What changed”</strong> for talking points and links to official MySQL documentation. Before/After compares application approaches on the same current server, not two database releases.</p><p><strong>Local and repeatable.</strong> No API keys, external services, or enterprise license are required. The README includes launch, test, stop, and data-reset instructions.</p>`;
  $('#dialog-content').innerHTML=content;$('#info-dialog').showModal();
}
$$('[data-lab]').forEach(b=>b.onclick=()=>selectLab(b.dataset.lab,b.classList.contains('lab-nav')));
$$('[data-mode]').forEach(b=>b.onclick=async()=>{if(b.dataset.mode===state.mode)return;state.mode=b.dataset.mode;$$('[data-mode]').forEach(x=>x.classList.toggle('active',x===b));await selectLab(state.lab);});
$$('[data-inspect]').forEach(b=>b.onclick=()=>{state.inspect=b.dataset.inspect;$$('[data-inspect]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-selected',String(x===b));});renderInspector();});
$$('[data-nav]').forEach(b=>b.onclick=()=>{if(b.dataset.nav==='labs'){$('.labs-heading').scrollIntoView({behavior:'smooth'});}else{showDialog(b.dataset.nav);}});
$('#close-dialog').onclick=()=>$('#info-dialog').close();
$('#info-dialog').addEventListener('click',e=>{if(e.target===$('#info-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}});
$('#refresh').onclick=()=>{error('');health();};
health();selectLab('documents');
