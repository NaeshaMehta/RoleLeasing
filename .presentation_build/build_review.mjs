import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation,PresentationFile} from 'file:///C:/Users/arkob/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs';
import {slides,mainCount} from './review_content.mjs';
import {renderReview,tableOwners} from './review_render.mjs';
const root=path.resolve('.'),build=path.join(root,'.presentation_build'),out=path.join(root,'Project_Presentation_Output');
const skill='C:/Users/arkob/.codex/plugins/cache/openai-primary-runtime/presentations/26.1013.11914/skills/presentations';
const p=Presentation.create({slideSize:{width:1280,height:720}});
const C={bg:'#F4F6F8',ink:'#112B3C',muted:'#526775',teal:'#007F7B',blue:'#2269A0',white:'#FFFFFF',line:'#C9D6DD'};
function text(s,t,x,y,w,h,size=27,color=C.ink,bold=false){const a=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});a.text=t;a.text.style={fontSize:size,typeface:'Arial',color,bold,autoFit:'none',wrap:'square',insets:0};return a;}
function box(s,t,x,y,w,h,color=C.teal){const a=s.shapes.add({geometry:'rect',position:{left:x,top:y,width:w,height:h},fill:color,line:{fill:color,width:1}});a.text=t;a.text.style={fontSize:24,typeface:'Arial',color:C.white,alignment:'center',verticalAlignment:'middle',insets:10};return a;}
function connect(s,a,b,side='right'){s.shapes.connect(a,b,{kind:'straight',fromSide:side,toSide:side==='right'?'left':'top',line:{fill:C.muted,width:2},tail:{type:'triangle'}});}
await fs.mkdir(path.join(build,'renders_review'),{recursive:true});
for(let i=0;i<slides.length;i++){
 const d=slides[i],s=p.slides.add();s.background.fill=C.bg;
 if(d.kind==='cover'){
  s.background.fill=C.ink;text(s,'TECHNICAL PROJECT REVIEW',72,72,1100,36,21,'#66D5C9',true);text(s,d.title,72,160,1120,180,62,C.white,true);text(s,d.body,76,385,1100,240,26,'#D9E6EC');
 }else{
  text(s,d.title,64,56,1150,88,42,C.ink,true);
  if(d.kind==='viva')d.body.forEach(({q,a},j)=>{text(s,q,72,170+j*112,1130,34,27,C.teal,true);text(s,a,72,210+j*112,1130,65,24);});
  else{
   const status=renderReview(s,d,{text,box,connect,C},i+1);
   if(status==='image'){
    const bytes=await fs.readFile(path.join(root,d.image));s.images.add({blob:bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength),contentType:'image/png',alt:'Original supplied simulation figure',position:{left:140,top:149,width:1000,height:460},fit:'contain'});
    text(s,d.interpretation,72,615,1136,42,22,C.muted);
   }
  }
 }
 text(s,String(i+1).padStart(2,'0')+(i<mainCount?' / 12':' / appendix'),1120,681,120,24,16,d.kind==='cover'?'#B8D4DD':C.muted);
 if(d.kind!=='cover')text(s,d.source.length>148?d.source.slice(0,145)+'...':d.source,64,685,1040,25,13,C.muted);
 s.speakerNotes.text=d.notes+'\n\nImplementation evidence: '+d.source+'\n\nPanel prompt: '+(i<mainCount?'Explain the implementation boundary and how the evidence supports this slide.':'Use this supporting slide to answer a focused technical question.');
}
const candidate=path.join(build,'candidate_review.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
await fs.writeFile(path.join(build,'review_slides.json'),JSON.stringify(slides,null,2));
console.log('Exported',slides.length,'slides,',mainCount,'main');
for(let i=0;i<p.slides.items.length;i++){
 const blob=await p.export({slide:p.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(build,'renders_review',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));if(i%10===0)console.log('Rendered',i+1);
}
const {finalizePresentation}=await import('file:///'+skill+'/container_tools/artifact_tool_utils.mjs');
const result=await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:path.join(out,'Project_Presentation_Review_Final.pptx'),pythonExecutable:'C:/Users/arkob/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',...tableOwners.flatMap(n=>['--require-native-table-slide',String(n)])],requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:[11],nativeChartTargetApplication:'powerpoint',materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Arial']},verifyArtifactToolImport:true,receiptPath:path.join(build,'validation_review_final.json')});
console.log('Finalized',result.finalPath,result.presentationLayout.findingCount,'layout findings');

