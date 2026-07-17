import{describe,expect,it}from'vitest';import{validateSourceFile}from'./files'
describe('资料文件校验',()=>{it('接受公开的四类资料',()=>{expect(validateSourceFile({name:'课标.md',size:100})).toBeNull();expect(validateSourceFile({name:'教材.PDF',size:100})).toBeNull()});it('拒绝危险类型、空文件和超大文件',()=>{expect(validateSourceFile({name:'script.html',size:1})).toContain('仅支持');expect(validateSourceFile({name:'empty.txt',size:0})).toContain('空文件');expect(validateSourceFile({name:'huge.pdf',size:21*1024*1024})).toContain('20MB')})})

