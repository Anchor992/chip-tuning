export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export function smooth(a, b, x) { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); }
export const lerp = (a, b, t) => a + (b - a) * t;
export const wrap = (index, count = 3) => ((index % count) + count) % count;
export function deriveTimeline(progress) {
  const p = clamp(progress);
  return Object.freeze({progress:p,chapter:p<.30?0:p<.48?1:p<.87?2:3,ecuOpen:smooth(.025,.26,p),macro:smooth(.28,.435,p),engineIn:smooth(.44,.53,p),engineOpen:smooth(.54,.70,p)*(1-smooth(.755,.86,p)),carReturn:smooth(.865,.96,p)});
}
export function carouselOffset(index, active, count = 3) {let x=wrap(index-active,count);if(x>count/2)x-=count;return x;}
