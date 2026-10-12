const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

// The headers are ignored by the legacy local-only server.  When the SaaS
// feature flag is enabled they bind mutating same-origin API requests to the
// logged-in session and give the server a stable device identity.
const readerFetch = window.fetch.bind(window);
function readerCookie(name){return document.cookie.split('; ').find(value=>value.startsWith(`${name}=`))?.slice(name.length+1)||"";}
function readerDeviceId(){
  let value=localStorage.getItem("shiyue-device-id");
  if(!value){value=(crypto.randomUUID?.()||`${Date.now()}-${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9._:-]/g,"");localStorage.setItem("shiyue-device-id",value);}
  return value;
}
window.fetch=(input,init={})=>{
  const requestUrl=typeof input==="string"?input:input.url;
  const method=(init.method||(typeof input!=="string"&&input.method)||"GET").toUpperCase();
  const isApi=requestUrl.startsWith("/api/")||requestUrl.startsWith(location.origin+"/api/");
  if(!isApi)return readerFetch(input,init);
  const headers=new Headers((typeof input!=="string"&&input.headers)||undefined);
  new Headers(init.headers||undefined).forEach((value,key)=>headers.set(key,value));
  headers.set("X-Device-Id",readerDeviceId());
  if(!["GET","HEAD","OPTIONS"].includes(method)){
    const csrf=readerCookie("shiyue_csrf");if(csrf)headers.set("X-CSRF-Token",csrf);
  }
  return readerFetch(input,{...init,headers});
};

let book;
let localDictionary = {};
let libraryBooks = [];
let currentBookId = "";
let importCatalog = [];
let runtimeMode="full";
let saasMode=false;
let saasUser=null;
let membershipData=null;
let catalogBooks=[];
let catalogFiltersLoaded=false;
let selectedCatalogBookId="";
let rewardStatusData=null;
let catalogReaderBookId="";
let catalogReadingSession=null;
let saasReaderContext=null;
let routeReady=false;
let workspaceBooks=[];
let workspaceBooksLoaded=false;
let workspaceReaderSession=null;
let workspaceReaderBook=null;
let workspaceWordContext=null;
let workspaceTasks=[];
let workspaceQuery="";
let workspaceSort="recent";
let adminData=null;
let adminTab="overview";
let adminMediaPage=1;
const ADMIN_MEDIA_PAGE_SIZE=20;
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
let wordResumeTimer = null;
const WORD_RESUME_DELAY_MS = 300;
const WORD_FADE_IN_MS = 240;
let mainAudioFadeFrame = null;
let mainAudioFadeToken = 0;
let mainAudioRestoreVolume = 1;
let mainAudioFadeTarget = null;
let currentSeries = "";
let seriesExpanded=false;
const RECENT_SERIES_LIMIT=4;
let shelfView = "tile";
let readerLayout="side";
let shortcuts = {previous:"a",repeat:"s",next:"d",play:"space"};
let shadowWaiting = false;
let shadowTimer;
let shadowSentenceIndex=-1;
let mediaRecorder;
let recordingChunks = [];
let recordingUrl = "";
let recognition;
let recognizedText = "";
let wordStopAt = null;
let spokenWordElement = null;
let audioStopTimer = null;
let playbackRequestToken = 0;
let wordTtsAudio = null;
let wordRequestId = 0;
let playbackFrameId = null;
let videoFrameCallbackId = null;
let mediaStageResizeFrame = null;
let seekPreviewFrame = null;
let seekPreviewPointerX = 0;
let seekPreviewDragging = false;
let pendingSeekTime = null;
let wordElementsBySentence = [];
let sentenceElementsByIndex=[];
let annotationIndex=new Map();
let vocabWordIndex=new Map();
let storyWindowStart=0;
let storyWindowEnd=0;
let virtualStory=false;
let lastPlaybackUiUpdate=0;
const STORY_WINDOW_RADIUS=45;
const STORY_WINDOW_EDGE=10;
const PLAYBACK_UI_INTERVAL_MS=100;
const VIDEO_SOFT_SYNC_SECONDS=.04;
const VIDEO_HARD_SYNC_SECONDS=.18;
const VIDEO_MAX_RATE_CORRECTION=.04;
let wordAnnotations=[];
let vocabItems=[];
let wordTipSeconds=2;
let eyeComfort=false;
let selectedWordContext=null;
let selectedGrammarSentence=null;
let grammarRequestId=0;
let expandedSentenceTranslations=new Set();
let wordTipTimer=null;
let wordHoverMeaningTimer=null;
let wordHoverMeaningRequestId=0;
let wordHoverMeaningElement=null;
const wordHoverMeaningCache=new Map();
const WORD_HOVER_MEANING_DELAY_MS=100;
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
let videoQuality="high";
let videoQualitySwitchToken=0;
let videoBufferTimer=null;
let videoDowngradeTimer=null;
let videoStatusTimer=null;
let videoRetryCount=0;
let videoAutoDowngraded=false;
let videoTitleManuallyEdited=false;
let videoImportPollTimer=null;
let sentenceAutoPause=false;
let highlightLeadMs=0;
let paintedSentenceIndex=-1;
let youtubeInfo=null;
let youtubePollTimer=null;
let youtubeTitleManuallyEdited=false;
let pendingDeleteBook=null;
let pendingImportJobs=[];
let deploymentPollTimer=null;
let deploymentLogOffset=0;
let activeDeploymentJob=null;
let deploymentTargets=[];
let activeDeploymentTargetId=0;
let pendingUninstallTargetId=0;
let bookChunkPromises=new Map();
let vocabLoaded=false;
let vocabLoadPromise=null;
let learningDaysLoaded=false;
let importCatalogLoaded=false;
let importTrackingRestored=false;
let deploymentConfigLoaded=false;
const compactTouchQuery=matchMedia("(max-width: 1023px) and (hover: none) and (pointer: coarse)");

const STORE = {
  state: "shiyue-reader-state-v2",
  vocab: "shiyue-vocab-v2",
  imports: "shiyue-active-imports-v1",
  settingsTab: "shiyue-settings-tab-v1",
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
function displaySource(value){
  const source=String(value||"");if(runtimeMode!=="reader")return source;
  return source.replace("Stanza 本地句法模型","Stanza 句法模型").replace("本地 ECDICT + Stanza","内置词典与句法").replace("本地词典","内置词典").replace("本地语境规则","语境规则").replace("本地模型","句法模型");
}
function onlineServiceFallback(error,kind,fallback){
  const detail=String(error?.message||"");
  if(/credentials|token|令牌|邮箱/i.test(detail))return `当前服务未配置Dioco邮箱或令牌，请在系统设置中保存后重试；已使用${fallback}`;
  if(/timed out|timeout|urlopen|network|502|连接|访问/i.test(detail))return `服务器暂时无法访问在线${kind}接口；已使用${fallback}`;
  return `${kind}接口暂不可用；已使用${fallback}`;
}
function applyRuntimePresentation(){
  const remote=runtimeMode==="reader";document.body.dataset.runtimeMode=runtimeMode;document.body.classList.remove("runtime-pending");
  $("#brandModeLabel").textContent=remote?"WEB READER":"LOCAL READER";
  const loading=$("#libraryLoadingText");if(loading)loading.textContent=remote?"正在读取书架…":"正在从本地数据库读取书架…";
  $("#statsDescription").textContent=remote?"查看最近的阅读、查词、复习和跟读情况。":"你的数据只保存在这台设备。";
  $("#settingsModeLabel").textContent=remote?"READER SETTINGS":"LOCAL SYSTEM SETTINGS";
  $("#settingsDescription").textContent=remote?"管理账户、快捷键与阅读体验。":"阅读偏好与服务器运维分区管理，配置只保存在你的设备中。";
  $("#tokenPrivacyText").textContent=remote?"令牌由当前阅读服务安全保存，仅在调用词典服务时使用。":"令牌只提交给本机服务，并保存在仅当前用户可读的配置文件中。";
}
function focusedWordContext(text,wordIndex){
  const matches=[...text.matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g)];const target=matches[wordIndex];if(!target)return text.slice(0,220);
  const position=target.index,terminator=/[.!?。！？…]/g;let start=0,end=text.length,match;
  while((match=terminator.exec(text))&&match.index<position)start=match.index+1;
  terminator.lastIndex=position;match=terminator.exec(text);if(match)end=match.index+1;
  let result=text.slice(start,end).trim();
  if(result.length>240||(!match&&end-start>240)){const from=Math.max(0,wordIndex-10),to=Math.min(matches.length,wordIndex+11);const first=matches[from],last=matches[to-1];result=text.slice(first.index,last.index+last[0].length).trim();if(from>0)result="… "+result;if(to<matches.length)result+=" …";}
  return result;
}
function wordRecordKey(sentenceId,wordIndex,bookId=currentBookId){return `${bookId}|${sentenceId}|${wordIndex}`;}
function rebuildWordIndexes(){
  annotationIndex=new Map(wordAnnotations.map(item=>[wordRecordKey(item.sentence_id,item.word_index,item.book_id||currentBookId),item]));
  vocabWordIndex=new Map(vocabItems.map(item=>[wordRecordKey(item.sentence_id,item.word_index,item.book_id),item]));
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
  syncResponsiveState();
  bindEvents();
  let health={};
  try{health=await fetch("/api/health",{cache:"no-store"}).then(response=>response.json());}catch{}
  if(health.saasEnabled){saasMode=true;await initSaasMode();return;}
  const [libraryData]=await Promise.all([fetch("/api/library",{cache:"no-cache"}).then(r=>r.json()),loadApiSettings()]);
  libraryBooks=libraryData.books||[];
  populateVideoSeriesOptions();
  setupSeriesSelector(); renderLibrary(); showScreen("shelf");
}

async function initSaasMode(){
  document.body.classList.add("saas-mode");
  try{
    const response=await fetch("/api/auth/me",{cache:"no-store"});
    if(!response.ok){showSaasAuth();return;}
    const data=await response.json();saasUser=data.user;activateSaasApp();
  }catch(error){console.error("SaaS 界面初始化失败",error);showSaasAuth(`会员界面初始化失败：${error?.message||"未知错误"}`);}
}
function showSaasAuth(message=""){
  vocabItems=[];vocabLoaded=false;vocabLoadPromise=null;learningDays=[];learningDaysLoaded=false;workspaceBooks=[];workspaceBooksLoaded=false;workspaceTasks=[];wordAnnotations=[];rebuildWordIndexes();document.body.classList.add("saas-unauthenticated");$("#saasAuth").classList.remove("hidden");$("#saasAuthMessage").textContent=message;
}
function activateSaasApp(){
  const preferences=load("shiyue-saas-preferences",{}),params=new URLSearchParams(location.search),requested=params.get("screen"),allowed=new Set(["catalog","my-library","workspace","stats","vocab","rewards","membership","admin","settings"]),initial=allowed.has(requested)&&!(requested==="admin"&&!saasUser?.isAdmin)?requested:"catalog";heatmapRange=preferences.heatmapRange||heatmapRange;document.body.classList.remove("saas-unauthenticated");$("#saasAuth").classList.add("hidden");$$('[data-saas-only]').forEach(item=>item.classList.remove("hidden"));$("#mobileBottomNav")?.classList.remove("hidden");if(!saasUser?.isAdmin)$$('[data-admin-only]').forEach(item=>item.classList.add("hidden"));$$('.nav:not([data-saas-only])').forEach(item=>item.classList.add("hidden"));$("#seriesChannels").classList.add("hidden");configureSaasSettings();showScreen(initial);if(initial==="admin"&&params.get("tab"))setAdminTab(params.get("tab"),false);if(initial==="settings"&&params.get("tab"))setSettingsTab(params.get("tab"),false);const readerId=params.get("id"),readerKind=params.get("reader");if(requested==="reader"&&readerId)setTimeout(()=>readerKind==="official"?openCatalogReader(readerId):openWorkspaceReader(readerId),0);else if(params.get("book"))setTimeout(()=>loadCatalogDetail(params.get("book")),0);
}
function configureSaasSettings(){const preferences=load("shiyue-saas-preferences",{});$("#settingsAccountEyebrow").textContent="ACCOUNT & PLATFORM";$("#settingsAccountTitle").textContent="账号与平台服务";$("#settingsAccountGrid").innerHTML=`<article class="saas-settings-account"><small>当前登录账号</small><b>${escapeHtml(saasUser?.email||"")}</b><p>${saasUser?.isAdmin?"平台管理员":"普通会员"} · ${escapeHtml(saasUser?.planVersion||"free-v1")}</p></article><article class="saas-settings-account"><small>词典与 AI</small><b>平台统一管理</b><p>个人端无需填写 Dioco 账号或令牌；AI 未配置时会给出明确提示且不扣额度。</p></article>`;$("#tokenStatus").textContent="SaaS 设置保存在当前浏览器";$("#tokenPrivacyText").textContent="阅读偏好只保存在当前浏览器；账号数据、学习数据和 AI 缓存保存在 PostgreSQL。";$("#settingsForm button[type=submit]").textContent="保存阅读偏好";shortcuts={previous:preferences.shortcutPrevious||"a",repeat:preferences.shortcutRepeat||"s",next:preferences.shortcutNext||"d",play:preferences.shortcutPlay||"space"};wordTipSeconds=+(preferences.wordTipSeconds||2);reviewPageSize=+(preferences.reviewPageSize||10);manualRepeatCount=+(preferences.manualRepeatCount||3);manualPauseSeconds=+(preferences.manualPauseSeconds||2);highlightLeadMs=Number.isFinite(+preferences.highlightLeadMs)?+preferences.highlightLeadMs:0;for(const [name,key] of Object.entries(shortcuts)){const input=$(`#shortcut${name[0].toUpperCase()+name.slice(1)}`);if(input){input.value=keyLabel(key);input.dataset.key=key;}}$("#wordTipSeconds").value=wordTipSeconds;$("#reviewPageSize").value=reviewPageSize;$("#manualRepeatCount").value=manualRepeatCount;$("#manualPauseSeconds").value=manualPauseSeconds;$("#highlightLeadMs").value=highlightLeadMs;updateShortcutHint();syncSettingsTabVisibility();}
function membershipFeatureName(feature){return {official_library_capacity:"官方书架",official_unlocks:"官方读物解锁",ai_context_generations:"AI语境精讲",ai_grammar_generations:"智能句法分析",mp3_imports:"MP3智能导入",video_imports:"本地视频导入",youtube_imports:"YouTube导入",storage_bytes:"私人学习空间",devices:"同时登录设备"}[feature]||feature;}
function membershipValue(feature,value){if(feature!=="storage_bytes")return String(value);const units=["B","KB","MB","GB","TB"];let n=Number(value)||0,index=0;while(n>=1024&&index<units.length-1){n/=1024;index++;}return `${n>=10||index===0?n.toFixed(0):n.toFixed(1)} ${units[index]}`;}
function membershipGroup(feature){if(["official_library_capacity","official_unlocks"].includes(feature))return["内容权益","书架与官方读物"];if(["ai_context_generations","ai_grammar_generations"].includes(feature))return["AI 学习","语境与句法分析"];if(["mp3_imports","video_imports","youtube_imports"].includes(feature))return["导入能力","MP3、视频与 YouTube"];return["账户资源","空间与设备"]}
function renderMembership(data,orders=[]){
  membershipData=data;const plan=data.plan||{},period=data.period||{};$("#membershipSummary").textContent=`${saasUser?.email||""} · 下次重置 ${period.endsAt?new Date(period.endsAt).toLocaleString():"-"}`;
  $("#membershipPlan").innerHTML=`<div><small>当前套餐</small><h2>${escapeHtml(plan.name||plan.id||"免费版")}</h2><p>${data.subscription?`有效至 ${new Date(data.subscription.endsAt).toLocaleDateString("zh-CN")}`:"免费版每 30 天重置一次"}</p></div><span class="membership-plan-badge">${escapeHtml(plan.name||"专业版")}</span>`;
  const groups=new Map();for(const item of data.usage||[]){const[group,description]=membershipGroup(item.feature);if(!groups.has(group))groups.set(group,{description,items:[]});groups.get(group).items.push(item);}let usageHtml="";for(const [title,group] of groups){let cards="";for(const item of group.items){const used=(item.used||0)+(item.reserved||0),limit=Math.max(1,item.limit||0),ratio=Math.min(1,used/limit);cards+=`<article><b>${escapeHtml(membershipFeatureName(item.feature))}</b><small>已使用 ${membershipValue(item.feature,item.used||0)}${item.reserved?` · ${membershipValue(item.feature,item.reserved)} 处理中`:""} / ${membershipValue(item.feature,item.limit||0)}</small><meter min="0" max="1" value="${ratio}"></meter>${item.credits?`<small>含补发 ${membershipValue(item.feature,item.credits)}</small>`:""}</article>`;}usageHtml+=`<section class="membership-usage-group"><div class="membership-usage-group-head"><h2>${title}</h2><small>${group.description}</small></div><div class="membership-usage-grid">${cards}</div></section>`;}$("#membershipUsage").innerHTML=usageHtml;
  $("#membershipOrderList").className="membership-order-list";$("#membershipOrderList").innerHTML=orders.length?orders.map(order=>`<article class="membership-order"><span><b>${escapeHtml(order.planVersion)}</b><small>${new Date(order.startsAt).toLocaleDateString()} — ${new Date(order.endsAt).toLocaleDateString()}${order.note?` · ${escapeHtml(order.note)}`:""}</small></span><span><em>${escapeHtml(order.status)}</em><small>${order.amountCents?`¥${(order.amountCents/100).toFixed(2)}`:"人工开通"}</small></span></article>`).join(""):'<p class="empty-state">暂无人工开通记录。</p>';
}
async function refreshMembership(){
  if(!saasMode)return;$("#membershipNotice").textContent="正在刷新权益…";
  try{const [membershipResponse,ordersResponse]=await Promise.all([fetch("/api/membership/usage",{cache:"no-store"}),fetch("/api/membership/orders",{cache:"no-store"})]);const membership=await membershipResponse.json(),orders=await ordersResponse.json();if(!membershipResponse.ok)throw new Error(membership.error||"无法读取会员信息");if(!ordersResponse.ok)throw new Error(orders.error||"无法读取订单记录");renderMembership(membership,orders.orders||[]);await loadDeletionStatus();$("#membershipNotice").textContent="额度会在成功结算后扣除；失败或取消的任务会自动释放预占额度。";}catch(error){$("#membershipNotice").textContent=error.message||"无法读取会员信息";}}
async function loadDeletionStatus(){try{const response=await fetch("/api/account/deletion-status",{cache:"no-store"}),data=await response.json();if(!response.ok)return;const pending=data.status==="requested";$("#accountCancelDeletion").classList.toggle("hidden",!pending);if(pending)$("#membershipNotice").textContent=`账号注销已请求，可在 ${new Date(data.scheduledFor).toLocaleString()} 前撤销。`;}catch{}}
async function exportAccountData(){try{const response=await fetch("/api/account/export",{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"导出失败");const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`shiyue-account-${new Date().toISOString().slice(0,10)}.json`;link.click();URL.revokeObjectURL(url);}catch(error){$("#membershipNotice").textContent=error.message||"导出失败";}}
async function requestAccountDeletion(){if(!confirm("确认请求注销账号？当前会话将退出，你可以在 30 天内重新登录并撤销。"))return;try{const response=await fetch("/api/account/deletion",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:"user requested from membership center"})}),data=await response.json();if(!response.ok)throw new Error(data.error||"注销请求失败");showSaasAuth(`注销请求已提交，可在 ${new Date(data.scheduledFor).toLocaleString()} 前重新登录撤销。`);}catch(error){$("#membershipNotice").textContent=error.message||"注销请求失败";}}
async function cancelAccountDeletion(){try{const response=await fetch("/api/account/deletion/cancel",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}),data=await response.json();if(!response.ok)throw new Error(data.error||"撤销失败");await refreshMembership();$("#membershipNotice").textContent="注销请求已撤销。";}catch(error){$("#membershipNotice").textContent=error.message||"撤销失败";}}
async function submitSaasLogin(event){event.preventDefault();const form=event.currentTarget,button=form.querySelector("button");button.disabled=true;$("#saasAuthMessage").textContent="正在登录…";try{const response=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("#saasLoginEmail").value,password:$("#saasLoginPassword").value})});const data=await response.json();if(!response.ok)throw new Error(data.error||"登录失败");saasUser=data.user;activateSaasApp();}catch(error){$("#saasAuthMessage").textContent=error.message||"登录失败";}finally{button.disabled=false;}}
async function submitSaasRegister(event){event.preventDefault();const form=event.currentTarget,button=form.querySelector("button");button.disabled=true;$("#saasAuthMessage").textContent="正在创建账号…";try{const response=await fetch("/api/auth/register",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({invitationCode:$("#saasInviteCode").value,email:$("#saasRegisterEmail").value,password:$("#saasRegisterPassword").value})});const data=await response.json();if(!response.ok)throw new Error(data.error||"注册失败");$("#saasAuthMessage").textContent=data.emailDelivery?"账号已创建，请查收验证邮件后登录。":"账号已创建。SMTP 尚未配置，请联系管理员完成邮箱验证。";}catch(error){$("#saasAuthMessage").textContent=error.message||"注册失败";}finally{button.disabled=false;}}
async function submitSaasForgot(event){event.preventDefault();try{await fetch("/api/auth/forgot-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("#saasForgotEmail").value})});$("#saasAuthMessage").textContent="如该邮箱存在，重置邮件已发送。";}catch{$("#saasAuthMessage").textContent="请求失败，请稍后重试。";}}
async function logoutSaas(){try{await fetch("/api/auth/logout",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});}finally{saasUser=null;showSaasAuth("已退出登录。");}}
function catalogCover(book){const seed=String(book.id||book.englishTitle||book.title||"R").replace(/[^a-z0-9]/gi,"").slice(-6)||"reader";const initial=escapeHtml((book.englishTitle||book.title||"R").slice(0,1).toUpperCase());return '<span class="catalog-cover catalog-cover-'+seed+'" aria-hidden="true"><b>'+initial+'</b><i></i></span>';}/*
function workspaceCard(book){const seconds=book.progress?.readingSeconds||0,progress=book.duration?Math.min(100,Math.round(seconds/book.duration*100)):0;return `<button class="catalog-book-card workspace-book-card" type="button" data-workspace-book="${escapeHtml(book.id)}">${catalogCover(book)}<span class="workspace-card-copy"><span class="catalog-state">私人</span><h3>${escapeHtml(book.title)}</h3><em>${escapeHtml(book.englishTitle||"")}</em><p>${escapeHtml(book.series||"未分组")} · ${escapeHtml(book.level||"-")}级 · ${book.sentenceCount||0}句</p><p>${book.mediaCount||0} 个受鉴权媒体 · 已读 ${Math.round(seconds/60)} 分钟</p><span class="book-progress"><i style="width:${progress}%"></i></span><small class="book-progress-label">${progress?`已完成 ${progress}%`:"尚未开始"}</small></span><i class="catalog-card-action">${progress?"继续阅读":"开始阅读"}</i></button>;}
*/function catalogCard(book,library=false){const status=book.unlocked?"已解锁":book.inLibrary?"已收藏":"官方读物",libraryExtra=library?'<p>'+(book.shelfState==="later"?"稍后阅读":"已收藏")+'</p>':'';return '<button class="catalog-book-card" type="button" data-catalog-book="'+escapeHtml(book.id)+'" data-catalog-origin="'+(library?"my-library":"catalog")+'">'+catalogCover(book)+'<span><span class="catalog-state">'+status+'</span><h3>'+escapeHtml(book.title)+'</h3><em>'+escapeHtml(book.englishTitle||"")+'</em><p>'+escapeHtml(book.series?.title||"未分组")+' · '+escapeHtml(book.level||"-")+'级 · '+(book.estimatedMinutes||0)+'分钟</p>'+libraryExtra+'</span><i class="catalog-card-action">查看详情</i></button>';}
function workspaceVisibleBooks(){const query=workspaceQuery.trim().toLocaleLowerCase();const list=workspaceBooks.filter(book=>{if(!query)return true;return [book.title,book.englishTitle,book.series,book.level].some(value=>String(value||"").toLocaleLowerCase().includes(query));});return list.sort((a,b)=>{if(workspaceSort==="title")return String(a.title||"").localeCompare(String(b.title||""),"zh-CN");if(workspaceSort==="progress")return (b.progress?.readingSeconds||0)-(a.progress?.readingSeconds||0);if(workspaceSort==="added")return String(b.createdAt||b.created_at||"").localeCompare(String(a.createdAt||a.created_at||""));return (b.progress?.lastReadAt||b.progress?.updatedAt||"").localeCompare(a.progress?.lastReadAt||a.progress?.updatedAt||"")||(b.progress?.readingSeconds||0)-(a.progress?.readingSeconds||0);});}
function renderWorkspaceBooks(){const list=workspaceVisibleBooks(),container=$("#workspaceBookList");container.innerHTML=list.length?list.map(workspaceCard).join(""):workspaceBooks.length?'<div class="empty-state"><h3>没有匹配的读物</h3><p>试试标题、英文标题或书系名称。</p><button type="button" data-workspace-reset>清除筛选</button></div>':'<div class="empty-state"><h3>私人学习空间还是空的</h3><p>展开“导入新内容”上传文档、MP3、本地视频或 YouTube。</p><button type="button" data-workspace-import>导入第一本读物</button></div>';renderWorkspaceContinue();}
function renderWorkspaceContinue(){const target=$("#workspaceContinue");if(!target)return;const candidate=workspaceBooks.filter(book=>(book.progress?.readingSeconds||0)>0&&!book.progress?.completedAt).sort((a,b)=>(b.progress?.lastReadAt||"").localeCompare(a.progress?.lastReadAt||""))[0]||workspaceBooks[0];if(!candidate){target.classList.add("hidden");target.innerHTML="";return;}const seconds=candidate.progress?.readingSeconds||0,progress=candidate.duration?Math.min(100,Math.round(seconds/candidate.duration*100)):0,progressLabel=progress?"已完成 "+progress+"%":"还没有开始阅读",action=progress?"继续阅读":"开始阅读";target.classList.remove("hidden");target.innerHTML='<div><small>CONTINUE LEARNING</small><h2>继续学习</h2><p>'+escapeHtml(candidate.title)+' · '+progressLabel+'</p><span class="book-progress"><i style="width:'+progress+'%"></i></span></div><button type="button" data-workspace-continue="'+escapeHtml(candidate.id)+'">'+action+' →</button>';}
async function loadCatalogFilters(){
  try{const [seriesResponse,tagsResponse]=await Promise.all([fetch("/api/catalog/series",{cache:"no-store"}),fetch("/api/catalog/tags",{cache:"no-store"})]);const series=await seriesResponse.json(),tags=await tagsResponse.json();if(seriesResponse.ok){$("#catalogSeries").innerHTML='<option value="">全部书系</option>'+(series.series||[]).map(item=>`<option value="${escapeHtml(item.slug)}">${escapeHtml(item.title)}（${item.bookCount}）</option>`).join("");}$("#catalogSearchForm").dataset.tags=JSON.stringify(tags.tags||[]);catalogFiltersLoaded=true;}catch{} }
async function loadCatalog(){
  if(!saasMode)return;const query=new URLSearchParams();const q=$("#catalogQuery").value.trim(),series=$("#catalogSeries").value,level=$("#catalogLevel").value,type=$("#catalogType").value;if(q)query.set("q",q);if(series)query.set("series",series);if(level)query.set("level",level);if(type)query.set("resourceType",type);$("#catalogBookList").innerHTML='<div class="empty-state">正在读取书城…</div>';
  try{const response=await fetch(`/api/catalog?${query}`,{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法读取书城");catalogBooks=data.books||[];const levels=[...new Set(catalogBooks.map(book=>book.level).filter(Boolean))];const selected=$("#catalogLevel").value;$("#catalogLevel").innerHTML='<option value="">全部难度</option>'+levels.map(value=>`<option value="${escapeHtml(value)}"${value===selected?" selected":""}>${escapeHtml(value)}级</option>`).join("");$("#catalogBookList").innerHTML=catalogBooks.length?catalogBooks.map(book=>catalogCard(book)).join(""):'<div class="empty-state"><h3>还没有公开读物</h3><p>管理员审核并发布公版或已授权内容后会显示在这里。</p></div>';}catch(error){$("#catalogBookList").innerHTML=`<div class="empty-state"><h3>无法读取书城</h3><p>${escapeHtml(error.message)}</p></div>`;}}
async function loadCatalogDetail(bookId){
  selectedCatalogBookId=bookId;$("#catalogDetail").innerHTML='<div class="empty-state">正在读取详情…</div>';const dialog=$("#catalogDetailDialog");if(!dialog.open)dialog.showModal();updateRoute({book:bookId},true);
  try{const response=await fetch(`/api/catalog/books/${encodeURIComponent(bookId)}`,{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法读取读物详情");const book=data.book,tagHtml=(book.tags||[]).map(tag=>`<span>${escapeHtml(tag.title)}</span>`).join(""),preview=(book.preview||[]).map(line=>`<p>${escapeHtml(line.text)}</p>`).join(""),main=book.unlocked?'<button data-catalog-action="read">继续阅读</button>':`<button data-catalog-action="read">解锁并开始阅读</button>`,add=book.inLibrary?'':`<button class="secondary" data-catalog-action="add">收藏到书架</button>`,remove=book.inLibrary?'<button class="secondary warn" data-catalog-action="remove">移出书架</button>':'';$("#catalogDetail").innerHTML=`${catalogCover(book)}<small>${escapeHtml(book.resourceType||"book").toUpperCase()}</small><h2>${escapeHtml(book.title)}</h2><p>${escapeHtml(book.englishTitle||"")}${book.author?` · ${escapeHtml(book.author)}`:""}</p><div class="catalog-meta"><span>${escapeHtml(book.series?.title||"未分组")}</span><span>${escapeHtml(book.level||"-")}级</span><span>${book.estimatedMinutes||0}分钟</span><span>${book.sentenceCount||0}句</span>${tagHtml}</div><p>${escapeHtml(book.description||"暂无简介。")}</p>${preview?`<div class="catalog-preview"><small>有限预览</small>${preview}</div>`:""}<p class="catalog-notice">${escapeHtml(book.readerNotice||"首次开始阅读会消耗一次官方读物解锁额度。")}</p><div class="catalog-actions">${main}${add}${remove}</div>`;}catch(error){$("#catalogDetail").innerHTML=`<div class="empty-state"><h3>无法读取详情</h3><p>${escapeHtml(error.message)}</p></div>`;}}
async function catalogAction(action){
  if(!selectedCatalogBookId)return;try{let response,data;if(action==="remove"){response=await fetch(`/api/library/items/${encodeURIComponent(selectedCatalogBookId)}`,{method:"DELETE"});data=await response.json();}else{const path=action==="add"?"/api/library/items":`/api/catalog/books/${encodeURIComponent(selectedCatalogBookId)}/unlock`;response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(action==="add"?{bookId:selectedCatalogBookId}:{})});data=await response.json();}if(!response.ok)throw new Error(data.error||"操作失败");await Promise.all([loadCatalog(),loadMyLibrary(),refreshMembership()]);if(action==="read"){await openCatalogReader(selectedCatalogBookId);return;}if(action!=="remove")await loadCatalogDetail(selectedCatalogBookId);}catch(error){const detail=error.message||"操作失败";$("#catalogDetail").insertAdjacentHTML("beforeend",`<p class="catalog-notice">${escapeHtml(detail)}</p>`);}}
async function openCatalogReader(bookId){
  try{$("#catalogReaderTitle").textContent="正在打开读物…";$("#catalogReaderContent").innerHTML='<div class="empty-state">正在加载正文…</div>';$("#catalogCompleteBook").classList.add("hidden");showScreen("catalog-reader");const response=await fetch(`/api/catalog/books/${encodeURIComponent(bookId)}/reader`,{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法打开读物");const book=data.book;catalogReaderBookId=bookId;catalogReadingSession={id:`reader-${bookId}-${crypto.randomUUID?.()||Date.now()}`,startedAt:Date.now(),seen:new Set() ,flushed:false};$("#catalogReaderMeta").textContent=`${book.level||"-"}级 · ${String(book.resourceType||"book").toUpperCase()} · ${book.estimatedMinutes||0}分钟`;$("#catalogReaderTitle").textContent=book.title;$("#catalogReaderNotice").textContent=book.mediaNotice||"";$("#catalogCompleteBook").classList.remove("hidden");$("#catalogCompleteBook").disabled=false;$("#catalogCompleteBook").textContent="标记完成并领取成长值";const media=(book.mediaAssets||[]).map(asset=>`<a class="catalog-media-link" href="${escapeHtml(asset.url)}" target="_blank" rel="noopener">打开受保护媒体：${escapeHtml(asset.kind)} · ${membershipValue("storage_bytes",asset.bytes)}</a>`).join("");$("#catalogReaderContent").innerHTML=`${media?`<div class="catalog-reader-media">${media}</div>`:""}`+((book.sentences||[]).length?(book.sentences||[]).map((sentence,index)=>`<section class="catalog-reader-sentence" data-catalog-sentence="${index}"><b>${index+1}.</b> ${escapeHtml(sentence.text)}${sentence.translation?`<small>${escapeHtml(sentence.translation)}</small>`:""}</section>`).join(""):'<div class="empty-state">该读物暂时没有可显示的正文。</div>');}catch(error){$("#catalogReaderContent").innerHTML=`<div class="empty-state"><h3>无法打开读物</h3><p>${escapeHtml(error.message)}</p></div>`;}}
async function loadMyLibrary(){
  if(!saasMode)return;$("#myLibraryList").innerHTML='<div class="empty-state">正在读取书架…</div>';try{const response=await fetch("/api/library",{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法读取书架");const items=data.items||[];$("#myLibraryList").innerHTML=items.length?items.map(book=>catalogCard(book,true)).join(""):'<div class="empty-state"><h3>书架还是空的</h3><p>从书城收藏官方读物后会出现在这里。</p></div>';}catch(error){$("#myLibraryList").innerHTML=`<div class="empty-state"><h3>无法读取书架</h3><p>${escapeHtml(error.message)}</p></div>`;}}
async function loadWorkspace(){if(!saasMode)return;$("#workspaceBookList").innerHTML='<div class="empty-state">正在读取私人学习空间…</div>';try{const [booksResponse,tasksResponse]=await Promise.all([fetch("/api/workspace/books",{cache:"no-store"}),fetch("/api/workspace/imports",{cache:"no-store"})]);const data=await booksResponse.json(),tasks=await tasksResponse.json();if(!booksResponse.ok)throw new Error(data.error||"无法读取私人学习空间");workspaceBooks=data.books||[];workspaceBooksLoaded=true;workspaceTasks=tasks.tasks||[];renderWorkspaceTasks();$("#workspaceBookCount").textContent=`${workspaceBooks.length} 本`;renderWorkspaceBooks();$("#workspaceNotice").textContent=workspaceBooks.length?`已迁移或导入 ${workspaceBooks.length} 本私人读物。阅读活动会按当前账号记录。`:"";}catch(error){$("#workspaceBookList").innerHTML=`<div class="empty-state"><h3>无法读取私人学习空间</h3><p>${escapeHtml(error.message)}</p></div>`;}}
function renderWorkspaceTasks(){const list=$("#workspaceTaskList"),activeTasks=workspaceTasks.filter(task=>["uploading","queued","running","awaiting_processor"].includes(task.status));if(activeTasks.length)$("#workspaceImportTools").open=true;list.innerHTML=workspaceTasks.length?workspaceTasks.map(task=>`<article class="workspace-task-row"><span><b>${escapeHtml(task.title||task.originalFilename||"未命名导入")}</b><small>${escapeHtml(task.kind)} · ${task.progress}% · ${escapeHtml(task.step||task.status)}${task.error?` · ${escapeHtml(task.error)}`:""}</small></span><span><em>${escapeHtml(task.status)}</em>${["uploading","queued","running","awaiting_processor"].includes(task.status)?` <button data-workspace-task-cancel="${escapeHtml(task.id)}" type="button">取消</button>`:""}</span></article>`).join(""):'<p class="empty-state">暂无导入任务。</p>';}
async function startWorkspaceTextImport(event){event.preventDefault();const file=$("#workspaceTextImportFile").files?.[0];if(!file)return;const form=event.currentTarget,button=form.querySelector("button[type=submit]"),kind=/\.pdf$/i.test(file.name)?"document":/\.mp3$/i.test(file.name)?"mp3":/\.(mp4|mov|m4v|mkv|webm)$/i.test(file.name)?"video":"text";button.disabled=true;$("#workspaceTaskNotice").textContent=kind==="video"?"正在上传视频，随后提取音频、封面并进行 Whisper 转写…":kind==="mp3"?"正在上传 MP3，随后进行 Whisper 转写…":"正在创建并上传导入任务…";try{const key=`${kind}-import-${crypto.randomUUID?.()||Date.now()}`,create=await fetch("/api/workspace/imports",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind,title:$("#workspaceTextImportTitle").value.trim(),filename:file.name,idempotencyKey:key})}),created=await create.json();if(!create.ok)throw new Error(created.error||"无法创建导入任务");const taskId=created.task.id,bytes=await file.arrayBuffer(),upload=await fetch(`/api/workspace/imports/${encodeURIComponent(taskId)}/upload`,{method:"POST",headers:{"Content-Type":file.type||"application/octet-stream","X-Upload-Filename":file.name},body:bytes});const uploaded=await upload.json();if(!upload.ok)throw new Error(uploaded.error||"上传失败");const complete=await fetch(`/api/workspace/imports/${encodeURIComponent(taskId)}/complete`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}),finished=await complete.json();if(!complete.ok)throw new Error(finished.error||"导入处理失败");$("#workspaceTaskNotice").textContent=finished.task.status==="complete"?(kind==="video"?"视频、音频、封面和 Whisper 正文已导入。":kind==="mp3"?"MP3 Whisper 转写完成。":"文档已导入私人学习空间。"):finished.task.step;form.reset();await loadWorkspace();}catch(error){$("#workspaceTaskNotice").textContent=error.message||"导入失败";}finally{button.disabled=false;}}
async function startWorkspaceYoutubeImport(event){event.preventDefault();const form=event.currentTarget,button=form.querySelector("button[type=submit]"),sourceUrl=$("#workspaceYoutubeImportUrl").value.trim();if(!sourceUrl)return;button.disabled=true;$("#workspaceTaskNotice").textContent="正在读取 YouTube 信息并下载视频、字幕…";try{const key=`youtube-import-${crypto.randomUUID?.()||Date.now()}`,create=await fetch("/api/workspace/imports",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"youtube",title:$("#workspaceYoutubeImportTitle").value.trim(),filename:"",sourceUrl,idempotencyKey:key})}),created=await create.json();if(!create.ok)throw new Error(created.error||"无法创建 YouTube 导入任务");const complete=await fetch(`/api/workspace/imports/${encodeURIComponent(created.task.id)}/complete`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}),finished=await complete.json();if(!complete.ok)throw new Error(finished.error||"YouTube 导入处理失败");$("#workspaceTaskNotice").textContent=finished.task.status==="complete"?"YouTube 视频、字幕、受保护媒体和 Whisper 正文已导入。":finished.task.step;form.reset();await loadWorkspace();}catch(error){$("#workspaceTaskNotice").textContent=error.message||"YouTube 导入失败";}finally{button.disabled=false;}}
async function cancelWorkspaceImport(taskId){try{const response=await fetch(`/api/workspace/imports/${encodeURIComponent(taskId)}/cancel`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}),data=await response.json();if(!response.ok)throw new Error(data.error||"取消失败");await loadWorkspace();}catch(error){$("#workspaceTaskNotice").textContent=error.message||"取消失败";}}
function workspaceSentenceHtml(sentence,index){let html="",last=0,wordIndex=0,match,regex=/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g;while((match=regex.exec(sentence.text))){html+=escapeHtml(sentence.text.slice(last,match.index));const saved=vocabItems.some(item=>item.book_id===workspaceReaderBook?.id&&item.sentence_id===String(sentence.id)&&item.word_index===wordIndex);html+=`<button type="button" class="workspace-reader-word${saved?" saved":""}" data-workspace-word="${wordIndex}">${escapeHtml(match[0])}</button>`;last=regex.lastIndex;wordIndex++;}html+=escapeHtml(sentence.text.slice(last));return `<section class="catalog-reader-sentence" data-workspace-sentence="${escapeHtml(sentence.id)}"><b>${index+1}.</b> ${html}<button type="button" class="secondary workspace-grammar-button" data-workspace-grammar>句法分析</button>${sentence.translation?`<small>${escapeHtml(sentence.translation)}</small>`:""}</section>`;}
function renderWorkspaceWordPanel(){const panel=$("#workspaceWordPanel"),context=workspaceWordContext;if(!context){panel.innerHTML='<div class="word-empty"><span>Aa</span><h3>点击正文单词</h3><p>可保存私人释义、语境和备注；数据只写入当前账号的 PostgreSQL 工作区。</p></div>';return;}const existing=vocabItems.find(item=>item.book_id===workspaceReaderBook.id&&item.sentence_id===String(context.sentence.id)&&item.word_index===context.wordIndex),annotation=wordAnnotations.find(item=>item.book_id===workspaceReaderBook.id&&item.sentence_id===String(context.sentence.id)&&item.word_index===context.wordIndex);panel.innerHTML=`<form id="workspaceWordForm" class="workspace-word-form"><small>PRIVATE WORD</small><h2>${escapeHtml(context.word)}</h2><p>${escapeHtml(context.sentence.text)}</p><label>私人释义<input id="workspaceWordMeaning" value="${escapeHtml(existing?.meaning||"")}" placeholder="例如：生存；幸存"></label><label>备注<textarea id="workspaceWordNote" rows="4" placeholder="记录语境、易错点或记忆方法">${escapeHtml(annotation?.note||existing?.note||"")}</textarea></label><div class="workspace-word-actions"><button type="submit">${existing?"更新生词":"加入生词本"}</button><button id="workspaceSaveAnnotation" type="button">保存备注</button><button id="workspaceAIContext" type="button">AI 语境精讲</button><button id="workspaceSpeakWord" type="button">播放发音</button></div><div id="workspaceAIResult" class="usage-note hidden"></div><p id="workspaceWordStatus" class="membership-notice">${existing?"该词已在当前账号的生词本中。":"AI 首次生成会消耗一次语境精讲额度，重复查看缓存不扣额度。"}</p></form>`;$("#workspaceWordForm").onsubmit=saveWorkspaceVocabulary;$("#workspaceSaveAnnotation").onclick=saveWorkspaceAnnotation;$("#workspaceAIContext").onclick=loadWorkspaceWordContext;$("#workspaceSpeakWord").onclick=()=>playWordTts(context.word);}
async function openWorkspaceReader(bookId){try{$("#workspaceReaderTitle").textContent="正在打开私人读物…";$("#workspaceReaderContent").innerHTML='<div class="empty-state">正在加载正文…</div>';workspaceWordContext=null;renderWorkspaceWordPanel();showScreen("workspace-reader");const [readerResponse,vocabularyResponse,annotationResponse]=await Promise.all([fetch(`/api/workspace/books/${encodeURIComponent(bookId)}/reader`,{cache:"no-store"}),fetch(`/api/workspace/vocabulary?bookId=${encodeURIComponent(bookId)}`,{cache:"no-store"}),fetch(`/api/workspace/annotations?bookId=${encodeURIComponent(bookId)}`,{cache:"no-store"})]),data=await readerResponse.json(),vocabulary=await vocabularyResponse.json(),annotations=await annotationResponse.json();if(!readerResponse.ok)throw new Error(data.error||"无法打开私人读物");workspaceReaderBook=data.book;const bookVocabulary=(vocabulary.items||[]).map(normalizeWorkspaceVocabulary);vocabItems=[...vocabItems.filter(item=>item.book_id!==bookId),...bookVocabulary];wordAnnotations=(annotations.items||[]).map(item=>({...item.payload,book_id:item.bookId,sentence_id:item.sentenceId,word_index:+item.wordIndex}));rebuildWordIndexes();workspaceReaderSession={id:`workspace-${bookId}-${crypto.randomUUID?.()||Date.now()}`,bookId,startedAt:Date.now(),seen:new Set(),flushed:false};$("#workspaceReaderMeta").textContent=`${workspaceReaderBook.level||"-"}级 · ${String(workspaceReaderBook.resourceType||"book").toUpperCase()} · 已读 ${Math.round((workspaceReaderBook.progress?.readingSeconds||0)/60)} 分钟`;$("#workspaceReaderTitle").textContent=workspaceReaderBook.title;$("#workspaceReaderNotice").textContent="媒体通过受鉴权接口打开；点击句子记录阅读，点击单词可保存私人释义和备注。";const media=(workspaceReaderBook.mediaAssets||[]).map(asset=>{const variants=asset.variants||[],audio=variants.find(item=>item.name==="audio"),cover=variants.find(item=>item.name==="cover"),captions=variants.filter(item=>item.name.startsWith("subtitles-")),source=String(asset.contentType||"").startsWith("video/")?`<video class="workspace-private-video" controls playsinline preload="metadata" poster="${escapeHtml(cover?.url||"")}" src="${escapeHtml(asset.url)}"></video>`:`<a class="catalog-media-link" href="${escapeHtml(asset.url)}" target="_blank" rel="noopener">打开私人媒体：${escapeHtml(asset.kind)} · ${membershipValue("storage_bytes",asset.bytes)}</a>`;return `${source}${audio?`<audio class="workspace-private-audio" controls preload="metadata" src="${escapeHtml(audio.url)}"></audio>`:""}${cover?`<a class="catalog-media-link" href="${escapeHtml(cover.url)}" target="_blank" rel="noopener">打开受保护封面</a>`:""}${captions.map(item=>`<a class="catalog-media-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener">打开受保护字幕：${escapeHtml(item.name)}</a>`).join("")}`;}).join("");$("#workspaceReaderContent").innerHTML=`${media?`<div class="catalog-reader-media">${media}</div>`:""}`+((workspaceReaderBook.sentences||[]).length?workspaceReaderBook.sentences.map(workspaceSentenceHtml).join(""):'<div class="empty-state">该读物没有可显示的正文。</div>');}catch(error){$("#workspaceReaderContent").innerHTML=`<div class="empty-state"><h3>无法打开私人读物</h3><p>${escapeHtml(error.message)}</p></div>`;}}
function markWorkspaceSentence(event){const sentenceElement=event.target.closest("[data-workspace-sentence]");if(!sentenceElement||!workspaceReaderSession)return;workspaceReaderSession.seen.add(sentenceElement.dataset.workspaceSentence);sentenceElement.classList.add("seen");const sentence=workspaceReaderBook?.sentences.find(item=>String(item.id)===sentenceElement.dataset.workspaceSentence);if(!sentence)return;if(event.target.closest("[data-workspace-grammar]")){loadWorkspaceGrammar(sentence);return;}const word=event.target.closest("[data-workspace-word]");if(!word||!workspaceReaderBook)return;workspaceWordContext={sentence,wordIndex:+word.dataset.workspaceWord,word:word.textContent,element:word};renderWorkspaceWordPanel();fetch("/api/workspace/activity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:workspaceReaderBook.id,readingSeconds:0,sentences:0,lookups:1,lastSentenceId:sentence.id,idempotencyKey:`lookup-${workspaceReaderBook.id}-${sentence.id}-${word.dataset.workspaceWord}-${crypto.randomUUID?.()||Date.now()}`})}).then(()=>{learningDaysLoaded=false;}).catch(()=>null);}
async function saveWorkspaceVocabulary(event){event.preventDefault();const context=workspaceWordContext;if(!context||!workspaceReaderBook)return;const existing=vocabItems.find(item=>item.book_id===workspaceReaderBook.id&&item.sentence_id===String(context.sentence.id)&&item.word_index===context.wordIndex),payload=workspaceVocabularyPayload(existing||{},{word:context.word,root:context.word.toLowerCase(),phonetic:existing?.phonetic||"",meaning:$("#workspaceWordMeaning").value.trim(),context:focusedWordContext(context.sentence.text,context.wordIndex),note:$("#workspaceWordNote").value.trim(),rating:existing?.rating||"unknown",interval_days:existing?.interval_days||1,due_at:existing?.due_at||new Date(Date.now()+86400000).toISOString(),reviews:existing?.reviews||0});const response=await fetch("/api/workspace/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:workspaceReaderBook.id,sentenceId:context.sentence.id,wordIndex:context.wordIndex,payload})}),saved=await response.json();if(!response.ok){$("#workspaceWordStatus").textContent=saved.error||"保存失败";return;}const normalized=normalizeWorkspaceVocabulary(saved),index=vocabItems.findIndex(item=>item.id===normalized.id);if(index>=0)vocabItems[index]=normalized;else vocabItems.push(normalized);vocabLoaded=false;context.element.classList.add("saved");rebuildWordIndexes();renderWorkspaceWordPanel();}
async function saveWorkspaceAnnotation(){const context=workspaceWordContext;if(!context||!workspaceReaderBook)return;const payload={original_word:context.word,corrected_word:"",note:$("#workspaceWordNote").value.trim()},response=await fetch("/api/workspace/annotations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:workspaceReaderBook.id,sentenceId:context.sentence.id,wordIndex:context.wordIndex,payload})}),saved=await response.json();if(!response.ok){$("#workspaceWordStatus").textContent=saved.error||"备注保存失败";return;}const record={...payload,book_id:workspaceReaderBook.id,sentence_id:String(context.sentence.id),word_index:context.wordIndex},index=wordAnnotations.findIndex(item=>item.book_id===record.book_id&&item.sentence_id===record.sentence_id&&item.word_index===record.word_index);if(index>=0)wordAnnotations[index]=record;else wordAnnotations.push(record);rebuildWordIndexes();renderWorkspaceWordPanel();}
async function loadWorkspaceWordContext(){const context=workspaceWordContext;if(!context||!workspaceReaderBook)return;const button=$("#workspaceAIContext"),result=$("#workspaceAIResult");button.disabled=true;result.classList.remove("hidden");result.textContent="正在生成语境精讲…";try{const response=await fetch("/api/word-context",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:workspaceReaderBook.id,sentenceId:context.sentence.id,wordIndex:context.wordIndex})}),data=await response.json();if(!response.ok)throw new Error(data.error||"生成失败");result.innerHTML=`<small>${data.cached?"已命中缓存":"本次已生成"} · ${escapeHtml(data.source||"平台 AI")}</small><p>${formatText(data.explanation)}</p>`;if(data.charged)refreshMembership();}catch(error){result.textContent=error.message||"语境精讲失败";}finally{button.disabled=false;}}
async function loadWorkspaceGrammar(sentence){const panel=$("#workspaceWordPanel");workspaceWordContext=null;panel.innerHTML=`<div class="workspace-word-form"><small>SMART GRAMMAR</small><h2>句法分析</h2><p>${escapeHtml(sentence.text)}</p><div id="workspaceGrammarResult" class="usage-note">正在生成句法讲解…</div></div>`;try{const response=await fetch("/api/sentence-grammar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:workspaceReaderBook.id,sentenceId:sentence.id})}),data=await response.json();if(!response.ok)throw new Error(data.error||"句法分析失败");$("#workspaceGrammarResult").innerHTML=`<small>${data.cached?"已命中缓存":"本次已生成"} · ${escapeHtml(data.source||"平台 AI")}</small><p>${formatText(data.aiExplanation)}</p>`;if(data.charged)refreshMembership();}catch(error){$("#workspaceGrammarResult").textContent=error.message||"句法分析失败";}}
async function flushWorkspaceActivity(){const session=workspaceReaderSession;if(!session||session.flushed)return;session.flushed=true;const seconds=Math.max(0,Math.round((Date.now()-session.startedAt)/1000)),sentences=session.seen.size;if(!seconds&&!sentences)return;try{await fetch("/api/workspace/activity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:session.bookId,readingSeconds:seconds,sentences,sessions:1,lastSentenceId:[...session.seen].at(-1)||"",idempotencyKey:session.id})});learningDaysLoaded=false;}catch{}}
function saasPlayableMedia(assets=[]){let audio="",video="",cover="";for(const asset of assets){const variants=asset.variants||[];if(!audio&&String(asset.contentType||"").startsWith("audio/"))audio=asset.url;if(!video&&String(asset.contentType||"").startsWith("video/"))video=asset.url;for(const variant of variants){if(!audio&&String(variant.contentType||"").startsWith("audio/"))audio=variant.url;if(!video&&String(variant.contentType||"").startsWith("video/"))video=variant.url;if(!cover&&String(variant.contentType||"").startsWith("image/"))cover=variant.url;}}return{audio,video,cover};}
function normalizeSaasReaderBook(source,kind){const media=saasPlayableMedia(source.mediaAssets||[]),raw=source.sentences||[];let cursor=0;const sentences=raw.map((item,index)=>{const start=Number.isFinite(+item.start)?+item.start:cursor,end=Number.isFinite(+item.end)&&+item.end>start?+item.end:start+Math.max(2.4,Math.min(8,String(item.text||"").split(/\s+/).length*.48));cursor=end+.04;const matches=[...String(item.text||"").matchAll(/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g)],words=(item.words||[]).length?item.words:matches.map((match,wordIndex)=>({text:match[0],start:start+(end-start)*wordIndex/Math.max(1,matches.length),end:start+(end-start)*(wordIndex+1)/Math.max(1,matches.length),aligned:false}));return{...item,id:String(item.id??index),start,end,page:item.page||1,section:item.section??index+1,words,_wordsLoaded:true};});const duration=Math.max(+source.duration||0,cursor,sentences.at(-1)?.end||0);return{id:source.id,title:source.title,englishTitle:source.englishTitle||source.title,level:source.level||"",sourceType:source.resourceType||kind,duration,alignment:"saas-protected-media",sentences,audio:media.audio||media.video||"",video:media.video||"",cover:media.cover||"",pageBase:"",hasOriginalPages:false,chunkSize:sentences.length||1,chunkCount:1,sentenceCount:sentences.length};}
async function openSaasFullReader(source,kind,returnScreen){saasReaderContext={kind,returnScreen,id:source.id,startedAt:Date.now(),completed:false};currentBookId=source.id;book=normalizeSaasReaderBook(source,kind);bookChunkPromises=new Map();selectedWordContext=null;selectedGrammarSentence=null;expandedSentenceTranslations=new Set();active=-1;displayedPage=null;if(kind==="official")wordAnnotations=[];rebuildWordIndexes();const audio=$("#audio");audio.pause();audio.src=book.audio||"";audio.load();$("#duration").textContent=fmt(book.duration);$(".book-heading small").textContent=`${book.level||"-"}级 · ${kind==="official"?"OFFICIAL":"PRIVATE"} READING`;$(".book-heading strong").innerHTML=`${escapeHtml(book.title)} <i>${escapeHtml(book.englishTitle||"")}</i>`;$(".chapter h1").textContent=book.englishTitle||book.title;$("#wordPanel").innerHTML='<div class="word-empty"><span>Aa</span><h3>单词与句子分析</h3><p>点击正文单词查看释义、保存生词和备注。</p></div>';$("#backBtn").textContent=kind==="workspace"?"← 学习空间":returnScreen==="my-library"?"← 我的书架":"← 书城";visualMode="frames";configureBookVisual();renderStory();restoreProgress();showScreen("reader");$("#backBtn").style.visibility="visible";$("#playBtn").disabled=!book.audio;if(!book.audio)showReaderToast("该读物暂无可播放音频，可正常阅读正文");updateRoute({screen:"reader",reader:kind,id:source.id},true);}
async function openCatalogReader(bookId){try{const response=await fetch(`/api/catalog/books/${encodeURIComponent(bookId)}/reader`,{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法打开读物");$("#catalogDetailDialog").close();catalogReaderBookId=bookId;catalogReadingSession={id:`reader-${bookId}-${crypto.randomUUID?.()||Date.now()}`,startedAt:Date.now(),seen:new Set(),flushed:false};await openSaasFullReader(data.book,"official",new URLSearchParams(location.search).get("screen")==="my-library"?"my-library":"catalog");}catch(error){$("#catalogDetail").insertAdjacentHTML("beforeend",`<p class="catalog-notice">${escapeHtml(error.message||"无法打开读物")}</p>`);}}
async function openWorkspaceReader(bookId){try{const [readerResponse,vocabularyResponse,annotationResponse]=await Promise.all([fetch(`/api/workspace/books/${encodeURIComponent(bookId)}/reader`,{cache:"no-store"}),fetch(`/api/workspace/vocabulary?bookId=${encodeURIComponent(bookId)}`,{cache:"no-store"}),fetch(`/api/workspace/annotations?bookId=${encodeURIComponent(bookId)}`,{cache:"no-store"})]),data=await readerResponse.json(),vocabulary=await vocabularyResponse.json(),annotations=await annotationResponse.json();if(!readerResponse.ok)throw new Error(data.error||"无法打开学习空间读物");workspaceReaderBook=data.book;vocabItems=[...vocabItems.filter(item=>item.book_id!==bookId),...(vocabulary.items||[]).map(normalizeWorkspaceVocabulary)];wordAnnotations=(annotations.items||[]).map(item=>({...item.payload,book_id:item.bookId,sentence_id:item.sentenceId,word_index:+item.wordIndex}));rebuildWordIndexes();workspaceReaderSession={id:`workspace-${bookId}-${crypto.randomUUID?.()||Date.now()}`,bookId,startedAt:Date.now(),seen:new Set(),flushed:false};await openSaasFullReader(data.book,"workspace","workspace");}catch(error){$("#workspaceNotice").textContent=error.message||"无法打开学习空间读物";}}
async function maybeCompleteOfficialReading(){const context=saasReaderContext;if(!context||context.kind!=="official"||context.completed||Date.now()-context.startedAt<60000)return;const nearBottom=window.scrollY+window.innerHeight>=document.documentElement.scrollHeight-100;if(!nearBottom&&active<book.sentences.length-1)return;context.completed=true;try{const seconds=Math.max(60,Math.round((Date.now()-context.startedAt)/1000)),sentences=Math.max(1,catalogReadingSession?.seen.size||0),key=`${catalogReadingSession?.id||context.id}:auto-complete`;await fetch("/api/rewards/activity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({readingSeconds:seconds,sentences,reviews:0,idempotencyKey:key})});const response=await fetch("/api/rewards/complete-book",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:context.id})}),data=await response.json();if(!response.ok)throw new Error(data.error||"完成记录失败");showReaderToast(data.pointsGranted?`阅读完成，自动获得 ${data.pointsGranted} 成长值`:"阅读完成，今日奖励已记录");}catch{context.completed=false;}}
function rewardEventLabel(type){return {checkin:"每日签到",streak:"连续签到奖励",valid_reading:"有效阅读",review:"完成生词复习",official_book_completed:"完成官方读物",redemption:"兑换奖励",member_invite_effective:"邀请有效学习",member_invite_paid:"邀请首次付费",seed:"活动奖励"}[type]||type;}
async function loadRewards(){
  if(!saasMode)return;$("#rewardNotice").textContent="正在读取成长奖励…";
  try{const [statusResponse,catalogResponse,ledgerResponse]=await Promise.all([fetch("/api/rewards/status",{cache:"no-store"}),fetch("/api/rewards/catalog",{cache:"no-store"}),fetch("/api/rewards/ledger",{cache:"no-store"})]);const status=await statusResponse.json(),catalog=await catalogResponse.json(),ledger=await ledgerResponse.json();if(!statusResponse.ok)throw new Error(status.error||"无法读取成长状态");if(!catalogResponse.ok)throw new Error(catalog.error||"无法读取奖励目录");if(!ledgerResponse.ok)throw new Error(ledger.error||"无法读取成长记录");renderRewards(status,catalog.rewards||[],ledger.items||[]);$("#rewardNotice").textContent="有效阅读需当天累计阅读 10 分钟并点读至少 5 句；同一天只发放一次。";}catch(error){$("#rewardNotice").textContent=error.message||"无法读取成长奖励";}}
function renderRewards(status,catalog,ledger){
  rewardStatusData=status;const invites=status.invites||[],allowance=Number(status.inviteAllowance||0);$("#rewardStatus").innerHTML=`<article><small>当前成长值</small><b>${status.balance||0}</b><small>本月已获得 ${status.monthEarned||0} / ${status.monthCap||100}</small><button id="rewardCheckin" type="button"${status.checkedIn?" disabled":""}>${status.checkedIn?"今日已签到":"每日签到 +1"}</button></article><article><small>连续签到</small><b>${status.streak||0} 天</b><small>${status.checkinKind==="makeup"?"今日为补签":"持续学习会获得里程碑奖励"}</small></article><article><small>补签卡</small><b>${status.makeupCards||0}</b><small>可为过去日期补签一次</small></article><article><small>我的时区</small><b>${escapeHtml(status.timezone||"-")}</b><small>签到与连续天数按此时区计算</small></article><article class="reward-invites"><small>会员邀请</small><b>${invites.length?"已发放邀请码":"暂无邀请码"}</b><small>${invites.length?invites.map(item=>`<code>${escapeHtml(item.code)} · ${escapeHtml(item.status)}</code>`).join(""):"进阶版和 Pro 版的邀请码由后台或活动发放。"}<br>可用邀请码额度：${allowance}</small><button id="rewardInvite" type="button"${allowance<1?" disabled":""}>生成邀请码</button></article>`;
  $("#rewardCatalogList").innerHTML=catalog.map(item=>`<article class="reward-item"><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.description)}</p><small>${item.costPoints} 成长值${item.quantity>1?` · ${item.quantity} 次`:""}</small><button data-reward-code="${escapeHtml(item.code)}" type="button">兑换</button></article>`).join("");
  $("#rewardLedgerList").innerHTML=ledger.length?ledger.map(item=>`<article class="reward-ledger-row"><span>${escapeHtml(rewardEventLabel(item.eventType))}<small>${item.day||""} · ${new Date(item.createdAt).toLocaleString()}</small></span><b class="${item.points>=0?"positive":"negative"}">${item.points>=0?"+":""}${item.points}</b></article>`).join(""):'<p class="empty-state">还没有成长记录。</p>';
}
async function checkinReward(){try{const response=await fetch("/api/checkins",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}),data=await response.json();if(!response.ok)throw new Error(data.error||"签到失败");await loadRewards();}catch(error){$("#rewardNotice").textContent=error.message||"签到失败";}}
async function redeemReward(code){try{const key=`reward-${code}-${crypto.randomUUID?.()||Date.now()}`,response=await fetch("/api/rewards/redeem",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({code,idempotencyKey:key})}),data=await response.json();if(!response.ok)throw new Error(data.error||"兑换失败");await Promise.all([loadRewards(),refreshMembership()]);}catch(error){$("#rewardNotice").textContent=error.message||"兑换失败";}}
async function issueMemberInvite(){try{const response=await fetch("/api/member-invites",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法生成邀请码");await loadRewards();}catch(error){$("#rewardNotice").textContent=error.message||"无法生成邀请码";}}
function markCatalogSentence(event){const sentence=event.target.closest("[data-catalog-sentence]");if(!sentence||!catalogReadingSession)return;catalogReadingSession.seen.add(sentence.dataset.catalogSentence);sentence.classList.add("seen");}
async function flushCatalogReadingActivity(){const session=catalogReadingSession;if(!session||session.flushed)return;session.flushed=true;const seconds=Math.max(0,Math.round((Date.now()-session.startedAt)/1000)),sentences=session.seen.size;if(!seconds&&!sentences)return;try{await fetch("/api/rewards/activity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({readingSeconds:seconds,sentences,reviews:0,idempotencyKey:session.id})});}catch{}}
async function completeCatalogBook(){if(!catalogReaderBookId)return;try{const response=await fetch("/api/rewards/complete-book",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:catalogReaderBookId})}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法记录完成状态");$("#catalogCompleteBook").textContent=data.pointsGranted?`已领取 +${data.pointsGranted} 成长值`:"已记录完成";$("#catalogCompleteBook").disabled=true;await loadRewards();}catch(error){$("#catalogReaderNotice").textContent=error.message||"无法记录完成状态";}}
async function adminRequest(path,payload){const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}),data=await response.json();if(!response.ok)throw new Error(data.error||"管理员操作失败");return data;}
async function loadAdmin(){
  if(!saasMode||!saasUser?.isAdmin)return;$("#adminNotice").textContent="正在读取运营数据…";
  try{const offset=(adminMediaPage-1)*ADMIN_MEDIA_PAGE_SIZE,[dashboardResponse,usersResponse,invitationsResponse,auditResponse,sourcesResponse,platformResponse,mediaResponse]=await Promise.all([fetch("/api/admin/dashboard",{cache:"no-store"}),fetch(`/api/admin/users?q=${encodeURIComponent($("#adminUserSearch").value.trim())}`,{cache:"no-store"}),fetch("/api/admin/invitations",{cache:"no-store"}),fetch("/api/admin/audit",{cache:"no-store"}),fetch("/api/admin/catalog/sources",{cache:"no-store"}),fetch("/api/admin/platform-config",{cache:"no-store"}),fetch(`/api/admin/media-assets?limit=${ADMIN_MEDIA_PAGE_SIZE}&offset=${offset}`,{cache:"no-store"})]);const dashboard=await dashboardResponse.json(),users=await usersResponse.json(),invitations=await invitationsResponse.json(),audit=await auditResponse.json(),sources=await sourcesResponse.json(),platform=await platformResponse.json(),media=await mediaResponse.json();if(!dashboardResponse.ok)throw new Error(dashboard.error||"无法读取运营数据");adminData={dashboard,users,invitations,audit,sources,platform,media};renderAdmin();enhanceAdminMediaRows();$("#adminNotice").textContent=`当前有效邀请码 ${dashboard.activeInvitations||0} 个 · 平台 AI：${platform.dioco?.configured?"已配置":"未配置"}。`; }catch(error){$("#adminNotice").textContent=error.message||"无法读取运营数据";}}
function renderAdmin(){const data=adminData||{},dashboard=data.dashboard||{},users=data.users?.users||[],sources=data.sources?.sources||[],audit=data.audit?.items||[],media=data.media?.assets||[],mediaTotal=data.media?.total||0,pages=Math.max(1,Math.ceil(mediaTotal/ADMIN_MEDIA_PAGE_SIZE));adminMediaPage=Math.min(adminMediaPage,pages);$("#adminDashboard").innerHTML=`<article><small>用户总数</small><b>${dashboard.users?.total||0}</b><small>已验证 ${dashboard.users?.verified||0}</small></article><article><small>有效订阅</small><b>${dashboard.activeSubscriptions||0}</b><small>封禁 ${dashboard.users?.suspended||0}</small></article><article><small>官方书城</small><b>${dashboard.catalog?.published||0}</b><small>共审核 ${dashboard.catalog?.total||0}</small></article><article><small>邀请码</small><b>${dashboard.activeInvitations||0}</b><small>当前可用</small></article><article><small>邀请关系</small><b>${dashboard.referrals||0}</b><small>${escapeHtml(dashboard.imports?.notice||"")}</small></article>`;$("#adminUserList").innerHTML=users.length?users.map(user=>`<article class="admin-user-row"><span><b>${escapeHtml(user.email)}</b><small>${escapeHtml(user.id)} · ${escapeHtml(user.planVersion)} · ${user.devices} 台设备 · ${user.emailVerified?"已验证":"未验证"}</small></span><span><button data-admin-user-select="${escapeHtml(user.id)}" type="button">使用此用户</button><button class="${user.status==="active"?"danger":""}" data-admin-user-status="${escapeHtml(user.id)}" data-admin-next-status="${user.status==="active"?"suspended":"active"}" type="button">${user.status==="active"?"封禁":"恢复"}</button></span></article>`).join(""):'<p class="empty-state">没有匹配用户。</p>';$("#adminCatalogSources").innerHTML=sources.length?sources.slice(0,30).map(source=>`<article class="admin-source-row"><span><b>${escapeHtml(source.title)}</b><small>${escapeHtml(source.englishTitle||"")} · ${escapeHtml(source.series||"")} · ${escapeHtml(source.rightsStatus)} / ${escapeHtml(source.publicationStatus)}</small><code>${escapeHtml(source.sourceBookId)}</code></span><button data-admin-source="${escapeHtml(source.sourceBookId)}" type="button">选择审核</button></article>`).join(""):'<p class="empty-state">没有待审核源内容。</p>';$("#adminAuditList").innerHTML=audit.length?audit.map(item=>`<article class="admin-audit-row"><span><b>${escapeHtml(item.action)}</b><small>${escapeHtml(item.actor||"系统")} → ${escapeHtml(item.target||"-")} · ${new Date(item.createdAt).toLocaleString()}</small></span><em>${escapeHtml(item.reason||"")}</em></article>`).join(""):'<p class="empty-state">暂无管理操作记录。</p>';$("#adminMediaList").innerHTML=media.length?media.map(item=>`<article class="admin-media-row"><span><b>${escapeHtml(item.kind)}</b><small>${escapeHtml(item.contentType)} · ${membershipValue("storage_bytes",(item.originalBytes||0)+(item.generatedBytes||0))}</small><code>${escapeHtml(item.storagePath)}</code></span><em>${escapeHtml(item.scope)} · ${escapeHtml(item.status)}</em></article>`).join(""):'<p class="empty-state">暂无登记媒体。</p>';$("#adminMediaPage").textContent=`第 ${adminMediaPage} / ${pages} 页 · 共 ${mediaTotal} 项`;$("#adminMediaPrev").disabled=adminMediaPage<=1;$("#adminMediaNext").disabled=adminMediaPage>=pages;setAdminTab(adminTab);}
function setAdminTab(tab,route=true){const allowed=new Set(["overview","membership","catalog","media","audit"]);adminTab=allowed.has(tab)?tab:"overview";$$('#adminTabs [data-admin-tab]').forEach(button=>{const active=button.dataset.adminTab===adminTab;button.classList.toggle('active',active);button.classList.toggle('btn-primary',active);button.classList.toggle('btn-outline-secondary',!active);button.setAttribute('aria-selected',String(active));});$$('[data-admin-pane]').forEach(pane=>pane.classList.toggle('hidden',pane.dataset.adminPane!==adminTab));if(route&&!$("#admin").classList.contains("hidden"))updateRoute({tab:adminTab});}
function enhanceAdminMediaRows(){
  $$("#adminMediaList .admin-media-row").forEach(row=>{
    const source=row.querySelector("span"),kind=source?.querySelector("b")?.textContent||"-",small=source?.querySelector("small")?.textContent||"",path=source?.querySelector("code")?.textContent||"",status=row.querySelector("em")?.textContent||"-";
    const parts=small.split(" · "),size=parts.pop()||"-",contentType=parts.join(" · ")||"-";
    row.innerHTML=`<span><b>${escapeHtml(kind)}</b></span><span>${escapeHtml(contentType)}</span><span>${escapeHtml(size)}</span><span>${escapeHtml(status)}</span><code>${escapeHtml(path)}</code>`;
  });
}
function dateTimeLocal(offsetDays=0){const value=new Date(Date.now()+offsetDays*86400000),pad=number=>String(number).padStart(2,"0");return `${value.getFullYear()}-${pad(value.getMonth()+1)}-${pad(value.getDate())}T${pad(value.getHours())}:${pad(value.getMinutes())}`;}
async function submitAdminForm(event,kind){event.preventDefault();const form=event.currentTarget,button=form.querySelector("button[type=submit]"),notice=$("#adminActionNotice"),original=button.textContent;button.disabled=true;button.textContent="处理中…";notice.textContent="正在提交操作…";notice.className="admin-action-notice working";try{if(kind==="invitation")await adminRequest("/api/admin/invitations",{code:$("#adminInvitationCode").value,maxUses:+$("#adminInvitationUses").value,channel:$("#adminInvitationChannel").value,note:$("#adminInvitationNote").value});if(kind==="quota")await adminRequest("/api/admin/quotas/adjust",{userId:$("#adminQuotaUserId").value,feature:$("#adminQuotaFeature").value,quantity:+$("#adminQuotaQuantity").value,reason:$("#adminQuotaReason").value,idempotencyKey:`ui-admin-${crypto.randomUUID?.()||Date.now()}`});if(kind==="order")await adminRequest("/api/admin/manual-orders",{userId:$("#adminOrderUserId").value,planVersion:$("#adminOrderPlan").value,startsAt:new Date($("#adminOrderStart").value).toISOString(),endsAt:new Date($("#adminOrderEnd").value).toISOString(),amountCents:+$("#adminOrderAmount").value,note:$("#adminOrderNote").value});if(kind==="allowance")await adminRequest("/api/admin/member-invite-allowances",{userId:$("#adminAllowanceUserId").value,quantity:+$("#adminAllowanceQuantity").value,reason:$("#adminAllowanceReason").value});if(kind==="catalog")await adminRequest("/api/admin/catalog/books",{sourceBookId:$("#adminCatalogSourceId").value,rightsStatus:$("#adminCatalogRights").value,publicationStatus:$("#adminCatalogPublication").value});notice.textContent="操作成功，数据已刷新。";notice.className="admin-action-notice success";await loadAdmin();}catch(error){notice.textContent=error.message||"管理员操作失败";notice.className="admin-action-notice error";}finally{button.disabled=false;button.textContent=original;}}
async function exportAdminSummary(){try{const response=await fetch("/api/admin/exports/summary",{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"导出失败");const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`shiyue-operations-${new Date().toISOString().slice(0,10)}.json`;link.click();URL.revokeObjectURL(url);}catch(error){$("#adminNotice").textContent=error.message||"导出失败";}}

function normalizeWorkspaceVocabulary(item){const payload=item?.payload&&typeof item.payload==="object"?item.payload:{};return {...payload,id:+item.id,book_id:item.bookId,sentence_id:item.sentenceId,word_index:+item.wordIndex};}
function normalizeWorkspaceLearningDay(item){const payload=item?.payload&&typeof item.payload==="object"?item.payload:{};return {...payload,day:item.day};}
function workspaceVocabularyPayload(entry,updates={}){const payload={...entry,...updates};for(const key of ["id","book_id","sentence_id","word_index","bookId","sentenceId","wordIndex","payload"])delete payload[key];return payload;}
async function ensureVocabularyLoaded(){
  if(vocabLoaded)return vocabItems;
  const endpoint=saasMode?"/api/workspace/vocabulary":"/api/vocabulary";
  if(!vocabLoadPromise)vocabLoadPromise=fetch(endpoint,{cache:"no-store"}).then(async response=>{if(!response.ok)throw new Error("无法加载生词数据");const data=await response.json();vocabItems=saasMode?(data.items||[]).map(normalizeWorkspaceVocabulary):(data.items||[]);vocabLoaded=true;rebuildWordIndexes();return vocabItems;}).finally(()=>{vocabLoadPromise=null;});
  return vocabLoadPromise;
}
async function ensureScreenData(id){
  try{
    if(id==="membership")await refreshMembership();
    if(id==="rewards")await loadRewards();
    if(id==="admin")await loadAdmin();
    if(id==="catalog"){if(!catalogFiltersLoaded)await loadCatalogFilters();await loadCatalog();}
    if(id==="my-library")await loadMyLibrary();
    if(id==="workspace")await loadWorkspace();
    if(id==="vocab"){await ensureVocabularyLoaded();renderReview();}
    if(id==="stats"){await ensureVocabularyLoaded();if(saasMode&&!workspaceBooksLoaded){const response=await fetch("/api/workspace/books",{cache:"no-store"}),data=await response.json();if(response.ok){workspaceBooks=data.books||[];workspaceBooksLoaded=true;}}if(!learningDaysLoaded){const endpoint=saasMode?"/api/workspace/learning-days":"/api/learning/days",response=await fetch(endpoint,{cache:"no-store"}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法加载学习记录");learningDays=saasMode?(data.days||[]).map(normalizeWorkspaceLearningDay):(data.days||[]);learningDaysLoaded=true;}renderStats();}
    if(id==="import"){if(!importCatalogLoaded){await loadImportCatalog();importCatalogLoaded=true;}if(!importTrackingRestored){await restoreImportTracking();importTrackingRestored=true;}}
    if(id==="settings"&&load(STORE.settingsTab,"general")==="deployment"&&!deploymentConfigLoaded){await loadDeploymentConfig();deploymentConfigLoaded=true;}
  }catch(error){console.warn(`加载${id}页面数据失败`,error);}
}

async function loadBook(bookId) {
  const response=await fetch(`/api/books/${encodeURIComponent(bookId)}/manifest`,{cache:"no-cache"});
  if(!response.ok) throw new Error("无法读取图书数据库");
  const record=await response.json(); currentBookId=bookId; book=record.book;bookChunkPromises=new Map();wordAnnotations=record.annotations||[];const bookVocabulary=record.vocabulary||[];vocabItems=[...vocabItems.filter(item=>item.book_id!==bookId),...bookVocabulary];selectedWordContext=null;selectedGrammarSentence=null;expandedSentenceTranslations=new Set();document.body.classList.remove("focus-word-open");rebuildWordIndexes();
  const saved=load(`${STORE.state}-${bookId}`,{}).time||book.sentences[0]?.start||0,center=Math.max(0,sentenceIndexAt(saved));await ensureBookChunksAround(center);
  $("#wordPanel").innerHTML='<div class="word-empty"><span>Aa</span><h3>单词与句子分析</h3><p>悬浮单词查看简释；点击单词查看完整释义，点击句末“句法”分析句型和语法。</p></div>';
  $("#audio").pause(); $("#audio").src=book.audio; $("#duration").textContent=fmt(book.duration);
  $(".book-heading small").textContent=runtimeMode==="reader"?`${book.level||""}级 · READING`:`${book.level||""}级 · LOCAL BOOK`;
  $(".book-heading strong").innerHTML=`${escapeHtml(book.title)} <i>${escapeHtml(book.englishTitle||"")}</i>`;
  $(".book-heading strong").title=[book.title,book.englishTitle].filter(Boolean).join(" · ");
  $(".chapter h1").textContent=book.englishTitle||book.title;
  visualMode="frames";configureBookVisual();active=-1; displayedPage=null; renderStory(); restoreProgress(); showPage(book.sentences[0]?.page||1);
  postActivity({bookId,open:true,sessions:1}).then(()=>fetch("/api/library",{cache:"no-cache"})).then(r=>r.json()).then(data=>{libraryBooks=data.books||libraryBooks;setupSeriesSelector();renderLibrary();}).catch(()=>{});
}

async function loadBookChunk(chunkIndex){
  if(!book||chunkIndex<0||chunkIndex>=(book.chunkCount||1))return;
  if(bookChunkPromises.has(chunkIndex))return bookChunkPromises.get(chunkIndex);
  const expectedBook=currentBookId,promise=fetch(`/api/books/${encodeURIComponent(expectedBook)}/chunks/${chunkIndex}`,{cache:"force-cache"}).then(async response=>{if(!response.ok)throw new Error("正文分块加载失败");const data=await response.json();if(currentBookId!==expectedBook)return;data.sentences.forEach((sentence,offset)=>{const index=data.start+offset;book.sentences[index]={...book.sentences[index],...sentence,_wordsLoaded:true};});return data;}).catch(error=>{bookChunkPromises.delete(chunkIndex);throw error;});
  bookChunkPromises.set(chunkIndex,promise);return promise;
}
async function ensureBookChunksAround(sentenceIndex){
  if(!book?.sentences?.length)return;
  const size=book.chunkSize||80,current=Math.floor(Math.max(0,sentenceIndex)/size),count=book.chunkCount||1,targets=book.sentences.length<=180?[...Array(count).keys()]:[current-1,current,current+1].filter(index=>index>=0&&index<count);
  await Promise.all(targets.map(loadBookChunk));
}
function prefetchBookChunks(sentenceIndex){
  if(!book||sentenceIndex<0)return;
  const needsWords=!book.sentences[sentenceIndex]?.words?.length;ensureBookChunksAround(sentenceIndex).then(()=>{if(needsWords&&readerIsVisible()&&currentBookId===book.id){renderStoryWindow(sentenceIndex,false);paintSentence(sentenceIndex,false);}}).catch(error=>console.warn(error));
}

function renderLibrary() {
  const grid=$("#libraryGrid");
  const visible=libraryBooks.filter(item=>!currentSeries||item.series===currentSeries);
  grid.className=`library-grid ${shelfView}-view`;
  $("#shelfCount").textContent=`${visible.length} 本`; $("#shelfSeriesTitle").textContent=currentSeries||"全部书籍";
  $("#tileViewBtn").classList.toggle("active",shelfView==="tile"); $("#listViewBtn").classList.toggle("active",shelfView==="list");
  if(!visible.length){grid.innerHTML='<div class="empty-state"><h3>当前书系暂无已导入书籍</h3><p>请从“导入书籍”选择书籍。</p></div>';return;}
  grid.innerHTML=visible.map((item,index)=>`<article class="book-card" data-book-id="${escapeHtml(item.id)}" data-source-type="${escapeHtml(item.source_type||'book')}"><details class="book-actions"><summary title="书籍操作" aria-label="书籍操作"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="4" r="1.6"></circle><circle cx="10" cy="10" r="1.6"></circle><circle cx="10" cy="16" r="1.6"></circle></svg></summary><div class="book-actions-menu"><button data-delete-book="${escapeHtml(item.id)}">删除书籍</button></div></details><img src="${encodeURI(item.cover_url)}" alt="${escapeHtml(item.title)}封面" width="160" height="220" loading="${index<8?'eager':'lazy'}" decoding="async" fetchpriority="${index<4?'high':'low'}"><div class="book-info"><span class="tag">LEVEL ${escapeHtml(item.level||"-")}</span><h3>${escapeHtml(item.title)}</h3><em>${escapeHtml(item.english_title||"")}</em><p>${escapeHtml(item.series)}</p><div class="progress"><i style="width:${bookProgress(item.id)}%"></i></div><small>${item.alignment.startsWith('whisper-')?'Whisper 词级点读':runtimeMode==='reader'?'词级点读':'本地点读'}</small></div><button class="round-play">▶</button></article>`).join("");
}
function populateVideoSeriesOptions(){
  const history=[...new Set(libraryBooks.map(item=>(item.series||"").trim()).filter(Boolean).filter(name=>!name.includes("牛津")))].sort((left,right)=>left.localeCompare(right,"zh-CN"));
  const options='<option value="">选择历史标签</option>'+history.map(name=>`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
  [$("#videoSeriesHistory")].forEach(select=>{if(!select)return;const previous=select.value;select.innerHTML=options;if(history.includes(previous))select.value=previous;});
}
function seriesActivity(item){const value=item.last_read_at||item.updated_at||"";const time=Date.parse(value);return Number.isFinite(time)?time:0;}
function seriesAvatar(name){const latin=(name.match(/[A-Za-z]+/g)||[]).join("");if(latin)return latin.slice(0,2).toUpperCase();const compact=name.replace(/[^\u3400-\u9fff]/g,"");return compact.slice(0,1)||"书";}
function seriesSummaries(){
  const summaries=new Map();
  libraryBooks.forEach(item=>{const name=(item.series||"未分类").trim()||"未分类",existing=summaries.get(name)||{name,count:0,activity:0};existing.count++;existing.activity=Math.max(existing.activity,seriesActivity(item));summaries.set(name,existing);});
  return [...summaries.values()].sort((left,right)=>right.activity-left.activity||left.name.localeCompare(right.name,"zh-CN"));
}
function setupSeriesSelector(){
  const series=seriesSummaries(),names=new Set(series.map(item=>item.name));if(currentSeries&&!names.has(currentSeries))currentSeries="";
  let visible=seriesExpanded?series:series.slice(0,RECENT_SERIES_LIMIT);
  if(!seriesExpanded&&currentSeries&&!visible.some(item=>item.name===currentSeries))visible=[series.find(item=>item.name===currentSeries),...visible.slice(0,RECENT_SERIES_LIMIT-1)].filter(Boolean);
  const allCount=libraryBooks.length;
  $("#seriesChannelList").innerHTML=`<button class="series-channel ${currentSeries?'':'active'}" data-series=""><i>全</i><span><b>全部书籍</b><small>${allCount} 本</small></span></button>`+visible.map(item=>`<button class="series-channel ${currentSeries===item.name?'active':''}" data-series="${escapeHtml(item.name)}" title="${escapeHtml(item.name)}"><i>${escapeHtml(seriesAvatar(item.name))}</i><span><b>${escapeHtml(item.name)}</b><small>${item.count} 本</small></span></button>`).join("");
  const more=$("#seriesMoreBtn"),remaining=Math.max(0,series.length-visible.length);more.classList.toggle("hidden",series.length<=RECENT_SERIES_LIMIT);more.textContent=seriesExpanded?"收起书系":`更多书系${remaining?` · ${remaining}`:''}`;more.setAttribute("aria-expanded",String(seriesExpanded));
}
function bookProgress(id){const state=load(`${STORE.state}-${id}`,{});const item=libraryBooks.find(x=>x.id===id);return item?.duration?Math.round((state.time||0)/item.duration*100):0}

function renderStory() {
  const saved=load(`${STORE.state}-${currentBookId}`,{}).time||book.sentences[0]?.start||0;
  const center=Math.max(0,sentenceIndexAt(saved));
  virtualStory=book.sentences.length>180||book.sentences.reduce((sum,sentence)=>sum+(sentence.words?.length||0),0)>12000;
  paintedSentenceIndex=-1;spokenWordElement=null;
  renderStoryWindow(center,false);
}
function renderStoryWindow(center,scroll=false){
  const box=$("#sentences"),total=book.sentences.length;
  const showSectionMarkers=(book.sourceType||"book")==="book";
  const start=virtualStory?Math.max(0,center-STORY_WINDOW_RADIUS):0;
  const end=virtualStory?Math.min(total,center+STORY_WINDOW_RADIUS+1):total;
  storyWindowStart=start;storyWindowEnd=end;box.innerHTML="";
  sentenceElementsByIndex=new Array(total);wordElementsBySentence=new Array(total);spokenWordElement=null;
  if(start>0)box.insertAdjacentHTML("beforeend",`<button class="story-window-nav" data-window-center="${Math.max(0,start-STORY_WINDOW_RADIUS)}">↑ 加载前文</button>`);
  let previousSection=start>0?book.sentences[start-1].section:null;
  for(let index=start;index<end;index++){
    const sentence=book.sentences[index];
    if (showSectionMarkers && sentence.section != null && sentence.section !== previousSection) {
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
    if(saasReaderContext?.kind!=="official")p.insertAdjacentHTML("beforeend",`<button type="button" class="sentence-grammar-btn" data-sentence-grammar title="分析这句话的句式和语法">语法</button>`);
    if(book.sourceType==="youtube"){
      const expanded=expandedSentenceTranslations.has(sentence.id),translation=sentence.translation||"原始中文字幕未提供该段译文";
      p.insertAdjacentHTML("beforeend",`<button type="button" class="sentence-grammar-btn sentence-translation-btn" data-sentence-translation aria-expanded="${expanded}" title="${expanded?'收起':'查看'}原始中文字幕">${expanded?'收起翻译':'翻译'}</button><span class="sentence-translation ${expanded?'':'hidden'}">${escapeHtml(translation)}</span>`);
    }
    if(index===paintedSentenceIndex)p.classList.add("active");
    box.append(p);
    sentenceElementsByIndex[index]=p;
    wordElementsBySentence[index]=[...p.querySelectorAll(".word[data-start][data-end]")];
    wordElementsBySentence[index].forEach((element,wordIndex)=>applyWordMark(element,sentence,wordIndex));
  }
  if(end<total)box.insertAdjacentHTML("beforeend",`<button class="story-window-nav" data-window-center="${Math.min(total-1,end+STORY_WINDOW_RADIUS-1)}">加载后文 ↓</button>`);
  if(scroll&&sentenceElementsByIndex[center])requestAnimationFrame(()=>scrollSentenceIntoView(sentenceElementsByIndex[center],"auto"));
}
function ensureSentenceRendered(index,scroll=false){
  if(!virtualStory)return sentenceElementsByIndex[index];
  const outside=!sentenceElementsByIndex[index],nearEdge=index<storyWindowStart+STORY_WINDOW_EDGE||index>=storyWindowEnd-STORY_WINDOW_EDGE;
  if(outside||nearEdge){const previous=paintedSentenceIndex;renderStoryWindow(index,scroll);if(previous!==index)sentenceElementsByIndex[previous]?.classList.remove("active");}
  return sentenceElementsByIndex[index];
}
function applyWordMark(element,sentence,wordIndex){const key=wordRecordKey(sentence.id,wordIndex),annotation=annotationIndex.get(key),vocab=vocabWordIndex.get(key);element.classList.toggle("annotated-word",!!annotation);element.classList.toggle("vocab-word",!!vocab);if(annotation?.note)element.dataset.note=annotation.note;else delete element.dataset.note;if(annotation?.corrected_word)element.dataset.correction=`OCR订正：${annotation.original_word} → ${annotation.corrected_word}`;else delete element.dataset.correction;element.title=[annotation?.note,element.dataset.correction,vocab?'已加入生词本':''].filter(Boolean).join(' · ');}
function refreshWordMarks(){for(let index=storyWindowStart;index<storyWindowEnd;index++){const sentence=book?.sentences?.[index];(wordElementsBySentence[index]||[]).forEach((element,wordIndex)=>applyWordMark(element,sentence,wordIndex));}}

function bindEvents() {
  $("#libraryGrid").onclick = async event => {
    const deleteButton=event.target.closest("[data-delete-book]");
    if(deleteButton){event.preventDefault();event.stopPropagation();openDeleteBookDialog(deleteButton.dataset.deleteBook);return;}
    if(event.target.closest(".book-actions"))return;
    const card=event.target.closest("[data-book-id]");if(!card)return;await loadBook(card.dataset.bookId);openReader();
  };
  $("#backBtn").onclick = () => {if(saasReaderContext){const target=saasReaderContext.returnScreen;saasReaderContext=null;showScreen(target);return;}showScreen("shelf");};
  $$(".nav").forEach(button => button.onclick = () => {closeMobileSidebar();showScreen(button.dataset.screen);});
  $$(".mode-switch button").forEach(button => button.onclick = () => setMode(button.dataset.mode));
  $("#sentences").addEventListener("click", event => {
    const windowButton=event.target.closest("[data-window-center]");
    if(windowButton){renderStoryWindow(+windowButton.dataset.windowCenter,true);return;}
    const branch = event.target.closest(".branch-link");
    if (branch) { event.stopPropagation(); jumpToSection(+branch.dataset.target); return; }
    const sentenceElement = event.target.closest(".sentence");
    if (!sentenceElement) return;
    const sentence = book.sentences[+sentenceElement.dataset.i];
    const translationButton=event.target.closest("[data-sentence-translation]");
    if(translationButton){
      event.stopPropagation();const translation=sentenceElement.querySelector(".sentence-translation"),expanded=translationButton.getAttribute("aria-expanded")!=="true";
      translationButton.setAttribute("aria-expanded",String(expanded));translationButton.textContent=expanded?"收起翻译":"翻译";translationButton.title=`${expanded?'收起':'查看'}原始中文字幕`;translation?.classList.toggle("hidden",!expanded);
      if(expanded)expandedSentenceTranslations.add(sentence.id);else expandedSentenceTranslations.delete(sentence.id);return;
    }
    if(event.target.closest(".sentence-translation")){event.stopPropagation();return;}
    if(event.target.closest("[data-sentence-grammar]")){event.stopPropagation();showSentenceGrammar(sentence);return;}
    if (event.target.classList.contains("word")) {
      event.stopPropagation();
      const word = event.target;
      hideWordHoverMeaning();
      const audio=$("#audio");
      // A click happens after pointer-over has already paused the main track.
      // Preserve that position so leaving the word can resume the book audio.
      if (!audio.paused || pausedForWord) {
        clickedWordPausedMain=true;
        clickedWordResumeTime=hoverPausedTime ?? audio.currentTime;
        clickedWordResumeSentence=hoverPausedSentence>=0 ? hoverPausedSentence : active;
      }
      cancelMainAudioFade();
      clearTimeout(audioStopTimer); wordStopAt=null; audio.pause(); pausedForWord=false;
      hoverPausedTime=null; hoverPausedSentence=-1;
      showWord(word.textContent, sentence, word);
      playWordTts(word.textContent);
      postActivity({lookups:1});
    }
    else playSentence(+sentenceElement.dataset.i);
  });
  $("#sentences").addEventListener("pointerover", handleWordPointerOver);
  $("#sentences").addEventListener("pointerout", handleWordPointerOut);
  $("#playBtn").onclick = () => { resetWordHoverSession(); clearTimeout(audioStopTimer); if ($("#audio").paused) { wordStopAt=null; $("#audio").play(); } else $("#audio").pause(); };
  $("#prevBtn").onclick = () => playSentence(Math.max(0, active - 1));
  $("#nextBtn").onclick = () => playSentence(Math.min(book.sentences.length - 1, active + 1));
  $("#seek").oninput = event => {
    if(!book?.duration)return;
    const time=event.target.value/1000*book.duration;
    if(isCompactTouchLayout()){
      pendingSeekTime=time;$("#currentTime").textContent=fmt(time);return;
    }
    commitSeekTime(time);
  };
  $("#seek").onchange = event => {if(isCompactTouchLayout()&&book?.duration&&pendingSeekTime!==null){commitSeekTime(event.target.value/1000*book.duration);pendingSeekTime=null;}};
  $("#seek").addEventListener("pointerdown",event=>{if(!isCompactTouchLayout())return;seekPreviewDragging=true;try{event.currentTarget.setPointerCapture(event.pointerId);}catch{}showSeekSentencePreview(event);});
  $("#seek").addEventListener("pointerenter",showSeekSentencePreview);
  $("#seek").addEventListener("pointermove",showSeekSentencePreview);
  $("#seek").addEventListener("pointerup",event=>{if(!isCompactTouchLayout())return;const time=pendingSeekTime??seekTimeFromPointer(event);commitSeekTime(time);seekPreviewDragging=false;pendingSeekTime=null;hideSeekSentencePreview();});
  $("#seek").addEventListener("pointerleave",()=>{if(!seekPreviewDragging)hideSeekSentencePreview();});
  $("#seek").addEventListener("pointercancel",()=>{seekPreviewDragging=false;pendingSeekTime=null;hideSeekSentencePreview();});
  const rates = [.75, 1, 1.25, 1.5]; let rateIndex = 1;
  $("#speedBtn").onclick = () => { rateIndex = (rateIndex + 1) % rates.length; $("#audio").playbackRate = rates[rateIndex];setVideoBaseRate();syncVideoToAudio(false);$("#speedBtn").textContent = rates[rateIndex] + "×"; };
  $("#sidebarToggle").onclick=()=>isResponsiveNavLayout()?closeMobileSidebar():setSidebarCollapsed(true);
  $("#sidebarReveal").onclick=()=>isResponsiveNavLayout()?setMobileSidebarOpen(true):setSidebarCollapsed(false);
  $("#sidebarBackdrop").onclick=closeMobileSidebar;
  $("#mobilePanelBackdrop").onclick=closeMobileDetailPanels;
  $("#readerLayoutBtn").onclick=toggleReaderLayout;
  $("#focusBtn").onclick = toggleFocusMode;
  $("#eyeComfortBtn").onclick = toggleEyeComfort;
  $("#recordBtn").onclick = toggleRecording;
  $("#playRecordBtn").onclick = playRecordingReview;
  $("#audio").ontimeupdate = persistAudioProgress;
  $("#audio").onplay = () => { $("#playBtn").textContent = "Ⅱ"; if(sentenceAutoPause&&active>=0&&mode!=="shadow")wordStopAt=book.sentences[active].end+.03;if(mode==="shadow"){if(shadowSentenceIndex<0)shadowSentenceIndex=active>=0?active:sentenceIndexAt($("#audio").currentTime);if(!shadowWaiting&&shadowSentenceIndex>=0)scheduleShadowSentenceStop(shadowSentenceIndex);}if(visualMode==="video")playVideoView();trackListening(); startPlaybackSync(); };
  $("#audio").onpause = () => { $("#playBtn").textContent = "▶"; $("#videoView").pause();stopVideoFrameSync();stopPlaybackSync();syncVideoToAudio(true);syncPlaybackFrame(); };
  $("#audio").onseeked = () => {syncVideoToAudio(true);syncPlaybackFrame();};
  $("#audio").onended=()=>{maybeCompleteOfficialReading();};
  $("#videoView").onloadedmetadata=()=>{setVideoBaseRate();syncVideoToAudio(true);scheduleMediaStageSize();};
  $("#videoView").onloadeddata=markVideoReady;$("#videoView").oncanplay=markVideoReady;
  $("#videoView").onwaiting=handleVideoWaiting;$("#videoView").onstalled=handleVideoStalled;$("#videoView").onerror=handleVideoError;
  $("#pageImage").onload=()=>{$("#pageImage").classList.add("image-ready");$("#imageStatusOverlay").classList.add("hidden");$("#pagePanel").classList.remove("media-error");scheduleMediaStageSize();};
  $("#pageImage").onerror=()=>{$("#pageImage").classList.remove("image-ready");$("#imageStatusText").textContent="原书页面暂不可用，正文仍可继续阅读";$("#imageRetryBtn").classList.remove("hidden");$("#imageStatusOverlay").classList.remove("hidden");$("#pagePanel").classList.add("media-error");scheduleMediaStageSize();};
  $("#imageRetryBtn").onclick=()=>{if(!book)return;const page=displayedPage;displayedPage=null;$("#imageStatusOverlay").classList.add("hidden");showPage(page||1);};
  $("#videoView").onplaying=()=>{markVideoReady();startVideoFrameSync();};
  $("#videoView").onpause=stopVideoFrameSync;
  window.addEventListener("resize",()=>{syncResponsiveState();syncMobileBottomNav();scheduleTopbarContentAlignment();scheduleMediaStageSize();});
  window.addEventListener("scroll",()=>{if(readerIsVisible())maybeCompleteOfficialReading();},{passive:true});
  window.addEventListener("popstate",()=>{if(!saasMode)return;const params=new URLSearchParams(location.search),screen=params.get("screen")||"catalog";if(screen==="reader"&&params.get("id")){params.get("reader")==="official"?openCatalogReader(params.get("id")):openWorkspaceReader(params.get("id"));return;}showScreen(screen,false);if(screen==="admin")setAdminTab(params.get("tab")||"overview",false);if(screen==="settings")setSettingsTab(params.get("tab")||"general",false);const detail=params.get("book");if(detail)loadCatalogDetail(detail);else if($("#catalogDetailDialog").open)$("#catalogDetailDialog").close();});
  if(compactTouchQuery.addEventListener)compactTouchQuery.addEventListener("change",syncResponsiveState);
  else compactTouchQuery.addListener?.(syncResponsiveState);
  window.addEventListener("beforeunload", finishSession);
  $("#settingsTabs").onclick=event=>{const tab=event.target.closest("[data-settings-tab]");if(tab)setSettingsTab(tab.dataset.settingsTab);};
  $("#settingsTabs").onkeydown=event=>{if(!["ArrowLeft","ArrowRight","Home","End"].includes(event.key))return;event.preventDefault();const tabs=$$("#settingsTabs [data-settings-tab]:not(.hidden)"),current=Math.max(0,tabs.indexOf(document.activeElement));let next=event.key==="Home"?0:event.key==="End"?tabs.length-1:event.key==="ArrowRight"?(current+1)%tabs.length:(current-1+tabs.length)%tabs.length;tabs[next]?.focus();setSettingsTab(tabs[next].dataset.settingsTab);};
  setSettingsTab(load(STORE.settingsTab,"general"),false);
  $("#settingsForm").onsubmit = saveApiSettings;
  $("#deploymentForm").onsubmit=saveDeploymentConfig;
  $("#newDeploymentNode").onclick=()=>beginNewDeploymentNode();
  $("#cancelDeploymentEdit").onclick=()=>activeDeploymentTargetId?selectDeploymentTarget(activeDeploymentTargetId):beginNewDeploymentNode();
  $("#deploymentNodeList").onclick=handleDeploymentNodeListClick;
  $("#testDeployment").onclick=()=>startDeploymentAction("test");
  $("#deployCodeBtn").onclick=()=>startDeploymentAction("deploy");
  $("#upgradeCodeBtn").onclick=()=>startDeploymentAction("upgrade");
  $("#syncResourcesBtn").onclick=()=>startDeploymentAction("sync");
  $("#uninstallNodeBtn").onclick=()=>openUninstallNodeDialog(activeDeploymentTargetId);
  $("#deleteNodeConfigBtn").onclick=deleteSelectedNodeConfig;
  $("#uninstallNodeConfirm").oninput=validateUninstallNodeConfirmation;
  $("#confirmUninstallNode").onclick=confirmUninstallNode;
  $("#uninstallNodeDialog").addEventListener("close",resetUninstallNodeDialog);
  $("#rollbackRelease").onchange=event=>{$("#rollbackCodeBtn").disabled=!event.target.value;};
  $("#rollbackCodeBtn").onclick=()=>startDeploymentAction("rollback",{releaseId:$("#rollbackRelease").value});
  $("#rollbackContentRelease").onchange=event=>{$("#rollbackContentBtn").disabled=!event.target.value;};
  $("#rollbackContentBtn").onclick=()=>startDeploymentAction("content-rollback",{releaseId:$("#rollbackContentRelease").value});
  $("#cleanupVersionsBtn").onclick=()=>{const days=Math.max(1,+$("#versionRetentionDays").value||30);if(confirm(`将永久删除 ${days} 天前的非当前代码版本、内容快照及对应备份。当前运行版本不会删除，是否继续？`))startDeploymentAction("cleanup",{retentionDays:days});};
  $("#clearDeploymentLog").onclick=()=>{$("#deploymentLog").textContent="";};
  $("#seriesChannels").onclick=event=>{
    const more=event.target.closest("#seriesMoreBtn");if(more){seriesExpanded=!seriesExpanded;setupSeriesSelector();return;}
    const channel=event.target.closest("[data-series]");if(!channel)return;
    currentSeries=channel.dataset.series;seriesExpanded=false;setupSeriesSelector();renderLibrary();savePreference({currentSeries});showScreen("shelf");
  };
  $("#tileViewBtn").onclick=()=>setShelfView("tile"); $("#listViewBtn").onclick=()=>setShelfView("list");
  $$(".shortcut-input").forEach(input=>input.onkeydown=captureShortcut);
  $("#importSeries").onchange = updateImportBooks;
  $("#importBookList").onchange = updateBatchButton;
  $("#selectAllBooks").onclick = () => { $$("#importBookList .import-book-item:not(.imported) input:not(:disabled)").forEach(input=>input.checked=true); updateBatchButton(); };
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
  $("#videoHighBtn").onclick=()=>switchVideoQuality("high",false);$("#videoLowBtn").onclick=()=>switchVideoQuality("low",false);$("#videoRetryBtn").onclick=()=>switchVideoQuality(videoQuality,false,true);
  $("#closeStackLayoutBtn").onclick=event=>{event.currentTarget.blur();if(readerLayout!=="side"){readerLayout="side";applyReaderLayout();scheduleTopbarContentAlignment();showReaderToast("布局：画面左侧，文章右侧");}};
  document.addEventListener("keydown",handleReaderShortcut);
  document.addEventListener("pointerup",scheduleReaderShortcutFocus,true);
  document.addEventListener("click",event=>{const button=event.target.closest("button");if(button)setTimeout(()=>button.blur(),0);scheduleReaderShortcutFocus(event);});
  document.addEventListener("change",scheduleReaderShortcutFocus,true);
  $("#wordPanel").onclick=handleWordPanelAction;
  document.addEventListener("click",handleContextToggle);
  $("#statsContent").onclick=event=>{const button=event.target.closest("[data-heatmap-range]");if(button){setHeatmapRange(button.dataset.heatmapRange);return;}const continueButton=event.target.closest("[data-stats-continue]");if(continueButton){openWorkspaceReader(continueButton.dataset.statsContinue);return;}if(event.target.closest("[data-stats-go-workspace]"))showScreen("workspace");};
  $("#reviewContent").onclick=handleReviewClick;
  $("#reviewWordPanel").onclick=handleReviewClick;
  $("#deleteBookConfirmInput").oninput=validateDeleteBookConfirmation;
  $("#confirmDeleteBook").onclick=confirmDeleteBook;
  $("#deleteBookDialog").addEventListener("close",resetDeleteBookDialog);
  $("#cancelActiveImports").onclick=openCancelImportDialog;
  $("#confirmCancelImports").onclick=cancelActiveImports;
  $("#saasLoginForm").onsubmit=submitSaasLogin;
  $("#saasRegisterForm").onsubmit=submitSaasRegister;
  $("#saasForgotForm").onsubmit=submitSaasForgot;
  $("#membershipRefresh").onclick=refreshMembership;
  $("#saasLogout").onclick=logoutSaas;
  $("#accountExport").onclick=exportAccountData;
  $("#accountDelete").onclick=requestAccountDeletion;
  $("#accountCancelDeletion").onclick=cancelAccountDeletion;
  $("#catalogSearchForm").onsubmit=event=>{event.preventDefault();selectedCatalogBookId="";$("#catalogDetail").innerHTML='<div class="empty-state"><h3>选择一本读物</h3><p>查看介绍、难度、学习功能与解锁规则。</p></div>';loadCatalog();};
  $("#catalogBookList").onclick=event=>{const card=event.target.closest("[data-catalog-book]");if(card)loadCatalogDetail(card.dataset.catalogBook);};
  $("#myLibraryList").onclick=event=>{const card=event.target.closest("[data-catalog-book]");if(card)loadCatalogDetail(card.dataset.catalogBook);};
  $("#catalogDetail").onclick=event=>{const button=event.target.closest("[data-catalog-action]");if(button)catalogAction(button.dataset.catalogAction);};
  $("#catalogReaderBack").onclick=()=>showScreen("catalog");
  $("#catalogReaderContent").onclick=markCatalogSentence;
  $("#catalogDetailDialog").addEventListener("close",()=>updateRoute({book:null},true));
  $("#workspaceBookList").onclick=event=>{const card=event.target.closest("[data-workspace-book]");if(card){openWorkspaceReader(card.dataset.workspaceBook);return;}if(event.target.closest("[data-workspace-reset]")){workspaceQuery="";$("#workspaceQuery").value="";renderWorkspaceBooks();}if(event.target.closest("[data-workspace-import]"))$("#workspaceImportTools").open=true;};
  $("#workspaceContinue").onclick=event=>{const button=event.target.closest("[data-workspace-continue]");if(button)openWorkspaceReader(button.dataset.workspaceContinue);};
  $("#workspaceQuery").oninput=event=>{workspaceQuery=event.target.value;renderWorkspaceBooks();};
  $("#workspaceSort").onchange=event=>{workspaceSort=event.target.value;renderWorkspaceBooks();};
  $("#workspaceReaderBack").onclick=()=>showScreen("workspace");
  $("#workspaceReaderContent").onclick=markWorkspaceSentence;
  $("#workspaceTextImportForm").onsubmit=startWorkspaceTextImport;
  $("#workspaceYoutubeImportForm").onsubmit=startWorkspaceYoutubeImport;
  $("#workspaceTaskRefresh").onclick=loadWorkspace;
  $("#workspaceTaskList").onclick=event=>{const button=event.target.closest("[data-workspace-task-cancel]");if(button)cancelWorkspaceImport(button.dataset.workspaceTaskCancel);};
  $("#rewardStatus").onclick=event=>{if(event.target.closest("#rewardCheckin"))checkinReward();if(event.target.closest("#rewardInvite"))issueMemberInvite();};
  $("#rewardCatalogList").onclick=event=>{const button=event.target.closest("[data-reward-code]");if(button)redeemReward(button.dataset.rewardCode);};
  $("#rewardsRefresh").onclick=loadRewards;
  $("#adminRefresh").onclick=loadAdmin;
  $("#adminTabs").onclick=event=>{const button=event.target.closest("[data-admin-tab]");if(button)setAdminTab(button.dataset.adminTab);};
  $("#adminUserSearch").oninput=()=>{clearTimeout($("#adminUserSearch")._timer);$("#adminUserSearch")._timer=setTimeout(loadAdmin,250);};
  $("#adminInvitationForm").onsubmit=event=>submitAdminForm(event,"invitation");
  $("#adminQuotaForm").onsubmit=event=>submitAdminForm(event,"quota");
  $("#adminOrderForm").onsubmit=event=>submitAdminForm(event,"order");
  $("#adminAllowanceForm").onsubmit=event=>submitAdminForm(event,"allowance");
  $("#adminCatalogReviewForm").onsubmit=event=>submitAdminForm(event,"catalog");
  $("#adminExport").onclick=exportAdminSummary;
  $("#adminMediaRefresh").onclick=loadAdmin;
  $("#adminMediaPrev").onclick=()=>{if(adminMediaPage>1){adminMediaPage--;loadAdmin();}};$("#adminMediaNext").onclick=()=>{adminMediaPage++;loadAdmin();};
  $("#adminUserList").onclick=async event=>{const select=event.target.closest("[data-admin-user-select]");if(select){for(const id of ["adminQuotaUserId","adminOrderUserId","adminAllowanceUserId"])$("#"+id).value=select.dataset.adminUserSelect;$("#adminActionNotice").textContent="已选择用户，可切换到“会员与额度”继续操作。";return;}const status=event.target.closest("[data-admin-user-status]");if(status){const reason=prompt(`请输入${status.dataset.adminNextStatus==="suspended"?"封禁":"恢复"}原因：`);if(!reason)return;try{$("#adminActionNotice").textContent="正在更新用户状态…";await adminRequest(`/api/admin/users/${encodeURIComponent(status.dataset.adminUserStatus)}/status`,{status:status.dataset.adminNextStatus,reason});$("#adminActionNotice").textContent="用户状态已更新。";await loadAdmin();}catch(error){$("#adminActionNotice").textContent=error.message||"用户状态更新失败";}}};
  $("#adminCatalogSources").onclick=event=>{const source=event.target.closest("[data-admin-source]");if(source){$("#adminCatalogSourceId").value=source.dataset.adminSource;$("#adminActionNotice").textContent="已选择内容，请设置版权与发布状态后保存。";}};
  $("#adminOrderStart").value=dateTimeLocal(0);$("#adminOrderEnd").value=dateTimeLocal(30);
  document.addEventListener("click",event=>{if(!event.target.closest(".book-actions"))$$(".book-actions[open]").forEach(menu=>menu.removeAttribute("open"));});
}

function openDeleteBookDialog(bookId){
  pendingDeleteBook=libraryBooks.find(item=>item.id===bookId);if(!pendingDeleteBook)return;
  $("#deleteBookTitle").textContent=pendingDeleteBook.title;$("#deleteBookConfirmInput").value="";$("#deleteBookConfirmInput").placeholder=pendingDeleteBook.title;
  $("#deleteBookError").textContent="";$("#confirmDeleteBook").disabled=true;$("#deleteBookDialog").showModal();setTimeout(()=>$("#deleteBookConfirmInput").focus(),0);
}
function normalizedDeleteTitle(value){return String(value||"").replace(/\s+/gu,"");}
function validateDeleteBookConfirmation(){$("#confirmDeleteBook").disabled=!pendingDeleteBook||normalizedDeleteTitle($("#deleteBookConfirmInput").value)!==normalizedDeleteTitle(pendingDeleteBook.title);$("#deleteBookError").textContent="";}
function resetDeleteBookDialog(){pendingDeleteBook=null;$("#deleteBookConfirmInput").value="";$("#deleteBookError").textContent="";$("#confirmDeleteBook").disabled=true;}
async function confirmDeleteBook(){
  if(!pendingDeleteBook)return;const target={...pendingDeleteBook},button=$("#confirmDeleteBook");button.disabled=true;button.textContent="正在删除…";
  try{
    const response=await fetch(`/api/books/${encodeURIComponent(target.id)}/delete`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirmTitle:$("#deleteBookConfirmInput").value.trim()})});
    const result=await response.json();if(!response.ok)throw new Error(result.error||"删除失败");
    localStorage.removeItem(`${STORE.state}-${target.id}`);vocabItems=vocabItems.filter(item=>item.book_id!==target.id);libraryBooks=libraryBooks.filter(item=>item.id!==target.id);rebuildWordIndexes();
    if(currentBookId===target.id){$("#audio").pause();$("#audio").removeAttribute("src");$("#videoView").removeAttribute("src");book=null;currentBookId="";active=-1;wordAnnotations=[];rebuildWordIndexes();}
    $("#deleteBookDialog").close();setupSeriesSelector();populateVideoSeriesOptions();renderLibrary();await loadImportCatalog();showScreen("shelf");showReaderToast(`已永久删除《${target.title}》`);
  }catch(error){$("#deleteBookError").textContent=error.message;button.disabled=false;}
  finally{button.textContent="永久删除";}
}

function bookHasVideo(){return !!book?.video;}
function bookHasVisual(){return !!(bookHasVideo()||(book?.hasOriginalPages!==false&&book?.pageBase));}
function isResponsiveNavLayout(){return innerWidth<=1023;}
function isCompactTouchLayout(){return compactTouchQuery.matches;}
function setMobileSidebarOpen(open){
  if(!isResponsiveNavLayout())open=false;
  document.body.classList.toggle("mobile-nav-open",open);
  $("#sidebarBackdrop")?.classList.toggle("hidden",!open);
  $("#sidebarReveal")?.setAttribute("aria-expanded",String(open));
}
function closeMobileSidebar(){setMobileSidebarOpen(false);}
function openMobileDetailPanel(kind){
  if(!isCompactTouchLayout())return;
  document.body.classList.toggle("mobile-word-open",kind==="word");
  document.body.classList.toggle("mobile-review-open",kind==="review");
  $("#mobilePanelBackdrop")?.classList.remove("hidden");
}
function closeMobileDetailPanels(resume=true){
  const wasWordOpen=document.body.classList.contains("mobile-word-open");
  document.body.classList.remove("mobile-word-open","mobile-review-open");
  $("#mobilePanelBackdrop")?.classList.add("hidden");
  if(resume&&wasWordOpen&&(pausedForWord||clickedWordPausedMain))scheduleWordResume();
}
function syncResponsiveState(){
  const compact=isCompactTouchLayout();
  document.body.classList.toggle("compact-touch",compact);
  if(!isResponsiveNavLayout())closeMobileSidebar();
  if(!compact)closeMobileDetailPanels(false);
  if(compact)hideWordHoverMeaning();
}
function syncReaderPanels(){const focused=document.body.classList.contains("focus"),focusWordOpen=document.body.classList.contains("focus-word-open");$("#pagePanel").classList.toggle("hidden",focused||!bookHasVisual());$("#wordPanel").classList.toggle("hidden",focused&&!focusWordOpen);}
function readerIsVisible(){return !$("#reader").classList.contains("hidden");}
function syncReaderActionVisibility(){const reading=readerIsVisible();$("#focusBtn").classList.toggle("hidden",!reading);$("#eyeComfortBtn").classList.toggle("hidden",!reading);$("#readerLayoutBtn").classList.toggle("hidden",!reading||!bookHasVisual());}
function syncTopbarContentAlignment(){
  const inner=$(".topbar-inner");if(!inner)return;inner.style.width="";inner.style.marginLeft="";inner.style.marginRight="";
}
function scheduleTopbarContentAlignment(){requestAnimationFrame(()=>requestAnimationFrame(syncTopbarContentAlignment));}
function readerLayoutIcon(layout){
  return layout==="stack"?'<svg viewBox="0 0 24 24" aria-hidden="true"><rect class="layout-visual" x="2" y="3" width="16" height="7" rx="2"></rect><rect class="layout-story" x="2" y="12" width="16" height="9" rx="2"></rect><rect class="layout-dict" x="20" y="3" width="2" height="18" rx="1"></rect></svg>':'<svg viewBox="0 0 24 24" aria-hidden="true"><rect class="layout-visual" x="2" y="3" width="7" height="18" rx="2"></rect><rect class="layout-story" x="11" y="3" width="7" height="18" rx="2"></rect><rect class="layout-dict" x="20" y="3" width="2" height="18" rx="1"></rect></svg>';
}
function applyReaderLayout(){
  const reader=$("#reader"),button=$("#readerLayoutBtn"),hasVisual=bookHasVisual();reader.dataset.visualLayout=readerLayout;
  button.classList.toggle("hidden",!readerIsVisible()||!hasVisual);button.classList.toggle("active",readerLayout==="stack");button.setAttribute("aria-pressed",String(readerLayout==="stack"));button.innerHTML=readerLayoutIcon(readerLayout);
  const next=readerLayout==="side"?"上下":"左右";button.title=`切换为${next}布局`;button.setAttribute("aria-label",`当前${readerLayout==="side"?"左右":"上下"}布局，切换为${next}布局`);scheduleMediaStageSize();
}
function recommendedReaderLayout(){return bookHasVideo()?"stack":"side";}
function toggleReaderLayout(){readerLayout=readerLayout==="side"?"stack":"side";applyReaderLayout();scheduleTopbarContentAlignment();showReaderToast(readerLayout==="side"?"布局：画面左侧，文章右侧":"布局：画面上方，文章下方");}
function setSidebarCollapsed(collapsed){document.body.classList.toggle("sidebar-collapsed",collapsed);$("#sidebarToggle").setAttribute("aria-expanded",String(!collapsed));$("#sidebarReveal").setAttribute("aria-expanded",String(!collapsed));$(".topbar").setAttribute("aria-hidden",String(!readerIsVisible()&&!collapsed));scheduleTopbarContentAlignment();}
function setFocusMode(enabled){
  document.body.classList.toggle("focus",enabled);document.body.classList.remove("focus-word-open");setSidebarCollapsed(false);
  const button=$("#focusBtn");button.textContent=enabled?"普通模式":"专注模式";button.classList.toggle("active",enabled);button.setAttribute("aria-pressed",String(enabled));
  syncReaderPanels();syncReaderActionVisibility();scheduleTopbarContentAlignment();
}
function toggleFocusMode(){setFocusMode(!document.body.classList.contains("focus"));}
function videoVariant(quality){
  const variant=book?.videoVariants?.[quality];
  if(variant?.status==="ready"&&variant.url)return variant;
  if(quality==="high"&&book?.video)return{label:"高清",url:book.video,status:"ready"};
  return null;
}
function clearVideoLoadingTimers(){clearTimeout(videoBufferTimer);clearTimeout(videoDowngradeTimer);videoBufferTimer=videoDowngradeTimer=null;}
function showVideoStatus(message,type="loading",retry=false){
  clearTimeout(videoStatusTimer);const overlay=$("#videoStatusOverlay");$("#videoStatusText").textContent=message;overlay.classList.remove("hidden","is-error","is-notice");if(type==="error")overlay.classList.add("is-error");if(type==="notice")overlay.classList.add("is-notice");$("#videoRetryBtn").classList.toggle("hidden",!retry);
  if(type==="notice")videoStatusTimer=setTimeout(()=>overlay.classList.add("hidden"),2200);
}
function hideVideoStatus(){clearTimeout(videoStatusTimer);$("#videoStatusOverlay").classList.add("hidden");$("#videoRetryBtn").classList.add("hidden");}
function updateVideoQualityControls(){
  const low=videoVariant("low"),hasLow=!!low;$("#videoQualitySwitch").classList.toggle("hidden",!bookHasVideo()||!hasLow);$("#videoLowBtn").disabled=!hasLow;$("#videoHighBtn").classList.toggle("active",videoQuality==="high");$("#videoLowBtn").classList.toggle("active",videoQuality==="low");
}
function switchVideoQuality(quality="high",automatic=false,force=false){
  const variant=videoVariant(quality);if(!variant)return false;
  const video=$("#videoView"),previousQuality=videoQuality,same=video.dataset.quality===quality&&video.currentSrc;
  if(same&&!force){videoQuality=quality;updateVideoQualityControls();playVideoView();return true;}
  videoQualitySwitchToken++;clearVideoLoadingTimers();videoQuality=quality;if(!automatic||previousQuality!==quality)videoRetryCount=0;if(!automatic)videoAutoDowngraded=false;updateVideoQualityControls();stopVideoFrameSync();video.pause();$("#pagePanel").classList.remove("video-ready");showVideoStatus(`正在加载${variant.label||(quality==="high"?"高清":"流畅")}视频`);
  video.dataset.quality=quality;video.src=variant.url;video.load();videoBufferTimer=setTimeout(()=>{if(video.readyState<2&&visualMode==="video")showVideoStatus("视频加载较慢，可切换流畅画质或重试","notice",true);},4500);scheduleMediaStageSize();return true;
}
function markVideoReady(){
  if(visualMode!=="video"||!bookHasVideo())return;const video=$("#videoView");if(video.readyState<2)return;clearVideoLoadingTimers();$("#pagePanel").classList.add("video-ready");hideVideoStatus();videoRetryCount=0;setVideoBaseRate();syncVideoToAudio(true);scheduleMediaStageSize();if(!$("#audio").paused&&video.paused)video.play().then(startVideoFrameSync).catch(handleVideoError);
}
function playVideoView(){
  if(!bookHasVideo()||visualMode!=="video")return;const video=$("#videoView"),audio=$("#audio"),variant=videoVariant(videoQuality)||videoVariant("high");if(!variant)return;
  if(!video.currentSrc||video.dataset.quality!==videoQuality){switchVideoQuality(videoQuality,false);return;}
  if(video.readyState<2){showVideoStatus(`正在加载${videoQuality==="high"?"高清":"流畅"}视频`);return;}
  syncVideoToAudio(true);if(audio.paused){video.pause();markVideoReady();return;}video.play().then(startVideoFrameSync).catch(handleVideoError);
}
function handleVideoWaiting(){
  if(visualMode!=="video")return;clearVideoLoadingTimers();videoBufferTimer=setTimeout(()=>showVideoStatus("视频正在缓冲"),500);
  if(videoQuality==="high"&&videoVariant("low")&&!videoAutoDowngraded)videoDowngradeTimer=setTimeout(()=>{videoAutoDowngraded=true;showReaderToast("网络较慢，已切换到流畅视频");switchVideoQuality("low",true,true);},1800);
}
function handleVideoStalled(){
  if(visualMode!=="video")return;handleVideoWaiting();clearTimeout(videoBufferTimer);videoBufferTimer=setTimeout(()=>{videoRetryCount++;if(videoRetryCount<=2){showVideoStatus(`视频连接中断，正在重试 ${videoRetryCount}/2`);switchVideoQuality(videoQuality,true,true);}else handleVideoFailure();},5000);
}
function handleVideoError(){if(visualMode==="video")handleVideoFailure();}
function handleVideoFailure(){
  clearVideoLoadingTimers();if(videoQuality==="high"&&videoVariant("low")){videoAutoDowngraded=true;showReaderToast("高清视频不可用，已切换到流畅视频");switchVideoQuality("low",true,true);return;}
  if(videoRetryCount<2){videoRetryCount++;showVideoStatus(`视频加载失败，正在重试 ${videoRetryCount}/2`);switchVideoQuality(videoQuality,true,true);return;}
  $("#videoView").pause();$("#pagePanel").classList.remove("video-ready");showVideoStatus("视频暂不可用，当前显示关键帧","error",true);showReaderToast("视频不可用，当前显示关键帧");
}
function configureBookVisual(){
  const isVideo=bookHasVideo(),hasPages=book?.hasOriginalPages!==false&&!!book?.pageBase,hasVisual=isVideo||hasPages;readerLayout=recommendedReaderLayout();videoQuality=book?.videoDefaultQuality||"high";videoAutoDowngraded=false;videoRetryCount=0;clearVideoLoadingTimers();$("#pagePanel").classList.toggle("hidden",!hasVisual);$("#pagePanel").classList.toggle("has-video",isVideo);$("#pagePanel").classList.remove("video-ready");$("#visualSwitch").classList.toggle("hidden",!isVideo);$("#visualTitle").textContent=isVideo?"视频画面":hasPages?"原书页":"无原书页面";$("#pageImage").classList.toggle("hidden",isVideo||!hasPages);if(!hasPages)$("#pageImage").removeAttribute("src");stopVideoFrameSync();const video=$("#videoView");video.pause();video.removeAttribute("src");video.dataset.quality="";video.load();updateVideoQualityControls();setVisualMode(isVideo?"video":"frames");applyReaderLayout();syncReaderPanels();scheduleTopbarContentAlignment();scheduleMediaStageSize();
}
function setVisualMode(mode){
  visualMode=mode;const isVideo=bookHasVideo();$("#pagePanel").dataset.visualMode=mode;$("#pageImage").classList.toggle("hidden",mode==="video");$("#videoView").classList.toggle("hidden",mode!=="video");
  if(isVideo&&mode==="video"){updateVideoQualityControls();if(!$("#videoView").currentSrc)switchVideoQuality(videoQuality,false);else playVideoView();}else{clearVideoLoadingTimers();hideVideoStatus();stopVideoFrameSync();$("#videoView").pause();$("#pagePanel").classList.remove("video-ready");}
  scheduleMediaStageSize();
}

function activeMediaAspectRatio(){
  if(visualMode==="video"&&bookHasVideo()){const video=$("#videoView");if(video.videoWidth&&video.videoHeight)return video.videoWidth/video.videoHeight;}
  const image=$("#pageImage");if(image.naturalWidth&&image.naturalHeight)return image.naturalWidth/image.naturalHeight;
  return bookHasVideo()?16/9:3/4;
}
function updateMediaStageSize(){
  mediaStageResizeFrame=null;const panel=$("#pagePanel"),stage=$("#mediaStage");if(!panel||!stage||panel.classList.contains("hidden"))return;
  if(!panel.classList.contains("has-video")){stage.style.width="";stage.style.aspectRatio="";return;}
  const ratio=Math.max(.35,Math.min(4,activeMediaAspectRatio())),available=Math.max(180,panel.clientWidth||stage.parentElement?.clientWidth||innerWidth*.25);
  const effectiveStack=readerLayout==="stack"||innerWidth<=950,maxHeight=effectiveStack?Math.min(innerHeight*.44,540):Math.min(innerHeight*.72,720);
  const width=Math.max(160,Math.min(available,maxHeight*ratio));stage.style.width=`${Math.round(width)}px`;stage.style.aspectRatio=String(ratio);stage.style.setProperty("--media-ratio",String(ratio));
}
function scheduleMediaStageSize(){if(mediaStageResizeFrame!==null)cancelAnimationFrame(mediaStageResizeFrame);mediaStageResizeFrame=requestAnimationFrame(()=>requestAnimationFrame(updateMediaStageSize));}
function setImportType(type){$$('[data-import-type]').forEach(button=>button.classList.toggle('active',button.dataset.importType===type));$("#booksImportPane").classList.toggle("hidden",type!=="books");$("#videoImportPane").classList.toggle("hidden",type!=="video");$("#youtubeImportPane").classList.toggle("hidden",type!=="youtube");}
function videoNameWithoutExtension(name){return name.replace(/\.[^.]+$/,'').replace(/[._-]+/g,' ').trim();}
function handleVideoFileSelected(){const file=$("#videoFile").files[0];if(!file)return;const derived=videoNameWithoutExtension(file.name);if(!$("#videoEnglishTitle").value)$("#videoEnglishTitle").value=derived;if(!$("#videoTitle").value||!videoTitleManuallyEdited)$("#videoTitle").value=$("#videoEnglishTitle").value||derived;}
function syncVideoChineseTitle(){if(!videoTitleManuallyEdited)$("#videoTitle").value=$("#videoEnglishTitle").value;}
function setVideoOverallProgress(percent,step,message=''){const value=Math.max(0,Math.min(100,Math.round(percent)));$("#videoUploadBar").value=value;$("#videoUploadPercent").textContent=`${value}%`;$("#videoUploadStep").textContent=step;if(message)$("#videoUploadMessage").textContent=message;}
function uploadPart(uploadId,kind,file,baseProgress,span){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST",`/api/import/video/upload/${uploadId}?kind=${kind}`);xhr.upload.onprogress=event=>{if(event.lengthComputable)setVideoOverallProgress(baseProgress+event.loaded/event.total*span,kind==='video'?'上传媒体文件':'上传字幕','文件上传只是第一阶段，完成后将继续后台处理。');};xhr.onload=()=>xhr.status<300?resolve():reject(new Error(JSON.parse(xhr.responseText||'{}').error||'上传失败'));xhr.onerror=()=>reject(new Error('网络上传失败'));xhr.send(file);});}
async function startVideoImport(event){event.preventDefault();const video=$("#videoFile").files[0],subtitle=$("#videoSubtitle").files[0];if(!video)return;const isAudio=video.type.startsWith("audio/")||/\.(mp3|m4a|wav|flac|aac|ogg|opus)$/i.test(video.name),series=$("#videoSeries").value.trim();if(!series){$("#videoSeries").setCustomValidity("请选择历史标签或输入新标签");$("#videoSeries").reportValidity();return;}$("#videoSeries").setCustomValidity("");clearInterval(videoImportPollTimer);$("#videoUploadProgress").classList.remove("hidden");setVideoOverallProgress(0,"创建上传任务",isAudio?"总体进度包含上传、Whisper、SaT断句、CTC对齐和数据库写入。":"总体进度包含上传、音频提取、关键帧、Whisper、SaT断句、CTC对齐和数据库写入。");try{const englishTitle=$("#videoEnglishTitle").value.trim();const chineseTitle=$("#videoTitle").value.trim()||englishTitle;if(!$("#videoTitle").value.trim())$("#videoTitle").value=chineseTitle;const payload={title:chineseTitle,englishTitle,series,level:$("#videoLevel").value,subtitleStrategy:$("#videoSubtitleStrategy").value,videoFilename:video.name,subtitleFilename:subtitle?.name||""};const request=await postImportRequest("/api/import/video/init",payload);if(request.cancelled)return;const {response:initResponse,data:init}=request;if(!initResponse.ok)throw new Error(init.error||"无法创建上传");await uploadPart(init.uploadId,"video",video,1,subtitle?17:19);if(subtitle)await uploadPart(init.uploadId,"subtitle",subtitle,18,2);setVideoOverallProgress(20,"创建后台处理任务","文件上传完成，后台处理即将开始。");const doneResponse=await fetch(`/api/import/video/complete/${init.uploadId}`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});const done=await doneResponse.json();if(!doneResponse.ok)throw new Error(done.error||"无法开始导入");rememberImportTracking("video",[done.jobId]);refreshPendingImportJobs();pollVideoImport(done.jobId);}catch(error){clearInterval(videoImportPollTimer);setVideoOverallProgress($("#videoUploadBar").value,"媒体导入失败",error.message);}}
function pollVideoImport(jobId){clearInterval(videoImportPollTimer);$("#videoUploadProgress").classList.remove("hidden");const check=async()=>{try{const response=await fetch(`/api/import/jobs/${jobId}`,{cache:'no-store'}),job=await response.json();if(!response.ok)throw new Error(job.error||'无法读取任务');const overall=20+(job.progress||0)*.8;setVideoOverallProgress(overall,job.step||job.status,job.error||`后台处理中：${job.progress||0}%`);if(job.status==='complete'||job.status==='failed'){clearInterval(videoImportPollTimer);videoImportPollTimer=null;forgetImportTracking("video");refreshPendingImportJobs();if(job.status==='complete'){setVideoOverallProgress(100,'媒体导入完成','音频、正文、SaT断句、词级时间轴和SQLite数据均已完成；视频文件还包含关键帧。');const data=await fetch('/api/library',{cache:'no-store'}).then(r=>r.json());libraryBooks=data.books||[];populateVideoSeriesOptions();setupSeriesSelector();renderLibrary();await loadImportCatalog();}else setVideoOverallProgress(overall,'媒体导入失败',job.error||'后台任务失败');}}catch(error){clearInterval(videoImportPollTimer);videoImportPollTimer=null;setVideoOverallProgress($("#videoUploadBar").value,'进度查询失败',error.message);}};check();videoImportPollTimer=setInterval(check,1000);}

function setYoutubeProgress(percent,step,message=''){const value=Math.max(0,Math.min(100,Math.round(percent)));$("#youtubeBar").value=value;$("#youtubePercent").textContent=`${value}%`;$("#youtubeStep").textContent=step;if(message)$("#youtubeMessage").textContent=message;}
async function analyzeYoutubeUrl(){const url=$("#youtubeUrl").value.trim();if(!url)return;$("#analyzeYoutubeBtn").disabled=true;$("#youtubeProgress").classList.remove("hidden");setYoutubeProgress(1,"解析 YouTube 地址","正在读取标题、频道、时长和中英文字幕信息。");try{const response=await fetch('/api/import/youtube/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})}),data=await response.json();if(!response.ok)throw new Error(data.error||'解析失败');youtubeInfo=data;$("#youtubeThumbnail").src=data.thumbnail||'';$("#youtubeChannel").textContent=data.channel||'YouTube';$("#youtubeAutoSeries").textContent=data.series||data.channel||'YouTube';$("#youtubePreviewTitle").textContent=data.title;const english=data.hasEnglishSubtitles?'人工英文':data.hasEnglishAutoCaptions?'自动英文':'无英文字幕，将使用Whisper',chinese=data.hasChineseSubtitles?(data.chineseSubtitleTranslated?'自动翻译中文':data.chineseSubtitleSource==='manual'?'人工中文':'自动中文'):'无中文字幕';$("#youtubeMeta").textContent=`${fmt(data.duration||0)} · ${english} · ${chinese}`;$("#youtubePreview").classList.remove("hidden");$("#youtubeEnglishTitle").value=data.title;youtubeTitleManuallyEdited=false;$("#youtubeTitle").value=data.title;$("#startYoutubeImport").disabled=false;setYoutubeProgress(3,"解析完成",`将自动归入“${data.series||data.channel||'YouTube'}”，确认标题后开始下载。`);}catch(error){youtubeInfo=null;$("#youtubeAutoSeries").textContent='解析地址后自动识别';$("#startYoutubeImport").disabled=true;setYoutubeProgress(0,"解析失败",error.message);}finally{$("#analyzeYoutubeBtn").disabled=false;}}
async function startYoutubeImport(event){event.preventDefault();if(!youtubeInfo)return;clearInterval(youtubePollTimer);$("#youtubeProgress").classList.remove("hidden");setYoutubeProgress(1,"创建 YouTube 导入任务",`将自动归入“${youtubeInfo.series||youtubeInfo.channel||'YouTube'}”。`);try{const payload={url:youtubeInfo.webpageUrl||$("#youtubeUrl").value,title:$("#youtubeTitle").value.trim()||youtubeInfo.title,englishTitle:$("#youtubeEnglishTitle").value.trim()||youtubeInfo.title,level:$("#youtubeLevel").value.trim(),videoId:youtubeInfo.id,channel:youtubeInfo.channel};const request=await postImportRequest('/api/import/youtube',payload);if(request.cancelled)return;const {response,data}=request;if(!response.ok)throw new Error(data.error||'无法开始导入');rememberImportTracking("youtube",[data.jobId]);refreshPendingImportJobs();pollYoutubeImport(data.jobId);}catch(error){setYoutubeProgress($("#youtubeBar").value,'YouTube 导入失败',error.message);}}
function pollYoutubeImport(jobId){clearInterval(youtubePollTimer);$("#youtubeProgress").classList.remove("hidden");const check=async()=>{try{const response=await fetch(`/api/import/jobs/${jobId}`,{cache:'no-store'}),job=await response.json();if(!response.ok)throw new Error(job.error||'无法读取任务');setYoutubeProgress(job.progress||0,job.step||job.status,job.error||youtubeProgressMessage(job));if(job.status==='complete'||job.status==='failed'){clearInterval(youtubePollTimer);youtubePollTimer=null;forgetImportTracking("youtube");refreshPendingImportJobs();if(job.status==='complete'){setYoutubeProgress(100,'YouTube 导入完成','视频、字幕、音频、关键帧、词级时间轴和SQLite数据均已完成。');const data=await fetch('/api/library',{cache:'no-store'}).then(r=>r.json());libraryBooks=data.books||[];populateVideoSeriesOptions();setupSeriesSelector();renderLibrary();}else setYoutubeProgress(job.progress||0,'YouTube 导入失败',job.error||'任务失败');}}catch(error){clearInterval(youtubePollTimer);youtubePollTimer=null;setYoutubeProgress($("#youtubeBar").value,'进度查询失败',error.message);}};check();youtubePollTimer=setInterval(check,1000);}
function youtubeProgressMessage(job){if((job.progress||0)<25)return '正在下载最高720p视频、英文字幕和缩略图。';return `YouTube下载已完成，正在复用视频处理流程：${job.progress||0}%`;}

function wordTarget(node){return node?.nodeType===1?node.closest?.(".word"):null;}
function hideWordHoverMeaning(){
  clearTimeout(wordHoverMeaningTimer);wordHoverMeaningTimer=null;wordHoverMeaningElement=null;wordHoverMeaningRequestId++;
  const tip=$("#wordHoverMeaning");tip.classList.add("hidden");tip.textContent="";
}
function positionWordHoverMeaning(element){
  const tip=$("#wordHoverMeaning"),rect=element.getBoundingClientRect();
  const left=Math.min(innerWidth-tip.offsetWidth-12,Math.max(12,rect.left+(rect.width-tip.offsetWidth)/2));
  const top=Math.max(12,rect.top-tip.offsetHeight-10);
  tip.style.left=`${left}px`;tip.style.top=`${top}px`;
}
function showWordHoverMeaning(element,entries){
  if(wordHoverMeaningElement!==element||!element.isConnected||!readerIsVisible())return;
  const tip=$("#wordHoverMeaning");tip.innerHTML=`<b>${escapeHtml(element.textContent.trim())}</b><span>${entries.map(escapeHtml).join("；")}</span>`;
  tip.classList.remove("hidden");positionWordHoverMeaning(element);
}
function scheduleWordHoverMeaning(element){
  if(isCompactTouchLayout())return;
  clearTimeout(wordHoverMeaningTimer);const word=element.textContent.trim();if(!word)return;
  wordHoverMeaningElement=element;const requestId=++wordHoverMeaningRequestId,key=word.toLowerCase();
  wordHoverMeaningTimer=setTimeout(async()=>{
    if(wordHoverMeaningElement!==element||requestId!==wordHoverMeaningRequestId||!readerIsVisible())return;
    const cached=wordHoverMeaningCache.get(key);if(cached){showWordHoverMeaning(element,cached);return;}
    showWordHoverMeaning(element,["查询中…"]);
    try{
      const response=await fetch(`/api/word-hover?word=${encodeURIComponent(word)}`,{cache:"no-store"});const data=await response.json();
      if(!response.ok)throw new Error(data.error||"查询失败");
      const entries=(data.entries||[]).filter(Boolean);if(entries.length)wordHoverMeaningCache.set(key,entries);
      if(requestId===wordHoverMeaningRequestId&&entries.length)showWordHoverMeaning(element,entries);
    }catch{if(requestId===wordHoverMeaningRequestId)hideWordHoverMeaning();}
  },WORD_HOVER_MEANING_DELAY_MS);
}
function cancelWordResume(){clearTimeout(wordResumeTimer);wordResumeTimer=null;}
function cancelMainAudioFade(restoreVolume=false){
  mainAudioFadeToken++;
  if(mainAudioFadeFrame!==null)cancelAnimationFrame(mainAudioFadeFrame);
  mainAudioFadeFrame=null; mainAudioFadeTarget=null;
  if(restoreVolume){
    const audio=$("#audio");
    if(audio)audio.volume=mainAudioRestoreVolume;
  }
}
function fadeMainAudio(target,duration,onComplete){
  const audio=$("#audio");
  cancelMainAudioFade();
  const token=mainAudioFadeToken;
  const startVolume=audio.volume;
  const startedAt=performance.now();
  mainAudioFadeTarget=target;
  const step=now=>{
    if(token!==mainAudioFadeToken)return;
    const progress=Math.min(1,(now-startedAt)/duration);
    const eased=progress*(2-progress);
    audio.volume=startVolume+(target-startVolume)*eased;
    if(progress<1){mainAudioFadeFrame=requestAnimationFrame(step);return;}
    mainAudioFadeFrame=null; mainAudioFadeTarget=null; audio.volume=target;
    onComplete?.();
  };
  mainAudioFadeFrame=requestAnimationFrame(step);
}
function resetWordHoverSession(){
  cancelWordResume();
  hideWordHoverMeaning();
  cancelMainAudioFade(true);
  pausedForWord=false; hoverPausedTime=null; hoverPausedSentence=-1;
  clickedWordPausedMain=false; clickedWordResumeTime=null; clickedWordResumeSentence=-1;
  wordTtsAudio?.pause();
}
function scheduleWordResume(){
  if(!pausedForWord&&!clickedWordPausedMain)return;
  cancelWordResume();
  wordResumeTimer=setTimeout(resumeBookAfterWordHover,WORD_RESUME_DELAY_MS);
}
function resumeBookAfterWordHover(){
  wordResumeTimer=null;
  if(!pausedForWord&&!clickedWordPausedMain)return;
  const resumeTime=clickedWordPausedMain ? clickedWordResumeTime : hoverPausedTime;
  const resumeSentence=clickedWordPausedMain ? clickedWordResumeSentence : hoverPausedSentence;
  pausedForWord=false;
  clickedWordPausedMain=false; clickedWordResumeTime=null; clickedWordResumeSentence=-1;
  hoverPausedTime=null; hoverPausedSentence=-1;
  wordTtsAudio?.pause();
  if(resumeTime===null||resumeTime===undefined)return;
  const audio=$("#audio");
  cancelMainAudioFade();
  audio.volume=0;
  let playback;
  if(resumeSentence>=0&&book?.sentences?.[resumeSentence]){
    const stopAt=sentenceAutoPause?book.sentences[resumeSentence].end+.03:null;
    playback=seekAndPlay(resumeTime,stopAt);
  }else playback=seekAndPlay(resumeTime,null);
  playback.then(()=>{
    if(!pausedForWord&&!clickedWordPausedMain&&!audio.paused)fadeMainAudio(mainAudioRestoreVolume,WORD_FADE_IN_MS);
  });
}
function handleWordPointerOver(event){
  if(isCompactTouchLayout())return;
  const word=wordTarget(event.target),from=wordTarget(event.relatedTarget);
  if(!word||from===word)return;
  hideWordHoverMeaning();scheduleWordHoverMeaning(word);
  cancelWordResume();
  if(mode!=="intensive")return;
  if(!$("#audio").paused&&!pausedForWord){
    const audio=$("#audio");
    if(mainAudioFadeTarget===null||mainAudioFadeTarget<=audio.volume)mainAudioRestoreVolume=audio.volume;
    else mainAudioRestoreVolume=mainAudioFadeTarget;
    pausedForWord=true;hoverPausedTime=audio.currentTime;hoverPausedSentence=active;
    clearTimeout(audioStopTimer);
    cancelMainAudioFade();
    audio.volume=0;
    audio.pause();
  }
}
function handleWordPointerOut(event){
  if(isCompactTouchLayout())return;
  const word=wordTarget(event.target),to=wordTarget(event.relatedTarget);
  if(word&&to!==word)hideWordHoverMeaning();
  if(!word||to===word||to)return;
  if(!pausedForWord&&!clickedWordPausedMain)return;
  scheduleWordResume();
}
function handleWordPanelAction(event){
  if(event.target.closest("[data-close-focus-panel]")){closeMobileDetailPanels();document.body.classList.remove("focus-word-open");syncReaderPanels();return;}
  const tab=event.target.closest("[data-word-panel-tab]")?.dataset.wordPanelTab;
  if(tab==="grammar"&&selectedGrammarSentence){showSentenceGrammar(selectedGrammarSentence);return;}
  if(tab==="word"&&selectedWordContext){const item=selectedWordContext;showWord(item.word,item.sentence,item.element);return;}
  const action=event.target.closest("[data-panel-word-action]")?.dataset.panelWordAction;
  if(action){openWordEditor(action);return;}
  const editAction=event.target.closest("[data-word-edit]")?.dataset.wordEdit;
  if(editAction==="save")saveWordEdit(event);else if(editAction==="cancel")closeWordEditor(event);
}
function openWordEditor(mode){
  if(!selectedWordContext||mode!=="note")return;const editor=$("#wordPanelEditor"),input=$("#wordPanelEditValue");
  $("#wordPanelEditTitle").textContent="添加备注";
  input.placeholder="输入简短备注";input.value=selectedWordContext.note||"";
  editor.classList.remove("hidden");setTimeout(()=>input.focus(),0);
}
function closeWordEditor(event){event?.preventDefault();$("#wordPanelEditor")?.classList.add("hidden");scheduleReaderShortcutFocus();}
async function saveWordEdit(event){
  event.preventDefault();const value=$("#wordPanelEditValue")?.value.trim();if(!value||!selectedWordContext)return;const c=selectedWordContext;
  if(saasReaderContext?.kind==="workspace"){const payload={original_word:c.word,corrected_word:"",note:value},response=await fetch("/api/workspace/annotations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:currentBookId,sentenceId:c.sentence.id,wordIndex:c.wordIndex,payload})});if(!response.ok)return;const key=wordRecordKey(c.sentence.id,c.wordIndex),record={...payload,book_id:currentBookId,sentence_id:c.sentence.id,word_index:c.wordIndex},existing=annotationIndex.get(key);if(existing)Object.assign(existing,record);else wordAnnotations.push(record);annotationIndex.set(key,existing||record);c.note=value;closeWordEditor();refreshWordMarks();showWord(c.word,c.sentence,c.element);return;}
  const payload={bookId:currentBookId,sentenceId:c.sentence.id,wordIndex:c.wordIndex,note:value};
  const response=await fetch("/api/word-annotation",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(!response.ok)return;
  const result=await response.json(),key=wordRecordKey(c.sentence.id,c.wordIndex),existing=annotationIndex.get(key),record={book_id:currentBookId,sentence_id:c.sentence.id,word_index:c.wordIndex,original_word:result.originalWord,corrected_word:result.correctedWord,note:result.note};
  if(existing)Object.assign(existing,record);else wordAnnotations.push(record);annotationIndex.set(key,existing||record);c.note=value;closeWordEditor();refreshWordMarks();showWord(c.word,c.sentence,c.element);scheduleReaderShortcutFocus();
}
async function addSelectedWordToVocab(){const c=selectedWordContext,d=c.definition,payload={book_id:currentBookId,sentence_id:c.sentence.id,word_index:c.wordIndex,word:c.word,root:d.root,phonetic:d.phonetic,meaning:d.meaning,context:focusedWordContext(c.sentence.text,c.wordIndex),note:c.note||"",rating:"unknown",interval_days:1,due_at:new Date(Date.now()+86400000).toISOString()};if(saasReaderContext?.kind==="workspace"){const response=await fetch("/api/workspace/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:currentBookId,sentenceId:c.sentence.id,wordIndex:c.wordIndex,payload:workspaceVocabularyPayload(payload)})});if(response.ok){const saved=normalizeWorkspaceVocabulary(await response.json()),index=vocabItems.findIndex(item=>item.id===saved.id);if(index>=0)vocabItems[index]=saved;else vocabItems.push(saved);vocabLoaded=true;rebuildWordIndexes();refreshWordMarks();refreshDashboards();}return;}const r=await fetch("/api/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(r.ok){vocabItems=(await r.json()).items||[];vocabLoaded=true;rebuildWordIndexes();refreshWordMarks();refreshDashboards();}}

function setShelfView(view){shelfView=view;renderLibrary();savePreference({shelfView:view});}
function savePreference(value){if(saasMode){const key="shiyue-saas-preferences",current=load(key,{});save(key,{...current,...value});return;}fetch("/api/preferences",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(value)}).catch(()=>{});}
function toggleEyeComfort(){if(!readerIsVisible())return;eyeComfort=!eyeComfort;applyEyeComfort();savePreference({eyeComfort});}
function applyEyeComfort(){const enabled=eyeComfort&&readerIsVisible();document.body.classList.toggle("eye-comfort",enabled);const button=$("#eyeComfortBtn");button.classList.toggle("active",enabled);button.setAttribute("aria-pressed",String(enabled));button.textContent=enabled?"● 护眼":"◐ 护眼";}
function keyName(event){return event.key===" "?"space":event.key.toLowerCase();}
function keyLabel(key){return key==="space"?"空格":key.length===1?key.toUpperCase():key;}
function captureShortcut(event){event.preventDefault();event.stopPropagation();const key=keyName(event);if(["shift","control","alt","meta"].includes(key))return;event.target.value=keyLabel(key);event.target.dataset.key=key;event.target.blur();}

function readerTextInput(target){
  const editable=target?.closest?.('textarea,[contenteditable="true"],input:not([type="range"]):not([type="button"]):not([type="submit"]):not([type="checkbox"]):not([type="radio"])');
  return !!editable;
}
function scheduleReaderShortcutFocus(event){
  if(!readerIsVisible())return;
  const target=event?.target;
  if(target?.closest?.('[data-panel-word-action="note"]')||readerTextInput(target))return;
  requestAnimationFrame(()=>{
    if(!readerIsVisible()||readerTextInput(document.activeElement))return;
    try{$("#reader").focus({preventScroll:true});}catch{$("#reader").focus();}
  });
}

function handleReaderShortcut(event) {
  if(!$("#vocab").classList.contains("hidden")){handleReviewShortcut(event);return;}
  if($("#reader").classList.contains("hidden") || event.metaKey || event.ctrlKey || event.altKey) return;
  if(event.target.closest("input,textarea,select,button,[contenteditable=true]")) return;
  const key=keyName(event);
  if(key==="q"){event.preventDefault();toggleSentenceAutoPause();return;}
  const action=Object.entries(shortcuts).find(([,value])=>value===key)?.[0]; if(!action)return; event.preventDefault();
  if(action==="play") { resetWordHoverSession(); clearTimeout(audioStopTimer); wordStopAt=null; $("#audio").paused ? $("#audio").play() : $("#audio").pause(); }
  if(action==="previous" && book) playSentence(Math.max(0,(active<0?0:active)-1));
  if(action==="repeat" && book) playSentence(Math.max(0,active));
  if(action==="next" && book) playSentence(Math.min(book.sentences.length-1,(active<0?-1:active)+1));
}
function toggleSentenceAutoPause(){sentenceAutoPause=!sentenceAutoPause;if(sentenceAutoPause&&active>=0)wordStopAt=book.sentences[active].end+.03;else wordStopAt=null;updateShortcutHint();savePreference({sentenceAutoPause});showReaderToast(sentenceAutoPause?"句末自动暂停：已开启":"句末自动暂停：已关闭");}
function showReaderToast(message){let toast=$("#readerToast");if(!toast){toast=document.createElement("div");toast.id="readerToast";toast.className="reader-toast ui-toast";toast.setAttribute("role","status");toast.setAttribute("aria-live","polite");document.body.append(toast);}toast.textContent=message;toast.classList.add("show");clearTimeout(toast._timer);toast._timer=setTimeout(()=>toast.classList.remove("show"),2200);}
function syncMobileBottomNav(){const nav=$("#mobileBottomNav");if(!nav)return;const visible=saasMode&&innerWidth<=767&&!readerIsVisible()&&!document.body.classList.contains("focus");nav.classList.toggle("hidden",!visible);nav.style.display=visible?"grid":"none";}

function setSettingsTab(name,persist=true){
  const available=$(`[data-settings-tab="${name}"]:not(.hidden)`);if(!available)name="general";
  $$("#settingsTabs [data-settings-tab]").forEach(tab=>{const active=tab.dataset.settingsTab===name;tab.classList.toggle("active",active);tab.setAttribute("aria-selected",String(active));tab.tabIndex=active?0:-1;});
  $$("#settings [data-settings-panel]").forEach(panel=>{const active=panel.dataset.settingsPanel===name;panel.classList.toggle("hidden",!active);panel.setAttribute("aria-hidden",String(!active));});
  syncSettingsTabVisibility();
  if(persist)save(STORE.settingsTab,name);
  if(persist&&saasMode&&!$("#settings").classList.contains("hidden"))updateRoute({tab:name});
  if(name==="deployment"&&!deploymentConfigLoaded&&!$("#settings").classList.contains("hidden"))loadDeploymentConfig().then(()=>{deploymentConfigLoaded=true;}).catch(()=>{});
}
function syncSettingsTabVisibility(){
  const tabs=$$("#settingsTabs [data-settings-tab]:not(.hidden)");
  $("#settingsTabs").classList.toggle("hidden",tabs.length<=1);
  $("#settings").classList.toggle("single-settings-tab",tabs.length<=1);
}

function updateRoute(values={},replace=false){if(!saasMode)return;const url=new URL(location.href);for(const [key,value] of Object.entries(values)){if(value===null||value==="")url.searchParams.delete(key);else url.searchParams.set(key,String(value));}const method=replace?"replaceState":"pushState";history[method]({screen:url.searchParams.get("screen")},"",url.pathname+url.search);}
function showScreen(id,route=true) {
  if(saasMode)$("#mobileBottomNav")?.classList.remove("hidden");
  if(!["catalog-reader","reader"].includes(id)&&catalogReadingSession)flushCatalogReadingActivity();
  if(!["workspace-reader","reader"].includes(id)&&workspaceReaderSession)flushWorkspaceActivity();
  closeMobileSidebar();closeMobileDetailPanels(false);
  $$(".screen").forEach(screen => screen.classList.toggle("hidden", screen.id !== id));
  $$(".nav").forEach(nav => nav.classList.toggle("active", nav.dataset.screen === id));
  const screenLabels={shelf:"我的书架",stats:"学习记录",vocab:"生词复习",import:"导入书籍",catalog:"首页·书城","my-library":"我的书架",workspace:"学习空间","workspace-reader":"学习阅读",rewards:"成长奖励",membership:"会员中心",admin:"运营后台",settings:"系统设置",reader:"阅读器","catalog-reader":"官方阅读"};$("#mobileScreenLabel").textContent=screenLabels[id]||"导航";$("#sidebarReveal").setAttribute("aria-label",`打开导航，当前：${screenLabels[id]||id}`);
  const reading = id === "reader";
  document.body.classList.toggle("screen-reader",reading);
  document.body.classList.toggle("screen-shelf",id === "shelf");
  document.body.classList.toggle("screen-dashboard",["stats","vocab","import","catalog","my-library","workspace","workspace-reader","catalog-reader","rewards","membership","admin","settings"].includes(id));
  syncMobileBottomNav();
  $(".topbar").classList.toggle("non-reader",!reading);
  $(".topbar").setAttribute("aria-hidden",String(!reading&&!isResponsiveNavLayout()&&!document.body.classList.contains("sidebar-collapsed")));
  $("#player").classList.toggle("hidden", !reading);
  $(".book-heading").style.display = reading ? "block" : "none";
  $(".top-actions").style.display = reading ? "flex" : "none";
  $("#backBtn").style.visibility = reading ? "visible" : "hidden";
  if (!reading) { hideSeekSentencePreview();resetWordHoverSession();setFocusMode(false);if(eyeComfort){eyeComfort=false;savePreference({eyeComfort:false});}applyEyeComfort();$("#audio").pause();clearTimeout(shadowTimer); }
  else {syncReaderPanels();applyEyeComfort();}
  syncReaderActionVisibility();scheduleTopbarContentAlignment();
  if(id!=="vocab")stopManualDictation();
  ensureScreenData(id);
  if(route&&saasMode){updateRoute({screen:id,reader:id==="reader"?saasReaderContext?.kind:null,id:id==="reader"?saasReaderContext?.id:null,book:null,tab:id==="admin"?adminTab:id==="settings"?load(STORE.settingsTab,"general"):null},!routeReady);routeReady=true;}
}

function openReader() {
  showScreen("reader");
  if (active < 0) {
    const saved = load(`${STORE.state}-${currentBookId}`, {}).time || book.sentences[0].start;
    const index = book.sentences.findIndex(s => saved >= s.start && saved < s.end);
    highlight(index >= 0 ? index : 0, true);
  }
  scheduleReaderShortcutFocus();
}

function setMode(nextMode) {
  hideWordHoverMeaning();
  mode = nextMode;
  $$(".mode-switch button").forEach(button => button.classList.toggle("active", button.dataset.mode === mode));
  $("#reader").dataset.mode = mode;
  $("#shadowCoach").classList.toggle("hidden", mode !== "shadow");
  syncReaderPanels();
  $("#modeHint").textContent = mode === "intensive" ? "点击句子点读，点击单词查看语境释义。" : mode === "extensive" ? "连续听完整故事，右侧保留最近查看的单词释义。" : "听一句，停下来模仿；右侧保留单词释义并可录音回放。";
  if(mode==="shadow"){
    shadowWaiting=false;shadowSentenceIndex=active>=0?active:sentenceIndexAt($("#audio").currentTime);updateShadowMicrophoneHint();
    if(!$("#audio").paused&&shadowSentenceIndex>=0)scheduleShadowSentenceStop(shadowSentenceIndex);
  }else{shadowWaiting=false;shadowSentenceIndex=-1;clearTimeout(shadowTimer);clearTimeout(audioStopTimer);}
  logAction("modes", mode);
}

function playSentence(index) {
  resetWordHoverSession();
  clearTimeout(shadowTimer);
  shadowWaiting = false;
  const recording=$("#recording");recording.pause();recording.onended=null;
  active = index;
  const sentence = book.sentences[index];
  shadowSentenceIndex=mode==="shadow"?index:-1;
  wordStopAt = mode === "shadow" || !sentenceAutoPause ? null : sentence.end + .03;
  const playback=seekAndPlay(sentence.start, mode === "shadow" || !sentenceAutoPause ? null : sentence.end + .03);
  if(mode==="shadow")playback.then(started=>{if(started&&active===index)scheduleShadowSentenceStop(index);});
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

function setVideoBaseRate(){
  const audio=$("#audio"),video=$("#videoView"),rate=Math.max(.25,Math.min(4,audio.playbackRate||1));
  video.defaultPlaybackRate=rate;
  if(audio.paused||Math.abs(video.playbackRate-rate)>VIDEO_MAX_RATE_CORRECTION*1.5)video.playbackRate=rate;
}

function syncVideoToAudio(force=false,presentedTime=null){
  if(!bookHasVideo()||visualMode!=="video")return 0;
  const audio=$("#audio"),video=$("#videoView"),baseRate=Math.max(.25,Math.min(4,audio.playbackRate||1));
  if(video.readyState<1)return 0;
  const target=Math.max(0,audio.currentTime),actual=Number.isFinite(presentedTime)?presentedTime:video.currentTime,drift=actual-target,absolute=Math.abs(drift);
  video.defaultPlaybackRate=baseRate;
  if(force||absolute>=VIDEO_HARD_SYNC_SECONDS){
    if(Math.abs(video.currentTime-target)>.008)video.currentTime=target;
    video.playbackRate=baseRate;
  }else if(audio.paused||absolute<VIDEO_SOFT_SYNC_SECONDS){
    if(Math.abs(video.playbackRate-baseRate)>.002)video.playbackRate=baseRate;
  }else{
    const limit=Math.max(.01,baseRate*VIDEO_MAX_RATE_CORRECTION),correction=Math.max(-limit,Math.min(limit,-drift*.35));
    video.playbackRate=Math.max(.25,Math.min(4,baseRate+correction));
  }
  return drift;
}

function startVideoFrameSync(){
  const video=$("#videoView");
  if(videoFrameCallbackId!==null||visualMode!=="video"||!bookHasVideo()||typeof video.requestVideoFrameCallback!=="function")return;
  const frame=(_now,metadata)=>{
    videoFrameCallbackId=null;
    if(visualMode!=="video"||$("#audio").paused||video.paused)return;
    syncVideoToAudio(false,metadata?.mediaTime);
    videoFrameCallbackId=video.requestVideoFrameCallback(frame);
  };
  videoFrameCallbackId=video.requestVideoFrameCallback(frame);
}

function stopVideoFrameSync(){
  const video=$("#videoView");
  if(videoFrameCallbackId!==null&&typeof video.cancelVideoFrameCallback==="function")video.cancelVideoFrameCallback(videoFrameCallbackId);
  videoFrameCallbackId=null;
  setVideoBaseRate();
}

function syncPlaybackFrame() {
  if(!book)return;
  const audio = $("#audio"); const time = audio.currentTime;
  const now=performance.now();
  if(audio.paused||now-lastPlaybackUiUpdate>=PLAYBACK_UI_INTERVAL_MS){$("#currentTime").textContent=fmt(time);$("#seek").value=time/book.duration*1000;lastPlaybackUiUpdate=now;}
  if(visualMode==="video"&&bookHasVideo()&&typeof $("#videoView").requestVideoFrameCallback!=="function")syncVideoToAudio(false);
  if(mode==="shadow"&&!shadowWaiting&&shadowSentenceIndex>=0){const target=book.sentences[shadowSentenceIndex];if(target&&time>=target.end-.06){finishShadowSentence(shadowSentenceIndex);return;}}
  if (wordStopAt !== null && time >= wordStopAt) { wordStopAt = null; audio.pause(); }
  const rawIndex=sentenceIndexAt(time);
  if (rawIndex >= 0 && rawIndex !== active) {
    active=rawIndex;
    prefetchBookChunks(rawIndex);
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
}

function scheduleShadowSentenceStop(index){
  if(mode!=="shadow"||shadowWaiting||index!==shadowSentenceIndex)return;
  const sentence=book.sentences[index],audio=$("#audio");clearTimeout(audioStopTimer);
  const delay=Math.max(0,(sentence.end-audio.currentTime)/Math.max(.1,audio.playbackRate)*1000);
  audioStopTimer=setTimeout(()=>finishShadowSentence(index),delay);
}
function finishShadowSentence(index){
  if(mode!=="shadow"||shadowWaiting||index!==shadowSentenceIndex)return;
  const sentence=book.sentences[index],audio=$("#audio");
  if(!audio.paused&&audio.currentTime<sentence.end-.08){scheduleShadowSentenceStop(index);return;}
  beginShadowPause(sentence,index);
}
function beginShadowPause(sentence,index=shadowSentenceIndex) {
  clearTimeout(audioStopTimer);
  shadowWaiting = true;
  const audio=$("#audio");audio.pause();
  if(audio.currentTime>sentence.end+.02)audio.currentTime=sentence.end;
  active=index;highlight(index,false);
  const pauseMs = Math.max(2200, (sentence.end - sentence.start) * 1000 * +$("#pauseRatio").value);
  $("#shadowStatus").textContent = "现在跟读";
  $("#shadowPrompt").textContent = `模仿：${sentence.text}`;
  shadowTimer = setTimeout(() => {
    shadowWaiting = false;
    if (index < book.sentences.length - 1) playSentence(index + 1);
    else $("#shadowStatus").textContent = "本书跟读完成";
  }, pauseMs);
}

function highlight(index, scroll = false) {
  active = index;
  paintSentence(index,scroll);
}
function scrollSentenceIntoView(element,behavior="smooth"){
  if(!element)return;
  const pagePanel=$("#pagePanel"),stacked=readerLayout==="stack"&&bookHasVisual()&&!document.body.classList.contains("focus")&&innerWidth>950&&!pagePanel.classList.contains("hidden");
  if(!stacked){element.scrollIntoView({behavior,block:"center"});return;}
  const pageRect=pagePanel.getBoundingClientRect(),sentenceRect=element.getBoundingClientRect();
  const safeTop=Math.min(innerHeight-190,Math.max(96,pageRect.bottom+18)),safeBottom=innerHeight-112;
  if(sentenceRect.top<safeTop||sentenceRect.bottom>safeBottom){window.scrollBy({top:sentenceRect.top-safeTop,behavior});}
}
function paintSentence(index,scroll=false){
  if(index===paintedSentenceIndex&&!scroll)return;
  sentenceElementsByIndex[paintedSentenceIndex]?.classList.remove("active");
  const element=index>=0?ensureSentenceRendered(index,false):null;
  element?.classList.add("active");paintedSentenceIndex=index;
  if(catalogReadingSession&&saasReaderContext?.kind==="official"&&index>=0)catalogReadingSession.seen.add(String(index));
  if(workspaceReaderSession&&saasReaderContext?.kind==="workspace"&&index>=0)workspaceReaderSession.seen.add(String(book.sentences[index]?.id||index));
  if(scroll&&element)scrollSentenceIntoView(element,"smooth");
}
function lastStartedIndex(items,time,getStart){let low=0,high=items.length-1,result=-1;while(low<=high){const middle=(low+high)>>1;if(getStart(items[middle])<=time){result=middle;low=middle+1;}else high=middle-1;}return result;}
function sentenceIndexAt(time){return book?.sentences?.length?lastStartedIndex(book.sentences,time,item=>item.start):-1;}
function sentenceIndexForPreview(time){
  const sentences=book?.sentences||[];
  if(!sentences.length)return -1;
  const index=sentenceIndexAt(time);
  if(index<0)return 0;
  const current=sentences[index],next=sentences[index+1];
  if(!next)return index;
  const currentEnd=Number.isFinite(+current.end)?+current.end:+current.start;
  const nextStart=Number.isFinite(+next.start)?+next.start:currentEnd;
  if(time>currentEnd&&nextStart>currentEnd&&time>=(currentEnd+nextStart)/2)return index+1;
  return index;
}
function seekTimeFromPointer(event){
  const seek=$("#seek"),rect=seek.getBoundingClientRect();
  if(!book?.duration||rect.width<=0)return 0;
  return Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*book.duration;
}
function commitSeekTime(time){
  if(!book?.duration||!Number.isFinite(time))return;
  resetWordHoverSession();
  const safeTime=Math.max(0,Math.min(book.duration,time));
  $("#audio").currentTime=safeTime;$("#seek").value=safeTime/book.duration*1000;$("#currentTime").textContent=fmt(safeTime);
  syncVideoToAudio(true);syncPlaybackFrame();
}
function showSeekSentencePreview(event){
  if(!book?.sentences?.length||!Number.isFinite(+book.duration)||+book.duration<=0)return;
  if(isCompactTouchLayout()&&!seekPreviewDragging)return;
  seekPreviewPointerX=event.clientX;
  if(seekPreviewFrame!==null)return;
  seekPreviewFrame=requestAnimationFrame(()=>{
    seekPreviewFrame=null;
    const seek=$("#seek"),preview=$("#seekSentencePreview"),rect=seek.getBoundingClientRect();
    if(rect.width<=0)return;
    const ratio=Math.max(0,Math.min(1,(seekPreviewPointerX-rect.left)/rect.width));
    const time=ratio*(+book.duration),index=sentenceIndexForPreview(time),sentence=book.sentences[index];
    if(!sentence)return hideSeekSentencePreview();
    $("#seekPreviewTime").textContent=`${fmt(time)} · 第 ${index+1} 句`;
    $("#seekPreviewText").textContent=sentence.text||"";
    preview.classList.remove("hidden");preview.setAttribute("aria-hidden","false");
    const left=Math.min(innerWidth-preview.offsetWidth-12,Math.max(12,seekPreviewPointerX-preview.offsetWidth/2));
    const top=Math.max(12,rect.top-preview.offsetHeight-10);
    preview.style.left=`${left}px`;preview.style.top=`${top}px`;
  });
}
function hideSeekSentencePreview(){
  if(seekPreviewFrame!==null){cancelAnimationFrame(seekPreviewFrame);seekPreviewFrame=null;}
  const preview=$("#seekSentencePreview");
  if(!preview)return;
  preview.classList.add("hidden");preview.setAttribute("aria-hidden","true");
}
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
  openMobileDetailPanel("word");
  if(document.body.classList.contains("focus")){document.body.classList.add("focus-word-open");syncReaderPanels();}
  selectedGrammarSentence=sentence;
  const definition = getDefinition(raw, sentence);
  const selectedIndex=+(wordElement?.dataset.wordIndex??-1),key=wordRecordKey(sentence.id,selectedIndex);
  const annotation=annotationIndex.get(key);
  const saved = vocabWordIndex.get(key);
  selectedWordContext={element:wordElement,sentence,wordIndex:selectedIndex,word:raw,definition,note:annotation?.note||""};
  const requestId=++wordRequestId;
  $("#wordPanel").innerHTML = `${wordPanelTabsHtml("word")}<div class="definition">
    <button class="speak" id="speakWord" title="播放接口发音">♪</button><span class="phonetic">${formatText(definition.phonetic)}</span><h2>${escapeHtml(raw)}</h2>
    <div id="remoteDefinition"><p class="loading-line">正在查询中文释义…</p></div>
    <div class="rating"><small>${saved ? `当前：${ratingName(saved.rating)} · 下次 ${new Date(saved.due_at).toLocaleDateString("zh-CN")}` : "加入复习并评级"}</small>
      <div class="rating-actions"><button data-rating="known">认识</button><button data-rating="fuzzy">模糊</button><button data-rating="unknown">不认识</button><button type="button" data-panel-word-action="note">▤ 备注</button></div>
    </div>
    <div id="wordPanelEditor" class="word-panel-editor hidden"><b id="wordPanelEditTitle">添加备注</b><input id="wordPanelEditValue" autocomplete="off"><div><button type="button" data-word-edit="cancel">取消</button><button type="button" data-word-edit="save">保存</button></div></div>
    ${annotation?.note?`<div class="saved-word-note"><small>我的备注</small><p>${escapeHtml(annotation.note)}</p></div>`:""}
    ${contextBlockHtml(`IN THIS STORY · 第 ${sentence.page} 页`,highlightWord(sentence.text,raw),sentence.text)}
    <div id="remoteUsage" class="usage-note"><span class="loading-line">正在分析上下文用法…</span></div>
    <div id="remoteExamples" class="dict-examples"><span class="loading-line">正在加载例句…</span></div>
    </div>`;
  $("#speakWord").onclick = () => playWordTts(raw);
  $$("#wordPanel [data-rating]").forEach(button => button.onclick = () => rateWord(raw, sentence, definition, button.dataset.rating, wordElement));
  const sentenceIndex=book.sentences.findIndex(item=>item.id===sentence.id);
  const expanded=book.sentences.slice(Math.max(0,sentenceIndex-1),sentenceIndex+2).map(item=>item.text).join(" ");
  if(saasMode){$("#remoteDefinition").innerHTML=`<p class="meaning">${formatText(definition.meaning)}</p><p>${formatText(definition.english)}</p><small class="api-source">基础释义；平台词典尚未配置</small>`;$("#remoteExamples").innerHTML='<small>例句服务尚未配置</small>';if(saasReaderContext?.kind==="workspace"){fetch("/api/word-context",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:currentBookId,sentenceId:sentence.id,wordIndex:selectedIndex})}).then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.error||"分析失败");if(requestId===wordRequestId)$("#remoteUsage").innerHTML=`${formatText(data.explanation)}<small class="api-source">语境来源：${escapeHtml(data.source||"平台 AI")}</small>`;}).catch(error=>{if(requestId===wordRequestId)$("#remoteUsage").innerHTML=`${formatText(definition.usage)}<small class="api-source">${escapeHtml(error.message||"平台 AI 尚未配置")}</small>`;});}else $("#remoteUsage").innerHTML=`${formatText(definition.usage)}<small class="api-source">官方读物暂不生成私人 AI 语境缓存</small>`;return;}
  fetch(`/api/word-dictionary?word=${encodeURIComponent(raw)}`,{cache:"no-store"}).then(async response=>{
    if(!response.ok) throw new Error((await response.json()).error || "查询失败");
    return response.json();
  }).then(data=>{
    if(requestId!==wordRequestId) return;
    const groups=(data.groups||[]).map(group=>`<div class="dict-group"><b>${escapeHtml(group.pos)}</b><p>${group.translations.map(escapeHtml).join("；")}</p></div>`).join("");
    $("#remoteDefinition").innerHTML=groups || `<p class="meaning">${formatText(definition.meaning)}</p><p>${formatText(definition.english)}</p>`;
    $("#remoteDefinition").insertAdjacentHTML("beforeend",`<small class="api-source">释义来源：${escapeHtml(displaySource(data.source||"Dioco"))}</small>`);
    $("#remoteExamples").innerHTML=(data.examples||[]).length?`<small>EXAMPLES</small>${data.examples.map(item=>`<p>${escapeHtml(item)}</p>`).join("")}`:'<small>暂无例句</small>';
  }).catch(error=>{
    if(requestId!==wordRequestId) return;
    $("#remoteDefinition").innerHTML=`<p class="meaning">${formatText(definition.meaning)}</p><p>${formatText(definition.english)}</p><small class="api-source">${escapeHtml(onlineServiceFallback(error,"词典",runtimeMode==="reader"?"内置词典":"本地词典"))}</small>`;
    $("#remoteExamples").innerHTML='<small>例句接口暂不可用</small>';
  });
  fetch("/api/word-context",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({word:raw,contextSentence:sentence.text,expandedContext:expanded})}).then(async response=>{
    if(!response.ok) throw new Error((await response.json()).error || "分析失败");
    return response.json();
  }).then(data=>{
    if(requestId!==wordRequestId) return;
    $("#remoteUsage").innerHTML=`${formatText(data.explanation||definition.usage)}<small class="api-source">语境来源：${escapeHtml(displaySource(data.source||"Dioco Lexa"))}</small>`;
  }).catch(error=>{
    if(requestId!==wordRequestId) return;
    const fallback=runtimeMode==="reader"?"语境规则":"本地语境规则";
    $("#remoteUsage").innerHTML=`${formatText(definition.usage)}<small class="api-source">${escapeHtml(onlineServiceFallback(error,"语境",fallback))}</small>`;
  });
}

function wordPanelTabsHtml(active){return `<div class="word-panel-tabs"><button type="button" data-word-panel-tab="word" class="${active==="word"?"active":""}" ${selectedWordContext?"":"disabled"}>单词释义</button><button type="button" data-word-panel-tab="grammar" class="${active==="grammar"?"active":""}" ${selectedGrammarSentence?"":"disabled"}>句子语法</button><button type="button" class="focus-panel-close" data-close-focus-panel title="关闭释义栏" aria-label="关闭释义栏">×</button></div>`;}
function grammarTokenHtml(tokens){
  let html="";(tokens||[]).forEach((token,index)=>{const punctuation=token.role==="punctuation";if(index&&!punctuation&&!/^[’']/.test(token.text))html+=" ";html+=`<span class="grammar-token grammar-${escapeHtml(token.role)}" title="${escapeHtml(token.posZh||token.pos)} · ${escapeHtml(token.relation||"")}">${escapeHtml(token.text)}</span>`;});return html;
}
function grammarAnalysisHtml(data,loadingExplanation=false){
  const clauses=(data.clauses||[]).map(item=>`<li><b>${escapeHtml(item.type)}</b><span>${escapeHtml(item.text)}</span>${item.marker?`<small>引导词：${escapeHtml(item.marker)}</small>`:""}</li>`).join("");
  const points=(data.grammarPoints||[]).map(item=>`<span>${escapeHtml(item)}</span>`).join("");
  const explanation=data.aiExplanation||data.explanation||"";
  return `${wordPanelTabsHtml("grammar")}<div class="grammar-analysis"><small class="grammar-source">SENTENCE GRAMMAR · ${escapeHtml(displaySource(data.source||(runtimeMode==="reader"?"句法模型":"本地模型")))}</small><h2>${escapeHtml(data.sentenceType||"句法分析")}</h2><div class="grammar-colored-sentence">${grammarTokenHtml(data.tokens)}</div><div class="grammar-legend"><span class="grammar-subject">主语</span><span class="grammar-predicate">谓语</span><span class="grammar-object">宾语/补语</span><span class="grammar-clause">从句</span></div><section><small>基本句型</small><b>${escapeHtml(data.pattern||"")}</b></section><div class="grammar-core"><p><small>主语</small>${escapeHtml(data.subject||"")}</p><p><small>谓语</small>${escapeHtml(data.predicate||"")}</p>${data.object?`<p><small>宾语 / 补语</small>${escapeHtml(data.object)}</p>`:""}</div>${clauses?`<section class="grammar-clauses"><small>从句结构</small><ul>${clauses}</ul></section>`:""}${points?`<section><small>语法重点</small><div class="grammar-points">${points}</div></section>`:""}<section class="grammar-explanation"><small>中文讲解</small><p id="grammarExplanation">${formatText(explanation)}</p>${loadingExplanation?'<i>正在结合句法结构生成更自然的中文讲解…</i>':''}</section><details class="grammar-tree"><summary>查看成分句法树</summary><pre>${escapeHtml(data.constituency||"")}</pre></details></div>`;
}
async function showSentenceGrammar(sentence){
  openMobileDetailPanel("word");
  selectedGrammarSentence=sentence;if(document.body.classList.contains("focus")){document.body.classList.add("focus-word-open");syncReaderPanels();}
  const requestId=++grammarRequestId;$("#wordPanel").innerHTML=`${wordPanelTabsHtml("grammar")}<div class="grammar-analysis"><span class="loading-line">正在读取本地句法分析…</span></div>`;
  try{
    const payload={bookId:currentBookId,sentenceId:sentence.id};const response=await fetch("/api/sentence-grammar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok)throw new Error(data.error||"语法分析失败");if(requestId!==grammarRequestId)return;
    $("#wordPanel").innerHTML=grammarAnalysisHtml(data,!data.aiExplanation);
    if(!data.aiExplanation){fetch("/api/sentence-grammar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...payload,enhance:true})}).then(result=>result.ok?result.json():null).then(enhanced=>{if(enhanced&&requestId===grammarRequestId)$("#wordPanel").innerHTML=grammarAnalysisHtml(enhanced,false);}).catch(()=>{});}
  }catch(error){if(requestId===grammarRequestId)$("#wordPanel").innerHTML=`${wordPanelTabsHtml("grammar")}<div class="word-empty"><span>句</span><h3>暂时无法分析</h3><p>${escapeHtml(error.message)}</p></div>`;}
}

function highlightWord(sentence, word) {
  const safe = wordHtml(sentence);
  return safe.replace(new RegExp(`(<span class="word">)${escapeRegExp(word)}(</span>)`, "i"), `$1<em>${escapeHtml(word)}</em>$2`);
}
function contextBlockHtml(label,contentHtml,plainText){
  const text=plainText||"",long=text.length>260||(text.match(/[A-Za-z]+(?:['’][A-Za-z]+)?|\d+/g)||[]).length>45;
  return `<div class="context${long?' context-collapsible is-collapsed':''}"><small>${escapeHtml(label)}</small><p class="context-text">${contentHtml}</p>${long?'<button type="button" class="context-toggle" data-context-toggle aria-expanded="false">展开全文</button>':''}</div>`;
}
function handleContextToggle(event){
  const button=event.target.closest("[data-context-toggle]");if(!button)return;
  const context=button.closest(".context-collapsible");if(!context)return;
  const expanded=context.classList.toggle("is-expanded");context.classList.toggle("is-collapsed",!expanded);
  button.textContent=expanded?"收起":"展开全文";button.setAttribute("aria-expanded",String(expanded));
}
function escapeRegExp(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
function speak(word) { speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(word); utterance.lang = "en-US"; utterance.rate = .78; speechSynthesis.speak(utterance); }
async function playWordTts(word) {
  if(saasMode){speak(word);return;}
  try {
    wordTtsAudio?.pause();
    wordTtsAudio=new Audio(`/api/word-tts?word=${encodeURIComponent(word)}`);
    await wordTtsAudio.play();
  } catch { speak(word); }
}
async function seekAndPlay(time, stopAt=null) {
  const audio=$("#audio");
  const token=++playbackRequestToken;
  clearTimeout(audioStopTimer);audioStopTimer=null;
  const current=()=>token===playbackRequestToken;
  const waitFor=(events,timeout)=>new Promise((resolve,reject)=>{
    let settled=false;
    const cleanup=()=>{events.forEach(name=>audio.removeEventListener(name,onReady));audio.removeEventListener("error",onError);clearTimeout(timer);};
    const finish=callback=>{if(settled)return;settled=true;cleanup();callback();};
    const onReady=()=>finish(resolve),onError=()=>finish(()=>reject(audio.error||new Error("音频加载失败")));
    events.forEach(name=>audio.addEventListener(name,onReady,{once:true}));audio.addEventListener("error",onError,{once:true});
    const timer=setTimeout(()=>finish(resolve),timeout);
  });
  try{
    if(audio.readyState<1){const metadata=waitFor(["loadedmetadata"],5000);if(audio.readyState>=1)audio.dispatchEvent(new Event("loadedmetadata"));await metadata;}
    if(!current())return false;
    audio.pause();
    const duration=Number.isFinite(audio.duration)&&audio.duration>0?audio.duration:time;
    audio.currentTime=Math.max(0,Math.min(duration,time));
    if(audio.seeking){await waitFor(["seeked","canplay"],2500);if(!current())return false;}
    let lastError=null;
    for(let attempt=0;attempt<2;attempt++){
      if(!current())return false;
      try{await audio.play();lastError=null;break;}
      catch(error){
        lastError=error;
        if(!current())return false;
        if(error?.name!=="AbortError"||attempt===1)break;
        await waitFor(["seeked","canplay","canplaythrough"],350);
      }
    }
    if(lastError)throw lastError;
    if(!current())return false;
    if(stopAt!==null){
      const delay=Math.max(0,(stopAt-audio.currentTime)/Math.max(.1,audio.playbackRate)*1000);
      audioStopTimer=setTimeout(()=>{if(current()){audio.pause();wordStopAt=null;}},delay);
    }
    return true;
  }catch(error){
    if(!current())return false;
    console.warn("句子音频启动失败",error);
    showReaderToast(error?.name==="NotAllowedError"?"浏览器阻止了播放，请先点击一次播放键":"音频启动失败，请再按一次快捷键");
    return false;
  }
}
function ratingName(rating) { return ({ known:"认识", fuzzy:"模糊", unknown:"不认识" })[rating]; }

async function rateWord(raw, sentence, definition, rating, wordElement) {
  const previous=vocabWordIndex.get(wordRecordKey(sentence.id,+(wordElement?.dataset.wordIndex??-1)));
  const intervals = { known:7, fuzzy:3, unknown:1 };
  const base = intervals[rating];
  const nextInterval = rating === "known" && previous ? Math.min(60, Math.max(base, (previous.interval_days || base) * 2)) : base;
  const wordIndex=+(wordElement?.dataset.wordIndex??0);const payload={book_id:currentBookId,sentence_id:sentence.id,word_index:wordIndex,word:raw,root:definition.root,phonetic:definition.phonetic,meaning:definition.meaning,context:focusedWordContext(sentence.text,wordIndex),rating,interval_days:nextInterval,due_at:new Date(Date.now()+nextInterval*86400000).toISOString()};
  if(saasReaderContext?.kind==="workspace"){const response=await fetch("/api/workspace/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:currentBookId,sentenceId:sentence.id,wordIndex,payload:workspaceVocabularyPayload(payload)})});if(response.ok){const saved=normalizeWorkspaceVocabulary(await response.json()),index=vocabItems.findIndex(item=>item.id===saved.id);if(index>=0)vocabItems[index]=saved;else vocabItems.push(saved);vocabLoaded=true;rebuildWordIndexes();}refreshWordMarks();showWord(raw,sentence,wordElement);refreshDashboards();return;}
  const response=await fetch("/api/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(response.ok){vocabItems=(await response.json()).items||[];vocabLoaded=true;rebuildWordIndexes();}refreshWordMarks();showWord(raw,sentence,wordElement);refreshDashboards();
}

function refreshDashboards(){if(!$("#stats").classList.contains("hidden"))renderStats();if(vocabLoaded&&!$("#vocab").classList.contains("hidden"))renderReview();}

function learningStreak(){const days=new Set(learningDays.filter(item=>(item.reading_seconds||0)>0||(item.sentences||0)>0||(item.lookups||0)>0).map(item=>item.day));let streak=0,date=new Date();date.setHours(0,0,0,0);while(days.has(localDateKey(date))){streak++;date.setDate(date.getDate()-1);}return streak;}
async function renderStats() {
  if(saasMode){const readingSeconds=workspaceBooks.reduce((sum,item)=>sum+(item.progress?.readingSeconds||0),0),completed=workspaceBooks.filter(item=>item.progress?.completedAt).length,due=vocabItems.filter(item=>new Date(item.due_at)<=new Date()).length,streak=learningStreak(),continueBook=workspaceBooks.filter(item=>(item.progress?.readingSeconds||0)>0&&!item.progress?.completedAt).sort((a,b)=>(b.progress?.lastReadAt||"").localeCompare(a.progress?.lastReadAt||""))[0]||workspaceBooks[0];$("#statsContent").innerHTML=`<div class="metric-grid"><article><small>私人读物</small><b>${workspaceBooks.length}</b><p>仅统计当前账号</p></article><article><small>累计听读</small><b>${Math.round(readingSeconds/60)}</b><p>分钟</p></article><article><small>连续学习</small><b>${streak}</b><p>天</p></article><article><small>已学单词</small><b>${vocabItems.length}</b><p>${due} 个待复习</p></article></div><section class="stats-next-step panel"><div><small>NEXT STEP</small><h3>${continueBook?`继续：${escapeHtml(continueBook.title)}`:"开始第一次学习"}</h3><p>${continueBook?"保持今天的学习节奏，回到上次阅读位置。":"导入一本读物或从书城选择一篇官方内容。"}</p></div>${continueBook?`<button type="button" data-stats-continue="${escapeHtml(continueBook.id)}">继续阅读 →</button>`:`<button type="button" data-stats-go-workspace>去学习空间 →</button>`}</section><div class="panel"><div class="heatmap-head"><h3>学习热力图</h3><div class="heatmap-ranges"><button data-heatmap-range="year">年</button><button data-heatmap-range="quarter">季度</button><button data-heatmap-range="month">月</button><button data-heatmap-range="week">周</button></div></div><p id="heatmapPeriod" class="heatmap-period"></p><div id="studyHeatmap" class="study-heatmap"></div><div class="heatmap-legend"><span>少</span><i></i><i></i><i></i><i></i><i></i><span>多</span></div></div>`;renderHeatmap();return;}
  const state=book?load(`${STORE.state}-${currentBookId}`,{}):{};const vocab=vocabItems;
  const percent=book?.duration?Math.round((state.time||0)/book.duration*100):0;
  $("#statsContent").innerHTML = `<div class="metric-grid">
    <article><small>当前读物进度</small><b>${percent}%</b><p>${book?`${fmt(state.time||0)} / ${fmt(book.duration)}`:"尚未打开读物"}</p></article>
    <article><small>累计听读</small><b>${Math.round((state.secondsRead || 0) / 60)}</b><p>分钟</p></article>
    <article><small>已学单词</small><b>${vocab.length}</b><p>${vocab.filter(v => new Date(v.due_at)<=new Date()).length} 个待复习</p></article>
    <article><small>剧情选择</small><b>${state.branches || 0}</b><p>次主动选择</p></article>
  </div><div class="panel"><div class="heatmap-head"><h3>学习热力图</h3><div class="heatmap-ranges"><button data-heatmap-range="year">年</button><button data-heatmap-range="quarter">季度</button><button data-heatmap-range="month">月</button><button data-heatmap-range="week">周</button></div></div><p id="heatmapPeriod" class="heatmap-period"></p><div id="studyHeatmap" class="study-heatmap"></div><div class="heatmap-legend"><span>少</span><i></i><i></i><i></i><i></i><i></i><span>多</span></div></div><div class="panel"><h3>学习方式</h3><div class="mode-bars">${modeBar("精读", state.modes?.intensive || 0)}${modeBar("泛听", state.modes?.extensive || 0)}${modeBar("跟读", state.modes?.shadow || 0)}</div></div>`;
  renderHeatmap();
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
function stopManualDictation(){clearTimeout(manualDictation.timer);manualDictation.timer=null;manualDictation.running=false;manualDictation.token++;manualDictation.audio?.pause();manualDictation.audio=null;wordTtsAudio?.pause();if(saasMode)speechSynthesis.cancel();}
function resetManualDictation(){stopManualDictation();manualDictation=newManualState(manualDictation.items);updateManualDictationView();}
function startManualDictation(){if(manualDictation.complete||manualDictation.index>=0)manualDictation=newManualState(manualDictation.items);manualDictation.running=true;manualDictation.index=0;startManualWord();}
function startManualWord(){if(!manualDictation.running)return;if(manualDictation.index>=manualDictation.items.length){completeManualDictation();return;}manualDictation.played.add(manualDictation.index);manualDictation.repeatIndex=0;manualDictation.stage="speaking";updateManualDictationView();playManualRepetition(manualDictation.token);}
function playManualRepetition(token){if(!manualDictation.running||token!==manualDictation.token)return;const entry=manualDictation.items[manualDictation.index];manualDictation.stage="speaking";updateManualDictationView();const ended=()=>{if(token!==manualDictation.token)return;manualDictation.repeatIndex++;if(manualDictation.repeatIndex<manualRepeatCount){manualDictation.stage="between";updateManualDictationView();manualDictation.timer=setTimeout(()=>playManualRepetition(token),280);}else{manualDictation.stage="pause";updateManualDictationView();manualDictation.timer=setTimeout(()=>{if(token!==manualDictation.token||!manualDictation.running)return;manualDictation.index++;startManualWord();},manualPauseSeconds*1000);}};if(saasMode){const utterance=new SpeechSynthesisUtterance(entry.word);utterance.lang="en-US";utterance.rate=.78;utterance.onend=ended;utterance.onerror=ended;speechSynthesis.cancel();speechSynthesis.speak(utterance);manualDictation.audio=null;return;}const audio=new Audio(`/api/word-tts?word=${encodeURIComponent(entry.word)}`);manualDictation.audio=audio;audio.onended=ended;audio.onerror=ended;audio.play().catch(ended);}
function completeManualDictation(){clearTimeout(manualDictation.timer);manualDictation.complete=true;manualDictation.running=false;manualDictation.stage="complete";manualDictation.played=new Set(manualDictation.items.map((_,index)=>index));updateManualDictationView();}
function toggleManualPause(){if(manualDictation.index<0||manualDictation.complete)return;if(manualDictation.running){manualDictation.running=false;clearTimeout(manualDictation.timer);if(saasMode)speechSynthesis.pause();else manualDictation.audio?.pause();}else{manualDictation.running=true;if(saasMode&&manualDictation.stage==="speaking")speechSynthesis.resume();else if(manualDictation.stage==="speaking"&&manualDictation.audio?.paused)manualDictation.audio.play();else if(manualDictation.stage==="between")manualDictation.timer=setTimeout(()=>playManualRepetition(manualDictation.token),280);else if(manualDictation.stage==="pause")manualDictation.timer=setTimeout(()=>{manualDictation.index++;startManualWord();},manualPauseSeconds*1000);}updateManualDictationView();}
function jumpManual(direction){if(!manualDictation.items.length)return;clearTimeout(manualDictation.timer);manualDictation.audio?.pause();manualDictation.token++;manualDictation.index=Math.max(0,Math.min(manualDictation.items.length-1,(manualDictation.index<0?0:manualDictation.index)+direction));manualDictation.complete=false;manualDictation.running=true;manualDictation.played.add(manualDictation.index);manualDictation.repeatIndex=0;startManualWord();}
function handleManualAction(action){if(action==='start'){startManualDictation();return;}if(action==='pause'){toggleManualPause();return;}if(action==='prev'){jumpManual(-1);return;}if(action==='next'){jumpManual(1);}}
function updateManualDictationView(){const status=$("#manualStatus");if(!status)return;let message=`点击开始，共 ${manualDictation.items.length} 个词`;if(manualDictation.complete)message=`听写完成，已揭示 ${manualDictation.items.length} 个单词`;else if(manualDictation.index>=0){if(!manualDictation.running)message=`已暂停 · 第 ${manualDictation.index+1}/${manualDictation.items.length} 个`;else if(manualDictation.stage==='speaking')message=`第 ${manualDictation.index+1}/${manualDictation.items.length} 个 · 正在朗读第 ${Math.min(manualRepeatCount,manualDictation.repeatIndex+1)}/${manualRepeatCount} 遍`;else if(manualDictation.stage==='pause')message=`第 ${manualDictation.index+1} 个完成 · 停顿 ${manualPauseSeconds} 秒`;else message=`第 ${manualDictation.index+1}/${manualDictation.items.length} 个`;}status.textContent=message;const start=$("#manualStart"),pause=$("#manualPause");if(start)start.textContent=manualDictation.complete?'重新开始':manualDictation.index<0?'开始':'重新开始';if(pause){pause.disabled=manualDictation.index<0||manualDictation.complete;pause.textContent=manualDictation.running?'暂停':'继续';}$$('.manual-word').forEach((element,index)=>{const played=manualDictation.played.has(index),current=index===manualDictation.index&&!manualDictation.complete,text=element.querySelector('.manual-word-text');element.classList.toggle('played',played);element.classList.toggle('current',current);element.classList.toggle('revealed',manualDictation.complete);text.textContent=manualDictation.complete?manualDictation.items[index].word:played?'████████':'待听写';});}
function flashManualWord(index){const element=$(`.manual-word[data-manual-index="${index}"]`);if(!element)return;element.classList.remove('replay-flash');void element.offsetWidth;element.classList.add('replay-flash');}
function handleReviewClick(event){
  if(event.target.closest('[data-close-mobile-panel]')){closeMobileDetailPanels(false);return;}
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
  openMobileDetailPanel("review");
  const panel=$("#reviewWordPanel"),requestId=++wordRequestId,bookInfo=(saasMode?workspaceBooks:libraryBooks).find(item=>item.id===entry.book_id);
  panel.innerHTML=`<button class="mobile-sheet-close" type="button" data-close-mobile-panel aria-label="关闭释义">×</button><div class="manual-info-card"><button class="manual-info-speaker" data-word="${escapeHtml(entry.word)}">♪</button><span class="phonetic">${formatText(entry.phonetic)}</span><h3>${escapeHtml(entry.word)}</h3><p class="manual-info-meaning">${formatText(entry.meaning)}</p><div id="manualRemoteDefinition"><span class="loading-line">正在加载完整释义…</span></div>${contextBlockHtml(bookInfo?.title||'当前句子',escapeHtml(entry.context),entry.context)}<div id="manualRemoteUsage" class="usage-note"><span class="loading-line">正在分析当前句中的用法…</span></div><div id="manualRemoteExamples" class="dict-examples"><span class="loading-line">正在加载例句…</span></div>${entry.note?`<div class="saved-word-note"><small>我的备注</small><p>${escapeHtml(entry.note)}</p></div>`:''}</div>`;
  if(saasMode){$("#manualRemoteDefinition").innerHTML=`<p>${formatText(entry.meaning)}</p>`;$("#manualRemoteUsage").textContent="已显示保存时的语境；AI 语境精讲将在租户化阶段接入。";$("#manualRemoteExamples").innerHTML='';return;}
  fetch(`/api/word-dictionary?word=${encodeURIComponent(entry.word)}`,{cache:'no-store'}).then(async response=>response.ok?response.json():Promise.reject()).then(data=>{if(requestId!==wordRequestId)return;const groups=(data.groups||[]).map(group=>`<div class="dict-group"><b>${escapeHtml(group.pos)}</b><p>${group.translations.map(escapeHtml).join('；')}</p></div>`).join('');$("#manualRemoteDefinition").innerHTML=groups||`<p>${formatText(entry.meaning)}</p>`;$("#manualRemoteExamples").innerHTML=(data.examples||[]).length?`<small>EXAMPLES</small>${data.examples.map(example=>`<p>${escapeHtml(example)}</p>`).join('')}`:'<small>暂无例句</small>';}).catch(()=>{if(requestId===wordRequestId){$("#manualRemoteDefinition").innerHTML=`<p>${formatText(entry.meaning)}</p>`;$("#manualRemoteExamples").innerHTML='';}});
  fetch('/api/word-context',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({word:entry.word,contextSentence:entry.context,expandedContext:entry.context})}).then(async response=>response.ok?response.json():Promise.reject()).then(data=>{if(requestId===wordRequestId)$("#manualRemoteUsage").innerHTML=formatText(data.explanation||'结合当前句理解该词的具体用法。');}).catch(()=>{if(requestId===wordRequestId)$("#manualRemoteUsage").textContent='结合当前句理解该词的具体用法。';});
}

function changeReviewPage(action){const total=Math.max(1,Math.ceil(filteredReviewItems().length/reviewPageSize));if(action==='first')reviewPage=1;if(action==='prev')reviewPage=Math.max(1,reviewPage-1);if(action==='next')reviewPage=Math.min(total,reviewPage+1);if(action==='last')reviewPage=total;renderReview();}
function handleReviewShortcut(event){if(event.metaKey||event.ctrlKey||event.altKey||event.target.closest('input,textarea,select,[contenteditable=true]'))return;const key=event.key.toLowerCase();const action={a:'prev',d:'next',e:'last',f:'first'}[key];if(action){event.preventDefault();changeReviewPage(action);}}


async function reviewSavedWord(id,rating) {
  const entry=vocabItems.find(item=>item.id===id);if(!entry)return;
  const old=entry.interval_days||1;const interval=rating==="again"?1:rating==="hard"?Math.max(2,Math.round(old*1.2)):rating==="good"?Math.max(7,old*2):Math.max(14,old*3);
  const updates={rating,interval_days:Math.min(180,interval),due_at:new Date(Date.now()+Math.min(180,interval)*86400000).toISOString(),reviews:(entry.reviews||0)+1};
  if(saasMode){
    const response=await fetch("/api/workspace/vocabulary",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:entry.book_id,sentenceId:entry.sentence_id,wordIndex:entry.word_index,payload:workspaceVocabularyPayload(entry,updates)})});
    if(response.ok){
      const saved=normalizeWorkspaceVocabulary(await response.json()),index=vocabItems.findIndex(item=>item.id===id);if(index>=0)vocabItems[index]=saved;rebuildWordIndexes();
      const activityResponse=await fetch("/api/workspace/activity",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bookId:entry.book_id,readingSeconds:0,sentences:0,reviews:1,lastSentenceId:entry.sentence_id,idempotencyKey:`review-${id}-${crypto.randomUUID?.()||Date.now()}`})});
      if(activityResponse.ok&&learningDaysLoaded){const activity=await activityResponse.json(),day=learningDays.find(item=>item.day===activity.day);if(day)day.reviews=(day.reviews||0)+1;else learningDays.unshift({day:activity.day,reviews:1});}
    }
  }else{
    const response=await fetch(`/api/vocabulary/${id}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(updates)});if(response.ok){vocabItems=(await response.json()).items||[];rebuildWordIndexes();}
  }
  renderReview();renderStats();
}

function microphoneSecureHint(){
  const httpsUrl=`https://${location.hostname}:8766${location.pathname}`;
  return `当前页面是 ${location.origin}，局域网 HTTP 不允许申请麦克风权限。请使用 ${httpsUrl}；如果就在服务器电脑上，也可以使用 http://localhost:8765。`;
}
function microphoneErrorMessage(error){
  const name=error?.name||"";
  if(name==="NotAllowedError"||name==="SecurityError")return "麦克风权限被拒绝。请点击地址栏左侧的站点图标，将“麦克风”改为“允许”，然后刷新页面重试。";
  if(name==="NotFoundError"||name==="DevicesNotFoundError")return "没有检测到可用麦克风，请连接或启用麦克风后重试。";
  if(name==="NotReadableError"||name==="TrackStartError")return "麦克风当前无法读取，可能正被其他应用占用。请关闭占用麦克风的应用后重试。";
  if(name==="OverconstrainedError")return "当前麦克风不支持请求的录音参数，请更换输入设备后重试。";
  if(name==="AbortError")return "麦克风启动被系统中断，请稍后重试。";
  return `麦克风启动失败${name?`（${name}）`:""}。请检查浏览器和系统的麦克风权限。`;
}
async function microphonePermissionState(){
  try{return (await navigator.permissions?.query({name:"microphone"})).state||"unknown";}catch{return "unknown";}
}
async function playRecordingReview(){
  if(!recordingUrl)return;
  clearTimeout(shadowTimer);clearTimeout(audioStopTimer);wordStopAt=null;shadowWaiting=true;
  resetWordHoverSession();$("#audio").pause();wordTtsAudio?.pause();speechSynthesis.cancel();
  const recording=$("#recording");recording.pause();recording.src=recordingUrl;recording.currentTime=0;
  $("#shadowStatus").textContent="正在回放录音";$("#shadowPrompt").textContent="原文朗读已暂停；回放结束后仍保持暂停。";
  recording.onended=()=>{$("#shadowStatus").textContent="回放结束";$("#shadowPrompt").textContent="原文保持暂停。点击下一句、句子正文或播放键后再继续。";};
  try{await recording.play();}catch(error){$("#shadowStatus").textContent="无法回放录音";$("#shadowPrompt").textContent=error?.message||"请重新录音后再试。";}
}
function updateShadowMicrophoneHint(){
  if(mode!=="shadow"||mediaRecorder?.state==="recording")return;
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){$("#shadowStatus").textContent="当前地址无法申请麦克风";$("#shadowPrompt").textContent=microphoneSecureHint();}
}

async function toggleRecording() {
  if (mediaRecorder?.state === "recording") { mediaRecorder.stop(); recognition?.stop(); return; }
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia){updateShadowMicrophoneHint();return;}
  if(typeof MediaRecorder==="undefined"){$("#shadowStatus").textContent="浏览器不支持录音";$("#shadowPrompt").textContent="请使用最新版 Chrome、Edge、Safari 或 Firefox。";return;}
  try {
    clearTimeout(shadowTimer); shadowWaiting = true; $("#audio").pause(); recognizedText = "";
    const permission=await microphonePermissionState();
    if(permission==="denied"){
      $("#shadowStatus").textContent="麦克风权限已被禁止";
      $("#shadowPrompt").textContent="请点击地址栏左侧的站点图标，将“麦克风”改为“允许”，然后刷新页面。";
      return;
    }
    $("#shadowStatus").textContent="正在申请麦克风权限…";$("#shadowPrompt").textContent="请在浏览器弹出的权限窗口中选择“允许”。";
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
  } catch(error) { $("#shadowStatus").textContent = "无法使用麦克风"; $("#shadowPrompt").textContent = microphoneErrorMessage(error); }
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
function showPage(page) { if(!book||!book.pageBase||book.hasOriginalPages===false||page===displayedPage)return; displayedPage=page;$("#imageStatusOverlay").classList.add("hidden");$("#pagePanel").classList.remove("media-error");$("#pageImage").src = `${book.pageBase}/page-${String(page).padStart(3,"0")}.jpg`;$("#pageLabel").textContent = `原书第 ${page} 页`; }
function restoreProgress() { if(!book)return; const state=load(`${STORE.state}-${currentBookId}`,{});const time=state.time||0;$("#audio").currentTime=time;$("#backBtn").style.visibility="hidden"; }

async function loadApiSettings() {
  try {
    const response=await fetch("/api/settings",{cache:"no-store"}); const data=await response.json();
    runtimeMode=data.runtimeMode||"full";applyRuntimePresentation();
    if(runtimeMode==="reader"){$('[data-screen="import"]')?.classList.add("hidden");$("#import")?.classList.add("hidden");}
    $("#diocoEmail").value=data.userEmail||"";
    $("#tokenStatus").textContent=data.tokenConfigured?`令牌已配置：${data.tokenMask}`:"尚未配置令牌";
    shortcuts={previous:data.shortcutPrevious||"a",repeat:data.shortcutRepeat||"s",next:data.shortcutNext||"d",play:data.shortcutPlay||"space"};
    shelfView=data.shelfView||"tile"; currentSeries=data.currentSeries||"";
    wordTipSeconds=+(data.wordTipSeconds||2);reviewPageSize=+(data.reviewPageSize||10);manualRepeatCount=+(data.manualRepeatCount||3);manualPauseSeconds=+(data.manualPauseSeconds||2);highlightLeadMs=Number.isFinite(+data.highlightLeadMs)?+data.highlightLeadMs:0;sentenceAutoPause=!!data.sentenceAutoPause;eyeComfort=readerIsVisible()&&!!data.eyeComfort;heatmapRange=data.heatmapRange||"year";if(data.eyeComfort&&!readerIsVisible())savePreference({eyeComfort:false});$("#wordTipSeconds").value=wordTipSeconds;$("#reviewPageSize").value=reviewPageSize;$("#manualRepeatCount").value=manualRepeatCount;$("#manualPauseSeconds").value=manualPauseSeconds;$("#highlightLeadMs").value=highlightLeadMs;applyEyeComfort();
    for(const [name,key] of Object.entries(shortcuts)){const input=$(`#shortcut${name[0].toUpperCase()+name.slice(1)}`);if(input){input.value=keyLabel(key);input.dataset.key=key;}}
    updateShortcutHint();
  } catch { $("#tokenStatus").textContent=runtimeMode==="reader"?"无法读取设置":"无法读取本地设置"; }
}
async function saveApiSettings(event) {
  event.preventDefault(); const button=event.submitter; button.disabled=true; $("#tokenStatus").textContent="正在保存…";
  try {
    const proposed={previous:$("#shortcutPrevious").dataset.key,repeat:$("#shortcutRepeat").dataset.key,next:$("#shortcutNext").dataset.key,play:$("#shortcutPlay").dataset.key};
    if(new Set(Object.values(proposed)).size!==4)throw new Error("四个快捷键不能重复");
    if(saasMode){shortcuts=proposed;wordTipSeconds=+$("#wordTipSeconds").value;reviewPageSize=+$("#reviewPageSize").value;manualRepeatCount=+$("#manualRepeatCount").value;manualPauseSeconds=+$("#manualPauseSeconds").value;highlightLeadMs=+$("#highlightLeadMs").value;const key="shiyue-saas-preferences",current=load(key,{});save(key,{...current,shortcutPrevious:proposed.previous,shortcutRepeat:proposed.repeat,shortcutNext:proposed.next,shortcutPlay:proposed.play,wordTipSeconds,reviewPageSize,manualRepeatCount,manualPauseSeconds,highlightLeadMs,heatmapRange});reviewPage=1;stopManualDictation();updateShortcutHint();syncPlaybackFrame();$("#tokenStatus").textContent="阅读偏好已保存到当前浏览器";return;}
    const response=await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({userEmail:$("#diocoEmail").value,diocoToken:$("#diocoToken").value,shortcutPrevious:proposed.previous,shortcutRepeat:proposed.repeat,shortcutNext:proposed.next,shortcutPlay:proposed.play,wordTipSeconds:+$("#wordTipSeconds").value,reviewPageSize:+$("#reviewPageSize").value,manualRepeatCount:+$("#manualRepeatCount").value,manualPauseSeconds:+$("#manualPauseSeconds").value,highlightLeadMs:+$("#highlightLeadMs").value,eyeComfort})});
    const data=await response.json(); if(!response.ok) throw new Error(data.error||"保存失败");
    shortcuts=proposed;wordTipSeconds=+$("#wordTipSeconds").value;reviewPageSize=+$("#reviewPageSize").value;manualRepeatCount=+$("#manualRepeatCount").value;manualPauseSeconds=+$("#manualPauseSeconds").value;highlightLeadMs=+$("#highlightLeadMs").value;reviewPage=1;stopManualDictation();applyEyeComfort();updateShortcutHint();syncPlaybackFrame();$("#diocoToken").value=""; $("#tokenStatus").textContent=`已保存：${data.tokenMask}`;
  } catch(error) { $("#tokenStatus").textContent=error.message; }
  finally { button.disabled=false; }
}
function deploymentPayload(){return {id:+$("#deployTargetId").value||undefined,name:$("#deployName").value.trim()||"远程服务器",host:$("#deployHost").value.trim(),port:+$("#deployPort").value||22,username:$("#deployUser").value.trim()||"root",password:$("#deployPassword").value,remoteRoot:$("#deployRoot").value.trim()||"/srv/shiyue",servicePort:+$("#deployServicePort").value||8765,useHttps:$("#deployProtocol").value==="https",installRecording:$("#deployRecording").checked};}
function renderDeploymentNodes(){
  const list=$("#deploymentNodeList");
  if(!deploymentTargets.length){list.innerHTML='<div class="empty-state"><h3>还没有远程节点</h3><p>点击“新增节点”配置第一台Linux服务器。</p></div>';return;}
  list.innerHTML=deploymentTargets.map(target=>{const job=target.latestJob,status=job?.status||"idle",statusText=status==="running"||status==="queued"?`${job.progress||0}% · ${job.step||"处理中"}`:status==="complete"?"最近任务完成":status==="failed"?`失败：${job.error||job.step||"未知错误"}`:target.passwordConfigured?"已配置":"缺少密码",scheme=target.use_https?"https":"http";return `<article class="deployment-node ${target.id===activeDeploymentTargetId?'active':''}" data-target-id="${target.id}"><button type="button" class="deployment-node-main" data-node-action="select"><span class="deployment-node-icon">${escapeHtml((target.name||"节").slice(0,1))}</span><span><b>${escapeHtml(target.name)}</b><small>${escapeHtml(target.username)}@${escapeHtml(target.host)}:${target.port}</small><small>${scheme}://${escapeHtml(target.host)}:${target.service_port}</small><em class="${escapeHtml(status)}">${escapeHtml(statusText)}</em></span><i>${target.id===activeDeploymentTargetId?'当前节点':'选择'}</i></button></article>`;}).join("");
}
function fillDeploymentForm(target){
  $("#deployTargetId").value=target?.id||"";$("#deployName").value=target?.name||"";$("#deployHost").value=target?.host||"";$("#deployPort").value=target?.port||22;$("#deployUser").value=target?.username||"root";$("#deployRoot").value=target?.remote_root||"/srv/shiyue";$("#deployServicePort").value=target?.service_port||8765;$("#deployProtocol").value=target&&!target.use_https?"http":"https";$("#deployRecording").checked=target?!!target.install_recording:true;$("#deployPassword").value="";$("#deployPassword").placeholder=target?.passwordConfigured?"已保存到钥匙串；留空保持不变":"输入root密码";$("#deploymentConnection").textContent=target?(target.passwordConfigured?"已配置":"缺少密码"):"新增节点";$("#deploymentConnection").classList.toggle("ready",!!target?.passwordConfigured);$("#cancelDeploymentEdit").classList.toggle("hidden",!!target);
}
function beginNewDeploymentNode(){activeDeploymentTargetId=0;fillDeploymentForm(null);renderDeploymentNodes();$("#remoteCodeVersion").textContent="-";$("#remoteContentVersion").textContent="-";setDeploymentButtonsBusy(false);setTimeout(()=>$("#deployName").focus(),0);}
async function selectDeploymentTarget(targetId,reloadDetails=true){
  const target=deploymentTargets.find(item=>item.id===+targetId);if(!target)return;activeDeploymentTargetId=target.id;fillDeploymentForm(target);renderDeploymentNodes();
  if(reloadDetails)await loadDeploymentConfig(target.id);
}
function handleDeploymentNodeListClick(event){const node=event.target.closest("[data-target-id]");if(node)selectDeploymentTarget(+node.dataset.targetId);}
async function loadDeploymentConfig(preferredTargetId=activeDeploymentTargetId){
  try{
    const query=preferredTargetId?`?targetId=${preferredTargetId}`:"",response=await fetch(`/api/deployment/config${query}`,{cache:"no-store"});if(response.status===403){$("#settingsDeploymentTab")?.classList.add("hidden");$("#settingsDeploymentPanel")?.classList.add("hidden");setSettingsTab("general");return;}$("#settingsDeploymentTab")?.classList.remove("hidden");const data=await response.json();if(!response.ok)throw new Error(data.error||"无法读取部署配置");syncSettingsTabVisibility();
    deploymentTargets=data.targets||[];let selected=deploymentTargets.find(item=>item.id===+preferredTargetId)||deploymentTargets[0];activeDeploymentTargetId=selected?.id||0;if(selected)fillDeploymentForm(selected);else fillDeploymentForm(null);renderDeploymentNodes();
    const status=data.status||{};$("#remoteCodeVersion").textContent=status.codeVersion||"-";$("#remoteContentVersion").textContent=status.contentVersion||"-";$("#runtimeResourceSummary").textContent=`${status.localBooks||0} 本 · ${status.localRuntime||"待扫描"}`;
    const jobs=(data.jobs||[]).filter(job=>!activeDeploymentTargetId||job.target_id===activeDeploymentTargetId);renderDeploymentHistory(jobs);const running=jobs.find(job=>["queued","running"].includes(job.status));if(running)pollDeploymentJob(running.id,true);loadDeploymentReleases();setDeploymentButtonsBusy(false);
  }catch(error){$("#deploymentConnection").textContent=error.message;}
}
async function saveDeploymentConfig(event,quiet=false){
  event?.preventDefault();const payload=deploymentPayload(),button=event?.submitter||(!quiet?$("#saveDeploymentNode"):null),original=button?.textContent;if(button){button.disabled=true;button.textContent="正在保存…";}$("#deploymentConnection").textContent="正在保存";
  try{const response=await fetch("/api/deployment/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)}),data=await response.json();if(!response.ok)throw new Error(data.error||"保存失败");activeDeploymentTargetId=data.target.id;$("#deployPassword").value="";if(!quiet)showReaderToast("远程节点配置已保存");await loadDeploymentConfig(activeDeploymentTargetId);return data.target;}catch(error){$("#deploymentConnection").textContent=error.message;$("#deploymentConnection").classList.remove("ready");throw error;}finally{if(button){button.disabled=false;button.textContent=original||"保存节点";}}
}
async function startDeploymentAction(action,payload={}){
  try{
    if(!activeDeploymentTargetId){showReaderToast("请先选择或保存远程节点");return;}
    await saveDeploymentConfig(null,true);const response=await fetch(`/api/deployment/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({targetId:activeDeploymentTargetId,...payload})}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法启动任务");
    $("#deploymentLog").textContent="";deploymentLogOffset=0;pollDeploymentJob(data.jobId,false);
  }catch(error){$("#deploymentLog").textContent+=`\n启动失败：${error.message}\n`;}
}
function openUninstallNodeDialog(targetId){const target=deploymentTargets.find(item=>item.id===+targetId);if(!target)return;pendingUninstallTargetId=target.id;$("#uninstallNodeName").textContent=target.name;$("#uninstallNodeConfirm").value="";$("#uninstallNodeConfirm").placeholder=target.name;$("#uninstallNodeError").textContent="";$("#confirmUninstallNode").disabled=true;$("#uninstallNodeDialog").showModal();setTimeout(()=>$("#uninstallNodeConfirm").focus(),0);}
function validateUninstallNodeConfirmation(){const target=deploymentTargets.find(item=>item.id===pendingUninstallTargetId);$("#confirmUninstallNode").disabled=!target||$("#uninstallNodeConfirm").value.trim()!==target.name;$("#uninstallNodeError").textContent="";}
function resetUninstallNodeDialog(){pendingUninstallTargetId=0;$("#uninstallNodeConfirm").value="";$("#uninstallNodeError").textContent="";$("#confirmUninstallNode").disabled=true;}
async function confirmUninstallNode(){const target=deploymentTargets.find(item=>item.id===pendingUninstallTargetId),button=$("#confirmUninstallNode");if(!target)return;button.disabled=true;button.textContent="正在启动卸载…";try{$("#uninstallNodeDialog").close();await selectDeploymentTarget(target.id,false);const response=await fetch("/api/deployment/uninstall",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({targetId:target.id,confirmName:target.name})}),data=await response.json();if(!response.ok)throw new Error(data.error||"无法启动卸载");$("#deploymentLog").textContent="";deploymentLogOffset=0;pollDeploymentJob(data.jobId,false);}catch(error){$("#uninstallNodeError").textContent=error.message;if(!$("#uninstallNodeDialog").open)$("#uninstallNodeDialog").showModal();}finally{button.textContent="确认卸载";validateUninstallNodeConfirmation();}}
async function deleteSelectedNodeConfig(){const target=deploymentTargets.find(item=>item.id===activeDeploymentTargetId);if(!target)return;if(!confirm(`只删除本机节点配置“${target.name}”，不会操作远程服务器。是否继续？`))return;try{const response=await fetch("/api/deployment/delete-config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({targetId:target.id})}),data=await response.json();if(!response.ok)throw new Error(data.error||"删除配置失败");activeDeploymentTargetId=0;await loadDeploymentConfig();showReaderToast("节点配置已删除");}catch(error){showReaderToast(error.message);}}
function deploymentKindName(kind){return ({connection_test:"连接测试",code_deploy:"完整部署",program_upgrade:"程序升级",resource_sync:"数据同步",code_rollback:"代码回滚",content_rollback:"内容回滚",version_cleanup:"版本清理",remote_uninstall:"远程卸载",release_list:"代码版本读取",content_release_list:"内容版本读取"})[kind]||kind;}
function renderDeploymentHistory(jobs){$("#deploymentHistory").innerHTML=(jobs||[]).slice(0,10).map(job=>`<div class="${escapeHtml(job.status)}"><b>${escapeHtml(deploymentKindName(job.kind))}</b><span>${escapeHtml(job.step||job.status)}</span><small>${escapeHtml(job.updated_at||"")}</small></div>`).join("");}
function pollDeploymentJob(jobId,resume=false){
  clearInterval(deploymentPollTimer);activeDeploymentJob=jobId;if(!resume)deploymentLogOffset=0;$("#deploymentProgress").classList.remove("hidden");
  const check=async()=>{try{const response=await fetch(`/api/deployment/jobs/${jobId}?offset=${deploymentLogOffset}`,{cache:"no-store"}),job=await response.json();if(!response.ok)throw new Error(job.error||"无法读取任务");deploymentLogOffset=job.logOffset||deploymentLogOffset;if(job.logChunk){const log=$("#deploymentLog");if(log.textContent==="尚未运行部署任务。")log.textContent="";log.textContent+=job.logChunk;log.scrollTop=log.scrollHeight;}$("#deploymentBar").value=job.progress||0;$("#deploymentPercent").textContent=`${job.progress||0}%`;$("#deploymentStep").textContent=job.step||job.status;setDeploymentButtonsBusy(["queued","running"].includes(job.status));if(["complete","failed"].includes(job.status)){clearInterval(deploymentPollTimer);deploymentPollTimer=null;activeDeploymentJob=null;setDeploymentButtonsBusy(false);loadDeploymentConfig(activeDeploymentTargetId);}}catch(error){clearInterval(deploymentPollTimer);deploymentPollTimer=null;setDeploymentButtonsBusy(false);$("#deploymentLog").textContent+=`\n日志读取失败：${error.message}\n`;}};
  check();deploymentPollTimer=setInterval(check,1000);
}
function setDeploymentButtonsBusy(busy){const noTarget=!activeDeploymentTargetId;["#testDeployment","#deployCodeBtn","#upgradeCodeBtn","#syncResourcesBtn","#uninstallNodeBtn","#deleteNodeConfigBtn","#rollbackCodeBtn","#rollbackContentBtn","#cleanupVersionsBtn"].forEach(selector=>{const missingCode=selector==="#rollbackCodeBtn"&&!$("#rollbackRelease").value,missingContent=selector==="#rollbackContentBtn"&&!$("#rollbackContentRelease").value;$(selector).disabled=busy||noTarget||missingCode||missingContent;});}
async function loadDeploymentReleases(){
  if(!activeDeploymentTargetId){$("#rollbackRelease").innerHTML='<option value="">选择历史代码版本</option>';$("#rollbackContentRelease").innerHTML='<option value="">选择历史内容版本</option>';return;}
  try{const query=`?targetId=${activeDeploymentTargetId}`,[codeResponse,contentResponse]=await Promise.all([fetch(`/api/deployment/releases${query}`,{cache:"no-store"}),fetch(`/api/deployment/content-releases${query}`,{cache:"no-store"})]),codeData=await codeResponse.json(),contentData=await contentResponse.json();if(codeResponse.ok){const releases=codeData.releases||[];$("#rollbackRelease").innerHTML='<option value="">选择历史代码版本</option>'+releases.filter(item=>item.status!=="current").map(item=>`<option value="${escapeHtml(item.releaseId)}">${escapeHtml(item.releaseId)}</option>`).join("");const current=releases.find(item=>item.status==="current");$("#remoteCodeVersion").textContent=current?.releaseId||"-";}if(contentResponse.ok){const releases=contentData.releases||[];$("#rollbackContentRelease").innerHTML='<option value="">选择历史内容版本</option>'+releases.filter(item=>item.status!=="current").map(item=>`<option value="${escapeHtml(item.releaseId)}">${escapeHtml(item.releaseId)}</option>`).join("");const current=releases.find(item=>item.status==="current");$("#remoteContentVersion").textContent=current?.releaseId||"-";}$("#rollbackCodeBtn").disabled=!$("#rollbackRelease").value;$("#rollbackContentBtn").disabled=!$("#rollbackContentRelease").value;}catch{}
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
  const resourceText=item=>[[item.audioCount,"音频"],[item.pdfCount,"PDF"],[item.docCount,"DOC"],[item.txtCount,"TXT"],[item.chmCount,"CHM"]].filter(([count])=>count).map(([count,name])=>`${count} ${name}`).join(" · ")||"无支持资源";
  list.innerHTML=series.books.map(item=>`<label class="import-book-item ${item.importedId?'imported':''} ${item.ready?'':'unavailable'}"><img src="${encodeURI(item.coverUrl)}" alt="${escapeHtml(item.title)}封面" loading="lazy"><input type="checkbox" value="${escapeHtml(item.path)}" ${item.ready?'':'disabled'}><span><b>${escapeHtml(item.title)}</b><small>${escapeHtml(resourceText(item))}</small><small class="import-mode">${escapeHtml(item.importMode||"")}${item.importedId?' · 已导入，可重新导入':''}</small>${item.issue?`<small class="import-issue">${escapeHtml(item.issue)}</small>`:''}</span></label>`).join("");
  const ready=series.books.filter(item=>item.ready).length,blocked=series.books.length-ready;
  $("#importMeta").textContent=`${series.name}：扫描到 ${series.books.length} 个目录，${ready} 本可导入${blocked?`，${blocked} 本缺少音频或支持资源`:''}。批量任务将严格逐本顺序执行。`;
  updateBatchButton();
}
function selectedImportPaths(){return $$("#importBookList input:checked").map(input=>input.value)}
function updateBatchButton(){const count=selectedImportPaths().length;$("#startBatchImport").disabled=!count;$("#startBatchImport").textContent=count?`按顺序导入 ${count} 本`:'按顺序导入所选书籍'}
function rememberImportTracking(kind,jobIds){const tracked=load(STORE.imports,{});tracked[kind]={jobIds,updatedAt:Date.now()};save(STORE.imports,tracked);}
function forgetImportTracking(kind){const tracked=load(STORE.imports,{});delete tracked[kind];save(STORE.imports,tracked);}
function importJobKind(job){
  if(job.kind&&job.kind!=="books")return job.kind;
  const name=(job.source_path||"").split("/").pop();
  if(name.startsWith("youtube.")||job.source_path?.startsWith("youtube:"))return "youtube";
  if(name.startsWith("video."))return "video";
  return "books";
}
function setPendingImportJobs(jobs){
  pendingImportJobs=(jobs||[]).filter(job=>["queued","running","cancelling"].includes(job.status));
  const panel=$("#activeImportActions");panel.classList.toggle("hidden",!pendingImportJobs.length);
  if(!pendingImportJobs.length)return;
  const running=pendingImportJobs.filter(job=>job.status==="running").length,queued=pendingImportJobs.filter(job=>job.status==="queued").length;
  $("#activeImportTitle").textContent=`${running?`${running} 个运行中`:""}${running&&queued?" · ":""}${queued?`${queued} 个排队中`:""}`;
  const current=pendingImportJobs.find(job=>job.status==="running")||pendingImportJobs[0];
  $("#activeImportHint").textContent=current?.step?`当前阶段：${current.step}。刷新或关闭页面不会中断任务。`:"刷新或关闭页面不会中断任务。";
}
async function refreshPendingImportJobs(){
  try{const response=await fetch("/api/import/jobs",{cache:"no-store"});if(!response.ok)return pendingImportJobs;const data=await response.json();setPendingImportJobs(data.pendingJobs||data.jobs||[]);}catch{}
  return pendingImportJobs;
}
async function openCancelImportDialog(){
  await refreshPendingImportJobs();if(!pendingImportJobs.length){showReaderToast("当前没有运行中或排队中的任务");return;}
  $("#cancelImportError").textContent="";
  $("#cancelImportList").innerHTML=pendingImportJobs.map(job=>`<div><span>${escapeHtml((job.source_path||"").split("/").pop()||`任务 ${job.id}`)}</span><b>${job.status==="running"?`${job.progress||0}% · 运行中`:job.status==="queued"?"排队中":"正在中断"}</b><small>${escapeHtml(job.step||"")}</small></div>`).join("");
  $("#cancelImportDialog").showModal();
}
async function cancelActiveImports(){
  const button=$("#confirmCancelImports");button.disabled=true;button.textContent="正在中断…";$("#cancelImportError").textContent="";
  try{
    const response=await fetch("/api/import/jobs/cancel-active",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({confirm:true})});const data=await response.json();
    if(!response.ok)throw new Error(data.error||"无法中断任务");
    clearInterval(importPollTimer);clearInterval(videoImportPollTimer);clearInterval(youtubePollTimer);importPollTimer=videoImportPollTimer=youtubePollTimer=null;
    save(STORE.imports,{});setPendingImportJobs([]);$("#cancelImportDialog").close();
    $("#importProgress").classList.add("hidden");$("#videoUploadProgress").classList.add("hidden");$("#youtubeProgress").classList.add("hidden");
    const libraryData=await fetch("/api/library",{cache:"no-cache"}).then(result=>result.json());libraryBooks=libraryData.books||[];setupSeriesSelector();populateVideoSeriesOptions();renderLibrary();await loadImportCatalog();
    showReaderToast(`已中断并删除 ${data.removed||0} 个导入任务，可以重新导入`);
  }catch(error){$("#cancelImportError").textContent=error.message;}
  finally{button.disabled=false;button.textContent="中断并删除";}
}
async function discoverLegacyActiveJobs(){
  const jobs=[];let seenAny=false;
  for(let first=1;first<=500;first+=50){
    const batch=await Promise.all(Array.from({length:50},(_,offset)=>fetch(`/api/import/jobs/${first+offset}`,{cache:"no-store"}).then(async response=>response.ok?response.json():null).catch(()=>null)));
    const found=batch.filter(Boolean);if(!found.length&&seenAny)break;if(found.length)seenAny=true;jobs.push(...found);
  }
  const cutoff=Date.now()-24*60*60*1000;
  return jobs.filter(job=>["queued","running"].includes(job.status)&&new Date(job.updated_at||0).getTime()>=cutoff);
}
async function restoreImportTracking(){
  let jobs=[];
  try{const response=await fetch("/api/import/jobs",{cache:"no-store"});if(response.ok){const data=await response.json();jobs=data.jobs||[];setPendingImportJobs(data.pendingJobs||jobs);}else{jobs=await discoverLegacyActiveJobs();setPendingImportJobs(jobs);}}catch{jobs=await discoverLegacyActiveJobs();setPendingImportJobs(jobs);}
  const active=jobs.filter(job=>["queued","running"].includes(job.status));
  if(active.length){
    const latest=[...active].sort((a,b)=>a.id-b.id).at(-1);
    const latestKind=importJobKind(latest);
    const books=jobs.filter(job=>importJobKind(job)==="books");
    const latestBook=[...books].filter(job=>["queued","running"].includes(job.status)).sort((a,b)=>a.id-b.id).at(-1);
    if(latestBook){
      const batch=latestBook.batch_id?books.filter(job=>job.batch_id===latestBook.batch_id):books.filter(job=>["queued","running"].includes(job.status));
      const ids=batch.map(job=>job.id);rememberImportTracking("books",ids);pollImportBatch(ids);
    }
    for(const kind of ["video","youtube"]){const job=[...active].filter(item=>importJobKind(item)===kind).sort((a,b)=>a.id-b.id).at(-1);if(job){rememberImportTracking(kind,[job.id]);kind==="video"?pollVideoImport(job.id):pollYoutubeImport(job.id);}}
    setImportType(latestKind);
    showScreen("import");
    return;
  }
  const tracked=load(STORE.imports,{});const entries=Object.entries(tracked).filter(([,item])=>item?.jobIds?.length);
  if(!entries.length){if(pendingImportJobs.length)showScreen("import");return;}
  entries.forEach(([kind,item])=>{if(kind==="books")pollImportBatch(item.jobIds);else if(kind==="video")pollVideoImport(item.jobIds[0]);else if(kind==="youtube")pollYoutubeImport(item.jobIds[0]);});
  setImportType(entries.sort((a,b)=>(a[1].updatedAt||0)-(b[1].updatedAt||0)).at(-1)[0]);
  showScreen("import");
}
async function startBatchImport() {
  const paths=selectedImportPaths(); if(!paths.length)return;
  clearInterval(importPollTimer); $("#importProgress").classList.remove("hidden"); $("#importStep").textContent="正在创建顺序队列"; $("#importBar").value=0; $("#importPercent").textContent="0%";
  try {
    const request=await postImportRequest("/api/import/batch",{paths});if(request.cancelled){$("#importProgress").classList.add("hidden");return;}
    const {response,data}=request;if(!response.ok)throw new Error(data.error||"无法开始批量导入");
    rememberImportTracking("books",data.jobIds);refreshPendingImportJobs();pollImportBatch(data.jobIds);
  } catch(error){$("#importStep").textContent="导入失败";$("#importMessage").textContent=error.message;}
}
async function postImportRequest(url,payload){
  let response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});let data=await response.json();
  if(response.status===409&&data.code==="duplicate_import"){
    if(!await confirmReimport(data.duplicates||[]))return {cancelled:true,response,data};
    response=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({...payload,allowReimport:true})});data=await response.json();
  }
  return {cancelled:false,response,data};
}
function confirmReimport(duplicates){
  const dialog=$("#reimportDialog");$("#reimportList").innerHTML=duplicates.map(item=>`<div>${escapeHtml(item.title||item.name||item.source_path||"")}</div>`).join("");
  return new Promise(resolve=>{const close=()=>{dialog.removeEventListener("close",close);resolve(dialog.returnValue==="confirm");};dialog.addEventListener("close",close);dialog.showModal();});
}
function pollImportBatch(jobIds) {
  clearInterval(importPollTimer);$("#importProgress").classList.remove("hidden");
  const check=async()=>{
    try{
    const jobs=await Promise.all(jobIds.map(async id=>{const response=await fetch(`/api/import/jobs/${id}`,{cache:"no-store"});const job=await response.json();if(!response.ok)throw new Error(job.error||`无法读取任务 ${id}`);return job;}));
    const total=Math.round(jobs.reduce((sum,job)=>sum+(job.progress||0),0)/jobs.length); const finished=jobs.filter(job=>["complete","failed"].includes(job.status)).length;
    const current=jobs.find(job=>job.status==="running")||jobs.find(job=>job.status==="queued")||jobs[jobs.length-1];
    $("#importBar").value=total; $("#importPercent").textContent=`${total}%`; $("#importStep").textContent=`${finished}/${jobs.length} 完成 · ${current.step||current.status}`;
    $("#importMessage").textContent="批量任务严格按选择顺序逐本执行；单本失败不会阻止下一本。";
    $("#batchJobs").innerHTML=jobs.map((job,index)=>`<div class="batch-job ${job.status}"><span>${index+1}. ${escapeHtml(job.source_path.split('/').pop())}</span><b>${job.status==='complete'?'完成':job.status==='failed'?'失败':job.status==='running'?`${job.progress}%`:'排队'}</b>${job.error?`<small>${escapeHtml(job.error)}</small>`:''}</div>`).join("");
    if(finished===jobs.length){
      clearInterval(importPollTimer); importPollTimer=null;
      forgetImportTracking("books");refreshPendingImportJobs();
      const data=await fetch("/api/library",{cache:"no-cache"}).then(r=>r.json()); libraryBooks=data.books||[]; renderLibrary(); await loadImportCatalog();
      $("#importMessage").textContent=`批量导入结束：${jobs.filter(j=>j.status==='complete').length} 本成功，${jobs.filter(j=>j.status==='failed').length} 本失败。`;
    }
    }catch(error){$("#importStep").textContent="正在重新连接后台任务";$("#importMessage").textContent=error.message;}
  };
  check(); importPollTimer=setInterval(check,1500);
}

function workspaceCard(book){const seconds=book.progress?.readingSeconds||0,progress=book.duration?Math.min(100,Math.round(seconds/book.duration*100)):0,progressLabel=progress?"已完成 "+progress+"%":"尚未开始",action=progress?"继续阅读":"开始阅读";return '<button class="catalog-book-card workspace-book-card" type="button" data-workspace-book="'+escapeHtml(book.id)+'">'+catalogCover(book)+'<span class="workspace-card-copy"><span class="catalog-state">私人</span><h3>'+escapeHtml(book.title)+'</h3><em>'+escapeHtml(book.englishTitle||"")+'</em><p>'+escapeHtml(book.series||"未分组")+' · '+escapeHtml(book.level||"-")+'级 · '+(book.sentenceCount||0)+'句</p><p>'+(book.mediaCount||0)+' 个受鉴权媒体 · 已读 '+Math.round(seconds/60)+' 分钟</p><span class="book-progress"><i style="width:'+progress+'%"></i></span><small class="book-progress-label">'+progressLabel+'</small></span><i class="catalog-card-action">'+action+'</i></button>';}
init();
