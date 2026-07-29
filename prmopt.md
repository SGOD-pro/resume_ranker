
You are a Senior Principal Full-Stack Engineer. We are building Resume Ranker V2 freshly from the existing V1 codebase. 

Past attempts failed because the AI hallucinated infrastructure that didn't fit AWS Lambda limits and lost context of the existing V1 "glue". To prevent this, we follow a strict methodology.

### Step 1: Context Loading (No Code)
Read the following repository files in this exact order and treat them as binding law:
1. `AGENT.md`
2. `mamori.md` (The V1 truth)
3. `projectrequirement.md`A
4. `project.md`
5. `architecture.md`
6. `design.md`
7. `boundaries.md`
8. `rules.md`
9. `decision.md`
10. `phases.md`
11. `memory.md`

### Step 2: Acknowledge & Prepare
Once read, output a summary titled "PHASE 1: SYSTEM UNDERSTANDING". Detail:
1. How the V1 synchronous flow works (from mamori.md).
2. How V2 Phase 1 will migrate this to `/api/v2/` routes without breaking the frontend.
3. Confirm you understand that Phase 1 uses NO SQS and NO BackgroundTasks (it just restores the V1 sync flow on V2 routes).

Do not write any implementation code yet. Await my approval to begin Phase 1 implementation.