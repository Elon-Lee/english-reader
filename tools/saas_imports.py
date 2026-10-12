#!/usr/bin/env python3
"""Tenant-safe PostgreSQL-native private document, audio, and video imports.

Legacy import workers write SQLite, so they are intentionally not invoked here.
The YouTube downloader remains isolated until it has the same tenant contract.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from saas_auth import ROOT, SaaSError, SaaSService, new_id, utcnow
from build_video_book import duration as media_duration, whisper_book
from saas_media import MediaService
from saas_membership import MembershipService, as_json, timestamp
from youtube_subtitles import has_translated_english_track, select_chinese_track, select_native_english_track


IMPORT_FEATURES={"mp3":"mp3_imports","video":"video_imports","youtube":"youtube_imports"}
UPLOAD_LIMITS={"text":20*1024*1024,"document":100*1024*1024,"mp3":2*1024*1024*1024,"video":20*1024*1024*1024}


class WorkspaceImportService:
    def __init__(self, accounts:SaaSService,memberships:MembershipService,media:MediaService,pdf_ocr:Path|None=None,whisper_cli:Path|None=None,whisper_model:Path|None=None,audio_duration=None,ffmpeg:Path|None=None,yt_dlp:Path|None=None,node:Path|None=None):
        self.accounts,self.memberships,self.media=accounts,memberships,media
        self.pdf_ocr=(pdf_ocr or Path(os.environ.get("SHIYUE_PDF_OCR",str(ROOT/".local/bin/pdf_ocr")))).expanduser()
        self.whisper_cli=(whisper_cli or Path(os.environ.get("SHIYUE_WHISPER_CLI",str(ROOT/"tools/vendor/whisper.cpp/build/bin/whisper-cli")))).expanduser()
        self.whisper_model=(whisper_model or Path(os.environ.get("SHIYUE_WHISPER_MODEL",str(ROOT/"tools/vendor/whisper.cpp/models/ggml-base.en.bin")))).expanduser()
        self.audio_duration=audio_duration or media_duration
        self.ffmpeg=(ffmpeg or Path(os.environ.get("SHIYUE_FFMPEG","ffmpeg"))).expanduser()
        self.yt_dlp=(yt_dlp or Path(os.environ.get("SHIYUE_YTDLP",str(ROOT/".local/bin/yt-dlp")))).expanduser()
        self.node=(node or Path(os.environ.get("SHIYUE_NODE",shutil.which("node") or "/usr/local/bin/node"))).expanduser()

    def _user(self,cursor:Any,user_id:str)->dict[str,Any]:
        cursor.execute("SELECT id,status FROM users WHERE id=%s FOR UPDATE",(user_id,));user=self.accounts._one(cursor)
        if not user or user["status"]!="active":raise SaaSError("account_unavailable","账号不可用。",403)
        return user

    def _task(self,cursor:Any,user_id:str,task_id:str,lock:bool=True)->dict[str,Any]:
        cursor.execute(f"SELECT * FROM workspace_import_tasks WHERE id=%s AND user_id=%s {'FOR UPDATE' if lock else ''}",(task_id,user_id));task=self.accounts._one(cursor)
        if not task:raise SaaSError("import_task_not_found","导入任务不存在或你无权访问。",404)
        return task

    @staticmethod
    def _public(task:dict[str,Any])->dict[str,Any]:
        return {"id":task["id"],"kind":task["kind"],"status":task["status"],"title":task["title"],"originalFilename":task["original_filename"],"sourceUrl":task["source_url"],"sourceAssetId":task["source_asset_id"],"outputBookId":task["output_book_id"],"planVersion":task["plan_version_id"],"progress":int(task["progress"]),"step":task["step"],"error":task["error"],"createdAt":timestamp(task["created_at"]),"updatedAt":timestamp(task["updated_at"]),"completedAt":timestamp(task["completed_at"])}

    def create(self,user_id:str,kind:str,title:str,filename:str,idempotency_key:str,source_url:str="",metadata:dict[str,Any]|None=None)->dict[str,Any]:
        kind=str(kind or "").strip().casefold();key=str(idempotency_key or "").strip();filename=Path(str(filename or "")).name
        if kind not in {"text","document","mp3","video","youtube"}:raise SaaSError("invalid_import_kind","不支持的导入类型。",400)
        if not key or len(key)>255:raise SaaSError("invalid_idempotency_key","操作标识无效。",400)
        if kind=="youtube" and not self._valid_youtube_url(source_url):raise SaaSError("invalid_import_source","请输入有效的 YouTube 地址。",400)
        reservation=None
        feature=IMPORT_FEATURES.get(kind)
        if feature:
            reservation=self.memberships.reserve(user_id,feature,f"import:{kind}:{key}",1,{"kind":kind,"filename":filename,"sourceUrl":str(source_url or "")})["reservation"]
        try:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    self._user(cursor,user_id);cursor.execute("SELECT * FROM workspace_import_tasks WHERE user_id=%s AND idempotency_key=%s FOR UPDATE",(user_id,key));existing=self.accounts._one(cursor)
                    if existing:return {"task":self._public(existing),"idempotent":True}
                    context=self.memberships._context(cursor,user_id)
                    task_id=new_id();status="queued" if kind=="youtube" else "uploading";step="等待上传源文件" if status=="uploading" else "等待 PostgreSQL 原生处理器"
                    cursor.execute("""INSERT INTO workspace_import_tasks(id,user_id,workspace_id,kind,status,title,original_filename,source_url,quota_reservation_id,plan_version_id,step,metadata_json,idempotency_key)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",(task_id,user_id,user_id,kind,status,str(title or "").strip()[:300],filename,str(source_url or "")[:2000],reservation["id"] if reservation else None,context["plan"]["id"],step,json.dumps(metadata or {}),key))
                    cursor.execute("SELECT * FROM workspace_import_tasks WHERE id=%s",(task_id,));return {"task":self._public(self.accounts._one(cursor)or{}),"idempotent":False}
        except Exception:
            if reservation:self.memberships.release(user_id,reservation["id"])
            raise

    @staticmethod
    def _valid_youtube_url(value:Any)->bool:
        try:
            parsed=urlsplit(str(value or "").strip());host=(parsed.hostname or "").casefold()
            return parsed.scheme in {"http","https"} and (host=="youtu.be" or host=="youtube.com" or host.endswith(".youtube.com"))
        except ValueError:return False

    def upload(self,user_id:str,task_id:str,filename:str,data:bytes,content_type:str="application/octet-stream")->dict[str,Any]:
        if not data:raise SaaSError("empty_upload","上传文件为空。",400)
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                task=self._task(cursor,user_id,task_id);kind=task["kind"]
                if kind=="youtube":raise SaaSError("upload_not_required","YouTube 任务不接受文件上传。",409)
                if task["status"] not in {"uploading","failed"}:raise SaaSError("import_task_not_uploadable","该任务当前不能上传源文件。",409)
                limit=UPLOAD_LIMITS.get(kind,20*1024*1024)
                if len(data)>limit:raise SaaSError("upload_too_large","上传文件超过该类型的大小限制。",413,{"limit":limit})
                # Avoid overwriting a prior source asset.  The media service
                # re-checks private storage in its own transaction.
                safe_name=re.sub(r"[^A-Za-z0-9._-]+","-",Path(filename or task["original_filename"] or "source").name).strip("-") or "source"
                relative=f"private-uploads/{user_id}/{task_id}/{safe_name}"
        self.media.ensure_private_capacity(user_id,len(data))
        _,target=self.media._safe_path(relative);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(data)
        try:
            asset=self.media.register(user_id,user_id,"private",relative,"import-source",content_type)
        except Exception:
            try:target.unlink(missing_ok=True)
            except OSError:pass
            raise
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                task=self._task(cursor,user_id,task_id);old_asset=task.get("source_asset_id")
                cursor.execute("UPDATE workspace_import_tasks SET source_asset_id=%s,original_filename=%s,status='queued',progress=15,step='源文件已上传，等待处理',error='',updated_at=NOW() WHERE id=%s",(asset["id"],safe_name,task_id))
                if old_asset and old_asset!=asset["id"]:
                    cursor.execute("UPDATE media_assets SET status='deleted',deleted_at=NOW() WHERE id=%s",(old_asset,))
                cursor.execute("SELECT * FROM workspace_import_tasks WHERE id=%s",(task_id,));return self._public(self.accounts._one(cursor)or{})

    def _source_path(self,cursor:Any,user_id:str,task:dict[str,Any])->Path:
        asset_id=task.get("source_asset_id")
        if not asset_id:raise SaaSError("import_source_missing","导入任务尚未上传源文件。",409)
        cursor.execute("SELECT * FROM media_assets WHERE id=%s AND owner_id=%s AND scope='private' AND status='active' FOR UPDATE",(asset_id,user_id));asset=self.accounts._one(cursor)
        if not asset:raise SaaSError("import_source_missing","导入源文件不存在。",404)
        _,path=self.media._safe_path(asset["storage_path"])
        if not path.is_file():raise SaaSError("import_source_missing","导入源文件在存储中不存在。",404)
        return path

    @staticmethod
    def _sentences(text:str)->list[dict[str,Any]]:
        source=re.sub(r"\r\n?","\n",text);parts=re.split(r"(?<=[.!?。！？])\s+|\n{2,}",source);sentences=[]
        for part in parts:
            value=re.sub(r"\s+"," ",part).strip()
            if not value:continue
            words=[{"text":word} for word in re.findall(r"[A-Za-z]+(?:['’][A-Za-z]+)?|\d+",value)]
            sentences.append({"id":f"s-{len(sentences)+1}","text":value,"translation":"","words":words})
        return sentences

    def _document_text(self,source:Path,kind:str)->tuple[str,dict[str,Any]]:
        suffix=source.suffix.casefold()
        if kind=="text" or suffix in {".txt",".md",".markdown"}:
            try:return source.read_text(encoding="utf-8"),{"extractor":"utf8-text"}
            except UnicodeDecodeError:return source.read_text(encoding="utf-8",errors="replace"),{"extractor":"utf8-text-replacement"}
        if suffix==".pdf":
            if not self.pdf_ocr.is_file():raise SaaSError("pdf_ocr_unavailable","本机 PDF OCR 处理器未安装。",503)
            with tempfile.TemporaryDirectory(prefix="shiyue-pg-import-pdf-") as temporary:
                root=Path(temporary);ocr_file=root/"ocr.json";pages=root/"pages"
                try:subprocess.run([str(self.pdf_ocr),str(source),str(ocr_file),str(pages),"1.2"],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=240)
                except subprocess.TimeoutExpired as exc:raise SaaSError("pdf_ocr_timeout","PDF OCR 超时。",504) from exc
                except subprocess.CalledProcessError as exc:raise SaaSError("pdf_ocr_failed","PDF OCR 处理失败。",422) from exc
                try:pages_data=json.loads(ocr_file.read_text(encoding="utf-8"))
                except (OSError,json.JSONDecodeError) as exc:raise SaaSError("pdf_ocr_failed","PDF OCR 没有产生可读文本。",422) from exc
                lines=[]
                for page in pages_data if isinstance(pages_data,list) else []:
                    for line in page.get("lines",[]) if isinstance(page,dict) else []:
                        value=str(line.get("text","")).strip() if isinstance(line,dict) else ""
                        if value:lines.append(value)
                return "\n\n".join(lines),{"extractor":"local-pdf-ocr","pages":len(pages_data) if isinstance(pages_data,list) else 0,"lines":len(lines)}
        raise SaaSError("unsupported_document","当前原生文档处理器仅支持 TXT、Markdown 和 PDF。",422)

    def _audio_book(self,source:Path,task_id:str,title:str)->tuple[dict[str,Any],dict[str,Any]]:
        if not self.whisper_cli.is_file() or not self.whisper_model.is_file():
            raise SaaSError("whisper_unavailable","本机 Whisper 处理器或模型未安装。",503)
        with tempfile.TemporaryDirectory(prefix="shiyue-pg-import-audio-") as temporary:
            prefix=Path(temporary)/"whisper"
            command=[str(self.whisper_cli),"-m",str(self.whisper_model),"-f",str(source),"-l","en","-t",os.environ.get("SHIYUE_WHISPER_THREADS","3"),"-p","2","-ng","-dtw","base.en","-ml","1","-sow","-ojf","-of",str(prefix),"-np"]
            try:subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1800)
            except subprocess.TimeoutExpired as exc:raise SaaSError("whisper_timeout","MP3 转写超时。",504) from exc
            except subprocess.CalledProcessError as exc:raise SaaSError("whisper_failed","MP3 Whisper 转写失败。",422) from exc
            transcript_path=prefix.with_suffix(".json")
            try:transcript=json.loads(transcript_path.read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError) as exc:raise SaaSError("whisper_failed","Whisper 没有产生可读转写。",422) from exc
        sentences,segmentation=whisper_book(transcript)
        if not sentences:raise SaaSError("empty_audio_transcript","未从 MP3 中识别到可导入英文内容。",422)
        try:duration=float(self.audio_duration(source))
        except Exception as exc:raise SaaSError("audio_probe_failed","无法读取 MP3 时长。",422) from exc
        book={"id":f"private-{task_id}","title":title,"englishTitle":title,"sourceType":"audio","duration":duration,"alignment":"whisper-dtw-normalized","sentences":sentences,"whisper":{"engine":"whisper.cpp","model":self.whisper_model.name,"timestampMethod":"dtw","transcribedWords":sum(len(sentence.get("words",[])) for sentence in sentences)},"segmentation":segmentation}
        return book,{"extractor":"whisper.cpp","model":self.whisper_model.name,"sentences":len(sentences),"duration":duration}

    def _video_book(self,source:Path,task_id:str,title:str,asset_id:str)->tuple[dict[str,Any],dict[str,Any],list[dict[str,str]]]:
        if not self.whisper_cli.is_file() or not self.whisper_model.is_file():
            raise SaaSError("whisper_unavailable","本机 Whisper 处理器或模型未安装。",503)
        source=source.resolve();output_dir=source.parent;audio_path=output_dir/"audio.m4a";cover_path=output_dir/"cover.jpg";low_video_path=output_dir/"video-low.mp4"
        audio_relative=audio_path.relative_to(self.media.media_root).as_posix();cover_relative=cover_path.relative_to(self.media.media_root).as_posix();low_video_relative=low_video_path.relative_to(self.media.media_root).as_posix()
        try:
            with tempfile.TemporaryDirectory(prefix="shiyue-pg-import-video-") as temporary:
                root=Path(temporary);whisper_audio=root/"whisper.wav";prefix=root/"whisper";ffmpeg=str(self.ffmpeg)
                commands=[
                    [ffmpeg,"-y","-v","error","-i",str(source),"-vn","-c:a","aac","-b:a","128k",str(audio_path)],
                    [ffmpeg,"-y","-v","error","-i",str(source),"-vn","-ar","16000","-ac","1","-c:a","pcm_s16le",str(whisper_audio)],
                    [ffmpeg,"-y","-v","error","-ss","0","-i",str(source),"-frames:v","1","-vf","scale=960:-2",str(cover_path)],
                    [ffmpeg,"-y","-v","error","-i",str(source),"-map","0:v:0","-an","-vf","scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2","-c:v","libx264","-preset","veryfast","-crf","27","-maxrate","380k","-bufsize","760k","-g","50","-keyint_min","50","-pix_fmt","yuv420p","-threads","2","-movflags","+faststart",str(low_video_path)],
                ]
                for command in commands:
                    try:subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
                    except FileNotFoundError as exc:raise SaaSError("ffmpeg_unavailable","本机 FFmpeg 未安装。",503) from exc
                    except subprocess.TimeoutExpired as exc:raise SaaSError("video_processing_timeout","视频音频或封面提取超时。",504) from exc
                    except subprocess.CalledProcessError as exc:raise SaaSError("video_processing_failed","FFmpeg 无法处理该视频。",422) from exc
                command=[str(self.whisper_cli),"-m",str(self.whisper_model),"-f",str(whisper_audio),"-l","en","-t",os.environ.get("SHIYUE_WHISPER_THREADS","3"),"-p","2","-ng","-dtw","base.en","-ml","1","-sow","-ojf","-of",str(prefix),"-np"]
                try:subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1800)
                except subprocess.TimeoutExpired as exc:raise SaaSError("whisper_timeout","视频转写超时。",504) from exc
                except subprocess.CalledProcessError as exc:raise SaaSError("whisper_failed","视频 Whisper 转写失败。",422) from exc
                try:transcript=json.loads(prefix.with_suffix(".json").read_text(encoding="utf-8"))
                except (OSError,json.JSONDecodeError) as exc:raise SaaSError("whisper_failed","Whisper 没有产生可读视频转写。",422) from exc
            sentences,segmentation=whisper_book(transcript)
            if not sentences:raise SaaSError("empty_video_transcript","未从视频中识别到可导入英文内容。",422)
            try:duration=float(self.audio_duration(source))
            except Exception as exc:raise SaaSError("video_probe_failed","无法读取视频时长。",422) from exc
            base=f"/api/media/{asset_id}"
            book={"id":f"private-{task_id}","title":title,"englishTitle":title,"sourceType":"video","duration":duration,"alignment":"whisper-dtw-normalized","video":base,"videoDefaultQuality":"high","videoVariants":{"high":{"label":"高清","url":base,"status":"ready"},"low":{"label":"流畅","url":f"{base}?variant=low","status":"ready"}},"audio":f"{base}?variant=audio","cover":f"{base}?variant=cover","sentences":sentences,"whisper":{"engine":"whisper.cpp","model":self.whisper_model.name,"timestampMethod":"dtw","transcribedWords":sum(len(sentence.get("words",[])) for sentence in sentences)},"segmentation":segmentation}
            extractor={"extractor":"ffmpeg+whisper.cpp","model":self.whisper_model.name,"sentences":len(sentences),"duration":duration}
            variants=[{"name":"audio","storagePath":audio_relative,"contentType":"audio/mp4"},{"name":"cover","storagePath":cover_relative,"contentType":"image/jpeg"},{"name":"low","storagePath":low_video_relative,"contentType":"video/mp4"}]
            return book,extractor,variants
        except Exception:
            audio_path.unlink(missing_ok=True);cover_path.unlink(missing_ok=True);low_video_path.unlink(missing_ok=True)
            raise

    def _run_ytdlp(self,command:list[Any],timeout:int)->subprocess.CompletedProcess[str]:
        if not self.yt_dlp.is_file():raise SaaSError("youtube_downloader_unavailable","本机 yt-dlp 未安装。",503)
        try:return subprocess.run([str(item) for item in command],check=True,text=True,capture_output=True,timeout=timeout)
        except subprocess.TimeoutExpired as exc:raise SaaSError("youtube_download_timeout","YouTube 下载超时。",504) from exc
        except subprocess.CalledProcessError as exc:
            detail=(exc.stderr or exc.stdout or "").strip().splitlines()
            raise SaaSError("youtube_download_failed",(detail[-1] if detail else "YouTube 下载失败，请检查地址、网络或访问权限。")[:500],422) from exc

    def _youtube_caption(self,url:str,track:dict[str,Any]|None,prefix:str,destination:Path)->Path|None:
        if not track:return None
        flag="--write-subs" if track.get("source")=="manual" else "--write-auto-subs"
        template=destination/f"{prefix}.%(ext)s"
        try:self._run_ytdlp([self.yt_dlp,"--js-runtimes",f"node:{self.node}","--no-playlist","--skip-download",flag,"--sub-langs",track.get("code",""),"--sub-format","srt","--convert-subs","srt","-o",template,url],180)
        except SaaSError:return None
        candidates=sorted(destination.glob(f"{prefix}*.srt"))
        if not candidates:return None
        target=destination/("subtitles.en.srt" if prefix=="english" else "subtitles.zh-CN.srt")
        if candidates[0]!=target:shutil.move(candidates[0],target)
        for stale in destination.glob(f"{prefix}*.srt"):
            if stale!=target:stale.unlink(missing_ok=True)
        return target

    def _youtube_download(self,user_id:str,task_id:str,url:str)->tuple[Path,str,dict[str,Any],list[dict[str,str]]]:
        if not self.node.is_file():raise SaaSError("youtube_runtime_unavailable","本机 Node.js 运行时未安装。",503)
        info_result=self._run_ytdlp([self.yt_dlp,"--js-runtimes",f"node:{self.node}","--dump-single-json","--no-playlist","--skip-download",url],180)
        try:info=json.loads(info_result.stdout)
        except json.JSONDecodeError as exc:raise SaaSError("youtube_info_failed","yt-dlp 没有返回可读的视频信息。",422) from exc
        with tempfile.TemporaryDirectory(prefix="shiyue-pg-import-youtube-") as temporary:
            stage=Path(temporary);english_track=select_native_english_track(info);chinese_track=select_chinese_track(info)
            english=self._youtube_caption(url,english_track,"english",stage);chinese=self._youtube_caption(url,chinese_track,"chinese",stage)
            self._run_ytdlp([self.yt_dlp,"--js-runtimes",f"node:{self.node}","--no-playlist","--newline","--retries","5","--fragment-retries","5","-f","bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*[height<=720]+ba/b[height<=720]/best[height<=720]","--merge-output-format","mp4","-o",stage/"source.%(ext)s",url],3600)
            source=next(iter(sorted(stage.glob("source.mp4"))+sorted(stage.glob("source.mkv"))+sorted(stage.glob("source.webm"))+sorted(stage.glob("source.mov"))),None)
            if not source:raise SaaSError("youtube_download_failed","下载完成但没有找到视频文件。",422)
            if source.suffix.casefold()!=".mp4":
                converted=stage/"source.mp4"
                try:subprocess.run([str(self.ffmpeg),"-y","-v","error","-i",str(source),"-c","copy",str(converted)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
                except (FileNotFoundError,subprocess.TimeoutExpired,subprocess.CalledProcessError) as exc:raise SaaSError("youtube_remux_failed","YouTube 视频无法转换为 MP4。",422) from exc
                source=converted
            if source.stat().st_size>UPLOAD_LIMITS["video"]:raise SaaSError("upload_too_large","YouTube 视频超过本地视频大小限制。",413,{"limit":UPLOAD_LIMITS["video"]})
            relative_dir=f"private-uploads/{user_id}/{task_id}";relative=f"{relative_dir}/source.mp4";_,target=self.media._safe_path(relative)
            self.media.ensure_private_capacity(user_id,source.stat().st_size);target.parent.mkdir(parents=True,exist_ok=True);shutil.move(source,target)
            staged_captions=[]
            for caption,name,content_type in ((english,"subtitles-en","application/x-subrip"),(chinese,"subtitles-zh-CN","application/x-subrip")):
                if not caption:continue
                caption_target=target.parent/caption.name;shutil.move(caption,caption_target);staged_captions.append({"name":name,"storagePath":f"{relative_dir}/{caption_target.name}","contentType":content_type})
        try:asset=self.media.register(user_id,user_id,"private",relative,"youtube","video/mp4")
        except Exception:
            try:target.unlink(missing_ok=True)
            except OSError:pass
            for item in staged_captions:
                try:self.media._safe_path(item["storagePath"])[1].unlink(missing_ok=True)
                except (OSError,SaaSError):pass
            raise
        metadata={
            "sourceUrl":url,"youtubeId":str(info.get("id","")or""),"channel":str(info.get("channel") or info.get("uploader") or ""),
            "title":str(info.get("title") or ""),"duration":float(info.get("duration",0)or 0),
            "youtubeSubtitleSource":english_track.get("source","") if english_track else "none","youtubeSubtitleTrack":english_track.get("code","") if english_track else "",
            "youtubeSubtitleDownloaded":bool(english),"youtubeChineseSubtitleSource":chinese_track.get("source","") if chinese_track else "none",
            "youtubeChineseSubtitleTrack":chinese_track.get("code","") if chinese_track else "","youtubeChineseSubtitleDownloaded":bool(chinese),
            "youtubeChineseSubtitleTranslated":bool(chinese_track and chinese_track.get("translated")),"translatedEnglishRejected":has_translated_english_track(info),
        }
        try:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    task=self._task(cursor,user_id,task_id)
                    if task["status"]!="running":raise SaaSError("import_task_terminal","任务在 YouTube 下载期间已取消或结束。",409)
                    task_title=str(task["title"] or metadata["title"] or "YouTube 视频").strip()[:300]
                    cursor.execute("UPDATE workspace_import_tasks SET source_asset_id=%s,title=%s,original_filename='source.mp4',progress=45,step='YouTube 下载完成，开始音视频处理',metadata_json=%s::jsonb,updated_at=NOW() WHERE id=%s",(asset["id"],task_title,json.dumps(metadata,ensure_ascii=False),task_id))
        except Exception:
            try:self.media.delete(user_id,asset["id"])
            except SaaSError:pass
            for item in staged_captions:
                try:self.media._safe_path(item["storagePath"])[1].unlink(missing_ok=True)
                except (OSError,SaaSError):pass
            raise
        return target,asset["id"],metadata,staged_captions

    def complete(self,user_id:str,task_id:str)->dict[str,Any]:
        """Run document extraction outside database transactions.

        The task is marked running first, then OCR/text extraction happens with
        no user-row lock held.  The final transaction rechecks task state so a
        concurrent cancellation cannot publish a book after cancellation.
        """
        reservation_id=None;pending_variant_paths=[]
        try:
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    task=self._task(cursor,user_id,task_id)
                    if task["status"]=="complete":return {"task":self._public(task),"idempotent":True}
                    if task["status"] in {"cancelled","failed"}:raise SaaSError("import_task_terminal","该任务已经结束。",409)
                    if task["kind"] not in {"text","document","mp3","video","youtube"}:
                        cursor.execute("UPDATE workspace_import_tasks SET status='awaiting_processor',progress=20,step='等待 PostgreSQL 原生处理器迁移',updated_at=NOW() WHERE id=%s",(task_id,));cursor.execute("SELECT * FROM workspace_import_tasks WHERE id=%s",(task_id,));return {"task":self._public(self.accounts._one(cursor)or{}),"idempotent":False}
                    source=None if task["kind"]=="youtube" else self._source_path(cursor,user_id,task)
                    work={"kind":task["kind"],"title":task["title"],"filename":task["original_filename"],"source_url":task["source_url"],"source_asset_id":task["source_asset_id"],"reservation_id":task["quota_reservation_id"]}
                    step="下载 YouTube 视频和字幕" if task["kind"]=="youtube" else "提取音频、封面并转写" if task["kind"]=="video" else "提取文本并分句"
                    cursor.execute("UPDATE workspace_import_tasks SET status='running',progress=35,step=%s,updated_at=NOW() WHERE id=%s",(step,task_id))
            title=str(work["title"] or Path(work["filename"] or "私人文本").stem).strip() or "私人文本"
            if work["kind"]=="mp3":
                if source.suffix.casefold()!=".mp3":raise SaaSError("unsupported_audio","当前原生音频处理器仅支持 MP3。",422)
                data,extractor=self._audio_book(source,task_id,title);source_type="audio";book_id=data["id"]
            elif work["kind"]=="video":
                if source.suffix.casefold() not in {".mp4",".mov",".m4v",".mkv",".webm"}:raise SaaSError("unsupported_video","当前原生视频处理器仅支持 MP4、MOV、M4V、MKV 和 WebM。",422)
                data,extractor,variants=self._video_book(source,task_id,title,work["source_asset_id"]);source_type="video";book_id=data["id"]
                pending_variant_paths=[variant["storagePath"] for variant in variants]
                try:self.media.add_variants(user_id,work["source_asset_id"],variants)
                except Exception:
                    for variant in variants:
                        try:self.media._safe_path(variant["storagePath"])[1].unlink(missing_ok=True)
                        except (OSError,SaaSError):pass
                    raise
                pending_variant_paths=[]
            elif work["kind"]=="youtube":
                source,asset_id,youtube,captions=self._youtube_download(user_id,task_id,work["source_url"]);work["source_asset_id"]=asset_id
                title=str(work["title"] or youtube.get("title") or "YouTube 视频").strip() or "YouTube 视频"
                pending_variant_paths=[variant["storagePath"] for variant in captions]
                data,extractor,variants=self._video_book(source,task_id,title,asset_id);data["sourceType"]="youtube";data["youtube"]=youtube;source_type="youtube";book_id=data["id"]
                variants.extend(captions);pending_variant_paths=[variant["storagePath"] for variant in variants]
                try:self.media.add_variants(user_id,asset_id,variants)
                except Exception:
                    for variant in variants:
                        try:self.media._safe_path(variant["storagePath"])[1].unlink(missing_ok=True)
                        except (OSError,SaaSError):pass
                    raise
                pending_variant_paths=[]
            else:
                text,extractor=self._document_text(source,work["kind"]);sentences=self._sentences(text)
                if not sentences:raise SaaSError("empty_import_text","未从源文件提取到可导入的文本。",400)
                source_type="document" if work["kind"]=="document" else "text";book_id=f"private-{task_id}";data={"id":book_id,"title":title,"englishTitle":title,"sentences":sentences,"sourceType":source_type,"import":{"kind":work["kind"],"extractor":extractor}}
            data["import"]={"kind":work["kind"],"extractor":extractor}
            with self.accounts.transaction() as connection:
                with connection.cursor() as cursor:
                    current=self._task(cursor,user_id,task_id)
                    if current["status"]=="complete":return {"task":self._public(current),"idempotent":True}
                    if current["status"]!="running":raise SaaSError("import_task_terminal","任务在处理期间已取消或结束。",409)
                    cursor.execute("""INSERT INTO content_books(id,owner_id,title,english_title,series,level,source_type,source_path,status,visibility,cover_url,page_base_url,audio_url,pdf_url,video_url,duration,alignment,data_json,quality_json,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,'私人导入','',%s,%s,'ready','private',%s,'',%s,'',%s,%s,%s,%s::jsonb,'{}'::jsonb,NOW(),NOW())""",(book_id,user_id,title,title,source_type,f"workspace/{user_id}/{task_id}",str(data.get("cover","")or""),str(data.get("audio","")or""),str(data.get("video","")or""),float(data.get("duration",0)or 0),str(data.get("alignment","")or""),json.dumps(data,ensure_ascii=False)))
                    cursor.execute("UPDATE media_assets SET content_book_id=%s,kind=%s WHERE id=%s",(book_id,source_type,work["source_asset_id"]))
                    cursor.execute("UPDATE workspace_import_tasks SET status='complete',output_book_id=%s,progress=100,step='导入完成',completed_at=NOW(),updated_at=NOW() WHERE id=%s",(book_id,task_id))
                    cursor.execute("SELECT * FROM workspace_import_tasks WHERE id=%s",(task_id,));completed=self.accounts._one(cursor)or{}
            reservation_id=completed.get("quota_reservation_id")
        except Exception as exc:
            for relative in pending_variant_paths:
                try:self.media._safe_path(relative)[1].unlink(missing_ok=True)
                except (OSError,SaaSError):pass
            if not (isinstance(exc,SaaSError) and exc.code=="import_task_terminal"):
                self.fail(user_id,task_id,str(exc))
            raise
        if reservation_id:self.memberships.settle(user_id,reservation_id)
        return {"task":self._public(completed),"idempotent":False}

    def fail(self,user_id:str,task_id:str,error:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                task=self._task(cursor,user_id,task_id)
                if task["status"] in {"complete","cancelled"}:return {"task":self._public(task),"idempotent":True}
                cursor.execute("UPDATE workspace_import_tasks SET status='failed',step='导入失败',error=%s,updated_at=NOW() WHERE id=%s",(str(error)[:2000],task_id));cursor.execute("SELECT * FROM workspace_import_tasks WHERE id=%s",(task_id,));failed=self.accounts._one(cursor)or{}
        if failed.get("quota_reservation_id"):
            try:self.memberships.release(user_id,failed["quota_reservation_id"])
            except SaaSError:pass
        if failed.get("source_asset_id"):
            try:self.media.delete(user_id,failed["source_asset_id"])
            except SaaSError:pass
        return {"task":self._public(failed),"idempotent":False}

    def cancel(self,user_id:str,task_id:str)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                task=self._task(cursor,user_id,task_id)
                if task["status"]=="complete":raise SaaSError("import_task_complete","已完成任务不能取消。",409)
                if task["status"]=="cancelled":return {"task":self._public(task),"idempotent":True}
                cursor.execute("UPDATE workspace_import_tasks SET status='cancelled',step='用户取消任务',updated_at=NOW() WHERE id=%s",(task_id,));cursor.execute("SELECT * FROM workspace_import_tasks WHERE id=%s",(task_id,));cancelled=self.accounts._one(cursor)or{}
        if cancelled.get("quota_reservation_id"):
            try:self.memberships.release(user_id,cancelled["quota_reservation_id"])
            except SaaSError:pass
        if cancelled.get("source_asset_id"):
            try:self.media.delete(user_id,cancelled["source_asset_id"])
            except SaaSError:pass
        return {"task":self._public(cancelled),"idempotent":False}

    def list(self,user_id:str,limit:Any=100)->dict[str,Any]:
        with self.accounts.transaction() as connection:
            with connection.cursor() as cursor:
                self._user(cursor,user_id);cursor.execute("SELECT * FROM workspace_import_tasks WHERE user_id=%s ORDER BY created_at DESC LIMIT %s",(user_id,max(1,min(200,int(limit)))))
                return {"tasks":[self._public(row) for row in self.accounts._many(cursor)]}
