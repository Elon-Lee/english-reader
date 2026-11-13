import { Modal } from 'antd'
import { getJson } from '../../api/client'

export async function requestPrivateImport(messageApi) {
  try {
    const resources = await getJson('/api/resources')
    if (resources.privateImport?.allowed === true) return true
    Modal.confirm({
      title: '升级套餐后导入读物',
      content: '免费版不支持私人读物导入。进阶版提供 1 GB 私人空间，Pro 版提供 5 GB。',
      okText: '查看套餐',
      cancelText: '暂不升级',
      onOk: () => { location.href = '/pricing' },
    })
  } catch (error) {
    messageApi.error(error.message || '无法核对导入权限，请稍后重试。')
  }
  return false
}
