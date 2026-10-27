/* Supporting motion is subordinate to the ECU story. No scroll hijacking. */
(()=>{
const reduce=matchMedia('(prefers-reduced-motion:reduce)');
// Split existing heading lines without changing copy or accessible names.
document.querySelectorAll('.section h2.reveal,.section .reveal>h2').forEach(h=>{
 if(reduce.matches)return;
 const label=h.innerText.replace(/\n/g," ");h.setAttribute('aria-label',label);
 const lines=h.innerHTML.split(/<br\s*\/?\s*>/i);
 h.innerHTML=lines.map((line,i)=>'<span class="word-mask" aria-hidden="true"><span style="transition-delay:'+i*70+'ms">'+line+'</span></span>').join('');
});
// Selector feedback bridges the actual model update, including rapid taps.
const active=document.querySelector('.vehicle-active');let timer;
document.querySelector('#vehicle-brands').addEventListener('click',e=>{if(!e.target.closest('button')||reduce.matches)return;active.classList.add('changing');clearTimeout(timer);timer=setTimeout(()=>active.classList.remove('changing'),100)});
document.querySelector('#vehicle-model').addEventListener('change',()=>{if(!reduce.matches)active.animate([{opacity:.5,transform:'translateY(6px)'},{opacity:1,transform:'none'}],{duration:200,easing:'cubic-bezier(.23,1,.32,1)'})});
// Keyboard navigation cancels playback immediately, just like touch and wheel input.
addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp','PageDown','PageUp','Home','End',' '].includes(e.key)&&!e.target.matches('input,textarea,select,button')){const play=document.querySelector('#play');if(play.getAttribute('aria-pressed')==='true')play.click()}});
// A small, bounded depth shift accompanies the scene's exit and the editorial copy.
const items=[document.querySelector('.manifesto p'),document.querySelector('.intro .lead')];let queued=false;
function parallax(){queued=false;if(reduce.matches){items.forEach(n=>n.style.transform='');return}items.forEach(n=>{const r=n.getBoundingClientRect();if(r.bottom<0||r.top>innerHeight)return;const d=Math.max(-1,Math.min(1,(r.top+r.height/2-innerHeight/2)/innerHeight));n.style.transform='translateY('+(-d*18).toFixed(2)+'px)'})}
addEventListener('scroll',()=>{if(!queued){queued=true;requestAnimationFrame(parallax)}},{passive:true});reduce.addEventListener('change',parallax);parallax();
})();
