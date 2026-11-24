# Distribution and on-demand libraries

The [Almasi loader](https://github.com/WordWield/almasi) is the sole PyPI distribution. Core is an ordinary acquired library, `almasi.a`.

```python
from almasi import a, o, web
```

The loader owns checkout selection, Git acquisition, requirements installation and initial Python entry execution. It imports each entry under its canonical `almasi.<name>` name. Core owns architecture: `a.extend(name)` publishes one runtime instance, and `A.__getattr__` resolves native filesystem components or a configured fallback. The loader never depends on Core; Core is not reloaded while executing.

Library locations and update policy are documented in the loader README. Git and library-acquisition APIs are imported with `from almasi import Git, Libraries`; see [Git contract](architecture.git.md). Core requirements live in `requirements.txt` and its entry point is `a.py`. `ALMASI_PATH` and `ALMASI_GIT_BASE` preserve their meanings. Existing checkouts follow their configured upstream; local source trees without Git metadata remain untouched. Missing libraries are acquired only when requested. Updates execute trusted source, not sandboxed code; revisions are not pinned. Cross-process checkout changes are not transactional.

Application and Source workspaces remain separate from the reusable library cache. Application selection via `a.extend` in `__main__` is unchanged. The installed loader is released through PyPI separately from Core and other library revisions.
