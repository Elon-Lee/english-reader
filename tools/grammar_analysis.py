#!/usr/bin/env python3
"""English sentence grammar analysis backed by Stanza."""
import os,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODEL_DIR=Path(os.environ.get("SHIYUE_GRAMMAR_MODEL_DIR",ROOT/".local/grammar/stanza"))
MODEL_NAME="stanza-en-constituency-dependency-v1"
ANALYSIS_VERSION=2

CLAUSE_LABELS={
    "advcl":"状语从句","acl:relcl":"定语从句","ccomp":"宾语从句","xcomp":"非谓语补语",
    "csubj":"主语从句","csubj:pass":"主语从句","acl":"后置修饰从句",
}
MARK_LABELS={
    "if":"条件状语从句","unless":"条件状语从句","because":"原因状语从句","since":"原因或时间状语从句",
    "although":"让步状语从句","though":"让步状语从句","while":"时间或对比状语从句","when":"时间状语从句",
    "whenever":"时间状语从句","before":"时间状语从句","after":"时间状语从句","until":"时间状语从句",
    "as":"方式、原因或时间状语从句","so":"结果或目的结构","that":"名词性从句","whether":"名词性从句",
    "who":"定语从句","which":"定语从句","whose":"定语从句","where":"定语或状语从句","why":"名词性从句",
}
POS_ZH={"NOUN":"名词","PROPN":"专有名词","PRON":"代词","VERB":"动词","AUX":"助动词","ADJ":"形容词","ADV":"副词","ADP":"介词","DET":"限定词","CCONJ":"并列连词","SCONJ":"从属连词","NUM":"数词","PART":"小品词","INTJ":"感叹词","PUNCT":"标点"}

def clean_join(words):
    value=" ".join(words)
    value=re.sub(r"\s+([,.;:!?%\)])",r"\1",value);value=re.sub(r"([\(])\s+",r"\1",value)
    value=re.sub(r"\s+(['’])\s*",r"\1",value)
    return value.strip()

def feat_map(value):
    result={}
    for part in str(value or "").split("|"):
        if "=" in part:
            key,item=part.split("=",1);result[key]=item
    return result

