# Understanding Agents: Antigravity vs. Claude vs. CrewAI vs. LangChain

This document directly compares how each framework maps its agent concept and skills, using a concrete
analogy: an Agent is like an Employee, a Skill is like a Training Manual, and a Subagent is like a Junior
Assistant.

  To make sense of how different frameworks define Agents, Subagents, and Skills, the marketing jargon is
  cut through and the underlying mechanics are examined.
  ──────
  ## 1. The Core Distinction
   Term             | Real-World Analogy                    | What it actually is in software
  ------------------|---------------------------------------|----------------------------------------------
   Agent            | An Employee                           | An autonomous execution loop (LLM + memory +
                    |                                       | assigned tools + goal) that decides what
                    |                                       | actions to take.
   Subagent         | A Junior Assistant hired for a        | A separate, parallel process with its own
                    | specific task                         | fresh, isolated memory (context window)
                    |                                       | spawned to do work without cluttering the
                    |                                       | main agent's brain.
   Skill            | A Training Manual / SOP               | A markdown playbook (SKILL.md) that teaches
                    |                                       | an agent how to perform a multi-step task.
                    |                                       | It has no memory of its own and does not run
                    |                                       | by itself.
   Rule (AGENTS.md) | The Company Policy & Handbook         | Passive behavioral constraints and coding
                    |                                       | standards that are permanently injected into
                    |                                       | the agent's system prompt.
   Tool / MCP       | Physical Tools (Hammer, Wrench,       | Executable APIs or functions (e.g.
                    | Terminal)                             | run_command, git, database query) that the
                    |                                       | agent calls.
  ──────
  ## 2. How Antigravity Defines an "Agent"

  Google Antigravity is a terminal-based agentic coding assistant **(also distributed as a desktop command
  center)**. In Antigravity, an Agent is a live, autonomous worker that runs a loop of *read → decide →
  act* — executing commands, reading and writing files, and calling tools through skills and MCP servers —
  until the goal is complete. It can delegate side tasks to Subagents that run in their own isolated
  context window, **optionally in a separate Git worktree**.

  ### Is an Agent separate from a Skill in Antigravity?

  Yes, completely separate.
  • A Skill (.agents/skills/<name>/SKILL.md) is passive knowledge. Antigravity uses progressive disclosure:
  it only loads the skill's name and description into context, and only pulls the full text into the
  agent's prompt when relevant. A skill cannot run concurrently or hold its own context window.

  • An Agent / Subagent (.agents/agents/<name>.md) is an active actor. When spawned, it starts an
  independent conversation ID, has its own dedicated context window, can run on a separate model tier (e.g.,
  flash vs pro), and can even work in an isolated Git branch (branch worktree) so its edits don't conflict
  with the main working tree.

  ### What is "YAML frontmatter"? 

  It is the small "settings box" at the very top of a file, written as simple
  `name: value` lines and sandwiched between two `---` markers. It is the machine-readable label that tells
  the tool what the file is called, what it does, and which tools/model it may use — separate from the
  plain-English instructions that follow below it.

  ### How a Custom Agent is Defined in Antigravity:

  Custom agents live in .agents/agents/<name>.md with YAML frontmatter:
    ---
    name: code-auditor
    description: Specialized subagent for security audits and static analysis.
    tools:
      - view_file
      - grep_search
      - run_command
    subagent: true           # Can be spawned in the background
    mainAgent: false         # Hidden from the main chat dropdown
    model: pro               # Can use a different model tier (pro / flash / inherit)
    commandExecutionPolicy: sandbox
    skills:
      - skills/security-checklist   # An agent can USE skills!
    ---
    
    # System Prompt
    You are an expert security auditor. When invoked, inspect source code for vulnerabilities...


  ### Key Antigravity Agent Features:

  1. Context Window Isolation: When the main agent delegates a task to a subagent, the parent's context
  window stays clean and doesn't get flooded with hundreds of file lines.
  2. Parallel & Asynchronous: Subagents run in the background (CLI shortcut: Alt+J or /agents panel). The
  conversation can continue while 3 subagents run tests, query databases, or search code.
  3. Workspace Isolation (branch): A subagent can spin up a Git worktree, test changes, and report back
  before anything touches the main working tree.
  4. Inter-Agent Messaging: Agents can send messages to each other using conversation IDs and can nest up
  to 10 levels deep.
  ──────

  ## 3. How Claude Defines an "Agent"

