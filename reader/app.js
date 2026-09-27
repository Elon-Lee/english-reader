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
function rootWord(word) { const w = word.toLowerCase().replace("’", "'"); if (dictionary[w] || localDictionary[w]) return w; return [w.replace(/ies$/, "y"), w.replace(/ing$/, ""), w.replace(/ing$/, "e"), w.replace(/ed$/, ""), w.replace(/ed$/, "e"), w.replace(/es$/, ""), w.replace(/s$/, "")].find(x => dictionary[x] || localDictionary[x]) || w; }
function wordHtml(text, sentence, cursor = { index:0 }) {
  let html = ""; let last = 0; const regex = /[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g; let match;
  while ((match = regex.exec(text))) {
    html += escapeHtml(text.slice(last, match.index));
    const timing = sentence?.words?.[cursor.index++];
    const attrs = timing ? ` data-start="${timing.start}" data-end="${timing.end}" data-aligned="${timing.aligned ? "1" : "0"}"` : "";
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
  const [libraryData, dictionaryData] = await Promise.all([
    fetch("/api/library", {cache:"no-store"}).then(r => r.json()),
    fetch("/api/local-dictionary", {cache:"no-store"}).then(r => r.json()),
  ]);
  localDictionary=dictionaryData; libraryBooks=libraryData.books||[];
  bindEvents();
  await loadApiSettings();
  setupSeriesSelector(); renderLibrary();
  loadImportCatalog();
  if(libraryBooks.length) await loadBook(libraryBooks[0].id);
}

async function loadBook(bookId) {
  const response=await fetch(`/api/books/${encodeURIComponent(bookId)}`,{cache:"no-store"});
  if(!response.ok) throw new Error("无法读取图书数据库");
  const record=await response.json(); currentBookId=bookId; book=record.book;
  $("#audio").pause(); $("#audio").src=book.audio; $("#duration").textContent=fmt(book.duration);
  $(".book-heading small").textContent=`${book.level||""}级 · LOCAL BOOK`;
  $(".book-heading strong").innerHTML=`${escapeHtml(book.title)} <i>${escapeHtml(book.englishTitle||"")}</i>`;
  $(".chapter h1").textContent=book.englishTitle||book.title;
  active=-1; displayedPage=null; renderStory(); restoreProgress(); refreshDashboards(); showPage(book.sentences[0]?.page||1);
}

function renderLibrary() {
  const grid=$("#libraryGrid");
  const visible=libraryBooks.filter(item=>!currentSeries||item.series===currentSeries);
  grid.className=`library-grid ${shelfView}-view`;
  $("#shelfCount").textContent=`${visible.length} 本`; $("#shelfSeriesTitle").textContent=currentSeries||"全部书籍";
  $("#tileViewBtn").classList.toggle("active",shelfView==="tile"); $("#listViewBtn").classList.toggle("active",shelfView==="list");
  if(!visible.length){grid.innerHTML='<div class="empty-state"><h3>当前书系暂无已导入书籍</h3><p>请从“导入书籍”选择书籍。</p></div>';return;}
  grid.innerHTML=visible.map(item=>`<article class="book-card" data-book-id="${escapeHtml(item.id)}"><img src="${encodeURI(item.cover_url)}" alt="${escapeHtml(item.title)}封面"><div class="book-info"><span class="tag">LEVEL ${escapeHtml(item.level||"-")}</span><h3>${escapeHtml(item.title)}</h3><em>${escapeHtml(item.english_title||"")}</em><p>${escapeHtml(item.series)}</p><div class="progress"><i style="width:${bookProgress(item.id)}%"></i></div><small>${item.alignment==='whisper-word-timestamps'?'Whisper 词级点读':'本地点读'}</small></div><button class="round-play">▶</button></article>`).join("");
}
function setupSeriesSelector(){const series=[...new Set(libraryBooks.map(item=>item.series))];if(!currentSeries||!series.includes(currentSeries))currentSeries=series[0]||"";$("#seriesSelect").innerHTML=series.map(name=>`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");$("#seriesSelect").value=currentSeries;}
function bookProgress(id){const state=load(`${STORE.state}-${id}`,{});const item=libraryBooks.find(x=>x.id===id);return item?.duration?Math.round((state.time||0)/item.duration*100):0}

function renderStory() {
  const box = $("#sentences");
  box.innerHTML = "";
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
  });
}

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
      $("#audio").pause(); pausedForWord=false;
      showWord(word.textContent, sentence, word);
      playWordTts(word.textContent);
    }
    else playSentence(+sentenceElement.dataset.i);
  });
  $("#sentences").addEventListener("mouseover", event => {
    if (mode === "intensive" && event.target.classList.contains("word") && !$("#audio").paused) { pausedForWord = true; $("#audio").pause(); }
  });
  $("#sentences").addEventListener("mouseout", event => {
    if (pausedForWord && event.target.classList.contains("word")) { pausedForWord = false; $("#audio").play(); }
  });
  $("#playBtn").onclick = () => { clearTimeout(audioStopTimer); if ($("#audio").paused) { wordStopAt=null; $("#audio").play(); } else $("#audio").pause(); };
  $("#prevBtn").onclick = () => playSentence(Math.max(0, active - 1));
  $("#nextBtn").onclick = () => playSentence(Math.min(book.sentences.length - 1, active + 1));
  $("#seek").oninput = event => $("#audio").currentTime = event.target.value / 1000 * book.duration;
  const rates = [.75, 1, 1.25, 1.5]; let rateIndex = 1;
  $("#speedBtn").onclick = () => { rateIndex = (rateIndex + 1) % rates.length; $("#audio").playbackRate = rates[rateIndex]; $("#speedBtn").textContent = rates[rateIndex] + "×"; };
  $("#viewBtn").onclick = () => { $("#pagePanel").classList.toggle("hidden"); showPage(book.sentences[Math.max(0,active)]?.page||1); };
  $("#closePage").onclick = () => $("#pagePanel").classList.add("hidden");
  $("#focusBtn").onclick = () => document.body.classList.toggle("focus");
  $("#recordBtn").onclick = toggleRecording;
  $("#playRecordBtn").onclick = () => { if (recordingUrl) { $("#recording").src = recordingUrl; $("#recording").play(); } };
  $("#audio").ontimeupdate = onTimeUpdate;
  $("#audio").onplay = () => { $("#playBtn").textContent = "Ⅱ"; trackListening(); };
  $("#audio").onpause = () => $("#playBtn").textContent = "▶";
  window.addEventListener("beforeunload", finishSession);
  $("#settingsForm").onsubmit = saveApiSettings;
  $("#seriesSelect").onchange = event => {currentSeries=event.target.value;renderLibrary();savePreference({currentSeries});};
  $("#tileViewBtn").onclick=()=>setShelfView("tile"); $("#listViewBtn").onclick=()=>setShelfView("list");
  $$(".shortcut-input").forEach(input=>input.onkeydown=captureShortcut);
  $("#importSeries").onchange = updateImportBooks;
  $("#importBookList").onchange = updateBatchButton;
  $("#selectAllBooks").onclick = () => { $$("#importBookList input:not(:disabled)").forEach(input=>input.checked=true); updateBatchButton(); };
  $("#clearBooks").onclick = () => { $$("#importBookList input").forEach(input=>input.checked=false); updateBatchButton(); };
  $("#startBatchImport").onclick = startBatchImport;
  document.addEventListener("keydown",handleReaderShortcut);
  document.addEventListener("click",event=>{const button=event.target.closest("button");if(button)setTimeout(()=>button.blur(),0);});
}

function setShelfView(view){shelfView=view;renderLibrary();savePreference({shelfView:view});}
function savePreference(value){fetch("/api/preferences",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}).catch(()=>{});}
function keyName(event){return event.key===" "?"space":event.key.toLowerCase();}
function keyLabel(key){return key==="space"?"空格":key.length===1?key.toUpperCase():key;}
function captureShortcut(event){event.preventDefault();event.stopPropagation();const key=keyName(event);if(["shift","control","alt","meta"].includes(key))return;event.target.value=keyLabel(key);event.target.dataset.key=key;event.target.blur();}

function handleReaderShortcut(event) {
  if($("#reader").classList.contains("hidden") || event.metaKey || event.ctrlKey || event.altKey) return;
  if(event.target.closest("input,textarea,select,button,[contenteditable=true]")) return;
  const key=keyName(event); const action=Object.entries(shortcuts).find(([,value])=>value===key)?.[0]; if(!action)return; event.preventDefault();
  if(action==="play") { clearTimeout(audioStopTimer); wordStopAt=null; $("#audio").paused ? $("#audio").play() : $("#audio").pause(); }
  if(action==="previous" && book) playSentence(Math.max(0,(active<0?0:active)-1));
  if(action==="repeat" && book) playSentence(Math.max(0,active));
  if(action==="next" && book) playSentence(Math.min(book.sentences.length-1,(active<0?-1:active)+1));
}

function showScreen(id) {
  $$(".screen").forEach(screen => screen.classList.toggle("hidden", screen.id !== id));
  $$(".nav").forEach(nav => nav.classList.toggle("active", nav.dataset.screen === id));
  const reading = id === "reader";
  $("#player").classList.toggle("hidden", !reading);
  $(".book-heading").style.display = reading ? "block" : "none";
  $(".top-actions").style.display = reading ? "flex" : "none";
  $("#backBtn").style.visibility = reading ? "visible" : "hidden";
  if (!reading) { $("#audio").pause(); clearTimeout(shadowTimer); refreshDashboards(); }
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
  wordStopAt = mode === "shadow" ? null : sentence.end + .08;
  pausedForWord = false;
  seekAndPlay(sentence.start, mode === "shadow" ? null : sentence.end + .03);
  highlight(index, true);
  showPage(sentence.page);
  if (mode === "shadow") { $("#shadowStatus").textContent = "先听原音…"; $("#shadowPrompt").textContent = sentence.text; }
  const stateKey=`${STORE.state}-${currentBookId}`; const state=load(stateKey,{}); state.sentencesPlayed=(state.sentencesPlayed||0)+1; save(stateKey,state);
}

function onTimeUpdate() {
  const audio = $("#audio"); const time = audio.currentTime;
  $("#currentTime").textContent = fmt(time);
  $("#seek").value = time / book.duration * 1000;
  const state = load(`${STORE.state}-${currentBookId}`, {}); state.time = time; save(`${STORE.state}-${currentBookId}`, state);
  if (wordStopAt !== null && time >= wordStopAt) { wordStopAt = null; audio.pause(); }
  const index = book.sentences.findIndex(s => time >= s.start && time < s.end);
  if (index >= 0 && index !== active) {
    highlight(index, true);
    if(book.sentences[index].page!==displayedPage) showPage(book.sentences[index].page);
  }
  const nextSpoken = index >= 0 ? $$( `.sentence[data-i="${index}"] .word[data-start][data-end]`).find(word => time >= +word.dataset.start && time < +word.dataset.end) : null;
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
  $$(".sentence").forEach((element, i) => element.classList.toggle("active", i === index));
  active = index;
  if (scroll) $$(".sentence")[index]?.scrollIntoView({ behavior:"smooth", block:"center" });
}

function jumpToSection(section) {
  const index = book.sentences.findIndex(sentence => sentence.section === section);
  if (index < 0) { alert(`第 ${section} 段尚未成功识别，请在导入质检中检查。`); return; }
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
  const vocab = load(STORE.vocab, {});
  const saved = vocab[definition.root];
  const requestId=++wordRequestId;
  $("#wordPanel").innerHTML = `<div class="definition">
    <button class="speak" id="speakWord" title="播放接口发音">♪</button><span class="phonetic">${formatText(definition.phonetic)}</span><h2>${escapeHtml(raw)}</h2>
    <div id="remoteDefinition"><p class="loading-line">正在查询中文释义…</p></div>
    <div class="context"><small>IN THIS STORY · 第 ${sentence.page} 页</small><p>${highlightWord(sentence.text, raw)}</p></div>
    <div id="remoteUsage" class="usage-note"><span class="loading-line">正在分析上下文用法…</span></div>
    <div id="remoteExamples" class="dict-examples"><span class="loading-line">正在加载例句…</span></div>
    <div class="rating"><small>${saved ? `当前：${ratingName(saved.rating)} · 下次 ${day(saved.due)}` : "加入复习并评级"}</small>
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

function rateWord(raw, sentence, definition, rating, wordElement) {
  const vocab = load(STORE.vocab, {}); const previous = vocab[definition.root];
  const intervals = { known:7, fuzzy:3, unknown:1 };
  const base = intervals[rating];
  const nextInterval = rating === "known" && previous ? Math.min(60, Math.max(base, (previous.interval || base) * 2)) : base;
  vocab[definition.root] = { word:raw, root:definition.root, phonetic:definition.phonetic, meaning:definition.meaning, english:definition.english,
    usage:definition.usage, context:sentence.text, sentenceId:sentence.id, page:sentence.page, rating, interval:nextInterval,
    due:Date.now() + nextInterval * 86400000, updatedAt:Date.now(), reviews:(previous?.reviews || 0) + 1 };
  save(STORE.vocab, vocab); showWord(raw, sentence, wordElement); refreshDashboards();
}

function refreshDashboards() { renderStats(); renderReview(); }

function renderStats() {
  if (!book) return;
  const state = load(`${STORE.state}-${currentBookId}`, {}); const vocab = Object.values(load(STORE.vocab, {}));
  const percent = Math.round((state.time || 0) / book.duration * 100);
  $("#statsContent").innerHTML = `<div class="metric-grid">
    <article><small>阅读进度</small><b>${percent}%</b><p>${fmt(state.time || 0)} / ${fmt(book.duration)}</p></article>
    <article><small>累计听读</small><b>${Math.round((state.secondsRead || 0) / 60)}</b><p>分钟</p></article>
    <article><small>已学单词</small><b>${vocab.length}</b><p>${vocab.filter(v => v.due <= Date.now()).length} 个待复习</p></article>
    <article><small>剧情选择</small><b>${state.branches || 0}</b><p>次主动选择</p></article>
  </div><div class="panel"><h3>学习方式</h3><div class="mode-bars">${modeBar("精读", state.modes?.intensive || 0)}${modeBar("泛听", state.modes?.extensive || 0)}${modeBar("跟读", state.modes?.shadow || 0)}</div></div>`;
}
function modeBar(name, count) { return `<div><span>${name}</span><i style="width:${Math.min(100, count * 18 + 8)}%"></i><b>${count} 次</b></div>`; }

function renderReview() {
  if (!book) return;
  const vocab = Object.values(load(STORE.vocab, {})).sort((a,b) => a.due - b.due);
  const due = vocab.filter(entry => entry.due <= Date.now());
  $("#dueBadge").textContent = due.length; $("#dueBadge").classList.toggle("hidden", !due.length);
  if (!vocab.length) { $("#reviewContent").innerHTML = `<div class="empty-state"><span>☆</span><h3>还没有生词</h3><p>在精读模式中点击单词，再选择“模糊”或“不认识”。</p></div>`; return; }
  $("#reviewContent").innerHTML = `<div class="review-summary"><b>${due.length}</b><span>今天待复习</span><small>共收录 ${vocab.length} 个词</small></div><div class="vocab-list">${vocab.map(entry => `<article class="vocab-card ${entry.due <= Date.now() ? "due" : ""}" data-word="${entry.root}"><div><small>${entry.phonetic}</small><h3>${escapeHtml(entry.word)}</h3><p>${entry.meaning}</p></div><div class="vocab-context">${escapeHtml(entry.context)}<small>${entry.due <= Date.now() ? "现在复习" : `下次 ${day(entry.due)}`}</small></div><div class="mini-rates"><button data-review="known">认识</button><button data-review="fuzzy">模糊</button><button data-review="unknown">不认识</button></div></article>`).join("")}</div>`;
  $$("#reviewContent [data-review]").forEach(button => button.onclick = () => reviewSavedWord(button.closest(".vocab-card").dataset.word, button.dataset.review));
}

function reviewSavedWord(root, rating) {
  const vocab = load(STORE.vocab, {}); const entry = vocab[root]; if (!entry) return;
  const intervals = { known:Math.min(60, Math.max(7, (entry.interval || 3) * 2)), fuzzy:3, unknown:1 };
  entry.rating = rating; entry.interval = intervals[rating]; entry.due = Date.now() + entry.interval * 86400000; entry.reviews = (entry.reviews || 0) + 1; entry.updatedAt = Date.now();
  save(STORE.vocab, vocab); refreshDashboards();
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
  const now = Date.now(); const key=`${STORE.state}-${currentBookId}`; const state = load(key, {}); state.secondsRead = (state.secondsRead || 0) + Math.min(5, (now - lastTick) / 1000); lastTick = now; save(key, state);
}, 5000);
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
    for(const [name,key] of Object.entries(shortcuts)){const input=$(`#shortcut${name[0].toUpperCase()+name.slice(1)}`);if(input){input.value=keyLabel(key);input.dataset.key=key;}}
    updateShortcutHint();
  } catch { $("#tokenStatus").textContent="无法读取本地设置"; }
}
async function saveApiSettings(event) {
  event.preventDefault(); const button=event.submitter; button.disabled=true; $("#tokenStatus").textContent="正在保存…";
  try {
    const proposed={previous:$("#shortcutPrevious").dataset.key,repeat:$("#shortcutRepeat").dataset.key,next:$("#shortcutNext").dataset.key,play:$("#shortcutPlay").dataset.key};
    const response=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({userEmail:$("#diocoEmail").value,diocoToken:$("#diocoToken").value,shortcutPrevious:proposed.previous,shortcutRepeat:proposed.repeat,shortcutNext:proposed.next,shortcutPlay:proposed.play})});
    const data=await response.json(); if(!response.ok) throw new Error(data.error||"保存失败");
    shortcuts=proposed;updateShortcutHint();$("#diocoToken").value=""; $("#tokenStatus").textContent=`已保存：${data.tokenMask}`;
  } catch(error) { $("#tokenStatus").textContent=error.message; }
  finally { button.disabled=false; }
}
function updateShortcutHint(){$("#shortcutHint").textContent=`${keyLabel(shortcuts.previous)} 上一句 · ${keyLabel(shortcuts.repeat)} 复读 · ${keyLabel(shortcuts.next)} 下一句 · ${keyLabel(shortcuts.play)} 播放/暂停`;}

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
