const pptxgen = require('pptxgenjs');
const pptx = new pptxgen();
pptx.defineLayout({ name: 'SLOTWISE_WIDE', width: 13.333, height: 7.5 });
pptx.layout = 'SLOTWISE_WIDE';
pptx.author = 'Slotwise Hackathon Team';
pptx.subject = 'Judge presentation: product, data, algorithms and evaluation';
pptx.title = 'Slotwise — warehouse slotting, explained';
pptx.company = 'Slotwise';
pptx.lang = 'en-IN';
pptx.theme = { headFontFace: 'Aptos Display', bodyFontFace: 'Aptos', lang: 'en-IN' };

const W=13.333, H=7.5, S=pptx.ShapeType;
const C={navy:'102A43',ink:'243B53',muted:'627D98',blue:'1976A8',cyan:'65C3D0',mint:'DDF4EF',bg:'F5F8FA',white:'FFFFFF',line:'D9E2EC',gold:'F4B942',coral:'E9785B',green:'258A73',pale:'E7F2F8',paleGold:'FFF3D6',soft:'EAF0F4'};

function rect(slide,x,y,w,h,fill=C.white,line=C.line,r=0.12){slide.addShape(S.roundRect,{x,y,w,h,rectRadius:r,line:{color:line,width:0.8},fill:{color:fill}})}
function txt(slide,t,x,y,w,h,o={}){slide.addText(t,{x,y,w,h,fontFace:o.fontFace||'Aptos',fontSize:o.fs||14,color:o.color||C.ink,bold:o.bold||false,margin:0,breakLine:false,fit:'shrink',valign:o.valign||'mid',align:o.align||'left',paraSpaceAfterPt:0,...o});}
function line(slide,x1,y1,x2,y2,color=C.line,width=1,dash){slide.addShape(S.line,{x:x1,y:y1,w:x2-x1,h:y2-y1,line:{color,width,...(dash?{dashType:'dash'}:{})}})}
function badge(slide,n){slide.addShape(S.ellipse,{x:12.27,y:6.86,w:.42,h:.42,line:{color:C.blue,transparency:100},fill:{color:C.blue}});txt(slide,String(n).padStart(2,'0'),12.27,6.86,.42,.42,{fs:10,bold:true,color:C.white,align:'center'});}
function base(slide,n,kicker,title,sub=''){slide.background={color:C.bg};txt(slide,kicker.toUpperCase(),.62,.32,10,.25,{fs:9,bold:true,color:C.blue,charSpacing:1.5});txt(slide,title,.62,.73,12.05,.55,{fs:27,bold:true,color:C.navy});if(sub)txt(slide,sub,.64,1.38,11.9,.37,{fs:12,color:C.muted});txt(slide,'SLOTWISE  /  HACKATHON',.64,7.02,4,.18,{fs:8,bold:true,color:C.muted,charSpacing:1});badge(slide,n);}
function pill(slide,t,x,y,w,color=C.blue){slide.addShape(S.roundRect,{x,y,w,h:.31,rectRadius:.12,line:{color,transparency:100},fill:{color,transparency:89}});txt(slide,t,x+.09,y+.025,w-.18,.25,{fs:9,bold:true,color});}
function metric(slide,x,y,w,big,label,small,color=C.blue){rect(slide,x,y,w,1.22,C.white);txt(slide,big,x+.2,y+.13,w-.4,.46,{fs:27,bold:true,color});txt(slide,label,x+.2,y+.66,w-.4,.24,{fs:11,bold:true,color:C.navy});txt(slide,small,x+.2,y+.94,w-.4,.18,{fs:8.5,color:C.muted});}
function dot(slide,x,y,color=C.cyan,r=.09){slide.addShape(S.ellipse,{x,y,w:r*2,h:r*2,line:{color,transparency:100},fill:{color}})}

