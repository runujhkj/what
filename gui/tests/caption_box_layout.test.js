const assert = require('node:assert/strict');
const {createCaptionLayout} = require('../lib/caption_box_layout');
const layout = createCaptionLayout(text => text.length);
const view=(text,width=11,maxLines=5,reflow=false)=>layout.update(text,{width,maxLines,reflow});
assert.deepEqual(view('one two three four').lines,['one two','three four']);
assert.deepEqual(view('one two three four five').lines,['one two','three four','five']);
// Upstream eviction must not strip the beginning of a frozen visible line.
assert.deepEqual(view('two three four five six').lines,['one two','three four','five six']);
assert.deepEqual(view('two three four five six',20).lines,['two three four five','six']);
assert.deepEqual(view('two three four five six',20,1).lines,['six']);
assert.equal(view('two three four five six',20,1).hiddenLines,1);
assert.deepEqual(view('two three four five six',20,0).lines,[]);
assert.deepEqual(view('edited sentence here',11).lines,['edited','sentence','here']);
assert.deepEqual(view('',11).lines,[]);
assert.deepEqual(view('超長い単語😀',1).lines,['超長い単語😀']);
assert.deepEqual(view('repeat repeat repeat',13).lines,['repeat repeat','repeat']);
assert.deepEqual(view('repeat repeat repeat',13).lines,['repeat repeat','repeat']);
assert.deepEqual(view('repeat repeat repeat',6).lines,['repeat','repeat','repeat']);
// Font changes explicitly invalidate measured breaks even if the viewport is unchanged.
let scale=1;
const fontLayout=createCaptionLayout(text=>text.length*scale);
assert.deepEqual(fontLayout.update('one two',{width:8,maxLines:5}).lines,['one two']);
scale=2;
assert.deepEqual(fontLayout.update('one two',{width:8,maxLines:5,reflow:true}).lines,['one','two']);
console.log('caption_box_layout.test.js: ok');

// Stable publisher chunk IDs distinguish real repeated speech from reconnect snapshots.
const streamed=createCaptionLayout(text=>text.length);
const consume=(chunks,width=13,maxLines=3,id='session:mic')=>streamed.update(chunks.map(c=>c.text).join(' '),{
 width,maxLines,stream:{id,chunks},
});
const chunks=['one','two three','four five','six seven'].map((text,i)=>({id:i+1,text}));
consume(chunks.slice(0,1)); consume(chunks.slice(0,2)); consume(chunks.slice(0,3));
const frozen=consume(chunks.slice(1));
assert.deepEqual(frozen.lines,['one two three','four five six','seven']);
assert.deepEqual(consume(chunks.slice(1)).rows,frozen.rows);
assert.deepEqual(consume([{id:5,text:'eight nine ten'}]).lines,['four five six','seven eight','nine ten']);
assert.deepEqual(consume([{id:6,text:'eleven'}],24).lines,['one two three four five','six seven eight nine ten','eleven']);
assert.deepEqual(consume([],24,3,'new-session:mic').lines,[]);
assert.deepEqual(consume([{id:1,text:'again again'}],13,3,'new-session:mic').lines,['again again']);
assert.deepEqual(consume([{id:2,text:'again again'}],13,3,'new-session:mic').lines,['again again','again again']);
for(let id=3;id<500;id++) consume([{id,text:'again again'}],13,3,'new-session:mic');
assert.ok(consume([{id:499,text:'again again'}],13,3,'new-session:mic').hiddenLines<=29);

const edge=createCaptionLayout(text=>text==='one two' ? 100 : 30);
assert.deepEqual(edge.update('one two',{width:100,maxLines:3}).lines,['one two']);
