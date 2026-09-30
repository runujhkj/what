const assert=require('node:assert/strict');
const {createCaptionView}=require('../lib/caption_box_view');
const container={children:[],appendChild(node){this.children.push(node);},getBoundingClientRect(){return {top:0};}};
container.ownerDocument={createElement(){return {
 style:{},textContent:'',animations:[],
 remove(){container.children=container.children.filter(node=>node!==this);},
 getBoundingClientRect(){return {top:Number(this.style.transform.match(/-?[\d.]+/)[0])};},
 animate(frames,options){const animation={frames,options,cancel(){this.cancelled=true;}};this.animations.push(animation);return animation;},
};}};
const view=createCaptionView(container,{lineHeight:40});
view.render([{id:1,text:'one two'},{id:2,text:'three four'}],{reset:true});
const [one,two]=container.children;
view.render([{id:1,text:'one two'},{id:2,text:'three four five'}]);
assert.equal(container.children[0],one);
assert.equal(container.children[1],two);
assert.equal(one.animations.length,0);
view.render([{id:2,text:'three four five'},{id:3,text:'six'}]);
assert.equal(two.style.transform,'translateY(0px)');
assert.deepEqual(two.animations[0].frames,[{transform:'translateY(40px)'},{transform:'translateY(0px)'}]);
assert.equal(two.animations[0].options.duration,180);
assert.equal(one.style.transform,'translateY(-40px)');
one.animations[0].onfinish();
assert.ok(!container.children.includes(one));
const newest=container.children.find(node=>node.textContent==='six');
assert.deepEqual(newest.animations[0].frames,[{transform:'translateY(80px)'},{transform:'translateY(40px)'}]);
view.render([{id:2,text:'three four five'},{id:3,text:'six seven'}]);
assert.equal(two.animations.length,1,'arrival without rollover must not restart scroll');
view.render([],{reset:true});
assert.equal(container.children.length,0);
const reduced=createCaptionView(container,{lineHeight:40,reducedMotion:true});
reduced.render([{id:1,text:'one'},{id:2,text:'two'}]);
const reducedTwo=container.children[1];
reduced.render([{id:2,text:'two'},{id:3,text:'three'}]);
assert.equal(reducedTwo.animations.length,0);
assert.equal(container.children.length,2);
console.log('caption_box_view.test.js: ok');

reduced.render([],{reset:true});
const stalled=createCaptionView(container,{lineHeight:40});
for(let id=1;id<100;id++) stalled.render([{id,text:'same words'}]);
assert.ok(container.children.length<=5,'suspended animations must not retain unbounded outgoing lines');
