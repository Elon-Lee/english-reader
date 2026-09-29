const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

let book;
let localDictionary = {};
let libraryBooks = [];
let currentBookId = "";
let importCatalog = [];
let importPollTimer = null;
let displayedPage = null;
let active = -1;
let mode = "intensive";
let pausedForWord = false;
let hoverPausedTime = null;
let hoverPausedSentence = -1;
let clickedWordPausedMain = false;
let clickedWordResumeTime = null;
let clickedWordResumeSentence = -1;
let currentSeries = "";
let shelfView = "tile";
let shortcuts = {previous:"a",repeat:"s",next:"d",play:"space"};
let shadowWaiting = false;
let shadowTimer;
let mediaRecorder;
let recordingChunks = [];
let recordingUrl = "";
let recognition;
let recognizedText = "";
let wordStopAt = null;
let spokenWordElement = null;
let audioStopTimer = null;
let wordTtsAudio = null;
let wordRequestId = 0;
let playbackFrameId = null;
let wordElementsBySentence = [];
let wordAnnotations=[];
let vocabItems=[];
let wordTipSeconds=2;
let eyeComfort=false;
let selectedWordContext=null;
let wordTipTimer=null;
let wordEditMode="";
let heatmapRange="year";
let learningDays=[];
let reviewFilter="today";
let reviewMode="review";
let reviewPage=1;
let reviewPageSize=10;
let manualRepeatCount=3;
let manualPauseSeconds=2;
let manualDictation={items:[],index:-1,played:new Set(),running:false,complete:false,timer:null,audio:null,repeatIndex:0,stage:"ready",token:0};
let visualMode="frames";
let videoTitleManuallyEdited=false;
let videoImportPollTimer=null;
let sentenceAutoPause=false;
let highlightLeadMs=0;
let paintedSentenceIndex=-1;
let youtubeInfo=null;
let youtubePollTimer=null;
let youtubeTitleManuallyEdited=false;

const STORE = {
  state: "shiyue-reader-state-v2",
  vocab: "shiyue-vocab-v2",
};

const dictionary = {
  survive:["/səˈvaɪv/","生存；幸存","continue to live after danger"], plane:["/pleɪn/","飞机","an aircraft with wings"],
  mountain:["/ˈmaʊntən/","山；山脉","a very high area of land"], engine:["/ˈendʒɪn/","发动机","the machine that powers a vehicle"],
  strange:["/streɪndʒ/","奇怪的；陌生的","unusual or unexpected"], noise:["/nɔɪz/","声音；噪声","a sound, especially a loud one"],
  radio:["/ˈreɪdiəʊ/","无线电；收音机","equipment used to send or receive signals"], snow:["/snəʊ/","雪","soft white frozen water"],
  deep:["/diːp/","深的；厚的","extending far down or inward"], cold:["/kəʊld/","寒冷的","having a low temperature"],
  coat:["/kəʊt/","外套","clothing worn over other clothes"], carry:["/ˈkæri/","携带；搬运","hold and take something somewhere"],
  whisky:["/ˈwɪski/","威士忌酒","a strong alcoholic drink"], map:["/mæp/","地图","a drawing that shows places"],
  warm:["/wɔːm/","温暖的；使暖和","at a comfortably high temperature"], helicopter:["/ˈhelɪkɒptə/","直升机","an aircraft with rotating blades"],
  river:["/ˈrɪvə/","河流","a natural flow of water"], tunnel:["/ˈtʌnəl/","隧道","a passage under the ground"],
  valley:["/ˈvæli/","山谷","low land between hills or mountains"], fruit:["/fruːt/","水果；果实","the part of a plant containing seeds"],
  hungry:["/ˈhʌŋɡri/","饥饿的","needing or wanting food"], banana:["/bəˈnɑːnə/","香蕉","a long curved yellow fruit"],
  lighter:["/ˈlaɪtə/","打火机","a small device for making a flame"], fire:["/ˈfaɪə/","火；火堆","heat and flames from burning"],
  fish:["/fɪʃ/","鱼；捕鱼","an animal that lives in water"], build:["/bɪld/","建造；搭建","make something by joining parts"],
  shout:["/ʃaʊt/","大喊","speak with a very loud voice"], wave:["/weɪv/","挥动；挥手","move your hand to signal"],
  track:["/træk/","足迹；踪迹","a mark left by a person or animal"], animal:["/ˈænɪməl/","动物","a living creature that is not a plant"],
  dangerous:["/ˈdeɪndʒərəs/","危险的","likely to cause harm"], poisonous:["/ˈpɔɪzənəs/","有毒的","containing poison"],
  ice:["/aɪs/","冰","water that has frozen solid"], safe:["/seɪf/","安全的","not in danger"], rock:["/rɒk/","岩石","hard natural mineral material"],
  carefully:["/ˈkeəfəli/","小心地","with attention to avoiding danger"], smoke:["/sməʊk/","烟","gas produced by something burning"],
  land:["/lænd/","陆地；着陆","come down onto the ground"], hospital:["/ˈhɒspɪtəl/","医院","a place where ill people are treated"],
  rope:["/rəʊp/","绳子","strong thick cord"], break:["/breɪk/","断裂；打破","separate into pieces"],
  continue:["/kənˈtɪnjuː/","继续","keep doing something"], lake:["/leɪk/","湖","a large area of water surrounded by land"],
  quick:["/kwɪk/","快的","taking a short time"], finally:["/ˈfaɪnəli/","终于；最后","after a long time"],
  catch:["/kætʃ/","抓住；捕获","stop and hold something moving"], dark:["/dɑːk/","黑暗的","with little or no light"],
  lamp:["/læmp/","灯","a device that produces light"], bear:["/beə/","熊","a large strong wild animal"],
  quietly:["/ˈkwaɪətli/","安静地","with very little noise"], turn:["/tɜːn/","转向；转弯","change direction"],
  rest:["/rest/","休息","stop activity in order to relax"], wave:["/weɪv/","挥手；挥动","move your hand from side to side"],
};

const contextRules = [
  [/\bland(s|ed|ing)?\b/i, /helicopter|plane/i, "在交通工具语境中表示“着陆、降落”。"],
  [/\bfire(s)?\b/i, /light|build|make/i, "这里是可取暖或发信号的“火堆”，不是“开火”。"],
  [/\bturn(s|ed)?\b/i, /left|right/i, "与 left/right 连用，表示“向左/向右转”。"],
  [/\btrack(s)?\b/i, /animal|snow/i, "这里指动物留在雪地里的“足迹”。"],
  [/\bcatch\b/i, /fish/i, "catch a fish 是“抓到／钓到一条鱼”。"],
  [/\bgo down\b/i, /mountain|river|valley/i, "go down 在这里表示沿着较低方向前进。"],
];

