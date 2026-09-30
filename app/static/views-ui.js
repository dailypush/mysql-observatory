// View studio uses catalog capabilities and live metadata; it never accepts raw SQL.
async function loadViewStudio() {
  const epoch=state.epoch;
  $('#lab-content').innerHTML='<div class="loading"><span class="spinner"></span>Discovering demo views…</div>';
  try {
    const result=await api('/api/views');
    if(epoch!==state.epoch)return;
    state.viewCatalog=result.data;
    await loadSelectedView(state.viewName||'customer_profiles');
  } catch(e){if(epoch===state.epoch){error(e.message);$('#lab-content').innerHTML='<div class="empty-state">Could not load the view catalog.<button id="retry-views" class="text-button">Try again →</button></div>';$('#retry-views').onclick=loadViewStudio;}}
}
async function loadSelectedView(name) {
  const epoch=state.epoch;
  const sequence=state.viewSequence=(state.viewSequence||0)+1;
  error('');
  $('#lab-content').innerHTML='<div class="loading"><span class="spinner"></span>Reading view definition and metadata…</div>';
  try {
    const result=await api(`/api/views/${encodeURIComponent(name)}`);
    if(epoch!==state.epoch||sequence!==state.viewSequence)return;
    state.view=result.data;state.viewName=name;state.viewReceipt=null;
    renderViewStudio();record(result,`/api/views/${name}`);
  }catch(e){if(epoch===state.epoch&&sequence===state.viewSequence){error(e.message);$('#lab-content').innerHTML='<div class="empty-state">Could not inspect this view.<button id="retry-view" class="text-button">Try again →</button></div>';$('#retry-view').onclick=()=>loadSelectedView(name);}}
}
function viewTable(rows) {
  if(!rows.length)return '<p class="description">No rows yet.</p>';
  const keys=Object.keys(rows[0]);
  return `<div class="table-scroll"><table class="row-table"><thead><tr>${keys.map(k=>`<th>${escapeHTML(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${keys.map(k=>`<td>${escapeHTML(row[k]??'NULL')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function renderViewStudio() {
  const v=state.view;
  const formFields=v.kind==='sql'?v.columns.map(column=>{
    const name=column.name;
    const attrs=`id="view-field-${escapeHTML(name)}" name="${escapeHTML(name)}" ${column.nullable==='NO'?'required':''}`;
    return `<div class="field"><label for="view-field-${escapeHTML(name)}">${escapeHTML(name)} <span class="muted">· ${escapeHTML(column.type)}</span></label>${name==='tier'?`<select ${attrs}>${['Explorer','Plus','Pro'].map(t=>`<option>${t}</option>`).join('')}</select>`:`<input ${attrs} type="${column.type==='int'?'number':name==='email'?'email':'text'}" ${column.type==='int'?'min="1" max="2147483647" step="1"':''} ${column.max_length?`maxlength="${column.max_length}"`:''} value="${escapeHTML(v.template[name])}">`}</div>`;
  }).join(''):'';
  $('#lab-content').innerHTML=`<h3 class="section-title">From view to new data.</h3><p class="description">Choose a database view. The input adapts to its contract.</p><div class="field"><label for="view-selector">Database view</label><select id="view-selector">${state.viewCatalog.map(entry=>`<option value="${escapeHTML(entry.name)}" ${entry.name===v.name?'selected':''}>${escapeHTML(entry.title)}</option>`).join('')}</select></div><div class="view-badges"><span class="small-pill">${v.kind==='json_duality'?'JSON DUALITY':v.kind==='aggregate'?'AGGREGATE SQL':'SQL VIEW'}</span><span class="small-pill ${v.insertable?'writable':'readonly'}">${v.insertable?'INSERT ENABLED':'READ ONLY'}</span></div><p class="description">${escapeHTML(v.description)}</p><p class="view-availability">${escapeHTML(v.availability)}</p><details class="plan-detail"><summary>View definition · live SHOW CREATE VIEW</summary><pre class="code-block">${escapeHTML(v.definition)}</pre></details>${v.insertable?`<form id="view-insert-form">${v.kind==='json_duality'?`<label class="editor-label" for="view-json">New customer + addresses <span>JSON · EDITABLE</span></label><textarea id="view-json" class="json-editor view-json" spellcheck="false" aria-label="New customer and addresses JSON">${escapeHTML(pretty(v.template))}</textarea>`:`<p class="description">Form fields discovered from INFORMATION_SCHEMA.COLUMNS.</p><div class="field-grid">${formFields}</div>`}<p class="view-id-note">${escapeHTML(v.id_note)}</p><div class="action-row"><button class="primary" id="insert-view">Insert through view ↗</button><button type="button" class="text-button" id="fresh-view-example">New example ↻</button></div></form><div id="view-receipt" aria-live="polite"></div>`:'<div class="change-note">This view groups multiple customers into counts. MySQL cannot map a new aggregate row back to a single customer, so insertion is unavailable. Choose one of the writable views above.</div>'}<div class="relational-proof"><div class="editor-label">LIVE VIEW DATA <span>${escapeHTML(v.name)} · up to 5 rows</span></div><div id="view-sample">${v.kind==='json_duality'?`<pre class="code-block view-preview">${escapeHTML(pretty(v.rows))}</pre>`:viewTable(v.rows)}</div><button class="text-button" id="refresh-view-data">Refresh view data ↻</button></div>`;
  $('#view-selector').onchange=e=>loadSelectedView(e.target.value);
  $('#refresh-view-data').onclick=refreshViewData;
  if(v.insertable){$('#view-insert-form').onsubmit=insertThroughView;$('#fresh-view-example').onclick=()=>loadSelectedView(v.name);}
}
async function refreshViewData() {
  const epoch=state.epoch, sequence=state.viewSequence, name=state.viewName;
  const button=$('#refresh-view-data');button.disabled=true;error('');
  try {
    const result=await api(`/api/views/${name}`);
    if(epoch!==state.epoch||sequence!==state.viewSequence)return;
    state.view.rows=result.data.rows;
    $('#view-sample').innerHTML=state.view.kind==='json_duality'?`<pre class="code-block view-preview">${escapeHTML(pretty(result.data.rows))}</pre>`:viewTable(result.data.rows);
    record(result,`/api/views/${name}`);
  }catch(e){if(epoch===state.epoch&&sequence===state.viewSequence)error(e.message);}finally{if(button.isConnected)button.disabled=false;}
}
async function insertThroughView(event) {
  event.preventDefault();error('');
  const epoch=state.epoch,sequence=state.viewSequence,v=state.view;
  let recordData;
  try {
    recordData=v.kind==='json_duality'?JSON.parse($('#view-json').value):Object.fromEntries(new FormData($('#view-insert-form')));
    if(v.kind==='sql') for(const column of v.columns) if(column.type==='int')recordData[column.name]=Number(recordData[column.name]);
  }catch(e){error('Enter valid JSON. Check quotes, commas, and brackets.');return;}
  const button=$('#insert-view');button.disabled=true;button.textContent='Inserting…';
  const body={record:recordData},url=`/api/views/${v.name}/rows`;
  try {
    const result=await api(url,{method:'POST',body:pretty(body)});
    if(epoch!==state.epoch||sequence!==state.viewSequence)return;
    state.viewReceipt=result.data;
    record(result,url,'POST',body,201);
    $('#view-receipt').innerHTML=`<div class="insert-success"><strong>✓ Committed ${result.data.inserted_rows} row${result.data.inserted_rows===1?'':'s'} through the view</strong><p>Read back from the underlying tables. Choose New example for another insert.</p></div>${Object.entries(result.data.base_tables).map(([table,rows])=>`<div class="relational-proof"><div class="editor-label">${escapeHTML(table)} <span>${rows.length} new row${rows.length===1?'':'s'}</span></div>${viewTable(rows)}</div>`).join('')}<details class="plan-detail"><summary>Read back through the selected view</summary><pre class="code-block">${escapeHTML(pretty(result.data.record))}</pre></details>`;
    // Refresh the preview without replacing the INSERT trace in the inspector.
    v.rows=[result.data.record,...v.rows].slice(0,5);
    $('#view-sample').innerHTML=v.kind==='json_duality'?`<pre class="code-block view-preview">${escapeHTML(pretty(v.rows))}</pre>`:viewTable(v.rows);
    button.textContent='Inserted ✓';toast('Data committed through the view.');health();
  }catch(e){if(epoch===state.epoch&&sequence===state.viewSequence){error(e.message);button.disabled=false;button.textContent='Insert through view ↗';}}
}
