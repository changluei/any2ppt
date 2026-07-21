export const allowedExtensions = ['pdf','docx','txt','md'] as const
const statusLabels:Record<string,string>={uploaded:'已上传',parsing:'解析中',indexing:'索引中',ready:'已就绪',failed:'失败',pending:'等待中',running:'运行中',succeeded:'成功',cancelled:'已取消'}

export const statusText=(status:string)=>statusLabels[status]||status
export const isEmptySearch=(results:unknown[])=>results.length===0

export function validateSourceFile(file: Pick<File,'name'|'size'>, maxMb=20): string | null {
  const extension=file.name.split('.').pop()?.toLowerCase()||''
  if(!allowedExtensions.includes(extension as typeof allowedExtensions[number])) return '仅支持 PDF、DOCX、TXT、Markdown'
  if(file.size===0) return '不能上传空文件'
  if(file.size>maxMb*1024*1024) return `文件不能超过 ${maxMb}MB`
  return null
}