function load(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } }
function save(key, value) { localStorage.setItem(key, JSON.stringify(value)); }
function fmt(seconds) { seconds = Math.max(0, seconds || 0); return `${String(Math.floor(seconds / 60)).padStart(2,"0")}:${String(Math.floor(seconds % 60)).padStart(2,"0")}`; }
function day(ms) { return new Date(ms).toLocaleDateString("zh-CN", { month:"short", day:"numeric" }); }
function escapeHtml(value) { return value.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c])); }
function formatText(value) { return escapeHtml(value || "").replace(/\\n/g,"\n").replace(/\n/g,"<br>"); }
function focusedWordContext(text,wordIndex){
  const matches=[...text.matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g)];const target=matches[wordIndex];if(!target)return text.slice(0,220);
  const position=target.index,terminator=/[.!?。！？…]/g;let start=0,end=text.length,match;
  while((match=terminator.exec(text))&&match.index<position)start=match.index+1;
  terminator.lastIndex=position;match=terminator.exec(text);if(match)end=match.index+1;
  let result=text.slice(start,end).trim();
  if(result.length>240||(!match&&end-start>240)){const from=Math.max(0,wordIndex-10),to=Math.min(matches.length,wordIndex+11);const first=matches[from],last=matches[to-1];result=text.slice(first.index,last.index+last[0].length).trim();if(from>0)result="… "+result;if(to<matches.length)result+=" …";}
  return result;
}
function rootWord(word) { const w = word.toLowerCase().replace("’", "'"); if (dictionary[w] || localDictionary[w]) return w; return [w.replace(/ies$/, "y"), w.replace(/ing$/, ""), w.replace(/ing$/, "e"), w.replace(/ed$/, ""), w.replace(/ed$/, "e"), w.replace(/es$/, ""), w.replace(/s$/, "")].find(x => dictionary[x] || localDictionary[x]) || w; }
function wordHtml(text, sentence, cursor = { index:0 }) {
  let html = ""; let last = 0; const regex = /[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g; let match;
  while ((match = regex.exec(text))) {
    html += escapeHtml(text.slice(last, match.index));
    const wordIndex=cursor.index++; const timing = sentence?.words?.[wordIndex];
    const attrs = timing ? ` data-word-index="${wordIndex}" data-start="${timing.start}" data-end="${timing.end}" data-aligned="${timing.aligned ? "1" : "0"}"` : ` data-word-index="${wordIndex}"`;
    html += `<span class="word"${attrs}>${escapeHtml(match[0])}</span>`;
    last = regex.lastIndex;
  }
  return html + escapeHtml(text.slice(last));
}
function sentenceHtml(sentence) {
  const parts = sentence.text.split(/(Go (?:back )?to\s+(40|[1-3][0-9]|[1-9])\b\.?)/ig);
  let html = ""; const cursor = { index:0 };
  for (let i = 0; i < parts.length; i += 3) {
    html += wordHtml(parts[i] || "", sentence, cursor);
    if (parts[i + 1]) html += `<button class="branch-link" data-target="${parts[i + 2]}">${wordHtml(parts[i + 1], sentence, cursor)} <b>→</b></button>`;
  }
  return html;
}

async function init() {
  const [libraryData, dictionaryData, vocabData] = await Promise.all([
    fetch("/api/library", {cache:"no-store"}).then(r => r.json()),
    fetch("/api/local-dictionary", {cache:"no-store"}).then(r => r.json()),
    fetch("/api/vocabulary", {cache:"no-store"}).then(r => r.json()),
  ]);
  localDictionary=dictionaryData; libraryBooks=libraryData.books||[]; vocabItems=vocabData.items||[];
  populateVideoSeriesOptions();
  bindEvents();
  await loadApiSettings();
  setupSeriesSelector(); renderLibrary();
  loadImportCatalog();
  if(libraryBooks.length) await loadBook(libraryBooks[0].id);
}

async function loadBook(bookId) {
  const response=await fetch(`/api/books/${encodeURIComponent(bookId)}`,{cache:"no-store"});
  if(!response.ok) throw new Error("无法读取图书数据库");
  const record=await response.json(); currentBookId=bookId; book=record.book;wordAnnotations=record.annotations||[];
  $("#audio").pause(); $("#audio").src=book.audio; $("#duration").textContent=fmt(book.duration);
  $(".book-heading small").textContent=`${book.level||""}级 · LOCAL BOOK`;
  $(".book-heading strong").innerHTML=`${escapeHtml(book.title)} <i>${escapeHtml(book.englishTitle||"")}</i>`;
  $(".book-heading strong").title=[book.title,book.englishTitle].filter(Boolean).join(" · ");
  $(".chapter h1").textContent=book.englishTitle||book.title;
  visualMode="frames";configureBookVisual();active=-1; displayedPage=null; renderStory(); restoreProgress(); refreshDashboards(); showPage(book.sentences[0]?.page||1);
  postActivity({bookId,open:true,sessions:1}).then(()=>fetch("/api/library",{cache:"no-store"})).then(r=>r.json()).then(data=>{libraryBooks=data.books||libraryBooks;renderLibrary();}).catch(()=>{});
}

function renderLibrary() {
  const grid=$("#libraryGrid");
  const visible=libraryBooks.filter(item=>!currentSeries||item.series===currentSeries);
  grid.className=`library-grid ${shelfView}-view`;
  $("#shelfCount").textContent=`${visible.length} 本`; $("#shelfSeriesTitle").textContent=currentSeries||"全部书籍";
  $("#tileViewBtn").classList.toggle("active",shelfView==="tile"); $("#listViewBtn").classList.toggle("active",shelfView==="list");
  if(!visible.length){grid.innerHTML='<div class="empty-state"><h3>当前书系暂无已导入书籍</h3><p>请从“导入书籍”选择书籍。</p></div>';return;}
  grid.innerHTML=visible.map(item=>`<article class="book-card" data-book-id="${escapeHtml(item.id)}" data-source-type="${escapeHtml(item.source_type||'book')}"><img src="${encodeURI(item.cover_url)}" alt="${escapeHtml(item.title)}封面"><div class="book-info"><span class="tag">LEVEL ${escapeHtml(item.level||"-")}</span><h3>${escapeHtml(item.title)}</h3><em>${escapeHtml(item.english_title||"")}</em><p>${escapeHtml(item.series)}</p><div class="progress"><i style="width:${bookProgress(item.id)}%"></i></div><small>${item.alignment.startsWith('whisper-')?'Whisper 词级点读':'本地点读'}</small></div><button class="round-play">▶</button></article>`).join("");
}
function populateVideoSeriesOptions(){
  const history=[...new Set(libraryBooks.map(item=>(item.series||"").trim()).filter(Boolean).filter(name=>!name.includes("牛津")))].sort((left,right)=>left.localeCompare(right,"zh-CN"));
  const options='<option value="">选择历史标签</option>'+history.map(name=>`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  [$("#videoSeriesHistory"),$("#youtubeSeriesHistory")].forEach(select=>{if(!select)return;const previous=select.value;select.innerHTML=options;if(history.includes(previous))select.value=previous;});
}
function setupSeriesSelector(){const series=[...new Set(libraryBooks.map(item=>item.series))];if(!currentSeries||!series.includes(currentSeries))currentSeries=series[0]||"";$("#seriesSelect").innerHTML=series.map(name=>`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");$("#seriesSelect").value=currentSeries;}
function bookProgress(id){const state=load(`${STORE.state}-${id}`,{});const item=libraryBooks.find(x=>x.id===id);return item?.duration?Math.round((state.time||0)/item.duration*100):0}

function renderStory() {
  const box = $("#sentences");
  box.innerHTML = "";
  paintedSentenceIndex=-1;
  wordElementsBySentence=[];
  let previousSection = null;
  book.sentences.forEach((sentence, index) => {
    if (sentence.section != null && sentence.section !== previousSection) {
      const marker = document.createElement("div");
      marker.className = "section-marker";
      marker.id = `section-${sentence.section}`;
      marker.innerHTML = `<span>${sentence.section}</span><i>STORY PART</i>`;
      box.append(marker);
      previousSection = sentence.section;
    }
    const p = document.createElement("p");
    p.className = "sentence";
    p.dataset.i = index;
    p.dataset.section = sentence.section;
    p.innerHTML = sentenceHtml(sentence);
    box.append(p);
    wordElementsBySentence[index]=[...p.querySelectorAll(".word[data-start][data-end]")];
    wordElementsBySentence[index].forEach((element,wordIndex)=>applyWordMark(element,sentence,wordIndex));
  });
}
function applyWordMark(element,sentence,wordIndex){const annotation=wordAnnotations.find(item=>item.sentence_id===sentence.id&&item.word_index===wordIndex),vocab=vocabItems.find(item=>item.book_id===currentBookId&&item.sentence_id===sentence.id&&item.word_index===wordIndex);element.classList.toggle("annotated-word",!!annotation);element.classList.toggle("vocab-word",!!vocab);if(annotation?.note)element.dataset.note=annotation.note;else delete element.dataset.note;if(annotation?.corrected_word)element.dataset.correction=`OCR订正：${annotation.original_word} → ${annotation.corrected_word}`;else delete element.dataset.correction;element.title=[annotation?.note,element.dataset.correction,vocab?'已加入生词本':''].filter(Boolean).join(' · ');}
function refreshWordMarks(){book?.sentences.forEach((sentence,index)=>(wordElementsBySentence[index]||[]).forEach((element,wordIndex)=>applyWordMark(element,sentence,wordIndex)));}

function bindEvents() {
  $("#libraryGrid").onclick = async event => {const card=event.target.closest("[data-book-id]");if(!card)return;await loadBook(card.dataset.bookId);openReader();};
  $("#backBtn").onclick = () => showScreen("shelf");
  $$(".nav").forEach(button => button.onclick = () => showScreen(button.dataset.screen));
  $$(".mode-switch button").forEach(button => button.onclick = () => setMode(button.dataset.mode));
  $("#sentences").addEventListener("click", event => {
    const branch = event.target.closest(".branch-link");
    if (branch) { event.stopPropagation(); jumpToSection(+branch.dataset.target); return; }
    const sentenceElement = event.target.closest(".sentence");
    if (!sentenceElement) return;
    const sentence = book.sentences[+sentenceElement.dataset.i];
    if (event.target.classList.contains("word") && mode === "intensive") {
      event.stopPropagation();
      const word = event.target;
      const audio=$("#audio");
      // A click happens after pointer-over has already paused the main track.
      // Preserve that position so leaving the word can resume the book audio.
      if (!audio.paused || pausedForWord) {
        clickedWordPausedMain=true;
        clickedWordResumeTime=hoverPausedTime ?? audio.currentTime;
        clickedWordResumeSentence=hoverPausedSentence>=0 ? hoverPausedSentence : active;
      }
      clearTimeout(audioStopTimer); wordStopAt=null; audio.pause(); pausedForWord=false;
      hoverPausedTime=null; hoverPausedSentence=-1;
      showWord(word.textContent, sentence, word);
      playWordTts(word.textContent);
      showWordQuickTip(word,sentence);
      postActivity({lookups:1});
    }
    else playSentence(+sentenceElement.dataset.i);
  });
  $("#sentences").addEventListener("pointerover", handleWordPointerOver);
  $("#sentences").addEventListener("pointerout", handleWordPointerOut);
  $("#playBtn").onclick = () => { clearTimeout(audioStopTimer); if ($("#audio").paused) { wordStopAt=null; $("#audio").play(); } else $("#audio").pause(); };
  $("#prevBtn").onclick = () => playSentence(Math.max(0, active - 1));
  $("#nextBtn").onclick = () => playSentence(Math.min(book.sentences.length - 1, active + 1));
  $("#seek").oninput = event => { $("#audio").currentTime = event.target.value / 1000 * book.duration; syncPlaybackFrame(); };
  const rates = [.75, 1, 1.25, 1.5]; let rateIndex = 1;
  $("#speedBtn").onclick = () => { rateIndex = (rateIndex + 1) % rates.length; $("#audio").playbackRate = rates[rateIndex]; $("#speedBtn").textContent = rates[rateIndex] + "×"; };
  $("#viewBtn").onclick = () => { $("#pagePanel").classList.toggle("hidden"); showPage(book.sentences[Math.max(0,active)]?.page||1); };
  $("#closePage").onclick = () => $("#pagePanel").classList.add("hidden");
  $("#focusBtn").onclick = () => document.body.classList.toggle("focus");
  $("#eyeComfortBtn").onclick = toggleEyeComfort;
  $("#recordBtn").onclick = toggleRecording;
  $("#playRecordBtn").onclick = () => { if (recordingUrl) { $("#recording").src = recordingUrl; $("#recording").play(); } };
  $("#audio").ontimeupdate = persistAudioProgress;
  $("#audio").onplay = () => { $("#playBtn").textContent = "Ⅱ"; if(sentenceAutoPause&&active>=0&&mode!=="shadow")wordStopAt=book.sentences[active].end+.03;if(visualMode==="video")$("#videoView").play().catch(()=>{});trackListening(); startPlaybackSync(); };
  $("#audio").onpause = () => { $("#playBtn").textContent = "▶"; $("#videoView").pause();stopPlaybackSync(); syncPlaybackFrame(); };
  $("#audio").onseeked = syncPlaybackFrame;
  window.addEventListener("beforeunload", finishSession);
  $("#settingsForm").onsubmit = saveApiSettings;
  $("#seriesSelect").onchange = event => {
    currentSeries=event.target.value;
    renderLibrary();
    savePreference({currentSeries});
    showScreen("shelf");
  };
  $("#tileViewBtn").onclick=()=>setShelfView("tile"); $("#listViewBtn").onclick=()=>setShelfView("list");
  $$(".shortcut-input").forEach(input=>input.onkeydown=captureShortcut);
  $("#importSeries").onchange = updateImportBooks;
  $("#importBookList").onchange = updateBatchButton;
  $("#selectAllBooks").onclick = () => { $$("#importBookList input:not(:disabled)").forEach(input=>input.checked=true); updateBatchButton(); };
  $("#clearBooks").onclick = () => { $$("#importBookList input").forEach(input=>input.checked=false); updateBatchButton(); };
  $("#startBatchImport").onclick = startBatchImport;
  $$("[data-import-type]").forEach(button=>button.onclick=()=>setImportType(button.dataset.importType));
  $("#videoImportPane").onsubmit=startVideoImport;
  $("#youtubeImportPane").onsubmit=startYoutubeImport;
  $("#analyzeYoutubeBtn").onclick=analyzeYoutubeUrl;
  $("#youtubeEnglishTitle").oninput=()=>{if(!youtubeTitleManuallyEdited)$("#youtubeTitle").value=$("#youtubeEnglishTitle").value;};
  $("#youtubeTitle").oninput=()=>{youtubeTitleManuallyEdited=true;};
  $("#videoFile").onchange=handleVideoFileSelected;
  $("#videoEnglishTitle").oninput=syncVideoChineseTitle;
  $("#videoTitle").oninput=()=>{videoTitleManuallyEdited=true;};
  $("#videoSeriesHistory").onchange=event=>{if(event.target.value)$("#videoSeries").value=event.target.value;};
  $("#youtubeSeriesHistory").onchange=event=>{if(event.target.value)$("#youtubeSeries").value=event.target.value;};
  $("#framesViewBtn").onclick=()=>setVisualMode("frames");$("#videoViewBtn").onclick=()=>setVisualMode("video");
  document.addEventListener("keydown",handleReaderShortcut);
  document.addEventListener("click",event=>{const button=event.target.closest("button");if(button)setTimeout(()=>button.blur(),0);});
  $("#wordQuickTip").onclick=handleWordTipAction;
  $("#wordQuickTip").onmouseenter=()=>clearTimeout(wordTipTimer);
  $("#wordQuickTip").onmouseleave=()=>scheduleWordTipHide();
  $("#saveWordEdit").onclick=saveWordEdit;
  $("#closeWordEdit").onclick=closeWordEditor;$("#cancelWordEdit").onclick=closeWordEditor;
  $("#statsContent").onclick=event=>{const button=event.target.closest("[data-heatmap-range]");if(button)setHeatmapRange(button.dataset.heatmapRange);};
  $("#reviewContent").onclick=handleReviewClick;
}

function configureBookVisual(){const isVideo=book?.sourceType==="video"&&book.video;$("#visualSwitch").classList.toggle("hidden",!isVideo);$("#visualTitle").textContent=isVideo?"视频画面":"原书页";$("#videoView").src=isVideo?book.video:"";setVisualMode("frames");}
function setVisualMode(mode){visualMode=mode;const isVideo=book?.sourceType==="video"&&book.video;$("#framesViewBtn").classList.toggle("active",mode==="frames");$("#videoViewBtn").classList.toggle("active",mode==="video");$("#pageImage").classList.toggle("hidden",mode==="video");$("#videoView").classList.toggle("hidden",mode!=="video");if(isVideo&&mode==="video"){const video=$("#videoView"),audio=$("#audio");video.currentTime=audio.currentTime;if(!audio.paused)video.play().catch(()=>{});}else $("#videoView").pause();}
function setImportType(type){$$('[data-import-type]').forEach(button=>button.classList.toggle('active',button.dataset.importType===type));$("#booksImportPane").classList.toggle("hidden",type!=="books");$("#videoImportPane").classList.toggle("hidden",type!=="video");$("#youtubeImportPane").classList.toggle("hidden",type!=="youtube");}
function videoNameWithoutExtension(name){return name.replace(/\.[^.]+$/,'').replace(/[._-]+/g,' ').trim();}
function handleVideoFileSelected(){const file=$("#videoFile").files[0];if(!file)return;const derived=videoNameWithoutExtension(file.name);if(!$("#videoEnglishTitle").value)$("#videoEnglishTitle").value=derived;if(!$("#videoTitle").value||!videoTitleManuallyEdited)$("#videoTitle").value=$("#videoEnglishTitle").value||derived;}
function syncVideoChineseTitle(){if(!videoTitleManuallyEdited)$("#videoTitle").value=$("#videoEnglishTitle").value;}
function setVideoOverallProgress(percent,step,message=''){const value=Math.max(0,Math.min(100,Math.round(percent)));$("#videoUploadBar").value=value;$("#videoUploadPercent").textContent=`${value}%`;$("#videoUploadStep").textContent=step;if(message)$("#videoUploadMessage").textContent=message;}
function uploadPart(uploadId,kind,file,baseProgress,span){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST",`/api/import/video/upload/${uploadId}?kind=${kind}`);xhr.upload.onprogress=event=>{if(event.lengthComputable)setVideoOverallProgress(baseProgress+event.loaded/event.total*span,kind==='video'?'上传视频':'上传字幕','文件上传只是第一阶段，完成后将继续后台处理。');};xhr.onload=()=>xhr.status<300?resolve():reject(new Error(JSON.parse(xhr.responseText||'{}').error||'上传失败'));xhr.onerror=()=>reject(new Error('网络上传失败'));xhr.send(file);});}
async function startVideoImport(event){event.preventDefault();const video=$("#videoFile").files[0],subtitle=$("#videoSubtitle").files[0];if(!video)return;const series=$("#videoSeries").value.trim();if(!series){$("#videoSeries").setCustomValidity("请选择历史标签或输入新标签");$("#videoSeries").reportValidity();return;}$("#videoSeries").setCustomValidity("");clearInterval(videoImportPollTimer);$("#videoUploadProgress").classList.remove("hidden");setVideoOverallProgress(0,"创建上传任务","总体进度包含上传、音频提取、关键帧、Whisper、对齐和数据库写入。");try{const englishTitle=$("#videoEnglishTitle").value.trim();const chineseTitle=$("#videoTitle").value.trim()||englishTitle;if(!$("#videoTitle").value.trim())$("#videoTitle").value=chineseTitle;const initResponse=await fetch("/api/import/video/init",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:chineseTitle,englishTitle,series,level:$("#videoLevel").value,subtitleStrategy:$("#videoSubtitleStrategy").value,videoFilename:video.name,subtitleFilename:subtitle?.name||""})});const init=await initResponse.json();if(!initResponse.ok)throw new Error(init.error||"无法创建上传");await uploadPart(init.uploadId,"video",video,1,subtitle?17:19);if(subtitle)await uploadPart(init.uploadId,"subtitle",subtitle,18,2);setVideoOverallProgress(20,"创建后台处理任务","文件上传完成，后台处理即将开始。");const doneResponse=await fetch(`/api/import/video/complete/${init.uploadId}`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});const done=await doneResponse.json();if(!doneResponse.ok)throw new Error(done.error||"无法开始导入");pollVideoImport(done.jobId);}catch(error){clearInterval(videoImportPollTimer);setVideoOverallProgress($("#videoUploadBar").value,"视频导入失败",error.message);}}
function pollVideoImport(jobId){clearInterval(videoImportPollTimer);const check=async()=>{try{const response=await fetch(`/api/import/jobs/${jobId}`,{cache:'no-store'}),job=await response.json();if(!response.ok)throw new Error(job.error||'无法读取任务');const overall=20+(job.progress||0)*.8;setVideoOverallProgress(overall,job.step||job.status,job.error||`后台处理中：${job.progress||0}%`);if(job.status==='complete'||job.status==='failed'){clearInterval(videoImportPollTimer);videoImportPollTimer=null;if(job.status==='complete'){setVideoOverallProgress(100,'视频导入完成','音频、字幕、关键帧、词级时间轴和SQLite数据均已完成。');const data=await fetch('/api/library',{cache:'no-store'}).then(r=>r.json());libraryBooks=data.books||[];populateVideoSeriesOptions();setupSeriesSelector();renderLibrary();await loadImportCatalog();}else setVideoOverallProgress(overall,'视频导入失败',job.error||'后台任务失败');}}catch(error){clearInterval(videoImportPollTimer);videoImportPollTimer=null;setVideoOverallProgress($("#videoUploadBar").value,'进度查询失败',error.message);}};check();videoImportPollTimer=setInterval(check,1000);}