// 1 — Cover
{
 const s=pptx.addSlide();s.background={color:C.navy};
 // Warehouse aisle motif, built from native shapes
 for(let i=0;i<5;i++){let x=8.2+i*.88;s.addShape(S.rect,{x,y:1.02,w:.56,h:5.7,line:{color:'6B879D',width:.7,transparency:30},fill:{color:'193B55'}});for(let j=0;j<4;j++){s.addShape(S.rect,{x:x+.08,y:1.34+j*1.24,w:.4,h:.72,line:{color:'8FB7C9',width:.6,transparency:30},fill:{color:j===1&&i===2?C.gold:'39718C'}})}}
 txt(s,'HACKATHON PRODUCT WALKTHROUGH',.78,.86,6.7,.28,{fs:10,bold:true,color:C.cyan,charSpacing:1.7});
 txt(s,'Slotwise',.75,1.65,6.8,1.05,{fs:58,bold:true,color:C.white});
 txt(s,'Warehouse placement that balances\npick speed with physical rules.',.82,2.9,6.3,1.02,{fs:25,bold:true,color:'D9E8F0',breakLine:false});
 txt(s,'Turn order history into a feasible layout, then measure it on later orders.',.83,4.28,6.1,.65,{fs:15,color:'B9CDD9',breakLine:false});
 pill(s,'DEMAND → DECISION → VALIDATION',.84,5.35,3.5,C.cyan);
 txt(s,'A working prototype with transparent assumptions and measured comparisons',.84,6.7,7.1,.25,{fs:10,color:'B9CDD9'});
}
// 2 — Clear problem statement
{
 const s=pptx.addSlide();base(s,2,'01  /  THE PROBLEM','Warehouse locations shape every picking trip','A fast-moving product stored far away adds repeated walking. A convenient slot may still be unsafe or too small.');
 const cards=[['01','Travel waste','Pickers revisit distant aisles for products ordered often.','Order history tells us what is frequently picked.'],['02','Basket spread','Products ordered together can end up far apart.','Co-occurrence gives a signal for nearby placement.'],['03','Physical limits','Weight, size, shelf height and hazard rules are non-negotiable.','A useful plan must be feasible before it is fast.']];
 cards.forEach((a,i)=>{const x=.65+i*4.22;rect(s,x,2.18,3.88,2.56);txt(s,a[0],x+.25,2.43,.55,.36,{fs:22,bold:true,color:C.blue});txt(s,a[1],x+.25,2.98,3.3,.34,{fs:19,bold:true,color:C.navy});txt(s,a[2],x+.25,3.48,3.35,.52,{fs:12,bold:true});txt(s,a[3],x+.25,4.15,3.32,.39,{fs:10,color:C.muted});});
 rect(s,.65,5.2,12.0,.79,C.navy,C.navy);txt(s,'The need: put high-demand products in sensible reach, while keeping every assignment legal.',.95,5.42,11.4,.32,{fs:16,bold:true,color:C.white,align:'center'});
}
// 3 — Product and users
{
 const s=pptx.addSlide();base(s,3,'02  /  THE PRODUCT','Slotwise turns warehouse data into a decision you can inspect','For a warehouse planner: start with demand and warehouse facts, get a layout, then review its trade-offs.');
 const labels=[['INPUT','Transactions\nProduct facts\nBin map + rules'],['ANALYZE','Demand classes\nBasket affinity\nLegal bin options'],['DECIDE','Search for a\nlow-cost layout'],['REVIEW','Route comparison\nRule validation\nFeature explanations']];
 labels.forEach((a,i)=>{let x=.7+i*3.15;rect(s,x,2.22,2.55,2.15,i===2?C.paleGold:C.white,i===2?C.gold:C.line);pill(s,a[0],x+.18,2.43,1.05,i===2?C.coral:C.blue);txt(s,a[1],x+.2,2.98,2.17,.95,{fs:15,bold:true,color:C.navy,breakLine:false});if(i<3){line(s,x+2.58,3.28,x+3.02,3.28,C.cyan,2);s.addShape(S.chevron,{x:x+2.91,y:3.15,w:.24,h:.25,line:{color:C.cyan,transparency:100},fill:{color:C.cyan}})}});
 txt(s,'Useful outputs',.75,4.88,2,.28,{fs:12,bold:true,color:C.blue});
 ['A complete product-to-bin assignment','Why the optimizer prefers the layout','How a separate forest proposal performs'].forEach((t,i)=>{dot(s,2.95,4.93+i*.36,i===2?C.gold:C.green,.055);txt(s,t,3.18,4.86+i*.36,8.5,.24,{fs:12,color:C.ink});});
}
// 4 — Requirements / data model
{
 const s=pptx.addSlide();base(s,4,'03  /  DATA & STORAGE','What the product needs—and how this build stores it','The current persistence layer is a reproducible file-based run bundle, not a live database service.');
 const x1=.7,x2=6.85;rect(s,x1,2.05,5.78,3.65,C.white);rect(s,x2,2.05,5.78,3.65,C.white);
 txt(s,'Required inputs',x1+.28,2.3,4.9,.36,{fs:19,bold:true,color:C.navy});
 [['Order lines','order ID · SKU · quantity · time'],['Product facts','weight · dimensions · handling · stock'],['Warehouse facts','bins · coordinates · levels · capacities'],['Operating rules','hazmat zone · load limits · reach penalties']].forEach((a,i)=>{let y=2.9+i*.6;dot(s,x1+.3,y+.08,i===3?C.gold:C.cyan,.06);txt(s,a[0],x1+.5,y,1.48,.25,{fs:11,bold:true});txt(s,a[1],x1+2.05,y,3.38,.28,{fs:10,color:C.muted});});
 txt(s,'Run bundle (Parquet + JSON)',x2+.28,2.3,5.0,.36,{fs:19,bold:true,color:C.navy});
 const files=[['orders.parquet','cleaned lines + chronological split'],['skus / locations','product and bin dimensions'],['abc / affinity','demand + basket relationships'],['assignments','baseline, optimized, ML proposal'],['metrics + manifest','scores, rules, seed, source hash']];
 files.forEach((a,i)=>{let y=2.88+i*.48;txt(s,a[0],x2+.3,y,1.7,.24,{fs:10,bold:true,color:C.blue,fontFace:'Aptos Mono'});txt(s,a[1],x2+2.05,y,3.3,.24,{fs:9.5,color:C.muted});});
 rect(s,.7,5.95,11.93,.58,C.pale,C.pale);txt(s,'Why it helps a demo: each run can be reopened and traced to its source, configuration and random seeds.',.96,6.12,11.4,.26,{fs:11,bold:true,color:C.navy,align:'center'});
}
// 5 — End-to-end pipeline
{
 const s=pptx.addSlide();base(s,5,'04  /  END-TO-END PIPELINE','A simple story: learn demand, plan safely, measure honestly','Training, validation and test periods are chronological so later orders stay out of planning.');
 const stages=[['1','CLEAN','Remove invalid / cancelled lines'],['2','SPLIT','60% train · 20% validation · 20% test'],['3','LEARN','ABC velocity + basket pairs'],['4','PLAN','Feasible baseline + local search'],['5','CHECK','Validate constraints independently'],['6','MEASURE','Replay later held-out orders']];
 stages.forEach((a,i)=>{let x=.65+i*2.12;rect(s,x,2.35,1.83,1.75,i===4?C.mint:C.white,i===4?C.green:C.line);s.addShape(S.ellipse,{x:x+.16,y:2.54,w:.37,h:.37,line:{color:C.blue,transparency:100},fill:{color:C.blue}});txt(s,a[0],x+.16,2.54,.37,.37,{fs:11,bold:true,color:C.white,align:'center'});txt(s,a[1],x+.16,3.08,1.48,.25,{fs:11,bold:true,color:C.navy});txt(s,a[2],x+.16,3.43,1.48,.48,{fs:9.5,color:C.muted,breakLine:false});if(i<5){line(s,x+1.85,3.18,x+2.07,3.18,C.cyan,1.7)}});
 rect(s,.7,4.72,5.82,1.02,C.paleGold,C.paleGold);txt(s,'Validation chooses the published layout',.95,4.92,5.32,.25,{fs:13,bold:true,color:C.navy});txt(s,'Test orders are reserved for final comparison.',.95,5.29,5.32,.24,{fs:10,color:C.muted});
 rect(s,6.75,4.72,5.82,1.02,C.pale,C.pale);txt(s,'One route model scores every layout',7.0,4.92,5.32,.25,{fs:13,bold:true,color:C.navy});txt(s,'Same orders, map, walking speed and pick assumptions.',7.0,5.29,5.32,.24,{fs:10,color:C.muted});
}
// 6 — Algorithm
{
 const s=pptx.addSlide();base(s,6,'05  /  ALGORITHM','The optimizer makes the layout; the forest learns its pattern','Keep these two jobs separate when judges ask “what is the ML doing?”');
 rect(s,.7,2.0,5.82,3.88,C.white);rect(s,6.8,2.0,5.82,3.88,C.white);
 pill(s,'PRIMARY DECISION ENGINE',.98,2.25,2.3,C.blue);txt(s,'Feasible local search',.98,2.75,5.05,.38,{fs:21,bold:true,color:C.navy});
 txt(s,'Starts from a legal baseline and explores moves / swaps. It rewards shorter depot walks, nearby basket pairs and ergonomic shelf heights; it penalizes excess occupied capacity.',.98,3.28,5.05,.94,{fs:12,color:C.ink,breakLine:false});
 ['Hard rules reject illegal moves','Seeded, bounded search for repeatability','Validation selects; held-out test measures'].forEach((t,i)=>{dot(s,1.02,4.55+i*.35,i===0?C.green:C.cyan,.055);txt(s,t,1.25,4.48+i*.35,4.8,.24,{fs:10.5,color:C.ink});});
 pill(s,'LEARNED SURROGATE',7.08,2.25,2.0,C.coral);txt(s,'Random forest classifier',7.08,2.75,5.05,.38,{fs:21,bold:true,color:C.navy});
 txt(s,'Each row is a product + legal bin. The optimizer’s chosen bin is label 1; other legal bins are 0. Sixty bagged regression trees score candidates; average score ranks bins.',7.08,3.28,5.05,.94,{fs:12,color:C.ink,breakLine:false});
 ['60 bootstrap trees; random feature subset per tree','Ranks candidate bins; placement tracks rack load','Independent validator checks the full proposal'].forEach((t,i)=>{dot(s,7.12,4.55+i*.35,i===2?C.green:C.gold,.055);txt(s,t,7.35,4.48+i*.35,4.8,.24,{fs:10.5,color:C.ink});});
 txt(s,'The forest imitates optimizer choices; it does not learn from observed expert placements.',1.1,6.2,11.2,.32,{fs:13,bold:true,color:C.coral,align:'center'});
}
// 7 — Explain split & chart
{
 const s=pptx.addSlide();base(s,7,'06  /  MODEL EXPLANATION','How a tree decides to split—and what the chart says','A split is a threshold rule that best separates chosen-bin examples from alternatives.');
 rect(s,.7,2.0,5.15,3.92,C.navy,C.navy);txt(s,'Example split',1.02,2.28,4.4,.3,{fs:13,bold:true,color:C.cyan});txt(s,'unit weight ≤ 4.6 kg?',1.02,2.85,4.35,.62,{fs:24,bold:true,color:C.white});
 line(s,3.18,3.65,2.12,4.22,'9CC7D7',1.5);line(s,3.18,3.65,4.25,4.22,'9CC7D7',1.5);
 pill(s,'YES',1.6,4.02,.72,C.green);pill(s,'NO',4.0,4.02,.72,C.coral);
 txt(s,'The code tests candidate thresholds and chooses the one that reduces label variance most. For 0/1 labels, this matches Gini impurity reduction.',1.03,4.7,4.45,.8,{fs:11,color:'D9E8F0',breakLine:false});
 // Native chart from the saved run bundle, so the explanation remains editable.
 rect(s,6.05,2.0,6.55,3.92,C.white);
 txt(s,'What the forest used in this run',6.32,2.22,5.9,.3,{fs:14,bold:true,color:C.navy});
 const fi=[['Unit weight',.234],['Unit volume',.206],['Order frequency',.113],['Units shipped',.102],['Desk distance',.090]];
 fi.forEach((a,i)=>{const y=2.78+i*.49;txt(s,a[0],6.35,y,1.57,.2,{fs:9.5,color:C.ink});rect(s,8.02,y+.015,3.55,.18,'E7EEF3','E7EEF3',.04);rect(s,8.02,y+.015,3.55*(a[1]/.25),.18,i<2?C.blue:C.cyan,i<2?C.blue:C.cyan,.04);txt(s,`${Math.round(a[1]*100)}%`,11.68,y-.015,.55,.22,{fs:9.5,bold:true,color:C.navy,align:'right'});});
 txt(s,'Normalized split improvement; predictive signal, not causal impact.',6.34,5.42,5.9,.3,{fs:10,bold:true,color:C.muted,align:'center'});
}
// 8 — Product demo
{
 const s=pptx.addSlide();base(s,8,'07  /  PRODUCT DEMO','A 60-second walkthrough judges can follow','Show one scenario end to end; point to the same run ID while moving through each view.');
 const steps=[['01','Open run','Show source, seed and split.'],['02','Compare','Baseline vs optimized KPIs.'],['03','Inspect layout','Choose a SKU and explain its bin.'],['04','Explain ML','Show ranking + feature chart.'],['05','Prove safety','Open validation and rules.']];
 steps.forEach((a,i)=>{let y=2.05+i*.78;dot(s,.93,y+.07,i===4?C.green:C.blue,.15);txt(s,a[0],.93,y+.07,.3,.3,{fs:9,bold:true,color:C.white,align:'center'});txt(s,a[1],1.52,y,2.25,.3,{fs:15,bold:true,color:C.navy});txt(s,a[2],3.5,y,4.2,.32,{fs:11,color:C.muted});if(i<4)line(s,1.08,y+.38,1.08,y+.73,C.line,1.5)});
 // Mini dashboard storyboard
 rect(s,8.35,2.08,4.22,3.96,C.navy,C.navy);txt(s,'SLOTWISE DASHBOARD',8.65,2.36,3.55,.25,{fs:10,bold:true,color:C.cyan,charSpacing:1.1});
 [['RUN','default · reproducible'],['ROUTES','same held-out orders'],['LAYOUT','select product / bin'],['SAFETY','0 violations reported']].forEach((a,i)=>{let y=2.88+i*.67;rect(s,8.64,y,3.62,.49,'193B55','416079');txt(s,a[0],8.82,y+.1,.8,.2,{fs:8,bold:true,color:C.gold});txt(s,a[1],9.7,y+.1,2.35,.2,{fs:9,color:C.white});});
 txt(s,'Demo narration: “Here is the run → here is the measured change → here is why the assignment is allowed.”',.92,6.32,11.5,.33,{fs:13,bold:true,color:C.blue,align:'center'});
}
// 9 — Evidence/results
{
 const s=pptx.addSlide();base(s,9,'08  /  RESULTS','The optimizer reduced modeled travel on held-out orders','Final test: 3,199 later orders. Same route simulator, warehouse map and operating assumptions for both layouts.');
 metric(s,.72,2.05,2.85,'46.8 m','Baseline mean / order','test orders',C.muted);
 metric(s,3.75,2.05,2.85,'36.2 m','Optimized mean / order','22.6% lower distance',C.green);
 metric(s,6.78,2.05,2.85,'2,613','Orders with shorter route','447 longer · 139 unchanged',C.blue);
 metric(s,9.81,2.05,2.82,'0','Constraint violations','published optimized layout',C.green);
 // bar comparison
 txt(s,'Average walking distance',.95,3.8,4,.3,{fs:14,bold:true,color:C.navy});
 txt(s,'Baseline',.98,4.35,1.25,.22,{fs:10,bold:true});rect(s,2.3,4.32,6.5,.31,'D9E2EC','D9E2EC',.06);rect(s,2.3,4.32,6.1,.31,C.muted,C.muted,.06);txt(s,'46.8 m',8.58,4.32,1,.25,{fs:11,bold:true,color:C.navy});
 txt(s,'Optimized',.98,5.0,1.25,.22,{fs:10,bold:true});rect(s,2.3,4.97,6.5,.31,'D9E2EC','D9E2EC',.06);rect(s,2.3,4.97,4.72,.31,C.green,C.green,.06);txt(s,'36.2 m',8.58,4.97,1,.25,{fs:11,bold:true,color:C.green});
 rect(s,9.65,3.77,2.9,1.91,C.paleGold,C.paleGold);txt(s,'ML proposal',9.92,4.01,2.3,.25,{fs:13,bold:true,color:C.navy});txt(s,'38.3 m / order',9.92,4.38,2.3,.37,{fs:20,bold:true,color:C.coral});txt(s,'Better than baseline; optimizer remains stronger in this run.',9.92,4.9,2.24,.52,{fs:10,color:C.ink,breakLine:false});
 txt(s,'Modeled results, not a claim of measured worker productivity or realized savings.',.95,6.15,11.5,.28,{fs:10,bold:true,color:C.muted,align:'center'});
}
// 10 — Scenario robustness for the selected uploaded run
{
 const s=pptx.addSlide();base(s,10,'09  /  SCENARIO CHECKS','Desk, demand and safety rules change the measured gain','Selected upload · 108 held-out orders. This is a separate run from the 3,199-order default benchmark on the previous slide.');
 // Static desk-position sensitivity curve, full held-out orders at each aisle.
 txt(s,'Search gain vs saved random legal layout',.72,1.9,6.4,.29,{fs:14,bold:true,color:C.navy});
 const chart={x:1.22,y:2.48,w:5.54,h:2.45}, gains=[20.7,18.5,14.4,10.6,8.8,10.6];
 [0,10,20].forEach(v=>{const yy=chart.y+chart.h-(v/22)*chart.h;line(s,chart.x,yy,chart.x+chart.w,yy,v===0?'9FB0BF':C.line,v===0?1.1:.7,v===0?undefined:'dash');txt(s,String(v)+'%',.72,yy-.1,.42,.2,{fs:8.5,color:C.muted,align:'right'});});
 const pts=gains.map((value,i)=>({x:chart.x+i*chart.w/5,y:chart.y+chart.h-(value/22)*chart.h}));
 pts.slice(0,-1).forEach((p,i)=>line(s,p.x,p.y,pts[i+1].x,pts[i+1].y,C.blue,2.5));
 pts.forEach((p,i)=>{dot(s,p.x-.07,p.y-.07,i===0?C.gold:C.blue,.07);txt(s,String(i),p.x-.08,chart.y+chart.h+.13,.24,.18,{fs:8.5,bold:i===0,color:C.ink,align:'center'});});
 txt(s,'Packing-desk aisle',2.82,5.13,2.2,.22,{fs:9,color:C.muted,align:'center'});
 txt(s,'Aisle 0 is the current desk: 20.7% saved. Aisle 4 is the weakest point: 8.8%.',.9,5.42,6.0,.36,{fs:10.5,bold:true,color:C.ink,align:'center'});

 // Compact robustness scoreboard with one deliberately severe demand shock.
 txt(s,'Robustness scoreboard',7.12,1.9,5.2,.29,{fs:14,bold:true,color:C.navy});
 const scoreRows=[
  ['±30% · worst of top 40','20.5% gain remains','S-1001 demand rises; above 10% trigger'],
  ['Slow SKU · 10× surge','17.0% → 19.3%','S-1037 frozen → re-optimized · 1,200 proposals'],
  ['Heavy products · floor only','20.7% → 15.7%','5 SKUs constrained · fresh legal start'],
  ['Warehouse 90% full','Not measured','Current stock cube fill is 1.5%'],
 ];
 scoreRows.forEach((r,i)=>{const y=2.34+i*.72;line(s,7.12,y+.66,12.6,y+.66,C.line,.8);txt(s,r[0],7.18,y,2.14,.2,{fs:9.5,bold:true,color:C.navy});txt(s,r[1],9.42,y,3.0,.22,{fs:12,bold:true,color:i===1?C.green:(i===2?C.coral:C.blue)});txt(s,r[2],7.18,y+.28,5.3,.2,{fs:8.8,color:C.muted});});

 rect(s,.72,5.92,11.95,.67,C.paleGold,C.paleGold);txt(s,'The honest limit: 36/40 busy products have near-tied legal bins; frequency sort beats search, 39.0 m vs 40.2 m / order.',.95,6.12,11.5,.25,{fs:12,bold:true,color:C.navy,align:'center'});
 txt(s,'Scenario run: 58 SKUs · 240 bins · 108 test orders. Floor-only result includes starting-layout variation; no 90% utilization claim.',.82,6.72,11.7,.18,{fs:8.5,color:C.muted,align:'center'});
 s.addNotes(`Talk track (about 60 seconds): “This page checks whether the result survives changes in the operating scenario. The left chart moves the packing desk across aisles: the modeled gain versus a random legal layout falls from 20.7% at aisle 0 to 8.8% at aisle 4, so the benefit depends on desk location. On the right, the worst ±30% shift among the 40 busiest products still retains 20.5% gain. The harsher case is a slow product going viral: frozen S-1037 retains 17.0%; re-running the optimizer lifts that to 19.3%. Enforcing floor-only storage for heavy products reduces the displayed gain to 15.7% across five constrained SKUs. That comparison uses a fresh legal start, so the change includes starting-layout variation. We have not tested 90% utilization: this run occupies only 1.5% of modeled stock cube. The caveat at the bottom is the key decision: 36 of 40 busy products have near-tied legal bins, and in this uploaded run a simple frequency sort averages 39.0 m versus 40.2 m for search. That means this run does not show added value from the more complex search over that heuristic. These scenarios use a selected upload with 108 held-out orders; the previous results slide is the default run with 3,199 test orders, so treat them as separate datasets.”`);
}
// 11 — Testing and guardrails
{
 const s=pptx.addSlide();base(s,11,'10  /  TESTING & TRUST','We test the rules, the route math and the final assignment','The demo should show evidence and assumptions—not just a model score.');
 const tests=[['Constraint tests','Verify impossible fits and assignment-rule handling.'],['Routing tests','Check within-aisle / cross-aisle distances and route polyline consistency.'],['Forest diagnostic','30 products sampled; chosen-bin rows remain in training.'],['End-to-end replay','Evaluate 3,199 later test orders; report wins and regressions.']];
 tests.forEach((a,i)=>{let y=2.05+i*.82;rect(s,.8,y,7.25,.62,C.white);pill(s,String(i+1).padStart(2,'0'),1.02,y+.15,.55,i===3?C.green:C.blue);txt(s,a[0],1.83,y+.12,1.86,.28,{fs:11,bold:true,color:C.navy});txt(s,a[1],3.8,y+.12,3.9,.34,{fs:10,color:C.muted});});
 rect(s,8.42,2.05,4.05,3.9,C.navy,C.navy);txt(s,'MODEL RANKING DIAGNOSTIC',8.75,2.38,3.3,.25,{fs:10,bold:true,color:C.cyan,charSpacing:1.0});txt(s,'6.7%',8.75,2.92,3.15,.68,{fs:38,bold:true,color:C.white});txt(s,'top-1 exact-bin accuracy',8.78,3.62,3.2,.25,{fs:12,bold:true,color:C.white});txt(s,'20% top-3 · 30 sampled products',8.78,4.02,3.25,.28,{fs:10,color:'C6D8E2'});line(s,8.78,4.55,12.05,4.55,'416079',1);txt(s,'Imitation score only; sampled products’ positive labels were seen during training.',8.78,4.78,3.22,.65,{fs:11,bold:true,color:C.gold,breakLine:false});
 txt(s,'The forest top-1/top-3 figures are optimistic diagnostics until training excludes every row for sampled products.',.9,6.32,11.6,.33,{fs:11,bold:true,color:C.coral,align:'center'});
}
// 12 — Close / roadmap
{
 const s=pptx.addSlide();s.background={color:C.navy};
 txt(s,'11  /  WHAT WE BUILT',.75,.55,5.2,.25,{fs:10,bold:true,color:C.cyan,charSpacing:1.4});txt(s,'A decision aid, with its limits visible.',.75,1.05,11.7,.6,{fs:31,bold:true,color:C.white});
 const columns=[['TODAY','Reproducible data pipeline\nFeasible baseline + search\nForest ranking prototype\nHeld-out route evaluation'],['NEXT','Connect real bin inventory\nCapture observed pick times\nAdd operator review / overrides\nMonitor drift as demand changes']];
 columns.forEach((a,i)=>{let x=.78+i*6.15;rect(s,x,2.15,5.62,2.5,i===0?'193B55':'24485F','416079');txt(s,a[0],x+.28,2.45,4.9,.28,{fs:11,bold:true,color:i===0?C.cyan:C.gold,charSpacing:1.2});txt(s,a[1],x+.3,2.98,4.9,1.25,{fs:15,bold:true,color:C.white,breakLine:false});});
 txt(s,'What we need for real deployment',.8,5.2,5.5,.32,{fs:16,bold:true,color:C.cyan});
 txt(s,'Verified product weights / dimensions · actual bin capacities and map · safety sign-off · observed route/time data',.82,5.72,11.6,.53,{fs:14,color:'D9E8F0',breakLine:false});
 txt(s,'Slotwise: demand-aware placement, independently checked.',.82,6.72,10.8,.34,{fs:15,bold:true,color:C.white});
}

pptx.writeFile({fileName:__dirname+'/output/Slotwise_Judges_Presentation_Scenarios.pptx'});
