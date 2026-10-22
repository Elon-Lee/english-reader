// Reader API timestamps are absolute media seconds. Never guess an offset per word:
// a word slightly before a sentence boundary must not jump an entire sentence forward.
export const mediaSeconds = value => value === null || value === undefined || value === '' || !Number.isFinite(Number(value)) ? null : Number(value)
export const sentenceStart = sentence => mediaSeconds(sentence?.start)
export const sentenceEnd = (sentence, next) => mediaSeconds(sentence?.end) ?? sentenceStart(next)

export function buildReaderTimeline(sentences) {
  const entries = sentences.flatMap((sentence, index) => {
    const start = sentenceStart(sentence)
    return start === null ? [] : [{start, index, acoustic:sentence.timingPolicy==='acoustic-only'}]
  }).sort((a,b) => a.start-b.start || a.index-b.index)
  const words = sentences.map((sentence,index) => {
    const tokens = sentence.words || [], start = sentenceStart(sentence) ?? 0
    const end = sentenceEnd(sentence,sentences[index+1]) ?? start + Math.max(1,tokens.length*.42)
    const acoustic=sentence.timingPolicy==='acoustic-only'
    return tokens.map((word,wordIndex) => ({
      index:wordIndex,
      start:mediaSeconds(word.start ?? word.startTime) ?? (acoustic?null:start + (end-start)*wordIndex/Math.max(1,tokens.length)),
    })).filter(word=>word.start!==null).sort((a,b)=>a.start-b.start || a.index-b.index)
  })
  return {entries,words}
}

function atOrBefore(entries,time) {
  let low=0,high=entries.length
  while(low<high){const mid=(low+high)>>>1;if(entries[mid].start<=time)low=mid+1;else high=mid}
  return low-1
}
export function timelineSentence(timeline,time) {
  const entries=timeline.entries
  if(!entries.length)return -1
  const position=atOrBefore(entries,time),entry=entries[Math.max(0,position)]
  if(entry.acoustic&&position<0)return -1
  return entry.index
}
export function timelineWord(timeline,index,time) {
  const words=timeline.words[index]||[],position=atOrBefore(words,time)
  // A word's acoustic end can precede the next word by a pause. Keep the
  // highlight until the next measured start without changing stored times.
  return position<0 ? -1 : words[position].index
}

// Seeks (including native scrubbing) must not trigger sentence-end auto pause.
export function crossedSentenceEnd({previous,time,end,playing,seeking,paused}) {
  return playing&&!seeking&&!paused&&end!==null&&time>=previous&&previous<end&&time>=end
}

export function playReaderMedia(element,onError) {
  // A rapid pause/seek/source change can cancel an outstanding play request.
  // This is expected control flow, not an autoplay permission failure.
  return element.play().catch(error=>{if(error.name!=='AbortError')onError(error)})
}
