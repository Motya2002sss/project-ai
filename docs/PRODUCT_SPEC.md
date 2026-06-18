# AI Life Planner Product Spec

## What It Is

AI Life Planner is a personal planner that turns natural language into a remembered profile, long-term goals, daily tasks, a realistic day plan, and end-of-day outcomes.

The product is not a todo list and not a command-only Telegram bot. The user should be able to write the way they think: "I work until 19, low energy today, tomorrow I want to study math, what should I do for my goals?"

## User Value

The core value is reducing planning work. The user should not manually maintain dozens of fields, priorities, dates, and schedules. The system should remember stable context, extract useful structure from text, and help the user decide what is realistic today.

The backend owns state and planning rules. The parser or optional LLM extracts meaning from text, but it does not become the source of truth.

## Core Scenarios

1. Profile setup
   - User writes working hours and sleep time in natural language.
   - The planner stores work start, work end, sleep time, name, and timezone.
   - If profile data is missing, planning uses defaults and explains that better profile data will improve plans.

2. Goals
   - User writes any long-term goals.
   - Goals are stored as durable records, not only in chat history.
   - Goals can be about finances, learning, health, family, creativity, career, projects, or anything personal.

3. Tasks
   - User writes plans in natural language.
   - The parser extracts tasks, rough priority, duration, energy, budget, and date when available.
   - Tasks are attached to a target date so today and tomorrow do not mix.

4. Goal-driven tasks
   - User asks what to do for goals.
   - The system suggests small actionable tasks from active goals and adds them to the selected day.
   - Suggestions use broad domain heuristics now and should become more precise with a real LLM later.

5. Daily plan
   - The planner builds a day plan from active tasks for the selected date.
   - It considers priority, estimated duration, working hours, configurable buffer after work, sleep time, and energy.
   - Tasks that do not fit before sleep are marked as not scheduled.

6. Completion and daily summary
   - User can mark one task done.
   - User can write an end-of-day summary with done and not-done tasks.
   - Done tasks are closed; skipped tasks stay active and the plan is rebuilt.

7. Reschedule
   - User can say they are delayed or free later.
   - The plan is rebuilt from the new available time.

8. Web and future voice input
   - Web text and Telegram text should enter the same message processing pipeline.
   - Future voice/audio input should become speech-to-text first, then use the same text parser and backend services.
   - The API returns structured responses that a future Web UI can render without duplicating planning logic.
   - The initial Web UI is a minimal Today screen for local product testing: free-text input, AI response, today plan, tasks, goals, and temporary User ID.

## MVP Status

The current MVP supports:

- Telegram bot as the primary interface.
- FastAPI health endpoint and minimal Web API foundation.
- PostgreSQL persistence with SQLAlchemy and Alembic.
- User profile storage.
- Goal storage.
- Task creation from natural language through the mock parser.
- Shared message processing service for Telegram text, Web text, and future voice transcript inputs.
- API endpoints for message processing, profile, goals, tasks, and today/tomorrow plan reads.
- Minimal Vite/React Today Web UI in `web/`.
- Optional OpenAI/openai-compatible/native Ollama parser integration with mock fallback.
- Parser evaluation cases for comparing mock, local, and hosted provider behavior.
- Task `target_date` for today/tomorrow separation.
- Goal-task suggestions through backend heuristics.
- Day planning with work end, sleep, energy, priority, and duration.
- Mark done and daily summary flows.
- Smoke check script at `scripts/check_mvp.py`.

## Next

1. Improve LLM parsing quality with eval scenarios, provider comparisons, stricter prompts, and production monitoring.
2. Expand the Today Web UI only where product workflows need it, without turning it into a heavy task manager.
3. Add production authentication before exposing the Web API outside local development.
4. Expand the Web API only where the future Web UI needs additional workflow coverage.
5. Improve planning quality with better scheduling rules, conflict handling, and goal progress history.
