# Rule: Follow the Plan (and keep fixes simple)

Applies whenever you implement, debug, or modify this project's code. The design is already decided —
your job is to realize it faithfully and simply, not to redesign it.

## The plan is the source of truth

- **`PLAN.md`** is the roadmap (6 milestone-aligned steps, M1→M5). Build **in order**; each step ends
  with its acceptance test green and `make check` passing before the next begins.
- **`plan/S{i}_*/S{ij}_plan_*.md`** are the per-substep specs. Each one defines, for that unit:
  *Objective · Inputs and Outputs · Skeleton Python Code · How It Connects · Key Technology/Design
  Patterns/Packages · Definition of Done.* Read the substep doc before writing any of its code.
- The substep's **Skeleton Python Code** is the target shape: implement those exact classes/functions,
  with those signatures, in the file paths it names. Fill in the `...` bodies — **don't invent new
  modules, layers, or abstractions** that aren't in the plan.
- The substep's **Definition of Done** is the acceptance bar. "Done" means its acceptance command runs,
  `make check` is green, and the mapped `features.json` id flips to `passing` with evidence. Don't claim
  done without it (see `.claude/rules/testing-rules.md`, `verifier_agent`).

## Keep it as simple as the plan

- Match the plan's **altitude**. Simple functions over deep class hierarchies; the chosen libraries
  (`yfinance`, `ta`, LangChain/LangGraph, FAISS, sentence-transformers, scikit-learn, matplotlib);
  no new heavy dependency, no microservices/DB server/web framework (YAGNI, spec §12.3).
- The skeleton already encodes the right amount of structure. Implement it — do not "improve" it with
  extra configurability, indirection, or cleverness the plan didn't ask for.
- Numbers live in `config.py`; data only via `get_observation`; LLM only via `make_llm`; agents are
  `prompt | llm.with_structured_output(Schema)`. (See `architecture.md`, `coding-style.md`,
  `llm-and-prompts.md`.) The plan assumes these — don't route around them.

## When something breaks (this will happen)

1. **Debug the root cause first** (use `systematic-debugging`) — don't paper over a failure with a
   broad `try/except`, a silent fallback, or added complexity.
2. **Fix with the smallest change** that makes the substep's Definition of Done pass. Prefer editing the
   one function at fault over restructuring.
3. **Do not mess things up.** Preserve the plan's names, signatures, and file layout. Don't refactor
   unrelated code, don't add a class/parameter/dependency to dodge a bug, don't special-case one input
   with a new branch when a correct general fix is simpler.
4. **Prefer the plan's lightweight option** when it offers one (e.g. the deterministic `PositionManager`
   rule instead of an LLM).
5. **If the fix genuinely requires deviating from the plan** (the plan was wrong or incomplete): STOP
   and reconcile *first* — update the substep doc in `plan/` (and `PLAN.md` if affected), record a
   `DECISIONS.md` ADR (what changed + why), then implement. **Never let code silently diverge from the
   plan** — the plan must always describe the code that exists.

## Anti-complexity red flags (stop and find the simpler fix)

- A fix that introduces a new class, module, dependency, or abstraction layer.
- A `try/except` that hides *why* something failed.
- Copy-pasted logic, or a new config flag added only to special-case one failing case.
- Touching files outside the substep's scope to make it pass.
- The diff is larger than the bug. → step back; the plan's design is simple, your fix should be too.

## Anti-lookahead is never a casualty of a fix

A quick fix must not break point-in-time discipline (`≤ t`, `t+1` execution, delayed `t+1+h` memory
write) or offline determinism. Run the `check-lookahead` audit after any data/memory/backtest change.
