(function(){
var d=document.querySelector('.sx-dd');if(!d)return;
var b=d.querySelector('.sx-ddb');
function set(o){d.classList.toggle('open',o);b.setAttribute('aria-expanded',o?'true':'false');}
b.addEventListener('click',function(e){e.stopPropagation();set(!d.classList.contains('open'));});
document.addEventListener('click',function(e){if(!d.contains(e.target))set(false);});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){set(false);b.focus();}});
d.addEventListener('focusout',function(e){if(!d.contains(e.relatedTarget))set(false);});
})();
