# AI package placeholder

This root-level folder is not the active backend AI implementation. The current code is under **`backend/app/ai/`**, with related API routers under **`backend/app/api/`** (including AI assistant, prompts, usage, knowledge documents and RAG).

Read [AI framework documentation](../docs/ai.md) and inspect the provider configuration in [backend/.env.example](../backend/.env.example). The sample environment selects mock AI mode; configure and verify a real provider before claiming an external LLM integration is active.
