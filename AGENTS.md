# Project rules

## Project

We are building a personal offline Reels application.

The first version must:
- collect personalized Reels on the server;
- download video files;
- synchronize them with the phone;
- provide a vertical offline feed;
- track viewed videos;
- manage local storage limits.

The first version must not include:
- comments;
- likes;
- replies;
- content publishing;
- a custom recommendation algorithm.

## Architecture boundaries

- The frontend communicates only with our Backend API.
- Instagram credentials, cookies, and sessions must stay on the server.
- Instagram integration must be isolated from the core application logic.
- Offline playback must use locally stored video files.
- External integrations must be replaceable behind clear interfaces.

## Engineering rules

- Prefer simple and explicit solutions.
- Do not add unnecessary abstractions or dependencies.
- Validate all external input.
- Handle errors explicitly.
- Do not log secrets, cookies, tokens, or passwords.
- Never commit secrets or real account data.
- Database changes must use migrations.
- New behavior must include tests.
- Do not make unrelated changes.

## Workflow

Before changing code:
1. Read the relevant documentation and existing files.
2. Briefly explain the proposed solution.
3. List the files that will be changed.
4. Ask for clarification only when the task cannot be completed safely without it.

Before completing a task:
1. Run relevant tests and checks.
2. Review the final diff.
3. Report changed files.
4. Report commands that were run.
5. Mention remaining risks or unfinished work.

## Source of truth

The repository is the source of truth:
- `docs/PRODUCT.md` defines product scope.
- `docs/ARCHITECTURE.md` defines architecture.
- `docs/STATUS.md` defines current progress.

Do not rely only on chat history or memory.