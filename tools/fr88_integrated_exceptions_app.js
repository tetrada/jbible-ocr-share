(() => {
 "use strict";
 const $ = id => document.getElementById(id);
 const text = value => value == null ? "" : String(value);
 const num = id => $(id).value.trim() === "" ? null : Number($(id).value);
 const fmt = x => typeof x==="number" ? x.toFixed(3) : "unknown";
 const clamp = (v,a,b) => Math.max(a,Math.min(b,v));
 let cases=[], reviews={}, selected=null, decision="unresolved", zoom=1.4, centerY=.5, busy=false;
 const imageCache = new Map();
 function lineDesc(c){return c.margin_text || "(unreadable)";}
 function isDone(e){return !!e && !!e.choice;}
 function visibleCases(){
   const mode=$("filter").value;
   return cases.filter(c=>mode==="all" ||
     (mode==="done" && isDone(reviews[c.edge_id])) ||
     (mode==="pending" && !isDone(reviews[c.edge_id])));
 }
 function nav(){
   const queue=$("queue");queue.replaceChildren();
   for(const c of visibleCases()){
     const b=document.createElement("button");
     b.type="button";b.className="qitem"+(selected&&c.edge_id===selected.edge_id?" active":"")+(isDone(reviews[c.edge_id])?" done":"");
     const pn=document.createElement("span");pn.className="qpage";pn.textContent="P"+c.page+" "+c.column;
     const raw=document.createElement("span");raw.className="qtitle";raw.textContent=lineDesc(c);
     const tick=document.createElement("span");tick.textContent=isDone(reviews[c.edge_id])?"✓":"○";
     b.append(pn,raw,tick);
     b.onclick=()=>show(c);
     queue.appendChild(b);
   }
   $("progress").textContent=cases.filter(c=>isDone(reviews[c.edge_id])).length+" / "+cases.length+" classified";
 }
 function imageUrl(page){return "../api/image/"+String(page).padStart(4,"0")+".jpg";}
 function getImage(page){
   if(imageCache.has(page))return imageCache.get(page);
   const value={img:new Image(),ready:false,error:false};
   imageCache.set(page,value);
   value.img.onload=()=>{value.ready=true;draw();};
   value.img.onerror=()=>{value.error=true;draw();};
   value.img.src=imageUrl(page);
   return value;
 }
 function draw(){
   const cvs=$("scan"),ctx=cvs.getContext("2d");
   ctx.fillStyle="#e4dcca";ctx.fillRect(0,0,cvs.width,cvs.height);
   if(!selected)return;
   $("zoomLabel").textContent=zoom.toFixed(2)+"×";
   const record=getImage(selected.page);
   if(!record.ready){
     ctx.fillStyle="#605748";ctx.font="22px sans-serif";
     ctx.fillText(record.error?"Scan unavailable":"Loading original scan…",40,70);
     return;
   }
   const img=record.img,w=img.naturalWidth,h=img.naturalHeight;
   const x=selected.column==="R"?Math.floor(w/2):0;
   const ww=selected.column==="R"?w-x:Math.floor(w/2);
   const hh=clamp(ww*cvs.height/cvs.width/zoom,1,h);
   const y0=clamp(centerY*h-hh/2,0,h-hh);
   ctx.drawImage(img,x,y0,ww,hh,0,0,cvs.width,cvs.height);
   function marker(y,color,label,fill=false){
     if(typeof y!=="number"||!Number.isFinite(y))return;
     const yy=(y*h-y0)/hh*cvs.height;
     if(yy<0||yy>cvs.height)return;
     ctx.strokeStyle=color;ctx.lineWidth=3;ctx.setLineDash([10,5]);
     ctx.beginPath();ctx.moveTo(0,yy);ctx.lineTo(cvs.width,yy);ctx.stroke();ctx.setLineDash([]);
     if(fill){ctx.fillStyle=color;ctx.fillRect(0,clamp(yy-23,0,cvs.height-25),130,25);
       ctx.fillStyle="white";ctx.font="bold 15px sans-serif";ctx.fillText(label,9,clamp(yy-7,16,cvs.height-8));}
   }
   const interval=selected.source_y_interval;
   if(Array.isArray(interval)&&interval.length===2){
     const a=interval[0],b=interval[1];
     if(typeof a==="number"&&typeof b==="number"&&b>a){
       const start=(a*h-y0)/hh*cvs.height,end=(b*h-y0)/hh*cvs.height;
       ctx.fillStyle="rgba(24,155,86,.10)";
       ctx.fillRect(0,clamp(start,0,cvs.height),cvs.width,
         Math.max(0,clamp(end,0,cvs.height)-clamp(start,0,cvs.height)));
       marker(a,"#1b8a51","SOURCE",true);
     }
   }
   marker(selected.margin_y_fraction,"#c04a32","MARGIN",true);
 }
 function setDecision(){
   for(const b of document.querySelectorAll("[data-choice]")){
     b.classList.toggle("selected",b.dataset.choice===decision);
   }
 }
 function show(c){
   selected=c;
   const saved=reviews[c.edge_id]||{},src=saved.source||{},dst=saved.destination||{};
   $("title").textContent="Page "+c.page+" · "+(c.column==="L"?"left":"right")+" margin";
   $("caseId").textContent=c.edge_id;
   $("marginLine").textContent=lineDesc(c);
   $("targetNum").textContent="Individual destination #"+c.target_index+" · margin y="+fmt(c.margin_y_fraction);
   $("reasons").replaceChildren();
   for(const reason of c.reason_codes||[]){
     const tag=document.createElement("span");tag.className="tag bad";tag.textContent=reason;
     $("reasons").appendChild(tag);
   }
   const ab=(bk,ch,v)=>(bk||"?")+" "+(ch||"?")+":"+(v||"?");
   $("proposal").textContent=ab(c.source_book,c.source_chapter,c.source_verse)+" → "+
      ab(c.destination_book,c.destination_chapter,c.destination_verse);
   const header=c.running_head||{},pagebook=c.source_book_context||{};
   $("pageContext").textContent="Page book: "+(pagebook.book_code||"?")+
     " · header "+(header.header_position||"not recorded")+
     " "+(header.boundary_role||"")+
     " "+(header.chapter||"?")+":"+(header.verse||"?")+
     " · OCR target: "+(c.destination_literal||"(not parsed)");
   const assign=(id,value)=>$(id).value=value==null?"":value;
   assign("srcBook",src.book_code!==undefined?src.book_code:c.source_book);
   assign("srcChapter",src.chapter!==undefined?src.chapter:c.source_chapter);
   assign("srcVerse",src.verse!==undefined?src.verse:c.source_verse);
   assign("dstBook",dst.book_code!==undefined?dst.book_code:c.destination_book);
   assign("dstChapter",dst.chapter!==undefined?dst.chapter:c.destination_chapter);
   assign("dstVerse",dst.verse!==undefined?dst.verse:c.destination_verse);
   assign("dstEndChapter",dst.end_chapter!==undefined?dst.end_chapter:c.destination_end_chapter);
   assign("dstEndVerse",dst.end_verse!==undefined?dst.end_verse:c.destination_end_verse);
   assign("dstSuffix",dst.suffix!==undefined?dst.suffix:c.destination_suffix);
   $("dstType").value=["VERSE","VERSE_RANGE","CHAPTER_ONLY","CHAPTER_RANGE"].includes(
     dst.type||c.destination_type)?(dst.type||c.destination_type):"UNKNOWN";
   $("cause").value=saved.cause||"OTHER_OR_UNKNOWN";
   $("notes").value=saved.notes||"";
   $("checked").checked=saved.checked_original_scan===true;
   decision=saved.choice||"unresolved";setDecision();
   centerY=typeof c.margin_y_fraction==="number"?c.margin_y_fraction:.5;
   zoom=1.4;
   $("ySlider").value=Math.round(centerY*1000);
   $("feedback").textContent="";
   nav();draw();
 }
 async function save(next){
   if(!selected||busy)return;
   const payload={
     edge_id:selected.edge_id,choice:decision,cause:$("cause").value,
     source:{book_code:$("srcBook").value.trim(),chapter:num("srcChapter"),verse:num("srcVerse")},
     destination:{
       book_code:$("dstBook").value.trim(),
       chapter:num("dstChapter"),verse:num("dstVerse"),
       end_chapter:num("dstEndChapter"),end_verse:num("dstEndVerse"),
       suffix:$("dstSuffix").value.trim(),type:$("dstType").value
     },
     checked_original_scan:$("checked").checked,
     notes:$("notes").value
   };
   busy=true;$("feedback").textContent="Saving…";
   const oldId=selected.edge_id;
   const before=cases.findIndex(x=>x.edge_id===oldId);
   try{
     const response=await fetch("../api/integrated-exception-review",{
       method:"POST",credentials:"same-origin",
       headers:{"Content-Type":"application/json","X-JBible-Review":"1"},
       body:JSON.stringify(payload)
     });
     const body=await response.json();
     if(!response.ok||!body.ok)throw Error(body.error||"Save failed");
     reviews[oldId]=body.review;
     nav();
     $("feedback").textContent="Saved. Your observation will be available for parser improvements.";
     if(next){
       const following=cases.slice(before+1).concat(cases.slice(0,before));
       const target=following.find(x=>!isDone(reviews[x.edge_id]))||
         (following.length?following[0]:null);
       if(target&&target.edge_id!==oldId)show(target);
     }
   }catch(error){$("feedback").textContent="Cannot save: "+text(error.message);}
   finally{busy=false;}
 }
 function move(delta){
   if(!selected)return;
   const list=visibleCases();
   const i=list.findIndex(c=>c.edge_id===selected.edge_id);
   if(i>=0&&list[i+delta])show(list[i+delta]);
 }
 function bind(){
   $("filter").onchange=()=>{nav();const list=visibleCases();if(list.length&&!list.some(x=>selected&&x.edge_id===selected.edge_id))show(list[0]);};
   $("prev").onclick=()=>move(-1);$("next").onclick=()=>move(1);
   $("minus").onclick=()=>{zoom=clamp(zoom/1.3,.65,6);draw();};
   $("plus").onclick=()=>{zoom=clamp(zoom*1.3,.65,6);draw();};
   $("ySlider").oninput=()=>{centerY=Number($("ySlider").value)/1000;draw();};
   $("full").onclick=()=>{
     if(!selected)return;
     $("dialogTitle").textContent="Original Bible page "+selected.page;
     $("fullImg").src=imageUrl(selected.page);$("dialog").showModal();
   };
   $("close").onclick=()=>$("dialog").close();
   $("save").onclick=()=>save(false);$("saveNext").onclick=()=>save(true);
   for(const b of document.querySelectorAll("[data-choice]"))
     b.onclick=()=>{decision=b.dataset.choice;setDecision();};
 }
 async function init(){
   bind();
   try{
     const response=await fetch("../api/integrated-exceptions",{
       credentials:"same-origin",cache:"no-store"});
     const body=await response.json();
     if(!response.ok||!Array.isArray(body.cases))throw Error(body.error||"Queue unavailable");
     cases=body.cases;reviews=body.reviews||{};
     if(!cases.length)throw Error("No integrated OCR exceptions available");
     nav();show(cases.find(c=>!isDone(reviews[c.edge_id]))||cases[0]);
   }catch(error){
     $("progress").textContent="Unable to load exceptions";
     $("title").textContent="Unable to load";
     $("caseId").textContent=text(error.message);
   }
 }
 init();
})();