import React from 'react'
import { Alert, Button, Empty, Form, Input, Space, Spin, Tag, Typography } from 'antd'
import { CheckOutlined, SaveOutlined, SoundOutlined, StarOutlined } from '@ant-design/icons'

const { Text, Title, Paragraph } = Typography

export default function ReaderWordPanel({ info, sentence, savedWord, meaning, note, onMeaning, onNote, onSpeak, speaking, onSave, onSaveDetails, saving, savingDetails, saveError, onRetry, privateBook, locked }) {
  if (!info) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="点击正文单词，查看本句含义并加入生词本" />
  const context = info.context || {}
  const dictionary = info.dictionary || {}
  const contextMeaning = context.meaning || context.explanation || context.contextExplanation || context.payload?.text
  return <div className="reader-word-detail">
    <div className="reader-word-heading">
      <div>
        <Text className="eyebrow">WORD IN CONTEXT</Text>
        <div className="reader-word-title-line">
          <Title level={2}>{info.word}</Title>
          <Button shape="circle" className={`reader-word-speak ${speaking ? 'speaking' : ''}`} aria-label={`播放 ${info.word} 的发音`} icon={<SoundOutlined />} onClick={onSpeak} />
        </div>
        {(context.phonetic || dictionary.phonetic) && <Text className="reader-phonetic">{context.phonetic || dictionary.phonetic}</Text>}
      </div>
      <Text className="reader-word-source">{dictionary.source || context.source || '词汇学习'}</Text>
    </div>
    <section className="reader-source-sentence">
      <Text className="reader-section-label">来源原句</Text>
      <Paragraph>{sentence?.text}</Paragraph>
    </section>
    <section className="reader-context-section" aria-label="本句含义" aria-busy={info.contextLoading}>
      <Text className="reader-section-label">本句含义</Text>
      {info.contextLoading ? <div className="reader-section-loading" role="status"><Spin size="small" /> 正在分析本句含义…</div>
        : info.contextError ? <Alert type="warning" showIcon message="本句分析暂不可用" description={info.contextError} action={<Button size="small" onClick={() => onRetry('context')}>重试语境</Button>} />
        : contextMeaning ? <Paragraph>{contextMeaning}</Paragraph>
        : <Text type="secondary">暂未返回本句解释，可先参考下方词典释义。</Text>}
      {!info.contextLoading && !info.contextError && context.usage && <Paragraph className="reader-context-usage">{context.usage}</Paragraph>}
    </section>
    <section className="reader-word-collection" aria-label="生词收藏">
      <Space wrap>
        <Button type={savedWord ? 'default' : 'primary'} icon={savedWord ? <CheckOutlined /> : <StarOutlined />} loading={saving && !savingDetails} disabled={Boolean(savedWord) || savingDetails || locked} onClick={() => onSave()}>
          {savedWord ? '已加入生词本' : '加入生词本'}
        </Button>
        {savedWord && <Tag color="green">已收藏</Tag>}
      </Space>
      <Text type="secondary">{savedWord ? '已保存来源原句，可在生词复习中巩固。' : '保存单词与来源原句，稍后统一复习。'}</Text>
      {saveError && <Alert type="error" showIcon message={saveError} description="内容仍保留，请重试刚才的保存操作。" />}
    </section>
    {savedWord && <div className="reader-word-rating"><Text type="secondary">认识程度（可选）</Text><div>
      {[['again','不认识'],['hard','困难'],['good','记得'],['easy','简单']].map(([value,label]) => <Button key={value} aria-pressed={savedWord.payload?.rating === value} className={savedWord.payload?.rating === value ? 'selected' : ''} size="small" disabled={saving || savingDetails || locked} onClick={() => onSave(value)}>{label}</Button>)}
    </div></div>}
    <section aria-label="词典释义" aria-busy={info.dictionaryLoading}>
      <Text className="reader-section-label">词典释义</Text>
      {info.dictionaryLoading ? <div className="reader-section-loading" role="status"><Spin size="small" /> 正在查询词典…</div>
        : info.dictionaryError ? <Alert type="warning" showIcon message="词典暂不可用" description={info.dictionaryError} action={<Button size="small" onClick={() => onRetry('dictionary')}>重试词典</Button>} />
        : dictionary.groups?.length ? <div className="reader-dict-list">{dictionary.groups.map((group,index) => <div className="reader-dict-row" key={`${group.pos}-${index}`}><span className={`reader-pos-tag pos-${String(group.pos || 'other').toLowerCase().replace(/[^a-z]+/g,'')}`}>{group.pos === 'ANY' || group.pos === 'any' ? '释义' : group.pos || '其他'}</span><p>{(group.translations || []).join('；')}</p></div>)}</div>
        : <Text type="secondary">词典暂无此词，仍可收藏并补充私人释义。</Text>}
    </section>
    {!!dictionary.examples?.length && <details className="reader-word-editor"><summary>更多例句 · {dictionary.examples.length}</summary><div className="reader-examples">{dictionary.examples.map((example,index) => <Paragraph key={index}>{example}</Paragraph>)}</div></details>}
    {privateBook && <details className="reader-word-editor"><summary>私人释义与备注</summary><Form layout="vertical">
      <Form.Item label="私人释义" htmlFor="reader-private-meaning"><Input.TextArea id="reader-private-meaning" disabled={locked || saving || savingDetails} value={meaning} onChange={e => onMeaning(e.target.value)} autoSize={{minRows:2,maxRows:4}} /></Form.Item>
      <Form.Item label="单词笔记" htmlFor="reader-private-note"><Input.TextArea id="reader-private-note" disabled={locked || saving || savingDetails} value={note} onChange={e => onNote(e.target.value)} autoSize={{minRows:2,maxRows:4}} /></Form.Item>
      <Button icon={<SaveOutlined />} loading={savingDetails} disabled={saving || locked} onClick={onSaveDetails}>{savedWord ? '保存释义与备注' : '收藏并保存备注'}</Button>
    </Form></details>}
  </div>
}
