/* Model Radar — render trending HF models from data.json */
(function(){
  "use strict";
  var W=window;
  var nav=document.getElementById("nav");
  if(nav){var on=function(){nav.classList.toggle("scrolled",W.scrollY>20)};W.addEventListener("scroll",on,{passive:true});on();}

  var ALL=[], PAGE=120, limit=PAGE;
  var state={q:"",cat:"All",onlyFresh:false,sort:"trending",dir:"desc"};

  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];});}
  function fmtN(n){
    if(n>=1e9) return (n/1e9).toFixed(1).replace(/\.0$/,"")+"B";
    if(n>=1e6) return (n/1e6).toFixed(1).replace(/\.0$/,"")+"M";
    if(n>=1e3) return (n/1e3).toFixed(n>=1e4?0:1).replace(/\.0$/,"")+"k";
    return String(n);
  }
  function fmtDays(d){ if(d==null)return"—"; if(d<1)return"today"; if(d<2)return"1d ago"; if(d<30)return Math.round(d)+"d ago"; if(d<365)return Math.round(d/30)+"mo ago"; return Math.round(d/365)+"y ago"; }
  function relDate(iso){ if(!iso)return"recently"; var d=(Date.now()-new Date(iso).getTime())/86400000; if(isNaN(d))return"recently"; return fmtDays(d); }

  /* slug from model id — MUST match build_data.py slugify() exactly */
  function slugify(id){
    var s=String(id==null?"":id).toLowerCase();
    s=s.replace(/[^a-z0-9]+/g,"-").replace(/^-+|-+$/g,"");
    return s||"model";
  }

  function matches(m){
    if(state.onlyFresh && m.health!=="fresh") return false;
    if(state.cat!=="All" && m.category!==state.cat) return false;
    if(state.q){ var q=state.q.toLowerCase(); if((m.id+" "+m.task).toLowerCase().indexOf(q)<0) return false; }
    return true;
  }

  function sorted(list){
    var key=state.sort, dir=state.dir==="asc"?1:-1;
    if(key==="trending"&&state.dir==="desc"){ // default: trending desc == rank order
      return list.slice().sort(function(a,b){return a.rank-b.rank;});
    }
    var copy=list.slice();
    copy.sort(function(a,b){
      var x,y;
      if(key==="category"){ x=String(a.category||"").toLowerCase(); y=String(b.category||"").toLowerCase();
        if(x<y)return -1*dir; if(x>y)return 1*dir; return a.rank-b.rank; }
      if(key==="downloads"){ x=a.downloads||0; y=b.downloads||0; }
      else if(key==="updated"){ x=a.updated_days==null?Infinity:a.updated_days; y=b.updated_days==null?Infinity:b.updated_days; }
      else { x=a[key]||0; y=b[key]||0; } // trending, likes
      if(x<y)return -1*dir; if(x>y)return 1*dir; return a.rank-b.rank;
    });
    return copy;
  }

  function render(){
    var filtered=sorted(ALL.filter(matches)), shown=filtered.slice(0,limit);
    document.getElementById("rows").innerHTML = shown.length ? shown.map(function(m){
      var fresh = m.health==="fresh" ? '<span class="new">FRESH</span>' : '';
      return '<a class="row" href="/m/'+esc(slugify(m.id))+'/">'
        +'<div class="nm"><h3><span style="color:var(--muted);font-family:var(--mono);font-size:13px">#'+m.rank+'</span> '+esc(m.name)+' '+fresh+'</h3>'
          +'<div class="ns">'+esc(m.author)+' · '+esc(m.task)+'</div></div>'
        +'<div class="cat">'+esc(m.category)+'</div>'
        +'<div class="health"><span class="d '+esc(m.health)+'"></span>'+fmtN(m.downloads)+' dl · '+fmtDays(m.updated_days)+'</div>'
        +'<div class="cat" style="color:var(--accent)">▲ '+m.trending+'<span style="color:var(--muted);margin-left:8px">♥ '+fmtN(m.likes)+'</span><span class="go" aria-hidden="true" style="margin-left:8px">→</span></div></a>';
    }).join("") : '<div class="loading">No models match — try a broader search or clear filters.</div>';

    document.getElementById("count").innerHTML='Showing <b>'+Math.min(limit,filtered.length)+'</b> of <b>'+filtered.length+'</b> matching'+(filtered.length!==ALL.length?' · '+ALL.length+' total':'');
    var more=document.getElementById("more");
    more.innerHTML = filtered.length>limit ? '<button id="loadmore">Load more ('+(filtered.length-limit)+' more)</button>' : '';
    var lm=document.getElementById("loadmore"); if(lm) lm.addEventListener("click",function(){limit+=PAGE;render();});
  }

  /* sortable column headers */
  function bindSort(){
    var heads=document.querySelectorAll('#colhead .sortable');
    function apply(btn){
      var key=btn.getAttribute("data-sort");
      var cur=btn.getAttribute("aria-sort");
      // default sense per column: trending/downloads start desc, category starts asc
      var startAsc = key==="category";
      var dir;
      if(cur==="none"){ dir=startAsc?"asc":"desc"; }
      else { dir = cur==="ascending" ? "desc" : "asc"; }
      heads.forEach(function(h){ h.setAttribute("aria-sort","none"); var arr=h.querySelector(".arr"); if(arr)arr.textContent=""; });
      btn.setAttribute("aria-sort",dir==="asc"?"ascending":"descending");
      var arr=btn.querySelector(".arr"); if(arr)arr.textContent=dir==="asc"?"▲":"▼";
      state.sort=key; state.dir=dir; limit=PAGE; render();
    }
    heads.forEach(function(btn){
      btn.addEventListener("click",function(){apply(btn);});
      btn.addEventListener("keydown",function(e){ if(e.key==="Enter"||e.key===" "){e.preventDefault();apply(btn);} });
    });
  }

  function chip(label,group,val,n){ return '<button class="chip" data-group="'+group+'" data-val="'+esc(val)+'">'+esc(label)+(n!=null?'<span class="n">'+n+'</span>':'')+'</button>'; }
  function m_(v,l){ return '<div class="m"><b>'+v+'</b><span>'+l+'</span></div>'; }

  function injectJsonLd(data){
    var el=document.getElementById("jsonld-home"); if(!el) return;
    var base="https://modelradar.kymatalabs.com";
    var top=(data.models||[]).slice(0,50).map(function(m,i){
      return {"@type":"ListItem","position":i+1,"url":base+"/m/"+slugify(m.id)+"/","name":m.id};
    });
    var graph={"@context":"https://schema.org","@graph":[
      {"@type":"WebSite","@id":base+"/#website","url":base+"/","name":"Model Radar",
       "description":"A live radar of the AI models trending on Hugging Face, updated daily.",
       "publisher":{"@id":base+"/#org"},
       "inLanguage":"en"},
      {"@type":"Organization","@id":base+"/#org","name":"Kymata Labs","url":"https://kymatalabs.com/"},
      {"@type":"ItemList","@id":base+"/#models","name":"Trending Hugging Face models",
       "description":"Top "+top.length+" AI models by Hugging Face trending score.",
       "numberOfItems":top.length,"itemListElement":top}
    ]};
    el.textContent=JSON.stringify(graph);
  }

  function build(data){
    ALL=data.models||[];
    document.getElementById("metarow").innerHTML =
      m_(data.model_count,"Models tracked") + m_(data.fresh_count,"Fresh (&lt;14d)")
      + m_(fmtN(data.total_downloads),"Total downloads") + m_(data.categories.length,"Task types");
    document.getElementById("liveline").textContent="Sourced from the Hugging Face API · updated "+relDate(data.generated_at);
    var fg=document.getElementById("footgen"); if(fg) fg.textContent="Updated "+relDate(data.generated_at)+" from the Hugging Face API";

    var cc=data.category_counts||{}, cats=Object.keys(cc).sort(function(a,b){return cc[b]-cc[a];});
    document.getElementById("filters").innerHTML = chip("All","cat","All",data.model_count)+cats.map(function(c){return chip(c,"cat",c,cc[c]);}).join("");
    document.getElementById("toggles").innerHTML = chip("Fresh ⚡","onlyFresh","fresh",data.fresh_count);
    document.querySelector('.chip[data-group="cat"][data-val="All"]').classList.add("active");

    document.querySelectorAll(".chip").forEach(function(c){
      c.addEventListener("click",function(){
        var g=c.getAttribute("data-group");
        if(g==="onlyFresh"){ state.onlyFresh=c.classList.toggle("active"); }
        else { document.querySelectorAll('.chip[data-group="cat"]').forEach(function(x){x.classList.remove("active");}); c.classList.add("active"); state.cat=c.getAttribute("data-val"); }
        limit=PAGE; render();
      });
    });
    var q=document.getElementById("q"), clear=document.getElementById("clear");
    q.addEventListener("input",function(){state.q=q.value.trim();clear.style.display=state.q?"":"none";limit=PAGE;render();});
    clear.addEventListener("click",function(){q.value="";state.q="";clear.style.display="none";limit=PAGE;render();q.focus();});
    bindSort();
    injectJsonLd(data);
    render();
  }
  fetch("data.json",{cache:"no-store"}).then(function(r){return r.json();}).then(build).catch(function(e){
    document.getElementById("rows").innerHTML='<div class="loading">Could not load. '+esc(e.message||e)+'</div>';
  });
})();
