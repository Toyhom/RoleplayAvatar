import assert from 'node:assert/strict';
import test from 'node:test';
import {actionPose,actionLabels} from '../web/actions.js';

test('bounded clips are deterministic, distinct, and return to rest',()=>{
 const poses=[];
 for(const name of Object.keys(actionLabels)){
  const cue={name,start_s:.2,duration_s:2,strength:1};
  const rest=actionPose([],0);
  assert.deepEqual(actionPose([cue],.1),rest);
  assert.deepEqual(actionPose([cue],2.3),rest);
  const timeline=Array.from({length:20},(_,i)=>actionPose([cue],.2+i*.1));
  assert(timeline.some(p=>Object.entries(p).some(([k,v])=>k!=='active'&&Math.abs(v)>.02)),name);
  assert.deepEqual(timeline,Array.from({length:20},(_,i)=>actionPose([cue],.2+i*.1)));
  poses.push(JSON.stringify(timeline));
 }
 assert.equal(new Set(poses).size,8);
});

test('overlapping clips remain bounded and unknown controls cannot move a resource',()=>{
 const cue={name:'lean_forward',start_s:0,duration_s:2,strength:1};
 assert.equal(actionPose(Array(3).fill(cue),1).lean,.18);
 assert.deepEqual(actionPose([{...cue,name:'arbitrary'}],1),actionPose([],0));
});
