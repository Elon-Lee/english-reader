"""Exact source locations, separate from learning sentences and media timings."""
from saas_auth import SaaSError


def validate_source_location(data, location):
    if not isinstance(location,dict):
        raise SaaSError('invalid_reading_location','原文阅读位置无效。',400)
    document=data.get('readingDocument') or {}
    kind=location.get('format')
    if kind=='pdf' and document.get('format')=='pdf':
        page=location.get('page')
        maximum=int((data.get('import',{}).get('extractor') or {}).get('pages') or max((b.get('page',0) for b in document.get('blocks',[])),default=0))
        if type(page) is int and 1<=page<=maximum:
            return {'format':'pdf','page':page}
    if kind=='epub' and document.get('format')=='epub':
        spine=(document.get('source') or {}).get('spine',[])
        chapter=location.get('chapter');offset=location.get('offset')
        if type(chapter) is int and 0<=chapter<len(spine) and type(offset) is int and 0<=offset<=20*1024*1024:
            return {'format':'epub','chapter':chapter,'offset':offset}
    raise SaaSError('invalid_reading_location','阅读位置与原文不匹配。',400)
