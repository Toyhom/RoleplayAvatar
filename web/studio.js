import {t,locale} from './i18n.js';
const $ = id => document.getElementById(id);
const stages = {queued:t("等待生成"), understanding:t("正在认识你的角色"), illustrating:t("正在绘制角色形象"), modeling:t("正在生成 3D 身体与骨架"), landmarking:t("正在定位脸部细节"), refining:t("正在完善面部材质"), rigging:t("正在适配动作与表情"), voicing:t("正在设计专属声音"), mouth_design:t("正在生成角色口型"), mouth_binding:t("正在配准嘴部与表情"), packaging:t("正在检查角色资源"), complete:t("角色准备好了")};
let fileData=null, uploadFile=null, previewUrl=null, poll=null, currentCharacter=null, audition=null;
function el(tag, text, cls){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;}
async function api(path, options={}){
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...(options.headers??{})}});
  if(!response.ok){let message=t("操作未完成，请稍后重试");try{message=(await response.json()).detail??message;}catch{}throw new Error(typeof message==='string'?t(message):t("请检查输入"));}
  return response.json();
}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;setTimeout(()=>$('toast').hidden=true,5000);}
function close(dialog){$(dialog).close();if(audition){audition.pause();audition=null;}}
$('close-create').onclick=()=>close('create-dialog');$('close-library').onclick=()=>close('library-dialog');
for(const id of ['create-dialog','library-dialog'])$(id).addEventListener('click',event=>{if(event.target===$(id)){const box=$(id).getBoundingClientRect();if(event.clientX<box.left||event.clientX>box.right||event.clientY<box.top||event.clientY>box.bottom)close(id);}});
$('open-create').onclick=async()=>{$('create-dialog').showModal();await refreshJobs().catch(error=>$('creation-error').textContent=t(error.message));};
async function acceptFile(file){
  if(!file)return;
  uploadFile=null;fileData=null;
  if($('creation-source').value==='live2d'){
    if(!file.name.toLowerCase().endsWith('.zip')||file.size>128_000_000){$('creation-error').textContent=t("请选择不超过 128 MB 的 Live2D ZIP");return;}
    uploadFile=file;$('upload-preview').hidden=true;$('upload-hint').hidden=false;$('upload-hint').textContent=file.name;$('creation-error').textContent='';return;
  }
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10_000_000){$('creation-error').textContent=t("请选择不超过 10 MB 的 PNG、JPEG 或 WebP 图片");return;}
  if(previewUrl)URL.revokeObjectURL(previewUrl);previewUrl=URL.createObjectURL(file);
  $('upload-preview').src=previewUrl;$('upload-preview').hidden=false;$('upload-hint').hidden=true;
  fileData=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
  $('creation-error').textContent='';
}
$('character-image').onchange=event=>acceptFile(event.target.files[0]);
$('drop-zone').ondragover=event=>{event.preventDefault();$('drop-zone').classList.add('drag-over');};
$('drop-zone').ondragleave=()=>$('drop-zone').classList.remove('drag-over');
$('drop-zone').ondrop=event=>{event.preventDefault();$('drop-zone').classList.remove('drag-over');const file=event.dataTransfer.files[0];if(file){const data=new DataTransfer();data.items.add(file);$('character-image').files=data.files;acceptFile(file);}};
function updateCreationOptions(){
  const is3d=$('creation-mode').value==='3d';
  $('creation-source').options[1].disabled=is3d;if(is3d)$('creation-source').value='image';
  const native=$('creation-source').value==='live2d';
  fileData=null;uploadFile=null;$('character-image').value='';$('character-image').accept=native?'.zip':'image/png,image/jpeg,image/webp';
  $('upload-preview').hidden=true;$('upload-hint').hidden=false;$('upload-hint').textContent=native?t("选择或拖入完整 Live2D ZIP（最大 128 MB）"):t("选择或拖入角色图片（最大 10 MB）");
  $('creation-help').textContent=native?t("ZIP 需包含 .model3.json、.moc3、纹理以及引用的动作、表情和物理文件。保留目录结构及授权文件。"):t("每个角色只有一种展示类型。需要另一种类型时，请分别创建。");
}
$('creation-mode').onchange=updateCreationOptions;$('creation-source').onchange=updateCreationOptions;
$('create-form').onsubmit=async event=>{
  event.preventDefault();if(!fileData&&!uploadFile)return;
  $('create-submit').disabled=true;$('creation-error').textContent='';
  try{
    const description=$('character-brief').value,voice_candidates=Number($('voice-count').value);
    if($('creation-source').value==='live2d'){await api('/api/characters/import-live2d?'+new URLSearchParams({description,voice_candidates,locale}),{method:'POST',headers:{'Content-Type':'application/zip'},body:uploadFile});}
    else await api('/api/creations',{method:'POST',body:JSON.stringify({description,locale,image_base64:fileData,presentation:$('creation-mode').value,voice_candidates,seed:Math.floor(Math.random()*2**30)})});toast(t("已开始创作。完成后，角色会出现在会客室。"));await refreshJobs();}
  catch(error){$('creation-error').textContent=t(error.message);}
  finally{$('create-submit').disabled=false;}
};
const knownReady=new Set();
async function refreshJobs(){
  const jobs=await api('/api/creations');$('creation-jobs').replaceChildren();
  if(!jobs.length){$('creation-jobs').append(el('p',t("还没有创作。上传第一张图片，开始一段新的故事。"),'empty-jobs'));return;}
  for(const job of jobs){
    const card=el('article',undefined,'creation-job');const img=el('img');const preview=job.preview_url??job.concept_url??job.image_url;if(preview)img.src=preview;img.alt=t("角色创作预览");img.onerror=()=>img.hidden=true;if(!img.getAttribute('src')||img.getAttribute('src')==='undefined')img.hidden=true;
    const content=el('div',undefined,'job-content');content.append(el('h4',job.plan?.display_name??job.description.slice(0,28)));
    let state=stages[job.stage]??t("正在处理");if(job.state==='failed')state=t("这一步未完成");if(job.state==='cancelled')state=t("已取消");if(job.state==='submission_error')state=t("提交待核对");
    content.append(el('p',state,'job-stage'));const track=el('div',undefined,'progress-track'),fill=el('span');fill.style.width=`${job.progress}%`;track.append(fill);content.append(track);
    if(job.error)content.append(el('p',t(job.error),'job-error'));
    if(job.plan?.tagline)content.append(el('small',job.plan.tagline));
    const actions=el('div',undefined,'job-actions');
    if(job.state==='ready'){
      const button=el('button',t("和它聊聊"));button.onclick=async()=>{close('create-dialog');await window.avatarStudio.refresh(job.character_id);};actions.append(button);
      if(!knownReady.has(job.id)){knownReady.add(job.id);window.dispatchEvent(new CustomEvent('avatar:librarychange'));}
    }else if(['queued','running'].includes(job.state)){
      const button=el('button',t("取消"),'text-button');button.onclick=async()=>{button.disabled=true;try{await api(`/api/creations/${job.id}/cancel`,{method:'POST'});await refreshJobs();}catch(error){toast(t(error.message));}};actions.append(button);
    }else if(['failed','cancelled'].includes(job.state)){
      const button=el('button',t("继续生成"),'text-button');button.onclick=async()=>{button.disabled=true;try{await api(`/api/creations/${job.id}/retry`,{method:'POST'});await refreshJobs();}catch(error){toast(t(error.message));button.disabled=false;}};actions.append(button);
    }
    card.append(img,content,actions);$('creation-jobs').append(card);
  }
}
async function openLibrary(){
  const selected=window.avatarStudio?.selected();$('library-dialog').showModal();$('library-feedback').textContent='';
  if(!(selected?.profile.character_id.startsWith('char_')||selected?.profile.character_id.startsWith('sample_'))){$('library-empty').hidden=false;$('library-content').hidden=true;return;}
  $('library-empty').hidden=true;$('library-content').hidden=false;currentCharacter=selected.profile.character_id;
  const provenance=$('asset-provenance');provenance.replaceChildren();
  if(selected.provenance.kind==='external_asset'){for(const source of selected.provenance.sources){const row=document.createElement('p');row.textContent=`${source.component}: ${source.license} · ${source.attribution??source.note??source.source}`;provenance.append(row);if(source.terms){const link=document.createElement('a');link.href=source.terms;link.target='_blank';link.rel='noopener';link.textContent=t("官方资源使用条款");provenance.append(link);}}}
  else provenance.textContent=t("图片生成角色：口型绑定、表情和动作由创建流程自动准备。");
  $('library-title').textContent=selected.profile.display_name;$('edit-name').value=selected.profile.display_name;$('edit-persona').value=selected.profile.persona;
  $('library-image').onerror=()=>{$('library-image').hidden=true;};$('library-image').hidden=!selected.preview_url;if(selected.preview_url)$('library-image').src=selected.preview_url;$('export-character').href=`/api/characters/${currentCharacter}/export`;
  const data=await api(`/api/characters/${currentCharacter}/studio`);
  $('character-tagline').textContent=data.plan.tagline??'';$('voice-reason').textContent=data.plan.voice_reason??'';
  renderVoices(data.voices);
}
function renderVoices(voices){
  $('voice-candidates').replaceChildren();
  for(const voice of voices.candidates){
    const card=el('div',undefined,'voice-card'+(voice.candidate===voices.selected?' selected':''));
    card.append(el('h4',t("声线 {0}",voice.candidate)));
    const listen=el('button',t("▶ 试听"),'text-button');listen.onclick=()=>{if(audition)audition.pause();audition=new Audio(`/api/characters/${currentCharacter}/voice/${voice.candidate}`);audition.play().catch(()=>toast(t("样音暂时无法播放")));};
    const choose=el('button',voice.candidate===voices.selected?t("正在使用"):t("选用这个声音"),'voice-select');choose.disabled=voice.candidate===voices.selected;
    choose.onclick=async()=>{choose.disabled=true;try{const updated=await api(`/api/characters/${currentCharacter}/voice`,{method:'POST',body:JSON.stringify({candidate:voice.candidate})});renderVoices(updated);$('library-feedback').textContent=t("新声音将在下一次回复时生效");await window.avatarStudio.refresh(currentCharacter);}catch(error){toast(t(error.message));choose.disabled=false;}};
    card.append(listen,choose);$('voice-candidates').append(card);
  }
  $('voice-prompt').textContent=t("声音设计：")+voices.candidates.find(v=>v.candidate===voices.selected).prompt;
}
$('open-library').onclick=()=>openLibrary().catch(error=>toast(t(error.message)));
$('save-persona').onclick=async()=>{
  if(!currentCharacter)return;$('save-persona').disabled=true;
  try{await api(`/api/characters/${currentCharacter}`,{method:'PATCH',body:JSON.stringify({display_name:$('edit-name').value,persona:$('edit-persona').value})});$('library-feedback').textContent=t("已保存，下一轮对话将使用新设定");await window.avatarStudio.refresh(currentCharacter);}
  catch(error){$('library-feedback').textContent=t(error.message);}finally{$('save-persona').disabled=false;}
};
async function initialize(){
  const config=await api('/api/studio');if(!config.creation_available){$('create-submit').disabled=true;$('creation-error').textContent=t("角色生成服务尚未配置，请按部署文档启动工作进程");}
  await refreshJobs();poll=setInterval(()=>refreshJobs().catch(()=>{}),5000);
}
initialize().catch(()=>{});
window.addEventListener('beforeunload',()=>{clearInterval(poll);if(previewUrl)URL.revokeObjectURL(previewUrl);});
