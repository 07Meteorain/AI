
(function(){
  var b=document.querySelectorAll('.toolbar button');
  function set(m){
    document.body.className='mode-'+m;
    b.forEach(function(x){x.classList.toggle('on',x.dataset.m===m)});
    try{localStorage.setItem('c1view',m)}catch(e){}
  }
  b.forEach(function(x){x.addEventListener('click',function(){set(x.dataset.m)})});
  var saved='both';
  try{saved=localStorage.getItem('c1view')||'both'}catch(e){}
  set(saved);
  var q=document.getElementById('q');
  if(q){
    q.addEventListener('input',function(){
      var v=q.value.toLowerCase();
      document.querySelectorAll('.pair').forEach(function(p){
        p.style.display = !v || p.textContent.toLowerCase().indexOf(v)>-1 ? '' : 'none';
      });
    });
  }
})();
