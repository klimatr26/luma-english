/* Offline UI. Responses are untrusted text and are rendered using textContent. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const publicData = JSON.parse($('public-data').textContent);
  const sha = async text => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))), b => b.toString(16).padStart(2, '0')).join('');
  const notify = (message, success = false) => { $('notice').textContent = message; $('notice').className = success ? 'success' : ''; };
  if (!globalThis.crypto?.subtle) { notify('Este navegador no permite verificar los archivos. Abre la página en una versión reciente de Edge, Chrome o Firefox.'); $('case-area').hidden = true; return; }
  if (await sha(publicData.packet_source) !== publicData.packet_sha256) { notify('La integridad de las fichas no coincide. Solicita una copia nueva al coordinador.'); $('case-area').hidden = true; return; }
  const items = JSON.parse(publicData.packet_source).items;
  $('assignment').options[0].textContent = `Muestra completa · ${items.length} fichas`;
  $('assignment').options[1].textContent = `Segunda revisión · ${publicData.second_ids.length} fichas`;
  const byID = new Map(items.map(item => [item.blind_output_id, item]));
  const storageKey = 'human-review-web:' + publicData.packet_sha256;
  const today = new Date();
  const localDate = [today.getFullYear(), String(today.getMonth()+1).padStart(2,'0'), String(today.getDate()).padStart(2,'0')].join('-');
  let state = {schema_version:'human_review_web.backup/1.0', packet_sha256:publicData.packet_sha256, profile:{reviewer_id:'',review_date:localDate}, entries:[], current_id:items[0].blind_output_id};
  let assignment = 'all';
  let exportURLs = [];
  function clearExports() { exportURLs.forEach(url=>URL.revokeObjectURL(url)); exportURLs=[]; $('export-files').replaceChildren(); }
  try {
    const saved = localStorage.getItem(storageKey);
    if (saved) {
      const candidate = ReviewCore.parseJSONStrict(saved);
      const errors = ReviewCore.validateBackup(candidate, publicData.packet_sha256, [...byID.keys()]);
      if (errors.length) notify('No se cargó el respaldo del navegador porque no pasó la validación. Conserva una copia y consulta al coordinador.');
      else { state = candidate; notify('Se recuperó tu progreso guardado en este navegador.', true); }
    }
  } catch (_) { $('save-status').textContent = 'Guardado local no disponible. Descarga respaldos para conservar el progreso.'; }
  const criteria = {
    detection: ['Detección de errores', 'Omite la mayoría o inventa errores importantes.', 'Encuentra algunos, pero omite otros o incluye falsas alarmas.', 'Encuentra los errores reales sin inventar otros.', 'NA si el original es correcto o la respuesta no es evaluable.'],
    correction: ['Corrección', 'No corrige o introduce errores.', 'Corrección parcial o cambios innecesarios.', 'Corrige con cambios mínimos y un texto gramatical y coherente.', 'NA si el original es correcto o la respuesta no es evaluable.'],
    meaning_preservation: ['Conservación del significado', 'Cambia la intención o un dato central.', 'Mantiene la idea principal, pero cambia un detalle o deja ambigüedad.', 'Conserva el significado pretendido.', 'NA solo si la respuesta no es evaluable.'],
    level_appropriateness: ['Adecuación al nivel A1/A2', 'Lenguaje fuera del nivel o inadecuado.', 'Partes accesibles y otras demasiado complejas.', 'Lenguaje y explicación compatibles con el nivel y la tarea.', 'NA solo si la respuesta no es evaluable.'],
    grammatical_explanation: ['Explicación gramatical', 'Errónea, engañosa o ausente en un texto con errores.', 'Parcial, vaga o insuficiente.', 'Correcta, breve y explica la regla relevante.', 'NA en un original correcto sin explicación, o si la respuesta no es evaluable.'],
    pedagogical_clarity: ['Claridad pedagógica', 'Confunde, abruma o no ayuda a actuar.', 'Ayuda parcialmente, con ambigüedad o extensión innecesaria.', 'Clara, concreta, respetuosa y útil para aprender o actuar.', 'NA solo si la respuesta no es evaluable.'],
    clean_text_handling: ['Tratamiento del texto correcto', 'Altera el texto correcto o inventa errores.', 'Añade una edición innecesaria menor o una falsa alarma dudosa.', 'Conserva el texto correcto intacto sin inventar errores.', 'NA si el original contiene errores o la respuesta no es evaluable.']
  };
  for (const key of ReviewCore.CRITERIA) {
    const desc = criteria[key];
    const box = document.createElement('div'); box.className = 'criterion';
    const title = document.createElement('div'); title.textContent = desc[0]; title.id = 'label-' + key; title.style.fontWeight='600'; box.append(title);
    const anchors = document.createElement('p'); anchors.className='anchors'; anchors.textContent = `0 · ${desc[1]}  1 · ${desc[2]}  2 · ${desc[3]}`; box.append(anchors);
    const group = document.createElement('div'); group.className='rating'; group.setAttribute('role','radiogroup'); group.setAttribute('aria-labelledby',title.id);
    for (const value of ['0','1','2','NA']) { const label=document.createElement('label'); const input=document.createElement('input'); input.type='radio'; input.name=key; input.value=value; label.append(input, document.createTextNode(value)); group.append(label); }
    box.append(group); const hint=document.createElement('p'); hint.className='hint'; hint.textContent=desc[4]; box.append(hint); $('criteria').append(box);
  }
  function entry(id = state.current_id) {
    let found = state.entries.find(e => e.blind_output_id === id);
    if (!found) { found={blind_output_id:id, review:ReviewCore.blankReview(byID.get(id)), original_has_errors:null, completed:false}; state.entries.push(found); }
    return found;
  }
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify(state)); $('save-status').textContent='Guardado en este navegador · ' + new Date().toLocaleTimeString('es-EC',{hour:'2-digit',minute:'2-digit'}); }
    catch (_) { $('save-status').textContent='No se pudo guardar localmente. Descarga un respaldo antes de cerrar.'; }
  }
  const boolValue = value => value === 'true' ? true : value === 'false' ? false : value === 'NA' ? 'NA' : null;
  function readForm() {
    clearExports();
    const current = entry();
    current.original_has_errors = boolValue($('original').value);
    const review = current.review;
    review.reviewer_id = $('reviewer').value.trim() || null;
    review.review_date = $('review-date').value || null;
    review.response_assessable = boolValue($('assessable').value);
    review.meaning_preserved = boolValue($('meaning_preserved').value);
    review.explanations_ok = boolValue($('explanations_ok').value);
    review.verdict = $('verdict').value || null;
    review.rationale = $('rationale').value.trim() || null;
    for (const key of ReviewCore.CRITERIA) { const value = document.querySelector(`input[name="${key}"]:checked`)?.value; review[key] = value === 'NA' ? 'NA' : value === undefined ? null : Number(value); }
    current.completed=false;
    persist(); renderList(); renderProgress();
  }
  function applicability() {
    const unavailable = $('assessable').value === 'false';
    const original = $('original').value;
    for (const key of ReviewCore.CRITERIA) {
      const na = unavailable || (original === 'false' && ['detection','correction'].includes(key)) || (original === 'true' && key === 'clean_text_handling') || (original === 'false' && key === 'grammatical_explanation' && $('explanations_ok').value === 'NA');
      for (const input of document.querySelectorAll(`input[name="${key}"]`)) { input.disabled=na; if (na) input.checked=input.value==='NA'; else if (input.dataset.wasNa === 'true') input.checked=false; input.dataset.wasNa=String(na); }
    }
    for (const key of ['meaning_preserved','explanations_ok']) {
      const input=$(key);
      if (unavailable) { input.value='NA'; input.disabled=true; }
      else { input.disabled=false; if (input.dataset.wasNa==='true') input.value=''; }
      input.dataset.wasNa=String(unavailable);
    }
  }
  function activeItems() {
    let list = assignment==='second' ? items.filter(i=>publicData.second_ids.includes(i.blind_output_id)) : items;
    const query=$('search').value.toLocaleLowerCase();
    return list.filter(i=>($('level').value==='all'||i.level===$('level').value) && ($('status-filter').value==='all'||Boolean(state.entries.find(e=>e.blind_output_id===i.blind_output_id)?.completed)===($('status-filter').value==='completed')) && (!query || [i.blind_output_id,i.student_text,i.task].join(' ').toLocaleLowerCase().includes(query)));
  }
  function renderProgress() {
    const selected = assignment==='second' ? publicData.second_ids : [...byID.keys()];
    const done = state.entries.filter(e=>e.completed && selected.includes(e.blind_output_id)).length;
    $('progress').max=selected.length; $('progress').value=done; $('progress-label').textContent=`${done} de ${selected.length} evaluaciones completadas`;
  }
  function renderList() {
    const list=activeItems(); $('case-list').replaceChildren();
    for (const item of list) { const done=state.entries.find(e=>e.blind_output_id===item.blind_output_id)?.completed; const button=document.createElement('button'); button.type='button'; button.textContent=`${done?'✓':'○'} ${item.level} · ${items.indexOf(item)+1} · ${item.blind_output_id.slice(-6)}`; button.className=(item.blind_output_id===state.current_id?'active ':'')+(done?'done':''); button.setAttribute('aria-current',item.blind_output_id===state.current_id?'true':'false'); button.onclick=()=>show(item.blind_output_id); $('case-list').append(button); }
    const index=list.findIndex(i=>i.blind_output_id===state.current_id);
    $('previous').disabled=index<=0; $('next').disabled=index<0||index===list.length-1;
  }
  function show(id) {
    state.current_id=id; const item=byID.get(id); const current=entry(id); const review=current.review;
    $('empty').hidden=true; $('case-area').hidden=false;
    $('badge').textContent=item.level; $('position').textContent=`Ficha ${items.indexOf(item)+1} · ${id}${current.completed?' · completada':' · borrador'}`;
    $('task').textContent=item.task; $('student').textContent=item.student_text; $('response').textContent=item.response_text;
    $('original').value=typeof current.original_has_errors==='boolean'?String(current.original_has_errors):'';
    $('assessable').value=typeof review.response_assessable==='boolean'?String(review.response_assessable):'';
    for (const key of ['meaning_preserved','explanations_ok']) { $(key).value=review[key]===null?'':String(review[key]); $(key).disabled=false; delete $(key).dataset.wasNa; }
    $('verdict').value=review.verdict||''; $('rationale').value=review.rationale||'';
    for (const key of ReviewCore.CRITERIA) for (const input of document.querySelectorAll(`input[name="${key}"]`)) { input.checked=review[key]!==null&&input.value===String(review[key]); input.disabled=false; delete input.dataset.wasNa; }
    // Filled records retain their own reviewer/date when reopened.
    $('reviewer').value=review.reviewer_id??state.profile.reviewer_id; $('review-date').value=review.review_date??state.profile.review_date;
    applicability(); $('errors').replaceChildren(); renderList(); renderProgress(); persist();
  }
  function applyFilter() { renderList(); renderProgress(); const list=activeItems(); if(!list.length){$('case-area').hidden=true;$('empty').hidden=false;}else if(!list.some(i=>i.blind_output_id===state.current_id))show(list[0].blind_output_id);else{$('case-area').hidden=false;$('empty').hidden=true;} }
  const showErrors = errors => { $('errors').replaceChildren(); const ul=document.createElement('ul'); for (const message of errors){const li=document.createElement('li');li.textContent=message;ul.append(li);} $('errors').append(ul); $('errors').scrollIntoView({behavior:'smooth',block:'center'}); };
  $('review-form').addEventListener('input', event=> { if (['original','assessable','explanations_ok'].includes(event.target.id)) applicability(); readForm(); });
  for (const id of ['reviewer','review-date']) $(id).addEventListener('input',()=>{state.profile.reviewer_id=$('reviewer').value.trim();state.profile.review_date=$('review-date').value;readForm();});
  $('review-form').addEventListener('submit', event=> { event.preventDefault(); readForm(); const current=entry();const errors=ReviewCore.validateReview(current.review,current.original_has_errors);if(errors.length){showErrors(errors);return;}current.completed=true;persist();renderProgress();renderList();const list=activeItems();const index=list.findIndex(i=>i.blind_output_id===state.current_id);const next=list.slice(Math.max(0,index+1)).find(i=>!state.entries.find(e=>e.blind_output_id===i.blind_output_id)?.completed)||list.find(i=>!state.entries.find(e=>e.blind_output_id===i.blind_output_id)?.completed);if(next)show(next.blind_output_id);else{$('position').textContent+=' · completada';$('errors').replaceChildren();}notify('Evaluación completada y guardada.',true); });
  for(const id of ['level','status-filter','search'])$(id).addEventListener('input',applyFilter);
  $('assignment').addEventListener('change',()=>{assignment=$('assignment').value;clearExports();applyFilter();});
  for(const [id,delta]of[['previous',-1],['next',1]])$(id).onclick=()=>{const list=activeItems();const next=list[list.findIndex(i=>i.blind_output_id===state.current_id)+delta];if(next)show(next.blind_output_id);};
  function download(filename, text, type) { const url=URL.createObjectURL(new Blob([text],{type})); const link=document.createElement('a');link.href=url;link.download=filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000); }
  $('backup').onclick=()=>{persist();download('respaldo_revision_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json',JSON.stringify(state,null,2)+'\n','application/json');notify('Respaldo descargado. Contiene también tus borradores.',true);};
  $('restore').onchange=async event=>{const file=event.target.files[0];if(!file)return;try{if(file.size>10*1024*1024)throw Error('El respaldo excede el tamaño permitido.');const data=ReviewCore.parseJSONStrict(await file.text());const errors=ReviewCore.validateBackup(data,publicData.packet_sha256,[...byID.keys()]);if(errors.length)throw Error(errors.join(' '));if(state.entries.some(e=>e.completed||e.review.rationale||e.review.response_assessable!==null)&&!confirm('Restaurar sustituirá el progreso de este navegador. Descarga un respaldo antes si necesitas conservarlo. ¿Restaurar?'))return;clearExports();state=data;show(state.current_id&&byID.has(state.current_id)?state.current_id:items[0].blind_output_id);notify('Respaldo restaurado y validado.',true);}catch(error){notify('No se restauró: '+error.message);}finally{event.target.value='';}};
  $('export').onclick = async () => {
    try {
      const selected = assignment === 'second' ? state.entries.filter(e=>publicData.second_ids.includes(e.blind_output_id)) : state.entries;
      const result = ReviewCore.serializeCompletedReviews(selected);
      if (!result.records.length) { notify('Todavía no hay evaluaciones completadas. Guarda una ficha completa antes de exportar.'); return; }
      const now = new Date().toISOString();
      const filename = 'evaluaciones_' + now.replace(/[:.]/g,'-') + '.jsonl';
      const metadata = {
        schema_version:'human_review_web.export/1.0', packet_sha256:publicData.packet_sha256,
        reviews_sha256:await sha(result.text), reviews_filename:filename,
        reviews_byte_count:new TextEncoder().encode(result.text).length, record_count:result.records.length,
        exported_at:now, original_judgments:selected.filter(e=>e.completed).map(e=>({blind_output_id:e.blind_output_id,original_has_errors:e.original_has_errors}))
      };
      clearExports();
      for (const [name,content,type,label] of [
        [filename,result.text,'application/x-ndjson','1. Descargar notas JSONL'],
        [filename.replace('.jsonl','.metadata.json'),JSON.stringify(metadata,null,2)+'\n','application/json','2. Descargar metadatos JSON']
      ]) {
        const link = document.createElement('a');
        const url = URL.createObjectURL(new Blob([content],{type})); exportURLs.push(url);
        link.href=url; link.download=name; link.textContent=label; link.className='file-button';
        $('export-files').append(link);
      }
      notify(`Preparadas ${result.records.length} evaluaciones. Descarga ambos archivos con los enlaces de «Guardar y entregar». Los borradores quedan fuera.`,true);
    } catch (error) { notify('No se exportó: '+error.message); }
  };
  show(byID.has(state.current_id)?state.current_id:items[0].blind_output_id);
})();
