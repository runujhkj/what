const assert = require('node:assert/strict');
const vm = require('node:vm');
const {buildCaptionBoxHtml} = require('../lib/caption_box_page');
const {buildCaptionBoxSettingsHtml} = require('../lib/caption_box_settings');
let resize, receive, fontsChanged;
const frame={style:{},dataset:{},clientWidth:240,clientHeight:120};
const probe={textContent:'',getBoundingClientRect(){return {width:this.textContent.length*10};}};
const text={children:[],style:{},appendChild(node){this.children.push(node);}};
text.ownerDocument={createElement(){return {style:{},textContent:'',remove(){text.children=text.children.filter(node=>node!==this);}};}};
const elements={frame,measure:probe,text};
const html=buildCaptionBoxHtml();
vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],{
 URLSearchParams,location:{search:'?box=desktop&fontSize=32&padding=12'},
 document:{getElementById:id=>elements[id],createElement:()=>({}),
  fonts:{ready:{then:fn=>fn()},addEventListener:(_name,fn)=>{fontsChanged=fn;}}},
 ResizeObserver:function(fn){resize=fn;this.observe=()=>fn();},
 EventSource:function(url){assert.equal(url,'/events?box=desktop');Object.defineProperty(this,'onmessage',{set(fn){receive=fn;}});},
});
const lines=()=>Array.from(text.children,node=>node.textContent);
receive({data:JSON.stringify({text:'one two three four five six seven eight nine ten',fontSize:'100px',width:'1px'})});
assert.equal(frame.style.fontSize,'32px');
assert.equal(frame.style.padding,'12px');
assert.equal(text.children.length,2);
assert.ok(Number(frame.dataset.hiddenLines)>0);
const before=lines();
frame.clientWidth=420;resize();
assert.equal(frame.style.fontSize,'32px');
assert.notDeepEqual(lines(),before);
frame.clientHeight=30;resize();
assert.deepEqual(lines(),[]);
frame.clientHeight=120;receive({data:JSON.stringify({text:'Corrected words here'})});
assert.deepEqual(lines(),['Corrected words here']);
receive({data:'{bad-json'});assert.deepEqual(lines(),['Corrected words here']);
receive({data:'{"text":""}'});assert.deepEqual(lines(),[]);
fontsChanged();
// Preview and exported URL use the same renderer; sample mode is preview-only.
const settings=buildCaptionBoxSettingsHtml();
assert.ok(settings.includes("'/caption-box?'"));
assert.ok(settings.includes('resize:both'));
assert.ok(!settings.includes('transform:scale'));
console.log('caption_box_page.test.js: ok (simulated DOM metrics)');
