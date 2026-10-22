export function selectImportFiles(files) {
  const values = Array.from(files || [])
  const documents = values.filter(file => /\.(epub|pdf|txt|md|markdown)$/i.test(file.name))
  if (values.length === 1) return { file: values[0], audio: null }
  if (documents.length !== 1 || values.length !== 2) throw new Error('请选择一个文档，或同时选择文档与同名 MP3')
  const file = documents[0]
  const stem = name => name.replace(/\.[^.]+$/, '').normalize('NFC').toLowerCase()
  const audio = values.find(item => /\.mp3$/i.test(item.name) && stem(item.name) === stem(file.name))
  if (!audio) throw new Error('MP3 必须与文档同名（扩展名不同）')
  return { file, audio }
}
