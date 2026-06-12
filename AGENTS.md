# AGENTS.md

## Project name

AI Life Planner

## Project idea

AI Life Planner is an AI-powered daily planner that helps users plan their day without manually filling many fields.

The main problem: people do not want to constantly maintain a planner. They want to write or say plans in natural language, and the system should understand them, extract tasks, constraints, goals, budget, energy level, and build a realistic daily schedule.

## Core product principle

The product is not just a todo list.

The product is an AI life planner that reduces manual planning.

The user should not manually create dozens of tasks. The user writes natural text, and the system turns it into a structured plan.

## Tech stack

Use:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Telegram bot
- Docker Compose
- LLM API for natural language understanding

## Important architectural rule

LLM should not control everything.

Correct approach:

LLM understands and explains.
Backend calculates and controls.

The LLM is used for:
- parsing natural language;
- extracting tasks;
- extracting constraints;
- generating user-friendly explanations;
- suggesting plan changes.

The backend is responsible for:
- storing data;
- validating data;
- creating plans;
- checking time conflicts;
- sorting by priority;
- controlling task statuses;
- saving results to the database.

Do not store important state only inside LLM messages.

## First development step

Start with the project skeleton only.

Create:
- FastAPI app;
- `/health` endpoint;
- PostgreSQL in Docker Compose;
- SQLAlchemy config;
- Alembic setup;
- `.env.example`;
- `requirements.txt`;
- basic README.

Do not implement Telegram bot yet.
Do not implement LLM yet.
Do not implement business logic yet.

The first goal is to make the backend start locally.
