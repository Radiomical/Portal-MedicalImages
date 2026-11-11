"""Optional synthetic Chromium benchmark: requires Playwright and Pillow.
Run from the checkout; no external network or production credentials used.
Every URL is intercepted. Latencies are modeled, not production telemetry.
"""
import asyncio,json,time,io,re,subprocess,math,tempfile,shutil,os
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from PIL import Image,ImageDraw
from playwright.async_api import async_playwright
root=Path(__file__).resolve().parents[2];out=Path(tempfile.mkdtemp(prefix='prepared-series-qa-'));print('OUTPUT',out,flush=True)
section=(root/'blog/templates/blog/_series.html').read_text();section=re.sub(r'{% if description %}.*?{% endif %}','',section,flags=re.S);section=section.replace("{% url 'blog:series_slice' post.id plane %}",'/slice/PLANE').replace('{{ series_name }}','SINTÉTICA PLANE').replace('{{ images }}','80').replace('{{ series_id }}','PLANE')
# Synthetic, high-resolution JPEG. No patient data.
im=Image.new('RGB',(2100,2420),'#183839');d=ImageDraw.Draw(im)
for y in range(0,2420,23):d.line((0,y,2100,y),fill='#73a89a',width=2)
d.text((250,800),'SYNTHETIC - NOT A PATIENT IMAGE',font_size=65,fill='white');b=io.BytesIO();im.save(b,'JPEG',quality=85);jpeg=b.getvalue();print('JPEG_BYTES',len(jpeg),flush=True)
async def main():
 results={}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('CHROME_EXECUTABLE') or shutil.which('google-chrome'),headless=True,args=['--no-sandbox'])
  for mode in ['baseline','candidate']:
   ctx=await browser.new_context(viewport={'width':1200,'height':960});page=await ctx.new_page();counts={'metadata':0,'jpeg':0,'wire_bytes':0,'active':0,'max_active':0};cache=set();lat=[]
   async def route(r):
    u=urlparse(r.request.url);path=u.path
    if path=='/js':await r.fulfill(content_type='application/javascript',body=subprocess.check_output(['git','show','a31b1e4b379ae221aff4dde3207d7117136b98e7:static-src/js/clinical.js'],cwd=root,text=True) if mode=='baseline' else (root/'static-src/js/clinical.js').read_text())
    elif path.startswith('/slice/'):
     q=parse_qs(u.query);idx=int(q['index'][0]);n=int(q.get('count',['0'])[0]);before=int(q.get('before',['0'])[0]);after=int(q.get('after',['1'])[0]);start=idx if n else max(0,idx-before);end=min(80,idx+n if n else idx+after+1);counts['metadata']+=1;await asyncio.sleep(.225)
     await r.fulfill(json={'index':idx,'total':80,'ttl':300,'images':[{'index':i,'url':f'https://media.synthetic.test/{path.rsplit("/",1)[1]}-{i}.jpg'} for i in range(start,end)]})
    elif u.hostname=='media.synthetic.test':
     counts['jpeg']+=1;counts['active']+=1;counts['max_active']=max(counts['max_active'],counts['active']);await asyncio.sleep(.10 if r.request.url in cache else .40);cache.add(r.request.url);counts['wire_bytes']+=len(jpeg)
     await r.fulfill(content_type='image/jpeg',headers={'Access-Control-Allow-Origin':'*','Cache-Control':'public,max-age=31536000,immutable'},body=jpeg);counts['active']-=1
    else:
     html='<html lang="es"><meta charset="utf-8"><style>'+(root/'static-src/css/clinical.css').read_text()+'body{padding:24px}.test{max-width:760px;margin:auto}</style><h1>QA sintética: '+mode+'</h1><p>No contiene imágenes de pacientes.</p><div class="test">'+''.join(section.replace('PLANE',str(i)) for i in range(3))+'</div><script src="/js"></script></html>'
     await r.fulfill(content_type='text/html',body=html)
   await page.route('**/*',route);await page.goto('https://synthetic.test');await page.wait_for_function("[...document.querySelectorAll('output')].every(e=>e.value==='1 / 80')")
   await page.wait_for_timeout(600)
   for phase in ['first_pass','return_pass']:
    samples=[]
    for target in (range(1,25) if phase=='first_pass' else range(23,-1,-1)):
     t=time.perf_counter();await page.locator('[data-next]' if phase=='first_pass' else '[data-previous]').first.click();await page.wait_for_function("n=>document.querySelector('output').value===`${n+1} / 80`",arg=target,timeout=12000);samples.append((time.perf_counter()-t)*1000)
    s=sorted(samples);lat.append({'phase':phase,'samples':len(s),'p50_ms':round(s[len(s)//2]),'p95_ms':round(s[math.ceil(len(s)*.95)-1]),'raw_ms':[round(n) for n in samples]})
   await page.evaluate("window.visibleCuts=[];window.running=true;const tick=()=>{const n=document.querySelector('output').value;if(!n.includes('solicitado'))window.visibleCuts.push(n);if(window.running)requestAnimationFrame(tick)};requestAnimationFrame(tick)")
   await page.locator('.series-frame').first.hover()
   for _ in range(20):
    await page.mouse.wheel(0,100);await page.wait_for_timeout(60)
   end=time.perf_counter()
   await page.wait_for_function("document.querySelector('output').value==='21 / 80'",timeout=12000)
   wheel={'final_lag_ms':round((time.perf_counter()-end)*1000),'distinct_displayed_cuts':await page.evaluate('window.running=false;new Set(window.visibleCuts).size'),'ticks':20,'tick_interval_ms':60}
   state=await page.evaluate("({decoded:viewerBudget.bytes,compressed:typeof seriesBytes==='undefined'?null:seriesBytes.bytes,active:typeof seriesBytes==='undefined'?null:seriesBytes.active,originsDisabled:typeof seriesBytes==='undefined'?null:[...seriesBytes.disabled]})")
   if mode=='candidate':
    await page.screenshot(path=str(out/'automatic-desktop.png'));await page.set_viewport_size({'width':390,'height':844});await page.screenshot(path=str(out/'automatic-mobile.png'));assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   results[mode]={'latency':lat,'wheel':wheel,'counts':counts.copy(),'budget':state,'jpeg_bytes':len(jpeg),'dimensions':[2100,2420],'network_model':'225ms metadata,400ms cold JPEG,100ms repeat JPEG; routing fixture disables true browser HTTP cache, compressed blobs retained in candidate only','series':3,'slices_per_series':80}
   print(mode,json.dumps(results[mode]),flush=True);await page.unroute_all(behavior='wait');await ctx.close()
  await browser.close()
 (out/'benchmark.json').write_text(json.dumps(results,indent=2))
asyncio.run(main())
