---
tags: [ai-capabilities, skills, system-design]
---
# Conceptual Framework: AI System Capabilities as Executable Skills

## 1. I/O Engine Protocols
* **MCP (Model Context Protocol)**: Stateful JSON-RPC protocol abstracting tools, resources, and prompts.
* **RAG (Retrieval-Augmented Generation)**: Grounding LLM prompts with external vector stores.

## 2. State & Parametric Modifiers
* **LoRA (Low-Rank Adaptation)**: Factorized weight update matrices W = W_0 + (alpha/r)*(B * A).
* **Quantization**: Mapping FP32/FP16 tensors to FP8/INT4 to optimize VRAM and compute throughput.

## 3. Memory Geometry
* **Embeddings**: Dense high-dimensional vector representations.
* **Vector Databases**: HNSW & IVF indexing for low-latency k-NN search.
* **Context Windows**: Memory sequence buffer bounds.

## 4. Training & Scaling Targets
* **RLHF / DPO**: Aligning model outputs with human preference.
* **AGI**: Multi-domain cognitive flexibility.

## 5. Inference Mechanics
* **KV Cache**: Prefill and Decode phase attention caching (PagedAttention, FlashAttention).
* **Multimodal**: Latent space alignment of text, image, and voice inputs.