# Set up with Codex or Claude Code

[English](ai-setup.md) · [简体中文](zh-CN/ai-setup.md) · [日本語](ja/ai-setup.md)

Configure vLLM, SGLang, llama.cpp and module-specific memory settings in [Local inference and performance](performance.md).

Open this repository in Codex or Claude Code, then paste the block below. Fill in the first four lines when you have a preference; the assistant can inspect the machine and suggest values.

```text
Set up Roleplay Avatar in this repository and verify a working installation.
My goal: live 2D conversation with native Live2D import and microphone input.
Model storage directory: [choose a path, or recommend one]
Environment directory: [choose a new directory, or recommend one]
Model choice: [recommend for my hardware / compact / balanced / quality / showcase / provider API]
Download route: [Hugging Face / https://hf-mirror.com / another endpoint]

Read README.md, guides/quickstart.md, guides/setup.md, guides/models.md, guides/performance.md and
any applicable workspace instructions. Inspect Python, Node, GPU availability,
disk space and existing model directories. Reuse complete compatible weights.
On a managed cluster, use its established GPU queue and account identity.

1. Explain the selected runtime and creation models, their approximate memory
   needs, and which services will run concurrently. For a hosted provider,
   identify the model ID, regional endpoint and required key variable.
   For local dialogue, choose vLLM, SGLang or llama.cpp for the hardware and
   set context, concurrency and memory budgets. Agents using the same weights
   should share an endpoint.
2. Create dedicated environments at the chosen location. Install the CPU web
   app, build the frontend and run its CPU tests. Install model dependencies
   in the service environments described in the setup guide.
3. Use avatar models recommend/list/download/configure. Preview the download
   plan, then download the selected models, using --mirror when requested.
   Store fixed revisions and verify files. Fetch the pinned implementation
   repositories and auxiliary face/foreground resources needed for creation.
4. Create .local.env and configs/models.local.json with the actual paths,
   interpreter locations, agent routing and service URLs. Keep API key values
   in private environment variables. Use actor_director for free-form roleplay checkpoints; keep the
   other agents on a general instruction model. Configure the prompts and
   ASR language for my preferred language.
5. Start the model services through the machine's GPU runner, then the web
   application. Check each service health endpoint and /api/services. If I selected native
   Live2D examples, install their resources and voice references, then import.
6. Verify a real conversation: stream a reply, play speech, check expressions
   and actions, interrupt it, create another conversation, and export JSON.
   Check microphone transcription and a character creation/import task when
   those features are part of the selected installation.
7. Report the URL, selected models, verification results and exact start/stop
   commands. If an operation fails, resolve it or identify the failing step
   and its concrete dependency before reporting the installation status.

Use the backend API guide for headless installations, and the research guide
if I bring my own roleplay model or prompting method.
```

The [configuration guide](providers.md) provides examples for mixed local/API routing. The [research guide](research.md) describes independent actor, director, prompt and generation settings.

[← All guides](index.md)
