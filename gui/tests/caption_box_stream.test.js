const assert=require('node:assert/strict');
const {createLiveCaptionBridge}=require('../lib/live_caption_bridge');
const {normalizeOverlayPayload}=require('../lib/overlay_payload_contract');
const {overlayPayloadForBox,createInitialOverlayPayload}=require('../lib/overlay_runtime_state');
const {registerOverlayIpcHandlers}=require('../lib/overlay_ipc_handlers');
const {createCaptionLayout}=require('../lib/caption_box_layout');
const handlers=new Map();
let payload=createInitialOverlayPayload();
const layout=createCaptionLayout(text=>text.length);
const observed=[];
let savedStream;
registerOverlayIpcHandlers({
 ipcMain:{handle:(name,fn)=>handlers.set(name,fn)},normalizeOverlayPayload,
 getOverlayPayload:()=>payload,setOverlayPayload:value=>{payload=value;},
 overlayClients:new Map([[{write(line){
  const value=JSON.parse(line.slice(6)); savedStream=value.captionStream;
  observed.push(layout.update(value.text,{width:13,maxLines:3,stream:value.captionStream}));
 }},'mic']]),
 overlayPayloadForBox:(key,value)=>overlayPayloadForBox(value,key),encodeOverlay:JSON.stringify,
 getOverlayPort:()=>8790,getMainWindow:()=>null,getOverlayTestStreamEnabled:()=>false,setOverlayTestStreamEnabled(){},
});
const bridge=createLiveCaptionBridge({send:value=>handlers.get('set-overlay-text')(null,value),onEvent(){},onError:error=>{throw error;},getDelaySeconds:()=>0});
const send=text=>bridge.ingest(`EVENT:${JSON.stringify({type:'segment',text})}\n`,'mic');
bridge.start();
for(const text of ['one','two three','four five','six seven']) send(text);
assert.equal(payload.boxes.mic.text,'two three four five six seven');
assert.deepEqual(observed.at(-1).lines,['one two three','four five six','seven']);
assert.equal(savedStream.chunks.length,3);
// SSE reconnect replays a snapshot: do not append its chunks twice.
const replay=layout.update(payload.boxes.mic.text,{width:13,maxLines:3,stream:savedStream});
assert.deepEqual(replay.rows,observed.at(-1).rows);
const oldEpoch=savedStream.id;
bridge.stop();assert.deepEqual(observed.at(-1).lines,[]);
bridge.start();assert.notEqual(savedStream.id,oldEpoch);
for(let i=0;i<5;i++) send('again again');
assert.deepEqual(observed.at(-1).lines,['again again','again again','again again']);
assert.equal(savedStream.chunks.at(-1).id,5,'identical rolling text must still publish new chunk identities');
console.log('caption_box_stream.test.js: ok');
