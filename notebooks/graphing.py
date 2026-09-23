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

renderer = DOTRenderer()
dot_out = renderer.render(result.graph)

# %%
dot_out

# %%
