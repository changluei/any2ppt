import{describe,expect,it}from'vitest';import{isEmptySearch,statusText,validateSourceFile}from'./files'
describe('知识库工具',()=>{it('校验资料文件',()=>{expect(validateSourceFile({name:'课标.md',size:100})).toBeNull();expect(validateSourceFile({name:'script.html',size:1})).toContain('仅支持');expect(validateSourceFile({name:'empty.txt',size:0})).toContain('空文件');expect(validateSourceFile({name:'huge.pdf',size:21*1024*1024})).toContain('20MB')});it('转换状态文字',()=>expect(statusText('ready')).toBe('已就绪'));it('识别空检索结果',()=>expect(isEmptySearch([])).toBe(true))})

