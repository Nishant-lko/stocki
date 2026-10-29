const pptxgen = require('pptxgenjs');
const pptx = new pptxgen();
pptx.layout = 'LAYOUT_16x9';
pptx.author = 'Slotwise Hackathon Team';
pptx.subject = 'Live demo of warehouse slotting prototype';
pptx.title = 'Slotwise — Smarter warehouse slotting';
pptx.company = 'Hackathon Prototype';
pptx.lang = 'en-IN';
pptx.theme = { headFontFace: 'Aptos Display', bodyFontFace: 'Aptos', lang: 'en-US' };
pptx.defineSlideMaster({ title: 'CONTENT', background: { color: 'F7F9FC' }, objects: [
  { rect: { x: 0, y: 0, w: 10, h: 0.1, line: { color: '0077B6', transparency: 100 }, fill: { color: '0077B6' } } },
  { text: { text: 'SLOTWISE  /  HACKATHON DEMO', options: { x: 0.5, y: 5.25, w: 4.8, h: 0.2, fontFace: 'Aptos', fontSize: 8, color: '64748B', charSpacing: 1.2, margin: 0 } } },
  { text: { text: 'PRODUCT WALKTHROUGH', options: { x: 7.2, y: 5.25, w: 2.3, h: 0.2, fontFace: 'Aptos', fontSize: 8, color: '64748B', charSpacing: 1.2, align: 'right', margin: 0 } } }
], slideNumber: { x: 9.65, y: 5.2, color: 'FFFFFF', fill: { color: '0077B6' }, fontFace: 'Aptos', fontSize: 9, radius: 0.15, rect: { x: 9.7, y: 5.16, w: 0.25, h: 0.25 } } });
const C = { navy:'023047', blue:'0077B6', cyan:'8ECAE6', gold:'FFB703', orange:'FB8500', ink:'17324D', muted:'64748B', bg:'F7F9FC', white:'FFFFFF', line:'DCE5EF', green:'2A9D8F', red:'E76F51', pale:'EAF4F8', paleGold:'FFF4D4', dark:'001D3D' };
const shape = pptx.ShapeType;
function text(s,t,x,y,w,h,opt={}) { s.addText(t,{x,y,w,h,fontFace:'Aptos',fontSize:opt.fs||14,color:opt.color||C.ink,bold:!!opt.bold,margin:0,breakLine:false,fit:'shrink',valign:opt.valign||'mid',align:opt.align||'left',paraSpaceAfterPt:0,transparency:opt.transparency||0,...opt}); }
function box(s,x,y,w,h,fill=C.white,line=C.line,r=0.12){s.addShape(shape.roundRect,{x,y,w,h,rectRadius:r,line:{color:line,width:0.8},fill:{color:fill},radius:r});}
function title(s,kicker,heading,sub){text(s,kicker.toUpperCase(),0.55,0.35,8.8,0.22,{fs:9,bold:true,color:C.blue,charSpacing:1.6});text(s,heading,0.55,0.66,8.9,0.48,{fs:27,bold:true,color:C.navy});if(sub)text(s,sub,0.57,1.19,8.8,0.3,{fs:11.5,color:C.muted});}
function pill(s,label,x,y,w,color=C.blue){s.addShape(shape.roundRect,{x,y,w,h:0.29,rectRadius:0.12,line:{color,transparency:100},fill:{color,transparency:88}});text(s,label,x+0.08,y+0.02,w-0.16,0.23,{fs:8.5,bold:true,color});}
function line(s,x1,y1,x2,y2,color=C.line,width=1,dash){s.addShape(shape.line,{x:x1,y:y1,w:x2-x1,h:y2-y1,line:{color,width,...(dash?{dashType:'dash'}:{})}})}

