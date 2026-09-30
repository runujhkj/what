function buildCaptionBoxSettingsHtml() {
  return `<!doctype html><html><head><meta charset="utf-8"><title>What caption box prototype</title>
<style>
body{font:15px system-ui;background:#161921;color:#eee;margin:28px}h1{font-size:24px}
.controls{display:flex;flex-wrap:wrap;gap:16px;margin:20px 0}label{display:grid;gap:6px}
input,select,button{font:inherit;padding:7px;background:#272d3b;color:white;border:1px solid #687187;border-radius:4px}
input[type=number]{width:85px}#url{width:min(900px,90vw)}
#size{resize:both;overflow:hidden;width:640px;height:240px;min-width:80px;min-height:60px;max-width:100%;border:2px solid #a9b9e8;background:repeating-conic-gradient(#303440 0% 25%,#242834 0% 50%) 0/20px 20px}
iframe{display:block;width:100%;height:100%;border:0;pointer-events:none}p{max-width:850px;line-height:1.5}
</style></head><body><h1>Caption box prototype</h1>
<p>Drag the preview’s lower-right corner to resize the text area. Font size and padding stay fixed. The preview uses the same page as the OBS Browser source.</p>
<div class="controls">
<label>Source<select id="box"><option value="mic">Mic</option><option value="desktop">Desktop</option></select></label>
<label>Width<input id="width" type="number" min="80" max="3840" value="640"></label>
<label>Height<input id="height" type="number" min="60" max="2160" value="240"></label>
<label>Font size<input id="fontSize" type="number" min="8" max="160" value="32"></label>
<label>Padding<input id="padding" type="number" min="0" max="200" value="12"></label>
<label>Content<select id="demo"><option value="0">Live captions</option><option value="1">Sample text</option></select></label>
</div><div id="size"><iframe id="preview" title="Caption preview"></iframe></div>
<p>Paste this URL into an OBS Browser source, or into the plugin’s What Caption Box source for drag-to-reflow. Set its Width and Height to the values above. In What Caption Box, hold Shift while dragging to change width and height independently; after a short pause, the text reflows at the same font size. Choose Create new, not Add Existing, for each layout in OBS; Add Existing shares the viewport and disables automatic reflow. Ordinary Browser sources still use explicit Width and Height settings.</p>
<label>Browser source URL<input id="url" readonly></label><button id="copy">Copy URL</button>
<p>Oldest lines leave first when height is limited. Words wider than the box are clipped without shrinking the font. Less than one line of usable height shows no text. Completed lines stay frozen as speech arrives; intentional width changes reflow the retained text.</p>
<script>
const fields = Object.fromEntries(["box","width","height","fontSize","padding","demo","size","preview","url","copy"].map(id => [id, document.getElementById(id)]));
function refresh() {
 const params = new URLSearchParams({box:fields.box.value,fontSize:fields.fontSize.value,padding:fields.padding.value});
 fields.url.value = new URL('/caption-box?' + params, location.href).href;
 if(fields.demo.value === '1') params.set('demo','1');
 fields.preview.src = '/caption-box?' + params;
}
for(const key of ['box','fontSize','padding','demo']) fields[key].addEventListener('change',refresh);
for(const key of ['width','height']) fields[key].addEventListener('change',()=>{
 const input=fields[key]; const n=Math.max(Number(input.min),Math.min(Number(input.max),Number(input.value)||Number(input.min)));
 input.value=n; fields.size.style[key]=n+'px';
});
new ResizeObserver(()=>{fields.width.value=fields.size.clientWidth; fields.height.value=fields.size.clientHeight;}).observe(fields.size);
fields.copy.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(fields.url.value);fields.copy.textContent='Copied';}catch(_){fields.url.select();fields.copy.textContent='Select and copy URL';}});
refresh();
</script></body></html>`;
}
module.exports = { buildCaptionBoxSettingsHtml };
