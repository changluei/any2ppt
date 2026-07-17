export const allowedExtensions = ['pdf','docx','txt','md'] as const
export function validateSourceFile(file: Pick<File,'name'|'size'>, maxMb=20): string | null {
  const extension=file.name.split('.').pop()?.toLowerCase()||''
  if(!allowedExtensions.includes(extension as typeof allowedExtensions[number])) return '仅支持 PDF、DOCX、TXT、Markdown'
  if(file.size===0) return '不能上传空文件'
  if(file.size>maxMb*1024*1024) return `文件不能超过 ${maxMb}MB`
  return null
}