Claude Code is a terminal-based agentic coding assistant. In Claude Code, an Agent is a live, autonomous
worker that runs a loop of *read → decide → act* — executing commands, reading and writing files, and
calling tools through skills and MCP servers — until the goal is complete. It can delegate side tasks to
Subagents that run in their own isolated context window, **each limited to an allowed set of tools**.

### Is an Agent separate from a Skill in Claude?

Yes, completely separate.
• A Skill (.claude/skills/<name>/SKILL.md) is a "how-to" guide. Claude only loads the skill's title and
  one-line description at first, and reads the full instructions only when it decides that guide is needed.
  A skill cannot do work on its own or hold its own memory.

• An Agent / Subagent (.claude/agents/<name>.md) is an active worker. When spawned, it gets its own
  dedicated memory (context window), can use a different model tier (e.g., sonnet vs opus), and is limited
  to an allowed set of tools.

### How a Custom Agent is Defined in Claude:

  Custom agents live in .claude/agents/<name>.md with YAML frontmatter:
  
    ---
    name: code-auditor
    description: Specialized subagent for security audits and static analysis.
    tools:
      - Read
      - Grep
      - Glob
      - Bash
    model: sonnet            # Can use a different model tier (sonnet / opus / haiku / inherit)
    
    ---
    
    # System Prompt
    You are an expert security auditor. When invoked, inspect source code for vulnerabilities...

  

### Key Claude Agent Features:
1. Context Window Isolation: When the main agent hands a task to a subagent, the parent's memory stays
  clean and doesn't get flooded with hundreds of file lines.
2. Parallel & Asynchronous: Subagents are launched with the Task tool and run side-by-side. Work can continue
  while several subagents (search, review, audit) run at the same time.
3. Permission & Model Tiering: Each subagent can be locked to a short list of allowed tools and a
  cheaper/faster model (haiku / sonnet) to keep costs and risk low. Unlike Antigravity, Claude subagents
  work in the same folder rather than a separate Git branch.
4. Skill Progressive Disclosure: Skills are discovered only by title and description; the full guide is
  read only when the agent decides it's relevant.

## 4. How CrewAI Defines an "Agent"

CrewAI is a Python framework built around a corporate-team metaphor. In CrewAI, an Agent is an autonomous
unit defined by a **role**, a **goal**, and a **backstory**, powered by an LLM and a set of tools. It
performs tasks, decides actions based on its role and goal, collaborates with other agents, and keeps
memory of its interactions. Several agents are grouped into a **Crew**, and **Task** objects are assigned
to them.

### How an Agent is Defined in CrewAI:

  from crewai import Agent

  researcher = Agent(
      role="Senior Financial Analyst",
      goal="Analyze quarterly earnings",
      backstory="You have 20 years on Wall Street.",
      tools=[search_tool],
      llm="gpt-4",
  )

### Key CrewAI Agent Features:
1. Team Hierarchy: Agents are grouped into a Crew and can delegate work to each other when
  `allow_delegation: true`.
2. Role-Driven Decisions: Each action is guided by the agent's role, goal, and backstory rather than a
  hard-coded control flow.
3. Memory: Agents keep memory of their interactions and can use knowledge_sources for domain context.
4. Task Assignment: Task objects are assigned to agents, and a process (sequential or hierarchical)
  determines execution order.

## 5. How LangChain / LangGraph Defines an "Agent"

LangChain is a Python/TypeScript SDK for building LLM applications, and LangGraph is its low-level
orchestration engine. In LangChain, an Agent follows the formula **Agent = Model + Harness**: a model
wrapped in a harness made of a prompt, a set of tools, and middleware, looping until the goal is met. In
LangGraph, the same agent is drawn as a directed graph of **nodes** (functions or LLM calls) connected by
**edges** that pass a shared state dictionary.

### How an Agent is Defined in LangChain:

  from langchain.agents import create_agent

  agent = create_agent(
      model="openai:gpt-4",
      tools=[get_weather],
      system_prompt="You are a helpful assistant",
  )

### Key LangChain / LangGraph Agent Features:
1. Agent = Model + Harness: The harness is the prompt, the tools, and any middleware around the model loop.
2. Graph Form: In LangGraph, nodes are functions or LLM calls and edges pass state between them.
3. Deterministic + Agentic Mix: A graph can combine fixed steps with LLM-driven branches.
4. Built on LangGraph: LangChain's `create_agent` runs on LangGraph, gaining persistence and
  human-in-the-loop support.

