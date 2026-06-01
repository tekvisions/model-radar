/* Model Radar — render trending HF models from data.json */
(function(){
  "use strict";
  var W=window;
  var nav=document.getElementById("nav");
  if(nav){var on=function(){nav.classList.toggle("scrolled",W.scrollY>20)};W.addEventListener("scroll",on,{passive:true});on();}

  var ALL=[], PAGE=120, limit=PAGE;
  var state={q:"",cat:"All",onlyFresh:false};

  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c];});}
  function fmtN(n){
    if(n>=1e9) return (n/1e9).toFixed(1).replace(/\.0$/,"")+"B";
    if(n>=1e6) return (n/1e6).toFixed(1).replace(/\.0$/,"")+"M";
    if(n>=1e3) return (n/1e3).toFixed(n>=1e4?0:1).replace(/\.0$/,"")+"k";
    return String(n);
  }
  function fmtDays(d){ if(d==null)return"—"; if(d<1)return"today"; if(d<2)return"1d ago"; if(d<30)return Math.round(d)+"d ago"; if(d<365)return Math.round(d/30)+"mo ago"; return Math.round(d/365)+"y ago"; }
  function relDate(iso){ if(!iso)return"recently"; var d=(Date.now()-new Date(iso).getTime())/86400000; if(isNaN(d))return"recently"; return fmtDays(d); }
  function safeUrl(u){ if(!u)return"#"; try{var p=new URL(u,location.href).protocol;return(p==="http:"||p==="https:")?u:"#";}catch(e){return"#";} }

  function matches(m){
    if(state.onlyFresh && m.health!=="fresh") return false;
    if(state.cat!=="All" && m.category!==state.cat) return false;
    if(state.q){ var q=state.q.toLowerCase(); if((m.id+" "+m.task).toLowerCase().indexOf(q)<0) return false; }
    return true;
  }

  function render(){
    var filtered=ALL.filter(matches), shown=filtered.slice(0,limit);
    document.getElementById("rows").innerHTML = shown.length ? shown.map(function(m){
      var fresh = m.health==="fresh" ? '<span class="new">FRESH</span>' : '';
      return '<a class="row" href="'+esc(safeUrl(m.url))+'" target="_blank" rel="noopener noreferrer">'
        +'<div class="nm"><h3><span style="color:var(--muted);font-family:var(--mono);font-size:13px">#'+m.rank+'</span> '+esc(m.name)+' '+fresh+'</h3>'
          +'<div class="ns">'+esc(m.author)+' · '+esc(m.task)+'</div></div>'
        +'<div class="cat">'+esc(m.category)+'</div>'
        +'<div class="health"><span class="d '+esc(m.health)+'"></span>'+fmtN(m.downloads)+' dl · '+fmtDays(m.updated_days)+'</div>'
        +'<div class="cat" style="color:var(--accent)">▲ '+m.trending+'<span style="color:var(--muted);margin-left:8px">♥ '+fmtN(m.likes)+'</span></div></a>';
    }).join("") : '<div class="loading">No models match — try a broader search or clear filters.</div>';

    document.getElementById("count").innerHTML='Showing <b>'+Math.min(limit,filtered.length)+'</b> of <b>'+filtered.length+'</b> matching'+(filtered.length!==ALL.length?' · '+ALL.length+' total':'');
    var more=document.getElementById("more");
    more.innerHTML = filtered.length>limit ? '<button id="loadmore">Load more ('+(filtered.length-limit)+' more)</button>' : '';
    var lm=document.getElementById("loadmore"); if(lm) lm.addEventListener("click",function(){limit+=PAGE;render();});
  }

  function chip(label,group,val,n){ return '<button class="chip" data-group="'+group+'" data-val="'+esc(val)+'">'+esc(label)+(n!=null?'<span class="n">'+n+'</span>':'')+'</button>'; }
  function m_(v,l){ return '<div class="m"><b>'+v+'</b><span>'+l+'</span></div>'; }

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
    render();
  }
  fetch("data.json",{cache:"no-store"}).then(function(r){return r.json();}).then(build).catch(function(e){
    document.getElementById("rows").innerHTML='<div class="loading">Could not load. '+esc(e.message||e)+'</div>';
  });
})();
