"""真实 LangChain 检索器验证两个生产入口，无嵌入下载或模型请求。"""
import ast
import contextlib
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore, VectorStoreRetriever

class SyntheticStore(VectorStore):
    def similarity_search(self, query, k=4, **kwargs):
        return [Document(page_content='synthetic document',metadata={'source':'synthetic.txt'})]
    @classmethod
    def from_texts(cls,texts,embedding,metadatas=None,**kwargs):
        return cls()

@pytest.mark.parametrize('file,cls,name,args',[
    ('base_model.py','BaseLLMModel','prepare_inputs',('query',False,['synthetic.txt'],'English',[])),
    ('ChuanhuAgent.py','ChuanhuAgent_Client','query_index',('query',)),
])
def test_production_method_uses_current_retriever(file,cls,name,args):
    store=SyntheticStore()
    scope=dict(logging=logging,os=os,construct_index=lambda *a,**kw:store,
        retrieve_proxy=contextlib.nullcontext,i18n=lambda s:s,VectorStoreRetriever=VectorStoreRetriever,
        add_source_numbers=lambda rows:[f'{text} ({source})' for text,source in rows],
        add_details=lambda rows:rows,replace_today=lambda s:s,
        PROMPT_TEMPLATE='{query_str}\n{context_str}\n{reply_language}')
    path=Path(__file__).resolve().parents[1]/'modules/models'/file
    tree=ast.parse(path.read_text());class_node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==cls)
    method=next(n for n in class_node.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),scope)
    result=scope[name](SimpleNamespace(api_key=None,index=store),*args)
    assert 'synthetic document' in (result[3] if name=='prepare_inputs' else result)