class GrammarAnalyzer:
    def __init__(self):
        import torch
        original_load=torch.load
        def stanza_model_load(*args,**kwargs):
            if kwargs.get("weights_only") is True:kwargs["weights_only"]=False
            return original_load(*args,**kwargs)
        torch.load=stanza_model_load
        import stanza
        MODEL_DIR.mkdir(parents=True,exist_ok=True)
        self.pipeline=stanza.Pipeline("en",dir=str(MODEL_DIR),processors="tokenize,pos,lemma,depparse,constituency",tokenize_no_ssplit=True,use_gpu=False,verbose=False,download_method=None)

    def analyze(self,text):
        text=str(text or "").strip()
        if not text:raise ValueError("sentence is empty")
        document=self.pipeline(text);return self._build(text,document.sentences[0])

    def analyze_many(self,texts):
        cleaned=[str(text or "").strip() for text in texts]
        documents=self.pipeline.bulk_process(cleaned)
        return [self._build(text,document.sentences[0]) for text,document in zip(cleaned,documents)]

    def _build(self,text,sentence):
        words=sentence.words
        by_id={word.id:word for word in words};children={word.id:[] for word in words}
        for word in words:
            if word.head in children:children[word.head].append(word.id)
        root=next((word for word in words if word.head==0),words[0])

        def descendants(word_id):
            found={word_id};stack=[word_id]
            while stack:
                for child in children.get(stack.pop(),[]):
                    if child not in found:found.add(child);stack.append(child)
            return found
        def phrase(ids):return clean_join([word.text for word in words if word.id in ids])

        clauses=[];clause_ids=set()
        for word in words:
            if word.deprel not in CLAUSE_LABELS:continue
            ids=descendants(word.id);clause_ids.update(ids)
            markers=[by_id[item].text for item in children.get(word.id,[]) if by_id[item].deprel=="mark"]
            marker=(markers[0].casefold() if markers else "")
            label=MARK_LABELS.get(marker,CLAUSE_LABELS[word.deprel])
            clauses.append({"type":label,"relation":word.deprel,"marker":markers[0] if markers else "","text":phrase(ids),"head":word.text})

        subjects=[word for word in words if word.deprel in {"nsubj","nsubj:pass","csubj","csubj:pass"} and (word.head==root.id or by_id.get(word.head,root).deprel in {"root","cop"})]
        objects=[word for word in words if word.deprel in {"obj","iobj"} and word.head==root.id]
        complements=[word for word in words if word.deprel in {"xcomp","ccomp"} and word.head==root.id]
        subject_ids=set().union(*(descendants(word.id) for word in subjects)) if subjects else set()
        object_ids=set().union(*(descendants(word.id) for word in objects)) if objects else set()
        complement_ids=set().union(*(descendants(word.id) for word in complements)) if complements else set()
        inverted_cop=next((word for word in words if word.head==root.id and word.deprel=="parataxis" and word.upos=="AUX" and (word.lemma or "").casefold()=="be" and any(by_id[item].deprel=="nsubj" for item in children.get(word.id,[]))),None)
        if inverted_cop:
            subjects=[by_id[item] for item in children.get(inverted_cop.id,[]) if by_id[item].deprel=="nsubj"]
            subject_ids=set().union(*(descendants(word.id) for word in subjects));object_ids=descendants(root.id)-descendants(inverted_cop.id)-{word.id for word in words if word.upos=="PUNCT"};complement_ids=set(object_ids)
        predicate_core={root.id,*[word.id for word in words if word.head==root.id and word.deprel in {"aux","aux:pass","cop","compound:prt","neg"}]}
        predicate_ids={inverted_cop.id} if inverted_cop else set(predicate_core)
        for word in words:
            if word.head==root.id and word.deprel=="compound:prt":predicate_ids.add(word.id)
            if word.head==root.id and word.deprel=="conj":predicate_ids.update(descendants(word.id)-subject_ids-object_ids-clause_ids-{item.id for item in words if item.upos=="PUNCT"})

        has_coordination=any(word.deprel=="conj" and word.upos in {"VERB","AUX","ADJ","NOUN"} for word in words)
        has_subordinate=bool(clauses)
        if has_coordination and has_subordinate:sentence_type="并列复合句"
        elif has_coordination:sentence_type="并列句"
        elif has_subordinate:sentence_type="主从复合句"
        else:sentence_type="简单句"

        main_root=inverted_cop or root
        main_words=[word for word in words if word.id==main_root.id or (word.head==main_root.id and (word.deprel.startswith("aux") or word.deprel=="cop"))]
        auxiliary=[word.text.casefold() for word in main_words if word.upos=="AUX"]
        features=[feat_map(word.feats) for word in main_words if word.upos in {"VERB","AUX"}]
        grammar_points=[]
        perfect=any(value in auxiliary for value in ("have","has","had")) and ("been" in auxiliary or any(item.get("VerbForm")=="Part" for item in features))
        progressive=any(value in auxiliary for value in ("am","is","are","was","were","be","been")) and (any(item.get("VerbForm")=="Ger" for item in features) or root.text.casefold().endswith("ing"))
        if perfect and progressive:grammar_points.append("现在完成进行时" if any(value in auxiliary for value in ("have","has")) else "过去完成进行时")
        elif perfect:grammar_points.append("现在完成时" if any(value in auxiliary for value in ("have","has")) else "过去完成时")
        elif progressive:grammar_points.append("现在进行时" if any(value in auxiliary for value in ("am","is","are")) else "过去进行时")
        elif "will" in auxiliary or "shall" in auxiliary:grammar_points.append("一般将来时或将来表达")
        elif any(item.get("Tense")=="Past" for item in features):grammar_points.append("一般过去时")
        elif any(item.get("Tense")=="Pres" for item in features):grammar_points.append("一般现在时")
        passive=any(word.deprel in {"aux:pass","nsubj:pass","csubj:pass"} for word in words) or any(item.get("Voice")=="Pass" for item in features)
        if passive:grammar_points.append("被动语态")
        modals=[word.text for word in words if word.xpos=="MD"]
        if modals:grammar_points.append("情态动词 "+" / ".join(dict.fromkeys(modals)))
        if any(word.deprel=="neg" for word in words):grammar_points.append("否定结构")
        if text.rstrip().endswith("?"):grammar_points.append("疑问句")
        for clause in clauses:
            if clause["type"] not in grammar_points:grammar_points.append(clause["type"])

        subject_text=phrase(subject_ids) or "（省略或由上下文确定）"
        predicate_text=phrase(predicate_ids) or root.text
        object_text=phrase(object_ids) or phrase(complement_ids)
        pattern="主语 + 谓语"+(" + 宾语/补语" if object_text else "")
        if inverted_cop or (root.upos not in {"VERB","AUX"} and any(word.deprel=="cop" for word in words)):pattern="主语 + 系动词 + 表语"
        roles=[]
        for word in words:
            if word.id in clause_ids:role="clause"
            elif word.id in subject_ids:role="subject"
            elif word.id in object_ids or word.id in complement_ids:role="object"
            elif word.id in predicate_ids:role="predicate"
            else:role="modifier"
            if word.upos=="PUNCT":role="punctuation"
            roles.append({"id":word.id,"text":word.text,"lemma":word.lemma or word.text.casefold(),"pos":word.upos,"posZh":POS_ZH.get(word.upos,word.upos),"relation":word.deprel,"head":word.head,"role":role})

        summary=f"这是一个{sentence_type}，基本结构是“{pattern}”。主语是“{subject_text}”，谓语部分是“{predicate_text}”"
        if object_text:summary+=f"，宾语或补语是“{object_text}”"
        summary+="。"
        if clauses:summary+=" 句中包含"+"、".join(dict.fromkeys(clause["type"] for clause in clauses))+"。"
        if grammar_points:summary+=" 需要关注："+"、".join(grammar_points)+"。"

        return {"analysisVersion":ANALYSIS_VERSION,"text":text,"sentenceType":sentence_type,"pattern":pattern,"subject":subject_text,"predicate":predicate_text,"object":object_text,
                "clauses":clauses,"grammarPoints":grammar_points,"tokens":roles,"constituency":str(sentence.constituency),"explanation":summary,"source":"Stanza 本地句法模型"}
