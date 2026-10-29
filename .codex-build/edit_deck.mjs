import { PresentationFile, FileBlob } from '@oai/artifact-tool';
const p = await PresentationFile.importPptx(await FileBlob.load('slides/output/Slotwise_Judges_Presentation_seed.pptx'));
console.log('slides', p.slides.items.length);
const info=await p.inspect({kind:'slide',maxChars:10000}); console.log(info.ndjson);