function setYoutubeProgress(percent,step,message=''){const value=Math.max(0,Math.min(100,Math.round(percent)));$("#youtubeBar").value=value;$("#youtubePercent").textContent=`${value}%`;$("#youtubeStep").textContent=step;if(message)$("#youtubeMessage").textContent=message;}
async function analyzeYoutubeUrl(){const url=$("#youtubeUrl").value.trim();if(!url)return;$("#analyzeYoutubeBtn").disabled=true;$("#youtubeProgress").classList.remove("hidden");setYoutubeProgress(1,"解析 YouTube 地址","正在读取标题、频道、时长和字幕信息。");try{const response=await fetch('/api/import/youtube/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})}),data=await response.json();if(!response.ok)throw new Error(data.error||'解析失败');youtubeInfo=data;$("#youtubeThumbnail").src=data.thumbnail||'';$("#youtubeChannel").textContent=data.channel||'YouTube';$("#youtubePreviewTitle").textContent=data.title;$("#youtubeMeta").textContent=`${fmt(data.duration||0)} · ${data.hasEnglishSubtitles?'有人工英文字幕':data.hasEnglishAutoCaptions?'有自动英文字幕':'无英文字幕，将使用Whisper'}`;$("#youtubePreview").classList.remove("hidden");$("#youtubeEnglishTitle").value=data.title;youtubeTitleManuallyEdited=false;$("#youtubeTitle").value=data.title;if(!$("#youtubeSeries").value||$("#youtubeSeries").value==='视频课程')$("#youtubeSeries").value=data.channel||'视频课程';$("#startYoutubeImport").disabled=false;setYoutubeProgress(3,"解析完成","确认标题和标签后开始下载。");}catch(error){youtubeInfo=null;$("#startYoutubeImport").disabled=true;setYoutubeProgress(0,"解析失败",error.message);}finally{$("#analyzeYoutubeBtn").disabled=false;}}
async function startYoutubeImport(event){event.preventDefault();if(!youtubeInfo)return;const series=$("#youtubeSeries").value.trim();if(!series)return;clearInterval(youtubePollTimer);$("#youtubeProgress").classList.remove("hidden");setYoutubeProgress(1,"创建 YouTube 导入任务","下载、字幕和后续处理将严格顺序执行。");try{const response=await fetch('/api/import/youtube',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:youtubeInfo.webpageUrl||$("#youtubeUrl").value,title:$("#youtubeTitle").value.trim()||youtubeInfo.title,englishTitle:$("#youtubeEnglishTitle").value.trim()||youtubeInfo.title,series,level:$("#youtubeLevel").value.trim(),videoId:youtubeInfo.id,channel:youtubeInfo.channel})}),data=await response.json();if(!response.ok)throw new Error(data.error||'无法开始导入');pollYoutubeImport(data.jobId);}catch(error){setYoutubeProgress($("#youtubeBar").value,'YouTube 导入失败',error.message);}}
function pollYoutubeImport(jobId){clearInterval(youtubePollTimer);const check=async()=>{try{const response=await fetch(`/api/import/jobs/${jobId}`,{cache:'no-store'}),job=await response.json();if(!response.ok)throw new Error(job.error||'无法读取任务');setYoutubeProgress(job.progress||0,job.step||job.status,job.error||youtubeProgressMessage(job));if(job.status==='complete'||job.status==='failed'){clearInterval(youtubePollTimer);youtubePollTimer=null;if(job.status==='complete'){setYoutubeProgress(100,'YouTube 导入完成','视频、字幕、音频、关键帧、词级时间轴和SQLite数据均已完成。');const data=await fetch('/api/library',{cache:'no-store'}).then(r=>r.json());libraryBooks=data.books||[];populateVideoSeriesOptions();setupSeriesSelector();renderLibrary();}else setYoutubeProgress(job.progress||0,'YouTube 导入失败',job.error||'任务失败');}}catch(error){clearInterval(youtubePollTimer);youtubePollTimer=null;setYoutubeProgress($("#youtubeBar").value,'进度查询失败',error.message);}};check();youtubePollTimer=setInterval(check,1000);}
function youtubeProgressMessage(job){if((job.progress||0)<25)return '正在下载最高720p视频、英文字幕和缩略图。';return `YouTube下载已完成，正在复用视频处理流程：${job.progress||0}%`;}

