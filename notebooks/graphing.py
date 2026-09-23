# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.5
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Agentic Trace Graphs
# This notebook shows how to load a `jsonl` into a `TraceGraph` and then visualize that `TraceGraph`

# %%
from clanker_scope.graph import TraceGraph
from clanker_scope.loader import JSONLLoader

sample_file = "../sample.jsonl"
result = JSONLLoader().load(sample_file)

# %%
result

# %% [markdown]
# The `result` object contains a `graph` attribute which is the `TraceGraph` read from the file

# %%
result.graph.nodes

# %%
from clanker_scope.render import DOTRenderer

dot_render = DOTRenderer()
dot_source = dot_render.render(result.graph)

# %%
from graphviz_anywidget import graphviz_widget

widget = graphviz_widget(dot_source)
widget

# %% [markdown]
# ## What about a _Mermaid_ diagram? 
# The other kind of diagram that we might be generally interested in is a _mermaid diagram_ which shows use the temporal relationships between the stageso.

# %%
import mermaidx
from clanker_scope.render import MermaidRenderer

mermaid_render = MermaidRenderer()
mermaid_src = mermaid_render.render(result.graph)

# %%
mermaidx.render(mermaid_src)



