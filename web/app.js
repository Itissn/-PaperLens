"use strict";
const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
let currentDocs=[];
let lastResult=null;
let conversationId=null;
let activeRequest=null;
let structureDoc=null;
let historyLoad=0;
function showAlert(message){$("alert").textContent=message;$("alert").hidden=false;}
function clearAlert(){$("alert").hidden=true;}
async function api(path,options={}){
  const response=await fetch(path,options);
  const data=await response.json();
  if(response.status===401 && path!=="/api/auth/login")$("login-dialog").showModal();
  if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"Invalid request. Check the question and selected options.");
  return data;
}
const post=(path,body)=>api(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
function pdfLink(hit,text){const a=node("a",text);a.href=hit.pdf_url;a.target="_blank";a.rel="noopener";return a;}
function query(){return {question:$("question").value.trim(),mode:$("mode").value,k:Number($("top-k").value),document_id:$("scope").value||null,generator:$("generator").value,rerank:$("rerank").checked,conversation_id:conversationId};}
async function refresh(){
  const [status,docs]=await Promise.all([api("/api/status"),api("/api/documents")]);currentDocs=docs;
  $("doc-count").textContent=docs.length;
  $("stats").replaceChildren();
  for(const [value,label] of [[status.documents,"public / imported papers"],[status.chunks,"page-linked chunks"],[status.embedded_chunks,"neural embeddings"]]){
    const s=node("span");s.append(node("b",String(value)),document.createTextNode(label));$("stats").append(s);
  }
  $("stats").append(node("span","BGE SMALL · 384 DIM"));
  $("generator").querySelector('[value="ollama"]').disabled=!status.ollama_configured;
  $("generator").querySelector('[value="local_llm"]').disabled=!status.local_llm_configured;
  $("library").replaceChildren();
  const selected=$("scope").value;
  $("scope").replaceChildren(new Option("All papers",""));
  docs.forEach((d,i)=>{
    $("scope").add(new Option(d.title,d.id));
    const card=node("article",undefined,"doc-card");
    card.append(node("h3",d.title),node("p",d.status),node("p",d.pages+" pages · "+d.chunks+" chunks"));
    const links=node("div",undefined,"doc-links");
    links.append(pdfLink({pdf_url:"/api/documents/"+d.id+"/pdf"},"Open PDF ↗"));
    const inspect=node("button","Inspect chunks");inspect.type="button";inspect.onclick=()=>inspectDoc(d.id);links.append(inspect);const structure=node("button","Inspect page");structure.type="button";structure.onclick=()=>openStructure(d);links.append(structure);card.append(links);$("library").append(card);
  });
  $("scope").value=docs.some(d=>d.id===selected)?selected:"";
}
async function inspectDoc(id){
  try{
    const rows=await api("/api/documents/"+id+"/chunks");$("chunk-list").replaceChildren();
    rows.forEach(c=>{const item=node("article",undefined,"chunk-item");item.append(node("small","PDF page "+c.page+" · Chunk "+c.position),node("p",c.text));$("chunk-list").append(item);});
    $("chunk-dialog").showModal();
  }catch(e){showAlert(e.message);}
}
$("close-dialog").onclick=()=>$("chunk-dialog").close();
document.querySelectorAll("[data-panel]").forEach(button=>button.onclick=()=>{
  document.querySelectorAll(".panel").forEach(p=>p.hidden=p.id!==button.dataset.panel);
  document.querySelectorAll(".nav").forEach(b=>b.classList.toggle("active",b===button));
  if(button.dataset.panel==="evaluation")loadEvaluation();
});
document.querySelectorAll("[data-question]").forEach(b=>b.onclick=()=>{$("question").value=b.dataset.question;$("question").focus();});
$("mode").onchange=()=>{
 $("mode-help").textContent={hybrid:"BM25 and semantic vectors, combined with reciprocal rank fusion.",semantic:"Neural embeddings ranked by cosine similarity.",lexical:"BM25 keyword search for names and exact terminology."}[$("mode").value];
};
$("query-form").onsubmit=async e=>{
 e.preventDefault();if(activeRequest)return;
 clearAlert();$("ask").disabled=true;$("stop-request").hidden=false;
 $("ask").textContent="Working…";$("live-progress").hidden=false;$("progress-title").textContent="Starting research…";$("progress-detail").textContent="";$("draft-panel").hidden=true;$("export-result").disabled=true;
 activeRequest=new AbortController();
 try{
   const submitted=query();
   const response=await fetch($("workflow").value==="agent"?"/api/agent/stream":"/api/ask/stream",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(submitted),signal:activeRequest.signal});
   if(!response.ok){const error=await response.json();if(response.status===401)$("login-dialog").showModal();throw new Error(error.detail||"Research request failed.");}
   const reader=response.body.getReader();const decoder=new TextDecoder();let buffer="",terminal=false;
   while(true){
     const {value,done}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});
     let boundary;
     while((boundary=buffer.indexOf("\n\n"))>=0){
       const block=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);
       if(block.startsWith(":"))continue;
       const lines=block.split("\n");const name=lines.find(l=>l.startsWith("event: "))?.slice(7);
       const payload=lines.filter(l=>l.startsWith("data: ")).map(l=>l.slice(6)).join("\n");
       if(!name||!payload)continue;const data=JSON.parse(payload);
       if(name==="error"){terminal=true;throw new Error(data.message);}
       if(name==="draft"){if(data.text){$("draft-panel").hidden=false;$("draft-text").textContent=data.text;}continue;}
       if(name==="result"){
         terminal=true;conversationId=data.conversation_id;lastResult={query:submitted,response:data};
         $("draft-panel").hidden=true;$("progress-title").textContent=data.status==="abstained"?"Evidence review complete · answer withheld":"Research complete";
         $("progress-detail").textContent="Final result saved to this conversation.";$("export-result").disabled=false;
         renderAnswer(data);$("results").hidden=false;$("empty-state").hidden=true;await refreshHistory();await showTurns(conversationId,false);continue;
       }
       const labels={started:"Research started",retrieval:"Searching papers",evidence:"Evidence retrieved",planning:"Planning the next tool call",tool_start:"Running a tool",tool_end:"Tool completed",generation_start:"Generating a draft",repair:"Checking requested items",validation:"Validating the answer",verification_read:"Reading a final cited page"};
       $("progress-title").textContent=labels[name]||"Working…";
       $("progress-detail").textContent=data.message||data.tool||(name==="planning"?"Round "+data.round+" of "+data.limit:name==="verification_read"?"PDF page "+data.page+" · controller verification":name==="started"&&data.resolved_question!==submitted.question?"Resolved question: "+data.resolved_question:"");
     }
   }
   if(!terminal)throw new Error("The connection closed before the task finished. No complete result was received.");
 }catch(error){
   $("draft-panel").hidden=true;$("progress-title").textContent=error.name==="AbortError"?"Request cancelled":"Research interrupted";
   showAlert(error.name==="AbortError"?"Request cancelled. Partial drafts are not saved.":error.message);
 }finally{activeRequest=null;$("ask").disabled=false;$("stop-request").hidden=true;$("ask").textContent=$("workflow").value==="agent"?"Run Agent ↗":"Search & read ↗";}
};
$("stop-request").onclick=()=>activeRequest?.abort();
$("workflow").onchange=()=>{
 const agent=$("workflow").value==="agent";
 for(const id of ["mode","scope","top-k","rerank"])$(id).disabled=agent;
 if(agent){$("mode").value="hybrid";$("rerank").checked=true;$("scope").value="";$("generator").value="local_llm";}
 $("ask").textContent=agent?"Run Agent ↗":"Search & read ↗";
 if(agent)$("mode-help").textContent="The model selects read-only tools: up to 4 rounds and 6 calls.";
 else $("mode").onchange();
};
function renderAnswer(data){
 $("agent-trace").hidden=!data.agent;
 $("agent-steps").replaceChildren();
 if(data.agent){
  $("agent-summary").textContent="Tool calls: "+data.agent.tool_calls+" · Page read: "+(data.agent.page_verification?"completed":"not performed")+" · Cited pages: "+(data.agent.all_cited_pages_read?"all read":"may rely on search excerpts")+" · Stop reason: "+data.agent.stop_reason+" · Token totals include planning and final synthesis.";
  const steps=[...data.agent.trace,...(data.agent.verification_reads||[]).map((s,i)=>({step:data.agent.trace.length+i+1,tool:"read_page · controller",arguments:{document_id:s.document_id,page:s.page},result:{actor:s.actor},outcome:s.outcome,latency_ms:"—"}))];
  steps.forEach(step=>{
   const item=node("details",undefined,"agent-step");item.append(node("summary",step.step+". "+step.tool+" · "+step.outcome+" · "+step.latency_ms+" ms"),node("pre",JSON.stringify({arguments:step.arguments,result:step.result},null,2)));$("agent-steps").append(item);
  });
 }
 $("answer-title").textContent=data.generator!=="extractive"?"LLM answer":"Extractive answer";
 $("answer-status").textContent={evidence:"EXTRACTIVE",generated:"LLM",abstained:"EVIDENCE INSUFFICIENT"}[data.status];
 $("answer-notice").textContent=data.notice;
 const assessment=data.evidence_assessment||{};
 const reasons={below_reranker_cutoff:"No passage met the relevance threshold",empty_retrieval:"No retrieval results",model_declined:"The model found insufficient evidence",support_check_failed:"The generated answer failed the source checks",above_reranker_cutoff:"Relevant passages selected for the answer",legacy_overlap_heuristic:"Using the baseline term-overlap heuristic",incomplete_answer:"The draft omitted requested items",semantic_support_failed:"The draft failed semantic-support screening"};
 $("evidence-assessment").textContent=(reasons[assessment.reason]||"Evidence requires review")+(assessment.top_score!==undefined?" · Top reranker score "+assessment.top_score.toFixed(2)+" · Cutoff "+assessment.cutoff:"");
 $("evidence-assessment").classList.toggle("insufficient",data.status==="abstained");
 $("answer-content").replaceChildren();
 data.paragraphs.forEach(p=>{
  const para=node("p",p.text,"answer-paragraph");
  p.citation_ids.forEach(id=>{const h=data.citations.find(c=>c.citation_id===id);const a=pdfLink(h,"["+id+"] p."+h.page);a.className="citation";para.append(a);});
  $("answer-content").append(para);
  if(p.support_quotes?.length){
   const detail=node("details",undefined,"support-check");detail.append(node("summary","View supporting excerpts (check their meaning)"));
   p.support_quotes.forEach(q=>{const quote=node("blockquote",q.quote);const h=data.citations.find(c=>c.citation_id===q.citation_id);if(h){const a=pdfLink(h," ["+q.citation_id+"] p."+h.page);quote.append(a);}detail.append(quote);});
   $("answer-content").append(detail);
  }
 });
 if(!data.paragraphs.length)$("answer-content").append(node("p","Insufficient matching evidence. Rephrase the question or narrow the paper scope.","answer-paragraph"));
 if(data.review?.draft?.length){
   const review=node("details",undefined,"support-check");review.append(node("summary","Review withheld draft · not verified"));
   data.review.draft.forEach(p=>{review.append(node("p",p.text));p.support_quotes?.forEach(q=>{const quote=node("blockquote",q.quote),source=data.retrieval.hits.find(h=>h.citation_id===q.citation_id);if(source)quote.append(pdfLink(source," [source] p."+source.page));review.append(quote);});});$("answer-content").append(review);
 }
 $("answer-metrics").replaceChildren(node("span",(data.agent?"Tool-based research ":"Retrieval ")+data.retrieval.latency_ms+" ms"),node("span","Total "+data.total_latency_ms+" ms"),node("span","Output tokens "+(data.usage.output_tokens??"unknown")),node("span","API cost $0 · Local compute"));
 $("evidence").replaceChildren();
 data.retrieval.hits.forEach(h=>{
   const card=node("article",undefined,"evidence-card");card.append(node("div","["+h.citation_id+"]  PDF page "+h.page+"","evidence-label"),node("h4",h.title));
   card.append(node("div",h.status,"micro"));if(h.extraction_method==="ocr")card.append(node("div","OCR source · recognition score "+(h.ocr_confidence??0).toFixed(2),"micro"));
   const scores=[h.rerank_score!==undefined?"Reranker logit "+h.rerank_score:null,Number.isFinite(h.score)?"Base rank score "+h.score:null,Number.isFinite(h.lexical_score)?"BM25 "+h.lexical_score:null,Number.isFinite(h.semantic_score)?"Cosine "+h.semantic_score:null].filter(Boolean).join(" · ");
   card.append(node("div",scores,"evidence-scores"));if(h.rerank_score!==undefined&&h.rerank_score<0){card.classList.add("weak-evidence");card.append(node("div","Below the current evidence threshold","micro"));}
   const detail=node("details");detail.append(node("summary","Expand source passage"),node("p",h.text));card.append(detail,pdfLink(h,"Check source PDF ↗"));$("evidence").append(card);
 });
}
$("compare").onclick=async()=>{
 clearAlert();if(query().question.length<3){showAlert("Enter a question first.");return;}
 $("compare").disabled=true;$("compare").textContent="Comparing…";
 try{
   const modes=[{mode:"lexical",rerank:false},{mode:"semantic",rerank:false},{mode:"hybrid",rerank:false},{mode:"hybrid",rerank:true}];
   const result=await Promise.all(modes.map(settings=>post("/api/search",{...query(),...settings})));
   $("comparison-grid").replaceChildren();
   result.forEach(r=>{
     const c=node("article",undefined,"compare-column");c.append(node("h4",{lexical:"BM25",semantic:"Semantic",hybrid:"Hybrid · RRF"}[r.mode]+(r.rerank?.enabled?" + Reranker":"")),node("small",r.latency_ms+" ms"));
     r.hits.forEach((h,i)=>c.append(pdfLink(h,(i+1)+". "+h.title+" · p."+h.page)));
     if(!r.hits.length)c.append(node("p","No matching results."));$("comparison-grid").append(c);
   });$("comparison").hidden=false;$("comparison").scrollIntoView({behavior:"smooth",block:"start"});
 }catch(e){showAlert(e.message);}finally{$("compare").disabled=false;$("compare").textContent="Compare retrieval";}
};
$("pdf-upload").onchange=async()=>{
 const file=$("pdf-upload").files[0];if(!file)return;
 clearAlert();if(file.size>20*1024*1024){showAlert("PDF files must be 20 MB or smaller.");return;}
 $("pdf-upload").disabled=true;showAlert("Extracting PDF text and building embeddings…");
 try{
   const form=new FormData();form.append("file",file);form.append("ocr",String($("upload-ocr").checked));
   const r=await api("/api/documents",{method:"POST",body:form});
   showAlert(r.document.duplicate?"This PDF already exists. The index was checked; no duplicate was added.":"Paper imported. Embeddings created: "+r.embedded_chunks+".");await refresh();
 }catch(e){showAlert(e.message);await refresh();}finally{$("pdf-upload").disabled=false;$("pdf-upload").value="";}
};
$("reindex").onclick=async()=>{
 $("reindex").disabled=true;showAlert("Checking and repairing the index…");
 try{const r=await post("/api/index",{});await refresh();showAlert("Index ready. New embeddings: "+r.embedded_chunks+".");}
 catch(e){showAlert(e.message);}finally{$("reindex").disabled=false;}
};
async function loadEvaluation(){
 try{
  const r=await api("/api/evaluation");$("eval-summary").replaceChildren(node("span",r.created_date+" · "+r.answerable_cases+" answerable questions · "+r.unanswerable_cases+" unanswerable questions"),node("span","Fixed three-paper corpus · K="+r.k));
  const container=$("eval-content");container.replaceChildren(node("p",r.limitations,"notice"));
  const wrap=node("div",undefined,"table-wrap"),table=node("table"),head=node("thead"),tr=node("tr");
  ["Strategy","Hit@"+r.k,"Page Recall@"+r.k,"MRR@"+r.k,"Positive coverage","Negative refusal","Median latency"].forEach(t=>tr.append(node("th",t)));head.append(tr);table.append(head);
  const body=node("tbody");
  for(const [mode,m] of Object.entries(r.summary)){const row=node("tr");[mode,(m.hit_rate*100).toFixed(1)+"%",(m.page_recall*100).toFixed(1)+"%",m.mrr.toFixed(3),(m.positive_evidence_rate*100).toFixed(1)+"%",(m.unanswerable_abstention_rate*100).toFixed(1)+"%",m.median_latency_ms.toFixed(1)+" ms"].forEach(t=>row.append(node("td",t)));body.append(row);}
  table.append(body);wrap.append(table);container.append(wrap,node("h3","Per-question results and failure cases"));
  r.cases.forEach(c=>{const item=node("article",undefined,"eval-case");item.append(node("h4",c.id+" · "+c.question),node("p","Label rationale: "+c.evidence_note),node("p",c.answerable?"Relevant evidence pages: "+c.relevant.map(x=>x.arxiv_id+" p."+x.page).join(" / "):"No answer in this corpus; tests the refusal heuristic."));
   for(const [mode,m] of Object.entries(c.results)){item.append(node("p",mode+" · "+(c.answerable?(m.hit?"Hit":"Miss")+" · First relevant rank "+(m.first_relevant_rank??"none"):"Refused "+(m.abstained?"yes":"no"))+" · Returned pages "+m.hits.map(h=>h.arxiv_id+" p."+h.page).join(" / ")));}
   container.append(item);
  });
  const challenge=await api("/api/evaluation/challenge");
  const extra=node("section",undefined,"challenge-panel");extra.append(node("h3","Additional challenge set · "+challenge.cases.length+" questions"),node("p","Additional questions were written before testing and labelled by the same developer. This is not an independent held-out set.","notice"));
  const cm=challenge.summary.hybrid_rerank;
  extra.append(node("p","Hybrid + Reranker: Hit@5 "+(cm.hit_rate*100).toFixed(1)+"% · Positive coverage "+(cm.positive_evidence_rate*100).toFixed(1)+"% · Negative refusal "+(cm.unanswerable_abstention_rate*100).toFixed(1)+"%","notice"));
  challenge.cases.forEach(c=>{const item=node("div",undefined,"challenge-case");item.append(node("b",c.id+" · "+c.question),node("p",c.answerable?"Labelled answerable":"Labelled unanswerable in this corpus"),node("p","After reranking: "+(c.results.hybrid_rerank.abstained?"No answer evidence provided":"Answer evidence provided")));extra.append(item);});container.append(extra);
 }catch(e){$("eval-content").replaceChildren(node("p",e.message));}
}
$("export-result").onclick=()=>{
 if(!lastResult)return;
 const payload={exported_at:new Date().toISOString(),...lastResult};
 const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:"application/json"}));
 const a=node("a");a.href=url;a.download="paperlens-result.json";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
