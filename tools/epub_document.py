"""Read EPUB spine text and declared cover without extracting archive paths."""
from __future__ import annotations
import posixpath
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET


class BodyText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.hidden=0
        self.blocks=[];self.buffer=[];self.block_type='paragraph';self.page_label=None

    def flush_block(self):
        value=''.join(self.buffer)
        value='\n'.join(re.sub(r'\s+',' ',line).strip() for line in value.split('\n')).strip()
        kind=self.block_type
        # Some EPUB exporters encode chapter labels as styled <p> elements.
        if kind=='paragraph' and re.fullmatch(r'(?:chapter|part|book)\s+(?:[\divxlcdm]+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)(?:\s*[:.\-—].{0,100})?',value,re.I):kind='heading'
        if value:self.blocks.append({'type':kind,'text':value,**({'pageLabel':self.page_label} if self.page_label else {})})
        self.buffer=[]

    def handle_starttag(self, tag, attrs):
        if tag in {'head','script','style'}:self.hidden+=1
        if not self.hidden and tag in {'p','div','h1','h2','h3','li','br'}:self.parts.append('\n')
        if self.hidden:return
        attributes=dict(attrs)
        if 'pagebreak' in (attributes.get('epub:type') or '').split() or attributes.get('role')=='doc-pagebreak':
            self.flush_block();self.page_label=attributes.get('title') or attributes.get('aria-label') or attributes.get('id')
        if tag in {'p','div','h1','h2','h3','h4','h5','h6','li','blockquote'}:
            self.flush_block();self.block_type='heading' if tag.startswith('h') and tag[1:].isdigit() else 'quote' if tag=='blockquote' else 'paragraph'
        if tag=='br':self.buffer.append('\n')

    def handle_endtag(self, tag):
        if tag in {'head','script','style'}:self.hidden=max(0,self.hidden-1)
        if not self.hidden and tag in {'p','div','h1','h2','h3','li'}:self.parts.append('\n')
        if not self.hidden and tag in {'p','div','h1','h2','h3','h4','h5','h6','li','blockquote'}:self.flush_block()

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)
            # XHTML formatting whitespace is not an author-specified line break.
            self.buffer.append(re.sub(r'\s+',' ',value))


def read_epub(source:Path, cover_target:Path|None=None, *, structured=False, source_index=None):
    with zipfile.ZipFile(source) as archive:
        if len(archive.infolist())>10000 or sum(i.file_size for i in archive.infolist())>200*1024*1024:
            raise ValueError('EPUB 解压内容过大')
        def read(name):
            info=archive.getinfo(name)
            if info.file_size>20*1024*1024:raise ValueError('EPUB 单个内容文件过大')
            return archive.read(info)
        def xml(name):
            raw=read(name)
            if b'<!ENTITY' in raw.upper():raise ValueError('不支持包含实体声明的 EPUB')
            return ET.fromstring(raw)
        def resolve(base, href):
            parsed=urlsplit(href)
            if parsed.scheme or parsed.netloc:raise ValueError('EPUB 内容必须位于文件内部')
            name=posixpath.normpath(posixpath.join(posixpath.dirname(base),unquote(parsed.path)))
            if name.startswith(('../','/')):raise ValueError('EPUB 内容路径无效')
            return name
        container=xml('META-INF/container.xml')
        rootfile=container.find('.//{*}rootfile')
        if rootfile is None:raise ValueError('EPUB 缺少内容清单')
        opf_name=resolve('',rootfile.attrib['full-path']);opf=xml(opf_name)
        manifest={item.attrib['id']:item for item in opf.findall('.//{*}manifest/{*}item')}
        layout=(next((m.text for m in opf.findall('.//{*}metadata/{*}meta') if m.get('property')=='rendition:layout'),'reflowable') or 'reflowable').strip()
        if source_index is not None:
            source_index.update(version=1,layout='fixed' if layout=='pre-paginated' else 'reflow',spine=[])
        parts=[];blocks=[]
        for ref in opf.findall('.//{*}spine/{*}itemref'):
            if ref.get('linear')=='no':continue
            item=manifest.get(ref.get('idref'))
            if item is None or 'nav' in item.get('properties','').split():continue
            href=resolve(opf_name,item.attrib['href'])
            parser=BodyText();parser.feed(read(href).decode('utf-8-sig','replace'))
            parser.flush_block()
            section=f'section-{len(source_index["spine"])+1 if source_index is not None else len(parts)+1}'
            if source_index is not None:
                properties=ref.get('properties','').split()
                chapter_layout='fixed' if 'rendition:layout-pre-paginated' in properties else 'reflow' if 'rendition:layout-reflowable' in properties else source_index['layout']
                source_index['spine'].append({'href':href,'section':section,'layout':chapter_layout})
            blocks.extend({**block,'section':section} for block in parser.blocks)
            value=''.join(parser.parts).strip()
            if value:parts.append(value)
        cover=next((i for i in manifest.values() if 'cover-image' in i.get('properties','').split()),None)
        if cover is None:
            meta=next((m for m in opf.findall('.//{*}metadata/{*}meta') if m.get('name')=='cover'),None)
            if meta is not None:cover=manifest.get(meta.get('content'))
        output=None
        if cover_target and cover is not None:
            raw=read(resolve(opf_name,cover.attrib['href']))
            suffix='.jpg' if raw.startswith(b'\xff\xd8\xff') else '.png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else None
            if suffix:
                output=cover_target.with_suffix(suffix);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(raw)
        result=('\n\n'.join(parts),str(output) if output else None)
        return (*result,blocks) if structured else result