function showWordQuickTip(element,sentence){
  clearTimeout(wordTipTimer); const rect=element.getBoundingClientRect();
  selectedWordContext={element,sentence,wordIndex:+element.dataset.wordIndex,word:element.textContent,definition:getDefinition(element.textContent,sentence)};
  const annotation=wordAnnotations.find(item=>item.sentence_id===sentence.id&&item.word_index===selectedWordContext.wordIndex),note=$("#wordTipAnnotation");
  const annotationText=[annotation?.note,annotation?.corrected_word?`OCR：${annotation.original_word} → ${annotation.corrected_word}`:''].filter(Boolean).join(' · ');
  note.textContent=annotationText;note.classList.toggle("hidden",!annotationText);
  const tip=$("#wordQuickTip");tip.classList.remove("hidden"); tip.style.left=`${Math.min(innerWidth-tip.offsetWidth-12,Math.max(12,rect.left))}px`;tip.style.top=`${Math.max(12,rect.top-tip.offsetHeight-7)}px`;
  scheduleWordTipHide();
}
function wordTarget(node){return node?.nodeType===1?node.closest?.(".word"):null;}
function handleWordPointerOver(event){
  if(mode!=="intensive")return;
  const word=wordTarget(event.target),from=wordTarget(event.relatedTarget);
  if(!word||from===word)return;
  if(!$("#audio").paused&&!pausedForWord){
    pausedForWord=true;hoverPausedTime=$("#audio").currentTime;hoverPausedSentence=active;
    clearTimeout(audioStopTimer);$("#audio").pause();
  }
}
function handleWordPointerOut(event){
  if(mode!=="intensive")return;
  const word=wordTarget(event.target),to=wordTarget(event.relatedTarget);
  const movingToTip=event.relatedTarget?.nodeType===1 && event.relatedTarget.closest?.("#wordQuickTip,#wordInlineEditor");
  if(!word||to===word||to||movingToTip)return;
  if(!pausedForWord&&!clickedWordPausedMain)return;
  pausedForWord=false;
  const resumeTime=clickedWordPausedMain ? clickedWordResumeTime : hoverPausedTime;
  const resumeSentence=clickedWordPausedMain ? clickedWordResumeSentence : hoverPausedSentence;
  clickedWordPausedMain=false; clickedWordResumeTime=null; clickedWordResumeSentence=-1;
  hoverPausedTime=null; hoverPausedSentence=-1;
  wordTtsAudio?.pause();
  if(resumeTime===null||resumeTime===undefined)return;
  if(resumeSentence>=0&&book?.sentences?.[resumeSentence]){
    const stopAt=sentenceAutoPause?book.sentences[resumeSentence].end+.03:null;
    seekAndPlay(resumeTime,stopAt);
  }else seekAndPlay(resumeTime,null);
}
function scheduleWordTipHide(){clearTimeout(wordTipTimer);wordTipTimer=setTimeout(()=>$("#wordQuickTip").classList.add("hidden"),wordTipSeconds*1000);}
function handleWordTipAction(event){const action=event.target.closest("[data-word-action]")?.dataset.wordAction;if(!action||!selectedWordContext)return;clearTimeout(wordTipTimer);if(action==="vocab"){$("#wordQuickTip").classList.add("hidden");addSelectedWordToVocab();}else openWordEditor(action);}
function openWordEditor(mode){wordEditMode=mode;const tip=$("#wordQuickTip"),editor=$("#wordInlineEditor"),rect=tip.getBoundingClientRect();$("#wordEditTitle").textContent=mode==="correct"?"订正 OCR":"添加备注";const input=$("#wordEditValue");input.placeholder=mode==="correct"?"输入正确单词":"输入简短备注";input.value=mode==="correct"?selectedWordContext.word:(selectedWordContext.note||"");tip.classList.add("hidden");editor.classList.remove("hidden");editor.style.left=`${Math.min(innerWidth-editor.offsetWidth-12,Math.max(12,rect.left))}px`;editor.style.top=`${Math.min(innerHeight-editor.offsetHeight-12,rect.bottom+6)}px`;setTimeout(()=>input.focus(),0);}
function closeWordEditor(event){event?.preventDefault();$("#wordInlineEditor").classList.add("hidden");}
async function saveWordEdit(event){event.preventDefault();const value=$("#wordEditValue").value.trim();if(!value)return;const c=selectedWordContext;const payload={bookId:currentBookId,sentenceId:c.sentence.id,wordIndex:c.wordIndex};if(wordEditMode==="correct")payload.correctedWord=value;else payload.note=value;const response=await fetch("/api/word-annotation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(response.ok){const result=await response.json();const existing=wordAnnotations.find(item=>item.sentence_id===c.sentence.id&&item.word_index===c.wordIndex),record={book_id:currentBookId,sentence_id:c.sentence.id,word_index:c.wordIndex,original_word:result.originalWord,corrected_word:result.correctedWord,note:result.note};if(existing)Object.assign(existing,record);else wordAnnotations.push(record);if(wordEditMode==="note")selectedWordContext.note=value;closeWordEditor();if(wordEditMode==="correct"){await loadBook(currentBookId);const sentence=book.sentences.find(s=>s.id===c.sentence.id)||c.sentence;showWord(value,sentence,null);}else refreshWordMarks();}}
async function addSelectedWordToVocab(){const c=selectedWordContext,d=c.definition;const payload={book_id:currentBookId,sentence_id:c.sentence.id,word_index:c.wordIndex,word:c.word,root:d.root,phonetic:d.phonetic,meaning:d.meaning,context:focusedWordContext(c.sentence.text,c.wordIndex),note:c.note||"",rating:"unknown",interval_days:1,due_at:new Date(Date.now()+86400000).toISOString()};const r=await fetch("/api/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(r.ok){vocabItems=(await r.json()).items||[];refreshWordMarks();refreshDashboards();}}

function setShelfView(view){shelfView=view;renderLibrary();savePreference({shelfView:view});}
function savePreference(value){fetch("/api/preferences",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}).catch(()=>{});}
function toggleEyeComfort(){eyeComfort=!eyeComfort;applyEyeComfort();savePreference({eyeComfort});}
function applyEyeComfort(){document.body.classList.toggle("eye-comfort",eyeComfort);const button=$("#eyeComfortBtn");button.classList.toggle("active",eyeComfort);button.setAttribute("aria-pressed",String(eyeComfort));button.textContent=eyeComfort?"● 护眼":"◐ 护眼";}
function keyName(event){return event.key===" "?"space":event.key.toLowerCase();}
function keyLabel(key){return key==="space"?"空格":key.length===1?key.toUpperCase():key;}
function captureShortcut(event){event.preventDefault();event.stopPropagation();const key=keyName(event);if(["shift","control","alt","meta"].includes(key))return;event.target.value=keyLabel(key);event.target.dataset.key=key;event.target.blur();}

function handleReaderShortcut(event) {
  if(!$("#vocab").classList.contains("hidden")){handleReviewShortcut(event);return;}
  if($("#reader").classList.contains("hidden") || event.metaKey || event.ctrlKey || event.altKey) return;
  if(event.target.closest("input,textarea,select,button,[contenteditable=true]")) return;
  const key=keyName(event);
  if(key==="q"){event.preventDefault();toggleSentenceAutoPause();return;}
  const action=Object.entries(shortcuts).find(([,value])=>value===key)?.[0]; if(!action)return; event.preventDefault();
  if(action==="play") { clearTimeout(audioStopTimer); wordStopAt=null; $("#audio").paused ? $("#audio").play() : $("#audio").pause(); }
  if(action==="previous" && book) playSentence(Math.max(0,(active<0?0:active)-1));
  if(action==="repeat" && book) playSentence(Math.max(0,active));
  if(action==="next" && book) playSentence(Math.min(book.sentences.length-1,(active<0?-1:active)+1));
}
function toggleSentenceAutoPause(){sentenceAutoPause=!sentenceAutoPause;if(sentenceAutoPause&&active>=0)wordStopAt=book.sentences[active].end+.03;else wordStopAt=null;updateShortcutHint();savePreference({sentenceAutoPause});showReaderToast(sentenceAutoPause?"句末自动暂停：已开启":"句末自动暂停：已关闭");}
function showReaderToast(message){let toast=$("#readerToast");if(!toast){toast=document.createElement("div");toast.id="readerToast";toast.className="reader-toast";document.body.append(toast);}toast.textContent=message;toast.classList.add("show");clearTimeout(toast._timer);toast._timer=setTimeout(()=>toast.classList.remove("show"),1400);}

function showScreen(id) {
  $$(".screen").forEach(screen => screen.classList.toggle("hidden", screen.id !== id));
  $$(".nav").forEach(nav => nav.classList.toggle("active", nav.dataset.screen === id));
  const reading = id === "reader";
  $("#player").classList.toggle("hidden", !reading);
  $(".book-heading").style.display = reading ? "block" : "none";
  $(".top-actions").style.display = reading ? "flex" : "none";
  $("#backBtn").style.visibility = reading ? "visible" : "hidden";
  if (!reading) { document.body.classList.remove("focus"); $("#audio").pause(); clearTimeout(shadowTimer); refreshDashboards(); }
  if(id!=="vocab")stopManualDictation();
}

function openReader() {
  showScreen("reader");
  if (active < 0) {
    const saved = load(`${STORE.state}-${currentBookId}`, {}).time || book.sentences[0].start;
    const index = book.sentences.findIndex(s => saved >= s.start && saved < s.end);
    highlight(index >= 0 ? index : 0, true);
  }
}

function setMode(nextMode) {
  mode = nextMode;
  $$(".mode-switch button").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
  $("#reader").dataset.mode = mode;
  $("#shadowCoach").classList.toggle("hidden", mode !== "shadow");
  $("#wordPanel").classList.toggle("hidden", mode !== "intensive");
  $("#modeHint").textContent = mode === "intensive" ? "点击句子点读，点击单词查看语境释义。" : mode === "extensive" ? "隐藏查词干扰，连续听完整故事。" : "听一句，停下来模仿；可录音回放并检查文本匹配度。";
  if (mode !== "shadow") { shadowWaiting = false; clearTimeout(shadowTimer); }
  logAction("modes", mode);
}

function playSentence(index) {
  clearTimeout(shadowTimer);
  shadowWaiting = false;
  active = index;
  const sentence = book.sentences[index];
  wordStopAt = mode === "shadow" || !sentenceAutoPause ? null : sentence.end + .03;
  pausedForWord = false;
  seekAndPlay(sentence.start, mode === "shadow" || !sentenceAutoPause ? null : sentence.end + .03);
  highlight(index, true);
  showPage(sentence.page);
  if (mode === "shadow") { $("#shadowStatus").textContent = "先听原音…"; $("#shadowPrompt").textContent = sentence.text; }
  const stateKey=`${STORE.state}-${currentBookId}`; const state=load(stateKey,{}); state.sentencesPlayed=(state.sentencesPlayed||0)+1; save(stateKey,state);
  postActivity({bookId:currentBookId,sentences:1});
}

function persistAudioProgress() {
  if(!book||!currentBookId)return;
  const audio = $("#audio"); const time = audio.currentTime;
  const state = load(`${STORE.state}-${currentBookId}`, {}); state.time = time; save(`${STORE.state}-${currentBookId}`, state);
}

function startPlaybackSync() {
  if(playbackFrameId!==null)return;
  const frame=()=>{syncPlaybackFrame();playbackFrameId=$("#audio").paused?null:requestAnimationFrame(frame);};
  playbackFrameId=requestAnimationFrame(frame);
}

function stopPlaybackSync() {
  if(playbackFrameId!==null)cancelAnimationFrame(playbackFrameId);
  playbackFrameId=null;
}

function syncPlaybackFrame() {
  if(!book)return;
  const audio = $("#audio"); const time = audio.currentTime;
  $("#currentTime").textContent = fmt(time);
  $("#seek").value = time / book.duration * 1000;
  if(visualMode==="video"&&book.sourceType==="video"){const video=$("#videoView");if(Math.abs(video.currentTime-time)>.25)video.currentTime=time;}
  if (wordStopAt !== null && time >= wordStopAt) { wordStopAt = null; audio.pause(); }
  const rawIndex=sentenceIndexAt(time);
  if (rawIndex >= 0 && rawIndex !== active) {
    active=rawIndex;
    if(sentenceAutoPause&&mode!=="shadow")wordStopAt=book.sentences[rawIndex].end+.03;
    if(book.sentences[rawIndex].page!==displayedPage) showPage(book.sentences[rawIndex].page);
  }
  const visualTime=Math.max(0,time+highlightLeadMs/1000);
  const visualIndex=sentenceIndexAt(visualTime);
  if(visualIndex!==paintedSentenceIndex)paintSentence(visualIndex,true);
  const nextSpoken=visualIndex>=0?wordElementAt(visualIndex,visualTime):null;
  if (nextSpoken !== spokenWordElement) {
    spokenWordElement?.classList.remove("spoken"); spokenWordElement = nextSpoken; spokenWordElement?.classList.add("spoken");
  }
  if (active < 0) return;
  const sentence = book.sentences[active];
  if (time >= sentence.end - .08) {
    if (mode === "shadow" && !shadowWaiting) beginShadowPause(sentence);
  }
}

function beginShadowPause(sentence) {
  shadowWaiting = true;
  $("#audio").pause();
  const pauseMs = Math.max(2200, (sentence.end - sentence.start) * 1000 * +$("#pauseRatio").value);
  $("#shadowStatus").textContent = "现在跟读";
  $("#shadowPrompt").textContent = `模仿：${sentence.text}`;
  shadowTimer = setTimeout(() => {
    shadowWaiting = false;
    if (active < book.sentences.length - 1) playSentence(active + 1);
    else $("#shadowStatus").textContent = "本书跟读完成";
  }, pauseMs);
}

function highlight(index, scroll = false) {
  active = index;
  paintSentence(index,scroll);
}
function paintSentence(index,scroll=false){if(index===paintedSentenceIndex&&!scroll)return;const sentences=$$(".sentence");if(paintedSentenceIndex>=0)sentences[paintedSentenceIndex]?.classList.remove("active");if(index>=0)sentences[index]?.classList.add("active");paintedSentenceIndex=index;if(scroll&&index>=0)sentences[index]?.scrollIntoView({behavior:"smooth",block:"center"});}
function lastStartedIndex(items,time,getStart){let low=0,high=items.length-1,result=-1;while(low<=high){const middle=(low+high)>>1;if(getStart(items[middle])<=time){result=middle;low=middle+1;}else high=middle-1;}return result;}
function sentenceIndexAt(time){return book?.sentences?.length?lastStartedIndex(book.sentences,time,item=>item.start):-1;}
function wordElementAt(sentenceIndex,time){
  const sentence=book?.sentences?.[sentenceIndex],words=sentence?.words||[],elements=wordElementsBySentence[sentenceIndex]||[];
  if(!words.length||time<words[0].start)return null;
  const index=lastStartedIndex(words,time,item=>item.start);
  if(index<0)return null;
  // Once a word starts, keep it highlighted until the next word starts.
  // This also keeps the final word active throughout a sentence-ending pause.
  return elements[index]||null;
}

function jumpToSection(section) {
  const index = book.sentences.findIndex(sentence => sentence.section === section);
  if (index < 0) { alert(`第 ${section} 段尚未成功识别，该段落尚未成功识别。`); return; }
  const stateKey=`${STORE.state}-${currentBookId}`; const state=load(stateKey,{}); state.branches=(state.branches||0)+1; save(stateKey,state);
  playSentence(index);
}

function getDefinition(raw, sentence) {
  if (/^\d+$/.test(raw)) return { root:raw, phonetic:"", meaning:`数字 ${raw}`, english:`story section number ${raw}`, usage:"这里是互动故事的段落编号或跳转目标。" };
  const root = rootWord(raw);
  const offline=localDictionary[raw.toLowerCase()] || localDictionary[root];
  const basic = dictionary[root] || (offline ? [`/${offline.phonetic || ""}/`, offline.translation || "见英文解释", offline.definition || ""] : ["", "未在离线词典中找到", "This may be a name, OCR error, or uncommon inflected form."]);
  const rule = contextRules.find(([wordPattern, sentencePattern]) => wordPattern.test(raw) && sentencePattern.test(sentence.text));
  return { root, phonetic:basic[0], meaning:basic[1], english:basic[2], usage:rule?.[2] || "结合整句理解该词在故事中的具体含义。" };
}

async function showWord(raw, sentence, wordElement) {
  const definition = getDefinition(raw, sentence);
  const annotation=wordAnnotations.find(item=>item.sentence_id===sentence.id&&item.word_index===+(wordElement?.dataset.wordIndex??-1));
  const saved = vocabItems.find(item=>item.book_id===currentBookId&&item.sentence_id===sentence.id&&item.word_index===+(wordElement?.dataset.wordIndex??-1));
  const requestId=++wordRequestId;
  $("#wordPanel").innerHTML = `<div class="definition">
    <button class="speak" id="speakWord" title="播放接口发音">♪</button><span class="phonetic">${formatText(definition.phonetic)}</span><h2>${escapeHtml(raw)}</h2>
    <div id="remoteDefinition"><p class="loading-line">正在查询中文释义…</p></div>
    <div class="context"><small>IN THIS STORY · 第 ${sentence.page} 页</small><p>${highlightWord(sentence.text, raw)}</p></div>
    <div id="remoteUsage" class="usage-note"><span class="loading-line">正在分析上下文用法…</span></div>
    <div id="remoteExamples" class="dict-examples"><span class="loading-line">正在加载例句…</span></div>
    ${annotation?.note?`<div class="saved-word-note"><small>我的备注</small><p>${escapeHtml(annotation.note)}</p></div>`:""}
    <div class="rating"><small>${saved ? `当前：${ratingName(saved.rating)} · 下次 ${new Date(saved.due_at).toLocaleDateString("zh-CN")}` : "加入复习并评级"}</small>
      <div><button data-rating="known">认识</button><button data-rating="fuzzy">模糊</button><button data-rating="unknown">不认识</button></div>
    </div></div>`;
  $("#speakWord").onclick = () => playWordTts(raw);
  $$("#wordPanel [data-rating]").forEach(button => button.onclick = () => rateWord(raw, sentence, definition, button.dataset.rating, wordElement));
  const sentenceIndex=book.sentences.findIndex(item=>item.id===sentence.id);
  const expanded=book.sentences.slice(Math.max(0,sentenceIndex-1),sentenceIndex+2).map(item=>item.text).join(" ");
  fetch(`/api/word-dictionary?word=${encodeURIComponent(raw)}`,{cache:"no-store"}).then(async response=>{
    if(!response.ok) throw new Error((await response.json()).error || "查询失败");
    return response.json();
  }).then(data=>{
    if(requestId!==wordRequestId) return;
    const groups=(data.groups||[]).map(group=>`<div class="dict-group"><b>${escapeHtml(group.pos)}</b><p>${group.translations.map(escapeHtml).join("；")}</p></div>`).join("");
    $("#remoteDefinition").innerHTML=groups || `<p class="meaning">${formatText(definition.meaning)}</p><p>${formatText(definition.english)}</p>`;
    $("#remoteDefinition").insertAdjacentHTML("beforeend",`<small class="api-source">释义来源：${escapeHtml(data.source||"Dioco")}</small>`);
    $("#remoteExamples").innerHTML=(data.examples||[]).length?`<small>EXAMPLES</small>${data.examples.map(item=>`<p>${escapeHtml(item)}</p>`).join("")}`:'<small>暂无例句</small>';
  }).catch(()=>{
    if(requestId!==wordRequestId) return;
    $("#remoteDefinition").innerHTML=`<p class="meaning">${formatText(definition.meaning)}</p><p>${formatText(definition.english)}</p><small class="api-source">接口不可用，已使用本地词典</small>`;
    $("#remoteExamples").innerHTML='<small>例句接口暂不可用</small>';
  });
  fetch("/api/word-context",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({word:raw,contextSentence:sentence.text,expandedContext:expanded})}).then(async response=>{
    if(!response.ok) throw new Error((await response.json()).error || "分析失败");
    return response.json();
  }).then(data=>{
    if(requestId!==wordRequestId) return;
    $("#remoteUsage").innerHTML=`${formatText(data.explanation||definition.usage)}<small class="api-source">语境来源：${escapeHtml(data.source||"Dioco Lexa")}</small>`;
  }).catch(()=>{
    if(requestId!==wordRequestId) return;
    $("#remoteUsage").innerHTML=`${formatText(definition.usage)}<small class="api-source">接口不可用，已使用本地语境规则</small>`;
  });
}

function highlightWord(sentence, word) {
  const safe = wordHtml(sentence);
  return safe.replace(new RegExp(`(<span class="word">)${escapeRegExp(word)}(</span>)`, "i"), `$1<em>${escapeHtml(word)}</em>$2`);
}
function escapeRegExp(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
function speak(word) { speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(word); utterance.lang = "en-US"; utterance.rate = .78; speechSynthesis.speak(utterance); }
async function playWordTts(word) {
  try {
    wordTtsAudio?.pause();
    wordTtsAudio=new Audio(`/api/word-tts?word=${encodeURIComponent(word)}`);
    await wordTtsAudio.play();
  } catch { speak(word); }
}
async function seekAndPlay(time, stopAt=null) {
  const audio=$("#audio");
  clearTimeout(audioStopTimer);
  if (audio.readyState < 1) await new Promise(resolve => audio.addEventListener("loadedmetadata",resolve,{once:true}));
  audio.currentTime=time;
  try {
    await audio.play();
    if (stopAt !== null) {
      const delay=Math.max(0,(stopAt-audio.currentTime)/audio.playbackRate*1000);
      audioStopTimer=setTimeout(()=>{ audio.pause(); wordStopAt=null; },delay);
    }
  } catch { /* Browser will expose its normal play control if autoplay is denied. */ }
}
function ratingName(rating) { return ({ known:"认识", fuzzy:"模糊", unknown:"不认识" })[rating]; }

async function rateWord(raw, sentence, definition, rating, wordElement) {
  const previous=vocabItems.find(item=>item.book_id===currentBookId&&item.sentence_id===sentence.id&&item.word_index===+(wordElement?.dataset.wordIndex??-1));
  const intervals = { known:7, fuzzy:3, unknown:1 };
  const base = intervals[rating];
  const nextInterval = rating === "known" && previous ? Math.min(60, Math.max(base, (previous.interval_days || base) * 2)) : base;
  const wordIndex=+(wordElement?.dataset.wordIndex??0);const payload={book_id:currentBookId,sentence_id:sentence.id,word_index:wordIndex,word:raw,root:definition.root,phonetic:definition.phonetic,meaning:definition.meaning,context:focusedWordContext(sentence.text,wordIndex),rating,interval_days:nextInterval,due_at:new Date(Date.now()+nextInterval*86400000).toISOString()};
  const response=await fetch("/api/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(response.ok)vocabItems=(await response.json()).items||[];refreshWordMarks();showWord(raw,sentence,wordElement);refreshDashboards();
}

function refreshDashboards() { renderStats(); renderReview(); }

async function renderStats() {
  if (!book) return;
  const state = load(`${STORE.state}-${currentBookId}`, {}); const vocab = vocabItems;
  const percent = Math.round((state.time || 0) / book.duration * 100);
  $("#statsContent").innerHTML = `<div class="metric-grid">
    <article><small>阅读进度</small><b>${percent}%</b><p>${fmt(state.time || 0)} / ${fmt(book.duration)}</p></article>
    <article><small>累计听读</small><b>${Math.round((state.secondsRead || 0) / 60)}</b><p>分钟</p></article>
    <article><small>已学单词</small><b>${vocab.length}</b><p>${vocab.filter(v => new Date(v.due_at)<=new Date()).length} 个待复习</p></article>
    <article><small>剧情选择</small><b>${state.branches || 0}</b><p>次主动选择</p></article>
  </div><div class="panel"><div class="heatmap-head"><h3>学习热力图</h3><div class="heatmap-ranges"><button data-heatmap-range="year">年</button><button data-heatmap-range="quarter">季度</button><button data-heatmap-range="month">月</button><button data-heatmap-range="week">周</button></div></div><p id="heatmapPeriod" class="heatmap-period"></p><div id="studyHeatmap" class="study-heatmap"></div><div class="heatmap-legend"><span>少</span><i></i><i></i><i></i><i></i><i></i><span>多</span></div></div><div class="panel"><h3>学习方式</h3><div class="mode-bars">${modeBar("精读", state.modes?.intensive || 0)}${modeBar("泛听", state.modes?.extensive || 0)}${modeBar("跟读", state.modes?.shadow || 0)}</div></div>`;
  const data=await fetch("/api/learning/days",{cache:"no-store"}).then(r=>r.json()).catch(()=>({days:[]}));learningDays=data.days||[];renderHeatmap();
}
function setHeatmapRange(range){heatmapRange=range;renderHeatmap();savePreference({heatmapRange:range});}
function localDateKey(date){return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;}
function heatmapBounds(){const end=new Date();end.setHours(0,0,0,0);const start=new Date(end);if(heatmapRange==="year")start.setDate(end.getDate()-364-end.getDay());if(heatmapRange==="quarter")start.setDate(end.getDate()-90-end.getDay());if(heatmapRange==="month")start.setDate(1);if(heatmapRange==="week")start.setDate(end.getDate()-end.getDay());return{start,end};}
function renderHeatmap(){if(!$("#studyHeatmap"))return;const map=new Map(learningDays.map(item=>[item.day,item]));const {start,end}=heatmapBounds(),cells=[];for(let d=new Date(start);d<=end;d.setDate(d.getDate()+1)){const key=localDateKey(d),item=map.get(key)||{};const score=(item.reading_seconds||0)/300+(item.lookups||0)/5+(item.reviews||0)/3+(item.sentences||0)/10;const level=score<=0?0:score<1?1:score<3?2:score<6?3:4;cells.push(`<i class="level-${level}" title="${key} · ${Math.round((item.reading_seconds||0)/60)}分钟 · ${item.lookups||0}次查词 · ${item.reviews||0}次复习"></i>`);}const heatmap=$("#studyHeatmap");heatmap.className=`study-heatmap range-${heatmapRange}`;heatmap.innerHTML=cells.join("");$$("[data-heatmap-range]").forEach(button=>button.classList.toggle("active",button.dataset.heatmapRange===heatmapRange));$("#heatmapPeriod").textContent=`${localDateKey(start)} 至 ${localDateKey(end)} · ${cells.length} 天`;}
function modeBar(name, count) { return `<div><span>${name}</span><i style="width:${Math.min(100, count * 18 + 8)}%"></i><b>${count} 次</b></div>`; }

function dateOffsetKey(offset){const date=new Date();date.setDate(date.getDate()+offset);return localDateKey(date);}
function filteredReviewItems(){
  if(reviewFilter==="all")return [...vocabItems];
  const keys={yesterday:dateOffsetKey(-1),today:dateOffsetKey(0),tomorrow:dateOffsetKey(1)};
  return vocabItems.filter(item=>localDateKey(new Date(item.due_at))===keys[reviewFilter]);
}
function renderReview() {
  const filtered=filteredReviewItems().sort((a,b)=>new Date(a.due_at)-new Date(b.due_at));
  const due=vocabItems.filter(entry=>new Date(entry.due_at)<=new Date());
  $("#dueBadge").textContent=due.length;$("#dueBadge").classList.toggle("hidden",!due.length);
  const pages=Math.max(1,Math.ceil(filtered.length/reviewPageSize));reviewPage=Math.max(1,Math.min(reviewPage,pages));
  const items=filtered.slice((reviewPage-1)*reviewPageSize,reviewPage*reviewPageSize);
  const labels={yesterday:"昨日",today:"当日",tomorrow:"明日",all:"所有"};
  $("#reviewContent").innerHTML=`<div class="review-toolbar"><div class="review-filters">${Object.entries(labels).map(([key,label])=>`<button data-review-filter="${key}" class="${reviewFilter===key?'active':''}">${label}</button>`).join("")}</div><div class="review-mode-switch"><button data-review-mode="review" class="${reviewMode==='review'?'active':''}">复习</button><button data-review-mode="manual" class="${reviewMode==='manual'?'active':''}">听写</button></div></div>
    <div class="review-summary"><b>${filtered.length}</b><span>${labels[reviewFilter]}词条</span><small>第 ${reviewPage}/${pages} 页 · 每页 ${reviewPageSize} 条</small></div>
    ${items.length?(reviewMode==='manual'?manualDictationView(items):`<div class="vocab-list review">${items.map(entry=>reviewCard(entry)).join("")}</div>`):`<div class="empty-state"><span>☆</span><h3>${labels[reviewFilter]}没有词条</h3><p>在精读模式点击单词，使用浮动工具栏加入生词本。</p></div>`}
    <div class="review-pagination"><button data-review-page="first" ${reviewPage===1?'disabled':''}>F 首页</button><button data-review-page="prev" ${reviewPage===1?'disabled':''}>A 上一页</button><span>${reviewPage} / ${pages}</span><button data-review-page="next" ${reviewPage===pages?'disabled':''}>D 下一页</button><button data-review-page="last" ${reviewPage===pages?'disabled':''}>E 尾页</button></div>`;
  if(reviewMode==='manual'&&items.length)prepareManualDictation(items);
}
function reviewCard(entry){return `<article class="vocab-card compact ${new Date(entry.due_at)<=new Date()?'due':''}" data-id="${entry.id}"><div class="review-main-line"><button class="review-word" data-review-detail>${escapeHtml(entry.word)} <small>${entry.phonetic}</small></button><button class="review-speaker" title="播放发音">♪</button><p class="review-sentence">${escapeHtml(entry.context)}</p></div><div class="mini-rates hidden"><button data-review="again">忘记</button><button data-review="hard">困难</button><button data-review="good">记得</button><button data-review="easy">简单</button></div></article>`;}
function manualDictationView(items){return `<section class="manual-dictation"><div class="manual-dictation-head"><div><small>听写 · 每词 ${manualRepeatCount} 遍 · 停顿 ${manualPauseSeconds} 秒</small><b id="manualStatus">点击开始，共 ${items.length} 个词</b></div><div class="manual-controls"><button id="manualStart" data-manual-action="start">开始</button><button data-manual-action="prev">← 上一个</button><button id="manualPause" data-manual-action="pause" disabled>暂停</button><button data-manual-action="next">下一个 →</button></div></div><div class="manual-dictation-body"><div class="manual-word-grid">${items.map((entry,index)=>`<button class="manual-word" data-manual-index="${index}"><span class="manual-sequence">${index+1}</span><span class="manual-word-text">待听写</span><small>已播词可点击重听</small></button>`).join("")}</div></div></section>`;}
function sameManualItems(items){return manualDictation.items.length===items.length&&items.every((item,index)=>manualDictation.items[index]?.id===item.id);}
function newManualState(items){return{items:[...items],index:-1,played:new Set(),running:false,complete:false,timer:null,audio:null,repeatIndex:0,stage:"ready",token:(manualDictation.token||0)+1};}
function prepareManualDictation(items){if(!sameManualItems(items))manualDictation=newManualState(items);updateManualDictationView();}
function stopManualDictation(){clearTimeout(manualDictation.timer);manualDictation.timer=null;manualDictation.running=false;manualDictation.token++;manualDictation.audio?.pause();manualDictation.audio=null;wordTtsAudio?.pause();}
function resetManualDictation(){stopManualDictation();manualDictation=newManualState(manualDictation.items);updateManualDictationView();}
function startManualDictation(){if(manualDictation.complete||manualDictation.index>=0)manualDictation=newManualState(manualDictation.items);manualDictation.running=true;manualDictation.index=0;startManualWord();}
function startManualWord(){if(!manualDictation.running)return;if(manualDictation.index>=manualDictation.items.length){completeManualDictation();return;}manualDictation.played.add(manualDictation.index);manualDictation.repeatIndex=0;manualDictation.stage="speaking";updateManualDictationView();playManualRepetition(manualDictation.token);}
function playManualRepetition(token){if(!manualDictation.running||token!==manualDictation.token)return;const entry=manualDictation.items[manualDictation.index];manualDictation.stage="speaking";updateManualDictationView();const audio=new Audio(`/api/word-tts?word=${encodeURIComponent(entry.word)}`);manualDictation.audio=audio;audio.onended=()=>{if(token!==manualDictation.token)return;manualDictation.repeatIndex++;if(manualDictation.repeatIndex<manualRepeatCount){manualDictation.stage="between";updateManualDictationView();manualDictation.timer=setTimeout(()=>playManualRepetition(token),280);}else{manualDictation.stage="pause";updateManualDictationView();manualDictation.timer=setTimeout(()=>{if(token!==manualDictation.token||!manualDictation.running)return;manualDictation.index++;startManualWord();},manualPauseSeconds*1000);}};audio.onerror=()=>audio.onended();audio.play().catch(()=>audio.onended());}
function completeManualDictation(){clearTimeout(manualDictation.timer);manualDictation.complete=true;manualDictation.running=false;manualDictation.stage="complete";manualDictation.played=new Set(manualDictation.items.map((_,index)=>index));updateManualDictationView();}
function toggleManualPause(){if(manualDictation.index<0||manualDictation.complete)return;if(manualDictation.running){manualDictation.running=false;clearTimeout(manualDictation.timer);manualDictation.audio?.pause();}else{manualDictation.running=true;if(manualDictation.stage==="speaking"&&manualDictation.audio?.paused)manualDictation.audio.play();else if(manualDictation.stage==="between")manualDictation.timer=setTimeout(()=>playManualRepetition(manualDictation.token),280);else if(manualDictation.stage==="pause")manualDictation.timer=setTimeout(()=>{manualDictation.index++;startManualWord();},manualPauseSeconds*1000);}updateManualDictationView();}
function jumpManual(direction){if(!manualDictation.items.length)return;clearTimeout(manualDictation.timer);manualDictation.audio?.pause();manualDictation.token++;manualDictation.index=Math.max(0,Math.min(manualDictation.items.length-1,(manualDictation.index<0?0:manualDictation.index)+direction));manualDictation.complete=false;manualDictation.running=true;manualDictation.played.add(manualDictation.index);manualDictation.repeatIndex=0;startManualWord();}
function handleManualAction(action){if(action==='start'){startManualDictation();return;}if(action==='pause'){toggleManualPause();return;}if(action==='prev'){jumpManual(-1);return;}if(action==='next'){jumpManual(1);}}
function updateManualDictationView(){const status=$("#manualStatus");if(!status)return;let message=`点击开始，共 ${manualDictation.items.length} 个词`;if(manualDictation.complete)message=`听写完成，已揭示 ${manualDictation.items.length} 个单词`;else if(manualDictation.index>=0){if(!manualDictation.running)message=`已暂停 · 第 ${manualDictation.index+1}/${manualDictation.items.length} 个`;else if(manualDictation.stage==='speaking')message=`第 ${manualDictation.index+1}/${manualDictation.items.length} 个 · 正在朗读第 ${Math.min(manualRepeatCount,manualDictation.repeatIndex+1)}/${manualRepeatCount} 遍`;else if(manualDictation.stage==='pause')message=`第 ${manualDictation.index+1} 个完成 · 停顿 ${manualPauseSeconds} 秒`;else message=`第 ${manualDictation.index+1}/${manualDictation.items.length} 个`;}status.textContent=message;const start=$("#manualStart"),pause=$("#manualPause");if(start)start.textContent=manualDictation.complete?'重新开始':manualDictation.index<0?'开始':'重新开始';if(pause){pause.disabled=manualDictation.index<0||manualDictation.complete;pause.textContent=manualDictation.running?'暂停':'继续';}$$('.manual-word').forEach((element,index)=>{const played=manualDictation.played.has(index),current=index===manualDictation.index&&!manualDictation.complete,text=element.querySelector('.manual-word-text');element.classList.toggle('played',played);element.classList.toggle('current',current);element.classList.toggle('revealed',manualDictation.complete);text.textContent=manualDictation.complete?manualDictation.items[index].word:played?'████████':'待听写';});}
function flashManualWord(index){const element=$(`.manual-word[data-manual-index="${index}"]`);if(!element)return;element.classList.remove('replay-flash');void element.offsetWidth;element.classList.add('replay-flash');}
function handleReviewClick(event){
  const filter=event.target.closest('[data-review-filter]');if(filter){stopManualDictation();reviewFilter=filter.dataset.reviewFilter;reviewPage=1;renderReview();return;}
  const modeButton=event.target.closest('[data-review-mode]');if(modeButton){stopManualDictation();reviewMode=modeButton.dataset.reviewMode;reviewPage=1;renderReview();return;}
  const pageButton=event.target.closest('[data-review-page]');if(pageButton){changeReviewPage(pageButton.dataset.reviewPage);return;}
  const detail=event.target.closest('[data-review-detail]');if(detail){const card=detail.closest('.vocab-card'),entry=vocabItems.find(item=>item.id===+card.dataset.id);card.querySelector('.mini-rates').classList.remove('hidden');if(entry){playWordTts(entry.word);showReviewWordInfo(entry);}return;}
  const speaker=event.target.closest('.review-speaker');if(speaker){const entry=vocabItems.find(item=>item.id===+speaker.closest('.vocab-card').dataset.id);if(entry)playWordTts(entry.word);return;}
  const rating=event.target.closest('[data-review]');if(rating){reviewSavedWord(+rating.closest('.vocab-card').dataset.id,rating.dataset.review);return;}
  const manualControl=event.target.closest('[data-manual-action]');if(manualControl){handleManualAction(manualControl.dataset.manualAction);return;}
  const manualWord=event.target.closest('[data-manual-index]');if(manualWord){const index=+manualWord.dataset.manualIndex;if(manualDictation.played.has(index)){const entry=manualDictation.items[index];playWordTts(entry.word);showReviewWordInfo(entry);flashManualWord(index);}return;}
  const manualInfoSpeak=event.target.closest('.manual-info-speaker');if(manualInfoSpeak){playWordTts(manualInfoSpeak.dataset.word);}
}
async function showReviewWordInfo(entry){
  const panel=$("#reviewWordPanel"),requestId=++wordRequestId,bookInfo=libraryBooks.find(item=>item.id===entry.book_id);
  panel.innerHTML=`<div class="manual-info-card"><button class="manual-info-speaker" data-word="${escapeHtml(entry.word)}">♪</button><span class="phonetic">${formatText(entry.phonetic)}</span><h3>${escapeHtml(entry.word)}</h3><p class="manual-info-meaning">${formatText(entry.meaning)}</p><div id="manualRemoteDefinition"><span class="loading-line">正在加载完整释义…</span></div><div class="context"><small>${escapeHtml(bookInfo?.title||'当前句子')}</small><p>${escapeHtml(entry.context)}</p></div><div id="manualRemoteUsage" class="usage-note"><span class="loading-line">正在分析当前句中的用法…</span></div><div id="manualRemoteExamples" class="dict-examples"><span class="loading-line">正在加载例句…</span></div>${entry.note?`<div class="saved-word-note"><small>我的备注</small><p>${escapeHtml(entry.note)}</p></div>`:''}</div>`;
  fetch(`/api/word-dictionary?word=${encodeURIComponent(entry.word)}`,{cache:'no-store'}).then(async response=>response.ok?response.json():Promise.reject()).then(data=>{if(requestId!==wordRequestId)return;const groups=(data.groups||[]).map(group=>`<div class="dict-group"><b>${escapeHtml(group.pos)}</b><p>${group.translations.map(escapeHtml).join('；')}</p></div>`).join('');$("#manualRemoteDefinition").innerHTML=groups||`<p>${formatText(entry.meaning)}</p>`;$("#manualRemoteExamples").innerHTML=(data.examples||[]).length?`<small>EXAMPLES</small>${data.examples.map(example=>`<p>${escapeHtml(example)}</p>`).join('')}`:'<small>暂无例句</small>';}).catch(()=>{if(requestId===wordRequestId){$("#manualRemoteDefinition").innerHTML=`<p>${formatText(entry.meaning)}</p>`;$("#manualRemoteExamples").innerHTML='';}});
  fetch('/api/word-context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word:entry.word,contextSentence:entry.context,expandedContext:entry.context})}).then(async response=>response.ok?response.json():Promise.reject()).then(data=>{if(requestId===wordRequestId)$("#manualRemoteUsage").innerHTML=formatText(data.explanation||'结合当前句理解该词的具体用法。');}).catch(()=>{if(requestId===wordRequestId)$("#manualRemoteUsage").textContent='结合当前句理解该词的具体用法。';});
}

function changeReviewPage(action){const total=Math.max(1,Math.ceil(filteredReviewItems().length/reviewPageSize));if(action==='first')reviewPage=1;if(action==='prev')reviewPage=Math.max(1,reviewPage-1);if(action==='next')reviewPage=Math.min(total,reviewPage+1);if(action==='last')reviewPage=total;renderReview();}
function handleReviewShortcut(event){if(event.metaKey||event.ctrlKey||event.altKey||event.target.closest('input,textarea,select,[contenteditable=true]'))return;const key=event.key.toLowerCase();const action={a:'prev',d:'next',e:'last',f:'first'}[key];if(action){event.preventDefault();changeReviewPage(action);}}


async function reviewSavedWord(id,rating) {
  const entry=vocabItems.find(item=>item.id===id);if(!entry)return;
  const old=entry.interval_days||1;const interval=rating==="again"?1:rating==="hard"?Math.max(2,Math.round(old*1.2)):rating==="good"?Math.max(7,old*2):Math.max(14,old*3);
  const r=await fetch(`/api/vocabulary/${id}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({rating,interval_days:Math.min(180,interval),due_at:new Date(Date.now()+Math.min(180,interval)*86400000).toISOString()})});if(r.ok)vocabItems=(await r.json()).items||[];renderReview();renderStats();
}

async function toggleRecording() {
  if (mediaRecorder?.state === "recording") { mediaRecorder.stop(); recognition?.stop(); return; }
  try {
    clearTimeout(shadowTimer); shadowWaiting = true; $("#audio").pause(); recognizedText = "";
    const stream = await navigator.mediaDevices.getUserMedia({ audio:true });
    recordingChunks = []; mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = event => recordingChunks.push(event.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(recordingChunks, { type:mediaRecorder.mimeType });
      if (recordingUrl) URL.revokeObjectURL(recordingUrl); recordingUrl = URL.createObjectURL(blob);
      $("#playRecordBtn").disabled = false; $("#recordBtn").textContent = "● 重新录音";
      stream.getTracks().forEach(track => track.stop()); await scoreRecording(blob);
      const stateKey=`${STORE.state}-${currentBookId}`; const state=load(stateKey,{}); state.shadowAttempts=(state.shadowAttempts||0)+1; save(stateKey,state);
    };
    startRecognition(); mediaRecorder.start(); $("#recordBtn").textContent = "■ 停止"; $("#shadowStatus").textContent = "正在录音…";
  } catch { $("#shadowStatus").textContent = "无法使用麦克风"; $("#shadowPrompt").textContent = "请在浏览器设置中允许本地页面使用麦克风。"; }
}

function startRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return;
  recognition = new Recognition(); recognition.lang = "en-US"; recognition.interimResults = false;
  recognition.onresult = event => recognizedText = [...event.results].map(result => result[0].transcript).join(" ");
  recognition.start();
}

async function scoreRecording(blob) {
  $("#shadowStatus").textContent = "Whisper 正在分析…";
  try {
    const response = await fetch("/api/transcribe", { method:"POST", headers:{"Content-Type":blob.type || "application/octet-stream"}, body:blob });
    const result = await response.json();
    if (response.ok && result.text) recognizedText = result.text;
  } catch { /* Fall back to browser speech recognition when local API is unavailable. */ }
  const target = book.sentences[Math.max(0, active)].text.toLowerCase().match(/[a-z']+/g) || [];
  const heard = recognizedText.toLowerCase().match(/[a-z']+/g) || [];
  if (!heard.length) { $("#shadowStatus").textContent = "录音完成，可回放对比"; $("#shadowPrompt").textContent = "当前浏览器没有返回语音文本，建议戴耳机听原音后回放自评。"; return; }
  const matrix = Array.from({length:target.length+1},()=>Array(heard.length+1).fill(0));
  for (let i=1;i<=target.length;i++) for (let j=1;j<=heard.length;j++) matrix[i][j]=target[i-1]===heard[j-1]?matrix[i-1][j-1]+1:Math.max(matrix[i-1][j],matrix[i][j-1]);
  const matches=matrix[target.length][heard.length];
  const score = Math.min(100, Math.round(matches / Math.max(target.length, heard.length) * 100));
  const missing=target.filter(word=>!heard.includes(word));
  $("#shadowStatus").textContent = `Whisper 文本匹配度 ${score}%`;
  $("#shadowPrompt").textContent = `识别到：${recognizedText}${missing.length ? ` · 可能漏读：${[...new Set(missing)].join(", ")}` : ""}`;
}

let lastTick = 0;
function trackListening() { lastTick = Date.now(); }
setInterval(() => {
  if (!book || $("#audio").paused || !lastTick) return;
  const now = Date.now(); const seconds=Math.min(5,(now-lastTick)/1000);const key=`${STORE.state}-${currentBookId}`; const state = load(key, {}); state.secondsRead = (state.secondsRead || 0) + seconds; lastTick = now; save(key, state);postActivity({bookId:currentBookId,readingSeconds:seconds});
}, 5000);
function postActivity(payload){return fetch("/api/activity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}).catch(()=>null);}
function logAction(group, value) { if(!currentBookId)return; const key=`${STORE.state}-${currentBookId}`; const state = load(key, {}); state[group] ||= {}; state[group][value] = (state[group][value] || 0) + 1; save(key, state); }
function finishSession() { if (!book) return; const key=`${STORE.state}-${currentBookId}`; const state = load(key, {}); state.lastVisit = Date.now(); save(key, state); }
function showPage(page) { if(!book||page===displayedPage)return; displayedPage=page; $("#pageImage").src = `${book.pageBase}/page-${String(page).padStart(3,"0")}.jpg`; $("#pageLabel").textContent = `原书第 ${page} 页`; }
function restoreProgress() { if(!book)return; const state=load(`${STORE.state}-${currentBookId}`,{});const time=state.time||0;$("#audio").currentTime=time;$("#backBtn").style.visibility="hidden"; }

async function loadApiSettings() {
  try {
    const response=await fetch("/api/settings",{cache:"no-store"}); const data=await response.json();
    $("#diocoEmail").value=data.userEmail||"";
    $("#tokenStatus").textContent=data.tokenConfigured?`令牌已配置：${data.tokenMask}`:"尚未配置令牌";
    shortcuts={previous:data.shortcutPrevious||"a",repeat:data.shortcutRepeat||"s",next:data.shortcutNext||"d",play:data.shortcutPlay||"space"};
    shelfView=data.shelfView||"tile"; currentSeries=data.currentSeries||"";
    wordTipSeconds=+(data.wordTipSeconds||2);reviewPageSize=+(data.reviewPageSize||10);manualRepeatCount=+(data.manualRepeatCount||3);manualPauseSeconds=+(data.manualPauseSeconds||2);highlightLeadMs=Number.isFinite(+data.highlightLeadMs)?+data.highlightLeadMs:0;sentenceAutoPause=!!data.sentenceAutoPause;eyeComfort=!!data.eyeComfort;heatmapRange=data.heatmapRange||"year";$("#wordTipSeconds").value=wordTipSeconds;$("#reviewPageSize").value=reviewPageSize;$("#manualRepeatCount").value=manualRepeatCount;$("#manualPauseSeconds").value=manualPauseSeconds;$("#highlightLeadMs").value=highlightLeadMs;applyEyeComfort();
    for(const [name,key] of Object.entries(shortcuts)){const input=$(`#shortcut${name[0].toUpperCase()+name.slice(1)}`);if(input){input.value=keyLabel(key);input.dataset.key=key;}}
    updateShortcutHint();
  } catch { $("#tokenStatus").textContent="无法读取本地设置"; }
}
async function saveApiSettings(event) {
  event.preventDefault(); const button=event.submitter; button.disabled=true; $("#tokenStatus").textContent="正在保存…";
  try {
    const proposed={previous:$("#shortcutPrevious").dataset.key,repeat:$("#shortcutRepeat").dataset.key,next:$("#shortcutNext").dataset.key,play:$("#shortcutPlay").dataset.key};
    const response=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({userEmail:$("#diocoEmail").value,diocoToken:$("#diocoToken").value,shortcutPrevious:proposed.previous,shortcutRepeat:proposed.repeat,shortcutNext:proposed.next,shortcutPlay:proposed.play,wordTipSeconds:+$("#wordTipSeconds").value,reviewPageSize:+$("#reviewPageSize").value,manualRepeatCount:+$("#manualRepeatCount").value,manualPauseSeconds:+$("#manualPauseSeconds").value,highlightLeadMs:+$("#highlightLeadMs").value,eyeComfort})});
    const data=await response.json(); if(!response.ok) throw new Error(data.error||"保存失败");
    shortcuts=proposed;wordTipSeconds=+$("#wordTipSeconds").value;reviewPageSize=+$("#reviewPageSize").value;manualRepeatCount=+$("#manualRepeatCount").value;manualPauseSeconds=+$("#manualPauseSeconds").value;highlightLeadMs=+$("#highlightLeadMs").value;reviewPage=1;stopManualDictation();applyEyeComfort();updateShortcutHint();syncPlaybackFrame();$("#diocoToken").value=""; $("#tokenStatus").textContent=`已保存：${data.tokenMask}`;
  } catch(error) { $("#tokenStatus").textContent=error.message; }
  finally { button.disabled=false; }
}
function updateShortcutHint(){$("#shortcutHint").textContent=`${keyLabel(shortcuts.previous)} 上一句 · ${keyLabel(shortcuts.repeat)} 复读 · ${keyLabel(shortcuts.next)} 下一句 · ${keyLabel(shortcuts.play)} 播放/暂停 · Q 句末暂停${sentenceAutoPause?'开':'关'}`;}

async function loadImportCatalog() {
  try {
    const data=await fetch("/api/import/catalog",{cache:"no-store"}).then(response=>response.json()); importCatalog=data.series||[];
    $("#importSeries").innerHTML='<option value="">请选择系列</option>'+importCatalog.map((item,index)=>`<option value="${index}">${escapeHtml(item.name)}（${item.books.length}）</option>`).join("");
    $("#importBookList").innerHTML='<p>请先选择系列</p>';
  } catch { $("#importMeta").textContent="无法扫描 books 目录"; }
}
function updateImportBooks() {
  const series=importCatalog[+$("#importSeries").value]; const list=$("#importBookList");
  if(!series){list.innerHTML='<p>请先选择系列</p>';updateBatchButton();return;}
  const eligible=series.books.filter(item=>item.ready);
  list.innerHTML=eligible.map(item=>`<label class="import-book-item ${item.importedId?'imported':''}"><img src="${encodeURI(item.coverUrl)}" alt="${escapeHtml(item.title)}封面" loading="lazy"><input type="checkbox" value="${escapeHtml(item.path)}"><span><b>${escapeHtml(item.title)}</b><small>${item.pdfCount} PDF · ${item.audioCount} MP3${item.importedId?' · 已导入，可重新导入':''}</small></span></label>`).join("");
  $("#importMeta").textContent=`${series.name}：${eligible.length} 本可导入。批量任务将严格逐本顺序执行。`;
  updateBatchButton();
}
function selectedImportPaths(){return $$("#importBookList input:checked").map(input=>input.value)}
function updateBatchButton(){const count=selectedImportPaths().length;$("#startBatchImport").disabled=!count;$("#startBatchImport").textContent=count?`按顺序导入 ${count} 本`:'按顺序导入所选书籍'}
async function startBatchImport() {
  const paths=selectedImportPaths(); if(!paths.length)return;
  clearInterval(importPollTimer); $("#importProgress").classList.remove("hidden"); $("#importStep").textContent="正在创建顺序队列"; $("#importBar").value=0; $("#importPercent").textContent="0%";
  try {
    const response=await fetch("/api/import/batch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({paths})});
    const data=await response.json(); if(!response.ok)throw new Error(data.error||"无法开始批量导入");
    pollImportBatch(data.jobIds);
  } catch(error){$("#importStep").textContent="导入失败";$("#importMessage").textContent=error.message;}
}
function pollImportBatch(jobIds) {
  const check=async()=>{
    const jobs=await Promise.all(jobIds.map(id=>fetch(`/api/import/jobs/${id}`,{cache:"no-store"}).then(r=>r.json())));
    const total=Math.round(jobs.reduce((sum,job)=>sum+(job.progress||0),0)/jobs.length); const finished=jobs.filter(job=>["complete","failed"].includes(job.status)).length;
    const current=jobs.find(job=>job.status==="running")||jobs.find(job=>job.status==="queued")||jobs[jobs.length-1];
    $("#importBar").value=total; $("#importPercent").textContent=`${total}%`; $("#importStep").textContent=`${finished}/${jobs.length} 完成 · ${current.step||current.status}`;
    $("#importMessage").textContent="批量任务严格按选择顺序逐本执行；单本失败不会阻止下一本。";
    $("#batchJobs").innerHTML=jobs.map((job,index)=>`<div class="batch-job ${job.status}"><span>${index+1}. ${escapeHtml(job.source_path.split('/').pop())}</span><b>${job.status==='complete'?'完成':job.status==='failed'?'失败':job.status==='running'?`${job.progress}%`:'排队'}</b>${job.error?`<small>${escapeHtml(job.error)}</small>`:''}</div>`).join("");
    if(finished===jobs.length){
      clearInterval(importPollTimer); importPollTimer=null;
      const data=await fetch("/api/library",{cache:"no-store"}).then(r=>r.json()); libraryBooks=data.books||[]; renderLibrary(); await loadImportCatalog();
      $("#importMessage").textContent=`批量导入结束：${jobs.filter(j=>j.status==='complete').length} 本成功，${jobs.filter(j=>j.status==='failed').length} 本失败。`;
    }
  };
  check(); importPollTimer=setInterval(check,1500);
}

init();