// 1 Cover — Cover Page
{
 const s=pptx.addSlide(); s.background={color:C.dark};
 s.addShape(shape.rect,{x:6.85,y:0,w:3.15,h:5.625,line:{color:C.blue,transparency:100},fill:{color:C.blue,transparency:74}});
 s.addShape(shape.rect,{x:8.15,y:0,w:1.85,h:5.625,line:{color:C.cyan,transparency:100},fill:{color:C.cyan,transparency:65}});
 // Warehouse aisle motif
 for(let i=0;i<4;i++){const x=7.12+i*.63;s.addShape(shape.rect,{x,y:1.22,w:0.38,h:3.65,line:{color:'FFFFFF',transparency:75,width:1},fill:{color:'FFFFFF',transparency:100}});for(let j=0;j<5;j++){s.addShape(shape.rect,{x:x+0.04,y:1.45+j*.64,w:0.3,h:0.35,line:{color:'FFFFFF',transparency:80,width:0.7},fill:{color:j===2?C.gold:C.cyan,transparency:25}})}}
 text(s,'HACKATHON BUILD  /  LIVE DEMO',0.65,0.78,5.8,0.28,{fs:10,bold:true,color:C.gold,charSpacing:1.5});
 text(s,'Slotwise',0.62,1.45,5.9,0.9,{fs:54,bold:true,color:C.white});
 text(s,'Smarter warehouse slotting,\nwith safety built in.',0.68,2.5,5.7,0.85,{fs:22,bold:true,color:'DCEAF5',breakLine:false});
 text(s,'Turn order history into a feasible, demand-aware storage plan.',0.7,3.63,5.5,0.56,{fs:13,color:'C4D4E1',breakLine:false});
 pill(s,'DATA → INSIGHT → SAFE PLACEMENT',0.7,4.55,2.85,C.cyan);
 text(s,'Prototype status: validated baseline; optimization comparison is next.',0.7,5.05,6.0,0.26,{fs:9,color:'C4D4E1'});
}
// 2 Problem + value — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'01  /  THE PROBLEM','Every pick starts with a placement decision','A good location reduces walking. A valid location must also respect the warehouse.');
 const cards=[['01','Demand','Fast movers deserve accessible positions.','Orders reveal what is picked often.'],['02','Affinity','Basket companions should sit near one another.','Co-occurrence turns orders into proximity evidence.'],['03','Feasibility','A short route is useless if the slot is unsafe.','Fit, load, height and hazard rules constrain placement.']];
 cards.forEach((c,i)=>{let x=.58+i*3.05;box(s,x,1.9,2.8,2.28);text(s,c[0],x+.2,2.12,.5,.4,{fs:23,bold:true,color:C.blue});text(s,c[1],x+.2,2.65,2.35,.34,{fs:19,bold:true,color:C.navy});text(s,c[2],x+.2,3.13,2.4,.57,{fs:12,bold:true});text(s,c[3],x+.2,3.78,2.35,.32,{fs:9.5,color:C.muted});});
 box(s,.58,4.48,8.85,.53,C.navy,C.navy);text(s,'Slotwise combines order patterns with hard physical rules to build a usable starting layout.',.82,4.59,8.35,.28,{fs:12,bold:true,color:C.white,align:'center'});
}
// 3 Product flow — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'02  /  HOW IT WORKS','From transactions to a warehouse-ready baseline','A reproducible Python pipeline produces immutable run artifacts for the Streamlit demo.');
 const nodes=[['01','INGEST','Online Retail II\ntransactions'],['02','PREPARE','Clean + split\nchronologically'],['03','ANALYZE','ABC demand +\nbasket affinity'],['04','ALLOCATE','Feasible\nbaseline layout'],['05','INSPECT','Interactive\nStreamlit views']];
 nodes.forEach((n,i)=>{const x=.55+i*1.88;box(s,x,2.0,1.58,1.48,i===3?C.paleGold:C.white,i===3?C.gold:C.line);text(s,n[0],x+.16,2.16,.4,.25,{fs:10,bold:true,color:C.blue});text(s,n[1],x+.16,2.49,1.25,.25,{fs:10,bold:true,color:C.navy,charSpacing:.5});text(s,n[2],x+.16,2.88,1.25,.5,{fs:10,color:C.muted,breakLine:false});if(i<4){line(s,x+1.62,2.75,x+1.82,2.75,C.blue,1.6);s.addShape(shape.chevron,{x:x+1.73,y:2.65,w:.18,h:.2,line:{color:C.blue,transparency:100},fill:{color:C.blue}})}});
 text(s,'TECH STACK',.65,4.07,1.2,.22,{fs:9,bold:true,color:C.blue,charSpacing:1.4});
 [['PYTHON','pipeline'],['PANDAS','tables'],['PARQUET','run bundles'],['STREAMLIT','dashboard'],['PLOTLY','charts']].forEach((v,i)=>{const x=.65+i*1.82;box(s,x,4.4,1.55,.46,C.white);text(s,v[0],x+.1,4.48,1.35,.14,{fs:8.5,bold:true,color:C.navy,align:'center'});text(s,v[1],x+.1,4.64,1.35,.13,{fs:7.5,color:C.muted,align:'center'});});
}
// 4 Evidence — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'03  /  WHAT THE DATA SAYS','A real order history gives the prototype its signal','Current saved run: UCI Online Retail II; physical SKU and warehouse attributes are synthetic scenario data.');
 const metrics=[['123,818','order lines'],['150','active SKUs'],['240','warehouse bins'],['0','baseline violations']];
 metrics.forEach((m,i)=>{const x=.58+i*2.22;box(s,x,1.78,2.0,.92);text(s,m[0],x+.16,1.94,1.68,.39,{fs:25,bold:true,color:i===3?C.green:C.navy,align:'center'});text(s,m[1].toUpperCase(),x+.13,2.43,1.74,.14,{fs:8,bold:true,color:C.muted,align:'center',charSpacing:.7});});
 // Demand bars and affinity callout
 text(s,'TRAIN-SPLIT DEMAND',.68,3.02,2.7,.22,{fs:9,bold:true,color:C.blue,charSpacing:1.2});
 text(s,'ABC classes group products by cumulative pick frequency.',.68,3.3,4.1,.3,{fs:11,color:C.ink});
 const bars=[['A',.8,C.green],['B',.15,C.gold],['C',.05,C.red]]; bars.forEach((b,i)=>{let y=3.82+i*.38;text(s,b[0],.7,y,.22,.22,{fs:10,bold:true,color:b[2]});s.addShape(shape.roundRect,{x:1.0,y:y+.03,w:2.75,h:.16,rectRadius:.06,line:{color:C.line,transparency:100},fill:{color:C.line}});s.addShape(shape.roundRect,{x:1.0,y:y+.03,w:2.75*b[1],h:.16,rectRadius:.06,line:{color:b[2],transparency:100},fill:{color:b[2]}});text(s,['~80%','~15%','~5%'][i],3.88,y,0.62,.22,{fs:9,bold:true,color:C.ink});});
 box(s,5.1,3.03,4.25,1.63,C.navy,C.navy);pill(s,'AFFINITY EXAMPLE',5.35,3.27,1.35,C.gold);text(s,'22386  +  85099B',5.35,3.72,3.6,.34,{fs:19,bold:true,color:C.white});text(s,'Ordered together in 555 training baskets',5.35,4.14,3.55,.24,{fs:11,color:'DCEAF5'});
 text(s,'Chronological split: train 10,294  ·  validation 3,295  ·  test 3,199 orders',.68,4.9,8.4,.22,{fs:9,color:C.muted});
}
// 5 Safety — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'04  /  SAFETY BY DESIGN','The allocator works inside a rules envelope','Independent validation recomputes the assignment checks before a run is saved.');
 const rules=[['FIT','Stock quantities must pack into the bin volume and dimensions.'],['LOAD','Bin, shelf and rack weight limits are enforced.'],['HEIGHT','Heavy and fragile products follow shelf-level restrictions.'],['ISOLATION','Hazardous inventory stays in its designated zone with clearance.']];
 rules.forEach((r,i)=>{const y=1.8+i*.72;box(s,.62,y,5.2,.57);pill(s,r[0],.82,y+.13,1.05,i===3?C.orange:C.blue);text(s,r[1],2.08,y+.12,3.5,.32,{fs:10.5,color:C.ink});});
 // schematic rack
 box(s,6.35,1.8,2.95,2.98,C.white);text(s,'WAREHOUSE SLOT',6.62,2.02,2.4,.22,{fs:9,bold:true,color:C.blue,align:'center',charSpacing:1});
 for(let level=0;level<4;level++){const y=2.42+level*.48;s.addShape(shape.rect,{x:6.74,y,w:2.15,h:.36,line:{color:C.line,width:1},fill:{color:level===1?C.paleGold:C.pale}});text(s,['HEAVY / LOW','GOLDEN ZONE','LIGHT / REACH','RISK CHECK'][level],6.84,y+.08,1.95,.18,{fs:8,bold:true,color:level===1?'9A6500':C.muted,align:'center'});}
 line(s,6.62,4.48,9.05,4.48,C.navy,2);text(s,'AISLE / PICKER PATH',6.78,4.56,2.1,.16,{fs:8,bold:true,color:C.navy,align:'center'});
 box(s,.62,4.82,8.68,.34,'E7F5EF','B7E2CE');text(s,'CURRENT SAVED BASELINE  ·  150 / 150 products placed  ·  0 detected violations',.85,4.89,8.2,.18,{fs:9.5,bold:true,color:'207A58',align:'center'});
}
// 6 Demo walk-through — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'05  /  DEMO WALKTHROUGH','Show the evidence, then inspect the placement','A simple order for the live product tour.');
 // UI mock panel
 box(s,.58,1.75,5.38,3.05,C.white,C.line);s.addShape(shape.rect,{x:.58,y:1.75,w:5.38,h:.38,line:{color:C.navy,transparency:100},fill:{color:C.navy}});text(s,'SLOTWISE  ·  COMPLETED RUN',.8,1.86,3.1,.15,{fs:8,bold:true,color:C.white,charSpacing:.8});
 ['Start here','What customers buy','Where products are stored','Safety checks'].forEach((v,i)=>{const x=.82+(i%2)*2.45,y=2.34+Math.floor(i/2)*.92;box(s,x,y,2.16,.67,i===0?C.pale:C.white,i===0?C.blue:C.line);text(s,v,x+.13,y+.12,1.89,.18,{fs:9.5,bold:true,color:C.navy});if(i===0)text(s,'150 SKUs   ·   240 bins\n0 safety issues',x+.13,y+.35,1.8,.25,{fs:8,color:C.muted,breakLine:false});else text(s,['','Pareto + pairs','Shelf map','Rule results'][i],x+.13,y+.38,1.8,.16,{fs:8,color:C.muted});});
 // steps
 const steps=[['1','Start here','Explain scope, data provenance and chronological split.'],['2','What customers buy','Show demand groups and one frequent basket pair.'],['3','Where products are stored','Inspect a shelf, hover a SKU and explain accessibility.'],['4','Safety checks','Close on zero violations and the physical rules.']];
 steps.forEach((a,i)=>{const y=1.83+i*.75; s.addShape(shape.ellipse,{x:6.35,y:y+.05,w:.34,h:.34,line:{color:C.blue,transparency:100},fill:{color:C.blue}});text(s,a[0],6.35,y+.1,.34,.18,{fs:9,bold:true,color:C.white,align:'center'});text(s,a[1],6.86,y,2.2,.25,{fs:12,bold:true,color:C.navy});text(s,a[2],6.86,y+.3,2.45,.35,{fs:9.5,color:C.muted});});
}
// 7 Truthful close / next step — Summary
{
 const s=pptx.addSlide('CONTENT');title(s,'06  /  CLOSE','A safe foundation for measurable optimization','The next product slice is to compare a demand-aware layout against this same validated baseline.');
 box(s,.62,1.85,4.05,2.75,C.navy,C.navy);text(s,'BUILT TODAY',.9,2.12,3.4,.25,{fs:10,bold:true,color:C.gold,charSpacing:1.4});
 ['Real historical order pipeline','Train-only demand + affinity EDA','Feasible 150-SKU baseline','Interactive dashboard + run artifacts'].forEach((v,i)=>{s.addShape(shape.ellipse,{x:.93,y:2.65+i*.4,w:.12,h:.12,line:{color:C.cyan,transparency:100},fill:{color:C.cyan}});text(s,v,1.2,2.59+i*.4,3.0,.22,{fs:10,color:C.white});});
 box(s,5.0,1.85,4.35,2.75,C.white,C.line);text(s,'NEXT TO DEMONSTRATE',5.3,2.12,3.6,.25,{fs:10,bold:true,color:C.blue,charSpacing:1.4});
 ['Feasible relocate / swap search','Baseline vs optimized pick path','Held-out travel and time metrics','Measured trade-offs, no assumed gains'].forEach((v,i)=>{s.addShape(shape.ellipse,{x:5.33,y:2.65+i*.4,w:.12,h:.12,line:{color:C.gold,transparency:100},fill:{color:C.gold}});text(s,v,5.6,2.59+i*.4,3.35,.22,{fs:10,color:C.ink});});
 text(s,'The claim we can support now',.72,4.84,2.0,.18,{fs:9,bold:true,color:C.blue});text(s,'Every active product has a legal starting slot, and the rules are independently checked.',2.65,4.8,6.55,.32,{fs:11,bold:true,color:C.navy});
}
// 8 Detailed pipeline — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'07  /  PIPELINE','A reproducible run moves through five explicit stages','Each stage writes typed tables or validation evidence that downstream views can inspect.');
 const stages=[
  ['01  SOURCE','UCI Online Retail II ZIP','XLSX sheet → canonical order lines','openpyxl · pandas'],
  ['02  PREP','Clean + deduplicate','Chronological 60 / 20 / 20 split','pandas · Python'],
  ['03  SIGNAL','150 SKU cohort','ABC demand + basket pair metrics','pandas · NumPy'],
  ['04  SLOT','Generate scenario + allocate','Fit, weight, height, hazard checks','Python · rules'],
  ['05  PUBLISH','Immutable run bundle','Parquet tables + JSON manifest','PyArrow · JSON'],
 ];
 stages.forEach((a,i)=>{const x=.55+i*1.88;box(s,x,1.88,1.61,1.8,i===4?C.paleGold:C.white,i===4?C.gold:C.line);text(s,a[0],x+.14,2.05,1.32,.22,{fs:9,bold:true,color:C.blue,charSpacing:.5});text(s,a[1],x+.14,2.4,1.33,.48,{fs:12,bold:true,color:C.navy,breakLine:false});text(s,a[2],x+.14,2.98,1.33,.39,{fs:9,color:C.ink,breakLine:false});text(s,a[3],x+.14,3.48,1.33,.14,{fs:7.5,bold:true,color:C.muted});if(i<4){line(s,x+1.65,2.78,x+1.82,2.78,C.blue,1.5);s.addShape(shape.chevron,{x:x+1.74,y:2.69,w:.15,h:.18,line:{color:C.blue,transparency:100},fill:{color:C.blue}})}});
 box(s,.58,4.02,8.84,.78,C.navy,C.navy);text(s,'DASHBOARD READS THE SAVED BUNDLE',.83,4.19,2.65,.2,{fs:9,bold:true,color:C.gold,charSpacing:.8});text(s,'Streamlit + Plotly render summary metrics, demand / affinity views, shelf maps and safety results.',3.55,4.15,5.53,.34,{fs:10,color:C.white});
 text(s,'Run identity includes the configuration hash; validation is recomputed before the bundle is marked complete.',.68,4.93,8.55,.2,{fs:9,color:C.muted});
}
// 9 System architecture + stack — Content
{
 const s=pptx.addSlide('CONTENT');title(s,'08  /  ARCHITECTURE & STACK','A compact Python system with clear data boundaries','One local pipeline creates versioned artifacts; the dashboard reads them for interactive inspection.');
 // Left: architecture flow
 const blocks=[
  {y:1.78,label:'INPUTS',detail:'Online Retail II ZIP  ·  YAML config',color:C.pale},
  {y:2.5,label:'PIPELINE',detail:'ingest → EDA → baseline allocator → validator',color:C.paleGold},
  {y:3.22,label:'RUN BUNDLE',detail:'Parquet tables  ·  JSON manifest + validation',color:C.pale},
  {y:3.94,label:'DEMO UI',detail:'Streamlit tabs  ·  Plotly charts',color:C.pale},
 ];
 blocks.forEach((b,i)=>{box(s,.62,b.y,4.35,.54,b.color,i===1?C.gold:C.line);text(s,b.label,.82,b.y+.09,1.1,.17,{fs:8.5,bold:true,color:C.blue,charSpacing:.8});text(s,b.detail,1.95,b.y+.08,2.77,.25,{fs:9.4,color:C.ink});if(i<blocks.length-1){line(s,2.8,b.y+.55,2.8,b.y+.68,C.blue,1.4);s.addShape(shape.chevron,{x:2.72,y:b.y+.64,w:.16,h:.15,line:{color:C.blue,transparency:100},fill:{color:C.blue}})}});
 pill(s,'CURRENT: VALIDATED BASELINE',.9,4.72,2.25,C.green);
 // Right: stack detail
 box(s,5.28,1.78,4.08,3.18,C.white,C.line);text(s,'TECH STACK',5.57,2.0,3.48,.24,{fs:11,bold:true,color:C.navy,charSpacing:1});
 const stack=[
  ['LANGUAGE','Python 3.11+'],['DATA','pandas · NumPy · PyArrow'],['INGEST','openpyxl · ZIP / XLSX'],['CONFIG','PyYAML · YAML'],['UI + CHARTS','Streamlit · Plotly'],['QUALITY','pytest · Ruff (dev tools)'],['PACKAGE','setuptools · CLI entry point']
 ];
 stack.forEach((a,i)=>{const y=2.4+i*.32;text(s,a[0],5.58,y,1.05,.18,{fs:7.5,bold:true,color:C.blue,charSpacing:.4});text(s,a[1],6.68,y,2.36,.2,{fs:9.1,color:C.ink});if(i<stack.length-1)line(s,5.58,y+.27,9.02,y+.27,C.line,.5)});
 text(s,'Optimization / route comparison is the next implementation slice; it is not part of this saved baseline run.',.68,5.02,8.7,.17,{fs:8.5,color:C.muted});
}

pptx.writeFile({fileName: __dirname + '/output/Slotwise_Hackathon_Demo.pptx'});
