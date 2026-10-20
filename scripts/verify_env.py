"""验证虚拟环境里所有关键依赖是否可导入。"""
import importlib

MODULES = [
    ('fastapi', 'fastapi'),
    ('uvicorn', 'uvicorn'),
    ('starlette', 'starlette'),
    ('pydantic', 'pydantic'),
    ('langchain', 'langchain'),
    ('langchain_core', 'langchain_core'),
    ('langchain_openai', 'langchain_openai'),
    ('langchain_community', 'langchain_community'),
    ('openai', 'openai'),
    ('mysql.connector', 'mysql-connector-python'),
    ('pinecone', 'pinecone'),
    ('dotenv', 'python-dotenv'),
    ('requests', 'requests'),
    ('sqlalchemy', 'sqlalchemy'),
]

ok = 0
for module_name, package_name in MODULES:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, '__version__', '?')
        print(f'  OK    {package_name:<26} {version}')
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f'  FAIL  {package_name:<26} {type(exc).__name__}: {exc}')

print()
print(f'通过 {ok}/{len(MODULES)}')

# 关键版本组合，供后续排查兼容性问题
try:
    import langchain_core
    from langchain_openai import ChatOpenAI  # noqa: F401
    print('langchain-core :', langchain_core.__version__)
except Exception as exc:  # noqa: BLE001
    print('langchain 组合异常:', exc)