## 6. The Rosetta Stone: Comparing All 4 Frameworks
  Every major framework has slightly different terminology for the same underlying concepts:
   Feature            | Google Antigravity | Claude (Anthropic… | CrewAI             | LangChain / LangGr…
  -----------------|--------------------|------------------------|-----------------|-----------------------
   The Actor (Agent)  | Built-in Agent or  | Claude Code        | Agent(role, goal,  | AgentExecutor or
                     | .agents/agents/<na | Subagent task          | backstory, tools) | LangGraph State
                   | me>.md             |                        | backstory,      |
   Delegated Worker   | invoke_subagent    | Claude Subagents   | Sub-agents         | Subgraphs / Worker
   (Subagent)        | (Separate process  | (spawned by            | assigned to tasks | Worker nodes with
   Worker          | (Separate process  | (spawned by            | assigned to     | nodes with separate
   (Subagent)      | & context,         | orchestrator for       | tasks in a      | state
                   | optional git       | search/review)         | hierarchical    |
                   | worktree)          |                        | crew            |
   Procedural      | skills/<name>/SKIL | .claude/skills/<name>/ | Custom Tool or  | Custom Tool or
   Knowledge       | L.md (Loaded on    | SKILL.md (Loaded on    | RAG Task        | VectorStore Retriever
   (Skill)         | demand via         | demand via prompt      | knowledge       |
                   | progressive        | matching)              |                 |
                   | disclosure)        |                        |                 |
   Permanent Rules | AGENTS.md,         | CLAUDE.md or AGENTS.md | Agent backstory | System Message /
                   | GEMINI.md, or      |                        | &               | MessagesState
                   | .agents/rules/*.md |                        | system_template | invariants
   External        | MCP Servers        | MCP Servers            | LangChain Tools | LangChain Tools /
   Integrations    | (settings.json)    | (claude_desktop_config | / Custom Crew   | BaseTool / MCP
                   |                    | .json)                 | Tools           |
   Team            | /teamwork-preview  | Multi-turn planning    | Crew(agents=[.. | LangGraph State Graph
   Orchestration   | & /boost           | mode                   | .],             | / Router
                   |                    |                        | tasks=[...],    |
                   |                    |                        | process=...)    |
  ──────
  ## 7. Deep-Dive Comparison

  ### 1. Antigravity vs. Claude
  • Why did Claude have .claude/skills and Antigravity .agents/skills?
  They both use the exact same progressive disclosure standard: a folder with a SKILL.md containing name:
  and description: in YAML frontmatter. This is why the 30 .claude skills were symlinked directly
  into .agents/ without changing a single line of text!
  • What is AGENTS.md vs agent.md?
      • In both Antigravity and Claude Code, AGENTS.md (plural) at the project root is a Rules file
      (instructions for any agent working in this repo, like coding standards and directory maps).
      • An agent.md (singular, inside .agents/agents/<name>/agent.md) is a persona/agent definition with
      tool whitelists, model choices, and execution sandboxes.


  ### 2. Antigravity vs. CrewAI
  • CrewAI is designed around a corporate team hierarchy metaphor:
      • Agents are defined with a role ("Senior Financial Analyst"), a goal ("Analyze quarterly earnings"),
      and a backstory ("You have 20 years on Wall Street").
      • Task objects are then defined and assigned to agents inside a Crew.
  • Antigravity is designed around developer pair-programming:
      • It starts with one primary agent (Antigravity).
      • When a problem is too big or too noisy, it dynamically delegates to Subagents (like research,
      browser, or custom background agents) who execute concurrently in their own isolated Git worktrees.

  ### 3. Antigravity vs. LangChain / LangGraph
  • LangChain / LangGraph is a low-level Python/TypeScript developer SDK:
      • An agent is simply a mathematical loop: Agent = LLM + Tools + While Loop.
      • In LangGraph, a directed graph is constructed where nodes are functions or LLMs, and edges pass a
      state dictionary.
  • Antigravity operates at a higher platform level:
      • It handles process management, IPC (inter-process communication), context truncation, token
      optimization, TUI panels, terminal sandboxes, and file diffing out of the box.

  ──────
  ## 8. Summary Mental Model for a Repository

  To customize a project for AI agents going forward, the clean rule of thumb is:

  1. To teach the agent a procedure or syntax? (e.g., How to write a Malloy query, How to build a
  funnel chart)
  → Create a Skill (.agents/skills/<name>/SKILL.md).
  2. To tell the agent project rules and directory layout? (e.g., Always run tests before finishing,
  Look in workspace/ for models)
  → Put it in Rules (AGENTS.md at root).
  3. For an isolated worker with restricted tools or a cheaper model? (e.g., A fast background worker that
  only reads files and never modifies code)
  → Create a Subagent (.agents/agents/<name>.md).