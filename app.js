/* Model Radar — render trending HF models from data.json.
   Vanilla, no deps. Live filter / sort / search, signal meters, scroll-reveal,
   animated counters, keyboard navigation. Everything client-side over data.json. */
(function(){
  "use strict";
  var W=window, D=document;
  var RM = !!(W.matchMedia && W.matchMedia("(prefers-reduced-motion:reduce)").matches);
  var nav=D.getElementById("nav");
  if(nav){var on=function(){nav.classList.toggle("scrolled",W.scrollY>20)};W.addEventListener("scroll",on,{passive:true});on();}

  var ALL=[], PAGE=120, limit=PAGE, MAXTREND=1;
  var state={q:"",cat:"All",onlyFresh:false,sort:"trending",dir:"desc"};
  var revealObs=null;

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
  /* highlight a query substring inside escaped text */
  function hl(text,q){
    var safe=esc(text);
    if(!q) return safe;
    var i=text.toLowerCase().indexOf(q);
    if(i<0) return safe;
    return esc(text.slice(0,i))+"<mark>"+esc(text.slice(i,i+q.length))+"</mark>"+esc(text.slice(i+q.length));
  }
  /* log-scaled 0..100 intensity of a trending score vs the field's max */
  function intensity(t){ if(!t||t<=0||MAXTREND<=1) return 4; return Math.max(5,Math.round(Math.log1p(t)/Math.log1p(MAXTREND)*100)); }

  /* position movement vs the prior daily run: ▲N climbed, ▼N slipped, → held, '' new.
     rank_delta>0 means a smaller (better) rank number — i.e. climbed the radar. */
  function moveBadge(m){
    var d=m.rank_delta;
    if(d==null) return '';  /* no prior history yet — show nothing (fills in daily) */
    if(d>0) return '<span class="mv up" title="Climbed '+d+' since the prior run">▲'+d+'</span>';
    if(d<0) return '<span class="mv dn" title="Slipped '+Math.abs(d)+' since the prior run">▼'+Math.abs(d)+'</span>';
    return '<span class="mv flat" title="Held position">→</span>';
  }

  function matches(m){
    if(state.onlyFresh && m.health!=="fresh") return false;
    if(state.cat!=="All" && m.category!==state.cat) return false;
    if(state.q){ var q=state.q.toLowerCase(); if((m.id+" "+m.task+" "+m.category).toLowerCase().indexOf(q)<0) return false; }
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
      if(key==="name"){ x=String(a.name||"").toLowerCase(); y=String(b.name||"").toLowerCase();
        if(x<y)return -1*dir; if(x>y)return 1*dir; return a.rank-b.rank; }
      if(key==="category"){ x=String(a.category||"").toLowerCase(); y=String(b.category||"").toLowerCase();
        if(x<y)return -1*dir; if(x>y)return 1*dir; return a.rank-b.rank; }
      if(key==="downloads"){ x=a.downloads||0; y=b.downloads||0; }
      else if(key==="updated"){ x=a.updated_days==null?Infinity:a.updated_days; y=b.updated_days==null?Infinity:b.updated_days; }
      else { x=a[key]||0; y=b[key]||0; } // trending, likes
      if(x<y)return -1*dir; if(x>y)return 1*dir; return a.rank-b.rank;
    });
    return copy;
  }

  function rowHTML(m,q){
    var fresh = m.health==="fresh" ? '<span class="new">FRESH</span>' : '';
    var w=intensity(m.trending);
    return '<a class="row reveal" href="/m/'+esc(slugify(m.id))+'/" tabindex="0" aria-label="'+esc(m.name)+' by '+esc(m.author)+', rank '+m.rank+'">'
      +'<div class="nm"><h3><span class="rk">#'+m.rank+moveBadge(m)+'</span> '+hl(m.name,q)+' '+fresh+'</h3>'
        +'<div class="ns">'+hl(m.author,q)+' · '+hl(m.task,q)+'</div></div>'
      +'<div class="cat">'+esc(m.category)+'</div>'
      +'<div class="health"><span class="d '+esc(m.health)+'"></span>'+fmtN(m.downloads)+' dl · '+fmtDays(m.updated_days)+'</div>'
      +'<div class="trend"><div class="tline"><span class="tscore">▲ '+m.trending+'</span><span class="tlikes">♥ '+fmtN(m.likes)+'</span><span class="go" aria-hidden="true">→</span></div>'
        +'<div class="meter" aria-hidden="true"><i style="--w:'+w+'%"></i></div></div></a>';
  }

  function render(){
    var filtered=sorted(ALL.filter(matches)), shown=filtered.slice(0,limit);
    var q=state.q.toLowerCase();
    var rows=D.getElementById("rows");
    rows.innerHTML = shown.length ? shown.map(function(m){return rowHTML(m,q);}).join("")
      : '<div class="loading">No contacts match — try a broader search or clear filters.</div>';

    D.getElementById("count").innerHTML='Showing <b>'+Math.min(limit,filtered.length)+'</b> of <b>'+filtered.length+'</b> matching'+(filtered.length!==ALL.length?' · '+ALL.length+' total':'');
    var live=D.getElementById("live"); if(live) live.textContent=filtered.length+' models match'+(state.cat!=="All"?' in '+state.cat:'')+(state.q?' for "'+state.q+'"':'')+'.';
    var more=D.getElementById("more");
    more.innerHTML = filtered.length>limit ? '<button id="loadmore">Sweep deeper ('+(filtered.length-limit)+' more)</button>' : '';
    var lm=D.getElementById("loadmore"); if(lm) lm.addEventListener("click",function(){limit+=PAGE;render();});
    revealRows();
  }

  /* movers strip: horizontally-scrollable chips linking to detail pages. Each shows
     the position climb (▲N) when tracked, else the model's trending score on day one
     before position history exists. */
  function renderMovers(movers){
    var el=D.getElementById("movers"); if(!el) return;
    if(!movers || !movers.length){ el.hidden=true; return; }
    var chips=movers.map(function(m,i){
      var climbed=(typeof m.rank_delta==="number" && m.rank_delta>0);
      // real climbers get the ▲N climb arrow; day-one fallback (top-trending, NOT
      // actual climbers) gets a NEUTRAL hot-dot + the trending score so it never
      // misreads as a position climb.
      var tag=climbed
        ? '<span class="mv up">▲'+m.rank_delta+'</span>'
        : '<span class="mv flat">• '+(m.trending||0)+'</span>';
      var sub=climbed?("now #"+m.rank):("hot · #"+m.rank);
      return '<a class="mover" href="/m/'+esc(slugify(m.id))+'/" style="--d:'+(i*50)+'ms">'
        +tag+'<span class="mvn">'+esc(m.name)+'</span><span class="mvs">'+esc(sub)+'</span></a>';
    }).join("");
    el.innerHTML='<span class="movers-l">Movers</span><div class="movers-track">'+chips+'</div>';
    el.hidden=false;
  }

  /* staggered scroll-reveal for rows; instant if reduced-motion */
  function revealRows(){
    var els=D.querySelectorAll("#rows .row.reveal");
    if(RM || !("IntersectionObserver" in W)){ els.forEach(function(el){el.classList.remove("reveal");el.classList.add("shown");}); return; }
    if(revealObs) revealObs.disconnect();
    revealObs=new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if(en.isIntersecting){
          var el=en.target, i=+(el.dataset.i||0);
          el.style.transitionDelay=Math.min(i,12)*28+"ms";
          el.classList.remove("reveal"); el.classList.add("shown");
          revealObs.unobserve(el);
        }
      });
    },{rootMargin:"0px 0px -6% 0px"});
    els.forEach(function(el,i){el.dataset.i=i;revealObs.observe(el);});
  }

  /* keyboard nav: ↑/↓ move between rows, Enter opens (anchors already do Enter),
     "/" focuses search from anywhere. */
  function keyNav(){
    var rows=D.getElementById("rows");
    rows.addEventListener("keydown",function(e){
      if(e.key!=="ArrowDown"&&e.key!=="ArrowUp") return;
      var all=Array.prototype.slice.call(rows.querySelectorAll(".row"));
      var idx=all.indexOf(D.activeElement);
      if(idx<0) return;
      e.preventDefault();
      var nxt=e.key==="ArrowDown"?Math.min(idx+1,all.length-1):Math.max(idx-1,0);
      if(all[nxt]) all[nxt].focus();
    });
    D.addEventListener("keydown",function(e){
      if(e.key==="/" && D.activeElement && /^(INPUT|TEXTAREA)$/.test(D.activeElement.tagName)) return;
      if(e.key==="/"){ var q=D.getElementById("q"); if(q){e.preventDefault();q.focus();} }
    });
  }

  /* count-up animation on the hero stat numbers */
  function animateCounter(el,target,fmt){
    if(RM || target<=0){ el.textContent=fmt?fmt(target):String(target); return; }
    var dur=900, t0=null;
    function step(ts){
      if(t0==null) t0=ts;
      var p=Math.min((ts-t0)/dur,1), e=1-Math.pow(1-p,3); // easeOutCubic
      var v=Math.round(target*e);
      el.textContent=fmt?fmt(v):String(v);
      if(p<1) requestAnimationFrame(step); else el.textContent=fmt?fmt(target):String(target);
    }
    requestAnimationFrame(step);
  }

  function chip(label,group,val,n){ return '<button class="chip" data-group="'+group+'" data-val="'+esc(val)+'" type="button" aria-pressed="false">'+esc(label)+(n!=null?'<span class="n">'+n+'</span>':'')+'</button>'; }

  function injectJsonLd(data){
    var el=D.getElementById("jsonld-home"); if(!el) return;
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
    MAXTREND=ALL.reduce(function(mx,m){return Math.max(mx,m.trending||0);},1);

    // hero stat counters
    var mr=D.getElementById("metarow");
    mr.innerHTML =
      '<div class="m"><b data-n="'+(data.model_count||0)+'">0</b><span>Models tracked</span></div>'
      +'<div class="m"><b data-n="'+(data.fresh_count||0)+'">0</b><span>Fresh (&lt;14d)</span></div>'
      +'<div class="m"><b data-n="'+(data.total_downloads||0)+'" data-fmt="1">0</b><span>Total downloads</span></div>'
      +'<div class="m"><b data-n="'+((data.categories||[]).length)+'">0</b><span>Task types</span></div>';
    Array.prototype.forEach.call(mr.querySelectorAll("b[data-n]"),function(b){
      animateCounter(b,+b.getAttribute("data-n"),b.getAttribute("data-fmt")?fmtN:null);
    });

    renderMovers(data.movers||[]);  // biggest climbers since the prior run (board-wide, not filtered)

    var ll=D.getElementById("liveline"); if(ll) ll.textContent="Sourced from the Hugging Face API · updated "+relDate(data.generated_at);
    var fg=D.getElementById("footgen"); if(fg) fg.textContent="Updated "+relDate(data.generated_at)+" from the Hugging Face API";

    var cc=data.category_counts||{}, cats=Object.keys(cc).sort(function(a,b){return cc[b]-cc[a];});
    D.getElementById("filters").innerHTML = chip("All","cat","All",data.model_count)+cats.map(function(c){return chip(c,"cat",c,cc[c]);}).join("");
    D.getElementById("toggles").innerHTML = chip("Fresh ⚡","onlyFresh","fresh",data.fresh_count);
    var allChip=D.querySelector('.chip[data-group="cat"][data-val="All"]');
    if(allChip){allChip.classList.add("active");allChip.setAttribute("aria-pressed","true");}

    D.querySelectorAll(".chip").forEach(function(c){
      c.addEventListener("click",function(){
        var g=c.getAttribute("data-group");
        if(g==="onlyFresh"){ var act=c.classList.toggle("active"); state.onlyFresh=act; c.setAttribute("aria-pressed",act?"true":"false"); }
        else {
          D.querySelectorAll('.chip[data-group="cat"]').forEach(function(x){x.classList.remove("active");x.setAttribute("aria-pressed","false");});
          c.classList.add("active"); c.setAttribute("aria-pressed","true"); state.cat=c.getAttribute("data-val");
        }
        limit=PAGE; render();
      });
    });

    var q=D.getElementById("q"), clear=D.getElementById("clear"), qt=null;
    q.addEventListener("input",function(){
      clear.style.display=q.value?"":"none";
      if(qt) clearTimeout(qt);
      qt=setTimeout(function(){ state.q=q.value.trim(); limit=PAGE; render(); },90); // debounce for snappy-but-cheap
    });
    clear.addEventListener("click",function(){q.value="";state.q="";clear.style.display="none";limit=PAGE;render();q.focus();});
    q.addEventListener("keydown",function(e){ if(e.key==="Escape"&&q.value){q.value="";state.q="";clear.style.display="none";limit=PAGE;render();} });

    bindSort();
    keyNav();
    injectJsonLd(data);
    render();
  }

  /* sortable column headers — click or keyboard, with an aria-sort + arrow indicator */
  function bindSort(){
    var heads=D.querySelectorAll('#colhead .sortable');
    function apply(btn){
      var key=btn.getAttribute("data-sort");
      var cur=btn.getAttribute("aria-sort");
      var startAsc = (key==="category"||key==="name"); // text columns start A→Z; numbers start high→low
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

  fetch("data.json",{cache:"no-store"}).then(function(r){return r.json();}).then(build).catch(function(e){
    D.getElementById("rows").innerHTML='<div class="loading">Could not load. '+esc(e.message||e)+'</div>';
  });
})();
