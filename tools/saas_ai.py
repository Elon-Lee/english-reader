#!/usr/bin/env python3
"""Tenant-scoped AI generation with PostgreSQL cache and quota settlement."""
from __future__ import annotations

import hashlib
import json
import os
import re
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.request import Request, urlopen

from saas_auth import SaaSError, SaaSService, new_id
from saas_membership import MembershipService, as_json


WORD_RE=re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+")


class _TextExtractor(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)
    def text(self):return "".join(self.parts).strip()


def plain_html(value:Any)->str:
    parser=_TextExtractor();parser.feed(str(value or ""));return parser.text()


class WorkspaceAIService:
    def __init__(self,accounts:SaaSService,memberships:MembershipService,generator:Callable[[str,dict[str,Any]],dict[str,Any]]|None=None):
        self.accounts,self.memberships=accounts,memberships
        self.generator=generator or self._dioco_generate
        self.upstream=str(os.environ.get("SHIYUE_DIOCO_UPSTREAM","https://api-cdn-plus.dioco.io")).rstrip("/")

    def _sentence(self,cursor:Any,user_id:str,book_id:str,sentence_id:str)->tuple[dict[str,Any],dict[str,Any],list[dict[str,Any]],int]:
        cursor.execute("SELECT * FROM content_books WHERE id=%s AND owner_id=%s AND visibility IN ('private','draft')",(book_id,user_id));book=self.accounts._one(cursor)
        if not book:raise SaaSError("workspace_book_not_found","私人读物不存在或你无权访问。",404)
        data=as_json(book["data_json"]);sentences=data.get("sentences",[]) if isinstance(data.get("sentences",[]),list) else []
        for index,sentence in enumerate(sentences):
            if isinstance(sentence,dict) and str(sentence.get("id"))==str(sentence_id):return book,sentence,sentences,index
        raise SaaSError("workspace_sentence_not_found","句子不存在或不属于该私人读物。",404)

    @staticmethod
    def _digest(value:Any)->str:return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()

    def _cached(self,cursor:Any,user_id:str,result_type:str,content_key:str,input_hash:str)->dict[str,Any]|None:
        cursor.execute("SELECT * FROM workspace_ai_results WHERE owner_id=%s AND result_type=%s AND content_key=%s AND input_hash=%s",(user_id,result_type,content_key,input_hash));return self.accounts._one(cursor)

    def _generate(self,user_id:str,feature:str,result_type:str,content_key:str,input_hash:str,book_id:str,prompt:dict[str,Any])->dict[str,Any]:
        quota_key=f"ai:{result_type}:{hashlib.sha256(f'{content_key}:{input_hash}'.encode()).hexdigest()}";reservation=self.memberships.reserve(user_id,feature,quota_key,1,{"bookId":book_id,"contentKey":content_key,"inputHash":input_hash})["reservation"]
        if reservation.get("state")=="released":reservation=self.memberships.reserve(user_id,feature,f"{quota_key}:retry:{new_id()}",1,{"bookId":book_id,"contentKey":content_key,"inputHash":input_hash,"retry":True})["reservation"]
        charged=reservation.get("state")=="reserved"
        try:
            generated=self.generator(result_type,prompt)
            if not isinstance(generated,dict) or not str(generated.get("text","")).strip():raise SaaSError("ai_empty_result","AI 服务没有返回可用内容。",502)
            payload={**generated,"text":str(generated["text"]).strip()};provider=str(payload.get("provider","")or"platform-ai")[:100]
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""INSERT INTO workspace_ai_results(id,owner_id,content_book_id,result_type,content_key,input_hash,payload,provider)
                    VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT (owner_id,result_type,content_key,input_hash) DO NOTHING""",(new_id(),user_id,book_id,result_type,content_key,input_hash,json.dumps(payload,ensure_ascii=False),provider))
                    cursor.execute("SELECT * FROM workspace_ai_results WHERE owner_id=%s AND result_type=%s AND content_key=%s AND input_hash=%s",(user_id,result_type,content_key,input_hash));row=self.accounts._one(cursor)
                    if not row:raise SaaSError("ai_cache_failed","AI 结果保存失败。",503)
            if charged:self.memberships.settle(user_id,reservation["id"])
            return {"payload":as_json(row["payload"]),"provider":row["provider"],"cached":False,"charged":charged}
        except Exception as exc:
            if reservation.get("state")=="reserved":
                try:self.memberships.release(user_id,reservation["id"])
                except SaaSError:pass
            if isinstance(exc,SaaSError):raise
            raise SaaSError("ai_generation_failed","AI 生成失败，请稍后重试。",502) from exc

    def context(self,user_id:str,book_id:str,sentence_id:str,word_index:Any)->dict[str,Any]:
        try:index=int(word_index)
        except (TypeError,ValueError) as exc:raise SaaSError("invalid_word_index","单词索引无效。",400) from exc
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                _,sentence,sentences,sentence_index=self._sentence(cursor,user_id,book_id,sentence_id);text=str(sentence.get("text","")).strip();words=WORD_RE.findall(text)
                if index<0 or index>=len(words):raise SaaSError("workspace_word_not_found","单词不存在。",404)
                word=words[index];expanded=" ".join(str(item.get("text","")).strip() for item in sentences[max(0,sentence_index-1):sentence_index+2] if isinstance(item,dict)).strip()
                content_key=f"{book_id}:{sentence_id}:{index}";input_hash=self._digest({"word":word,"sentence":text,"expanded":expanded});cached=self._cached(cursor,user_id,"word_context",content_key,input_hash)
                if cached:return {"bookId":book_id,"sentenceId":str(sentence_id),"wordIndex":index,"word":word,"explanation":as_json(cached["payload"]).get("text",""),"source":cached["provider"],"cached":True,"charged":False}
        result=self._generate(user_id,"ai_context_generations","word_context",content_key,input_hash,book_id,{"word":word,"contextSentence":text,"expandedContext":expanded})
        return {"bookId":book_id,"sentenceId":str(sentence_id),"wordIndex":index,"word":word,"explanation":result["payload"]["text"],"source":result["provider"],"cached":result["cached"],"charged":result["charged"]}

    def grammar(self,user_id:str,book_id:str,sentence_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                _,sentence,_,_=self._sentence(cursor,user_id,book_id,sentence_id);text=str(sentence.get("text","")).strip();content_key=f"{book_id}:{sentence_id}";input_hash=self._digest({"sentence":text});cached=self._cached(cursor,user_id,"sentence_grammar",content_key,input_hash)
                cursor.execute("SELECT payload FROM content_sentence_grammar WHERE book_id=%s AND sentence_id=%s",(book_id,str(sentence_id)));structure_row=self.accounts._one(cursor);structure=as_json(structure_row["payload"]) if structure_row else {}
                if cached:return {"bookId":book_id,"sentenceId":str(sentence_id),"text":text,"aiExplanation":as_json(cached["payload"]).get("text",""),"source":cached["provider"],"structure":structure,"cached":True,"charged":False}
        result=self._generate(user_id,"ai_grammar_generations","sentence_grammar",content_key,input_hash,book_id,{"sentence":text,"structure":structure})
        return {"bookId":book_id,"sentenceId":str(sentence_id),"text":text,"aiExplanation":result["payload"]["text"],"source":result["provider"],"structure":structure,"cached":result["cached"],"charged":result["charged"]}

    def _dioco_generate(self,result_type:str,prompt:dict[str,Any])->dict[str,Any]:
        token=str(os.environ.get("SHIYUE_DIOCO_TOKEN","")).strip();email=str(os.environ.get("SHIYUE_DIOCO_EMAIL","")).strip()
        if not token or not email:raise SaaSError("ai_provider_unavailable","平台 AI 服务尚未配置。",503)
        if result_type=="word_context":instruction="请用简洁准确的中文解释这个英文单词在当前句和上下文中的具体含义、搭配与语气。<WORD>：<CONTEXT>";word=prompt["word"];sentence=prompt["contextSentence"];expanded=prompt["expandedContext"]
        else:instruction=f"请用简洁准确的中文讲解这句英文的句型、主干、从句、时态语态和学习重点。已有结构：{json.dumps(prompt.get('structure',{}),ensure_ascii=False)}。原句：<CONTEXT>";word="sentence grammar";sentence=prompt["sentence"];expanded=sentence
        body={"promptWithPlaceHolders_translated":instruction,"contextSentence":sentence,"expandedContext":expanded,"word":word,"userLanguage_G":"zh-CN","studyLanguage_G":"en","diocoToken":token,"userEmail":email}
        request=Request(self.upstream+"/base_lexa_generate",data=json.dumps(body,ensure_ascii=False).encode(),headers={"Accept":"application/json, text/plain, */*","Content-Type":"application/json","Origin":"https://www.youtube.com","Referer":"https://www.youtube.com/","User-Agent":"Mozilla/5.0"},method="POST")
        try:
            with urlopen(request,timeout=45) as response:raw=json.loads(response.read())
        except Exception as exc:raise SaaSError("ai_provider_failed","平台 AI 服务调用失败。",502) from exc
        text=plain_html(raw.get("data",{}).get("generation",""))
        if not text:raise SaaSError("ai_empty_result","平台 AI 服务没有返回可用内容。",502)
        return {"text":text,"provider":"Dioco Lexa"}