async function refreshHistory(){
 const rows=await api("/api/conversations");$("conversation-list").replaceChildren();
 rows.forEach(c=>{const item=node("div",undefined,"conversation-row"),open=node("button",c.title,"conversation-open");open.title=c.title;open.onclick=()=>showTurns(c.id,true);const remove=node("button","×","conversation-delete");remove.setAttribute("aria-label","Delete conversation "+c.title);remove.onclick=async()=>{if(activeRequest){showAlert("Stop the current request first.");return;}await api("/api/conversations/"+c.id,{method:"DELETE"});if(conversationId===c.id)newConversation();await refreshHistory();};item.append(open,remove);$("conversation-list").append(item);});
}
function newConversation(){
 if(activeRequest){showAlert("Stop the current request first.");return;}
 historyLoad++;conversationId=null;lastResult=null;$("turn-list").replaceChildren();$("turn-list").hidden=true;$("question").disabled=false;$("ask").disabled=false;$("results").hidden=true;$("empty-state").hidden=false;$("export-result").disabled=true;$("question").value="";$("live-progress").hidden=true;$("question").focus();
}
$("new-conversation").onclick=newConversation;
async function showTurns(id,openLast){
 if(activeRequest&&openLast){showAlert("Stop the current request first.");return;}
 const load=++historyLoad;$("turn-list").replaceChildren();$("ask").disabled=true;$("question").disabled=true;
 try{
  const conversation=await api("/api/conversations/"+id);if(load!==historyLoad)return;conversationId=id;$("turn-list").replaceChildren(node("h3","Conversation"));$("turn-list").hidden=false;
  conversation.turns.forEach(t=>{const b=node("button",t.question,"turn-button");b.onclick=()=>{lastResult={query:{question:t.question},response:t.response};renderAnswer(t.response);$("results").hidden=false;$("empty-state").hidden=true;$("export-result").disabled=false;};$("turn-list").append(b);});
  if(openLast&&conversation.turns.length){const t=conversation.turns.at(-1);lastResult={query:{question:t.question},response:t.response};renderAnswer(t.response);$("question").value="";$("results").hidden=false;$("empty-state").hidden=true;$("export-result").disabled=false;}
 }catch(e){showAlert(e.message);}finally{if(load===historyLoad){$("question").disabled=false;if(!activeRequest)$("ask").disabled=false;}}
}
async function openStructure(doc){
 structureDoc=doc;$("structure-page").max=doc.pages;$("structure-page").value=1;$("structure-content").replaceChildren();$("structure-dialog").showModal();await loadStructure();
}
async function loadStructure(){
 $("structure-content").replaceChildren(node("p","Inspecting PDF page…"));
 try{
  const page=Number($("structure-page").value),base="/api/documents/"+structureDoc.id+"/pages/"+page;
  const data=await api(base+"/structure?ocr="+$("structure-ocr").checked),out=$("structure-content");out.replaceChildren(node("p",data.limitations,"notice"));
  const image=node("img");image.src=base+"/image";image.alt="Source PDF page "+page;image.className="page-preview";out.append(image,node("h3","Tables · "+data.tables.length));
  data.tables.forEach(t=>{const wrap=node("div",undefined,"table-wrap"),table=node("table");t.rows.forEach(row=>{const tr=node("tr");row.forEach(cell=>tr.append(node("td",cell??"")));table.append(tr);});wrap.append(table);out.append(wrap);});
  out.append(node("h3","Formula candidates · "+data.formulas.length));
  data.formulas.forEach(f=>{const article=node("article",undefined,"formula-region");article.append(node("p",f.text));if(f.symbolic?.parsed)article.append(node("p","Parsed expression · LaTeX: "+f.symbolic.latex));else article.append(node("p","Source text only · unsupported symbolic syntax","notice"));const crop=node("img");crop.src=base+"/image?bbox="+f.bbox.join(",");crop.alt="Original formula region";crop.loading="lazy";article.append(crop);out.append(article);});
  if(data.ocr_lines.length){out.append(node("h3","OCR text"));data.ocr_lines.forEach(line=>out.append(node("p",line.text+" · score "+line.confidence.toFixed(2))));}
 }catch(e){$("structure-content").replaceChildren(node("p",e.message));}
}
$("structure-form").onsubmit=e=>{e.preventDefault();loadStructure();};$("close-structure").onclick=()=>$("structure-dialog").close();
$("login-form").onsubmit=async e=>{
 e.preventDefault();$("login-error").textContent="";
 try{await post("/api/auth/login",{username:$("login-username").value,password:$("login-password").value});$("login-password").value="";$("login-dialog").close();await boot();}catch(e){$("login-error").textContent=e.message;}
};
$("login-dialog").addEventListener("cancel",e=>e.preventDefault());
$("sign-out").onclick=async()=>{activeRequest?.abort();await post("/api/auth/logout",{});location.reload();};
async function boot(){
 try{
  const who=await api("/api/auth/me");$("identity-label").textContent=who.authentication_required?who.username+" · "+who.role:"Local workspace";
  $("sign-out").hidden=!who.authentication_required;
  $("pdf-upload").disabled=who.role!=="admin";$("reindex").hidden=who.role!=="admin";$("upload-ocr").disabled=who.role!=="admin";
  await refresh();await refreshHistory();
 }catch(e){if(!$("login-dialog").open)showAlert(e.message);}
}
boot();
