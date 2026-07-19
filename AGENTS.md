# Project rules

## Project overview

We are building a personal offline Reels application.

The goal:
Allow a user to automatically prepare a personalized Instagram Reels feed and watch it offline without internet access.

The system will:
- collect personalized Reels on the server;
- download video files;
- synchronize videos with the phone;
- provide a vertical offline feed;
- track watched videos;
- manage local storage limits.

## MVP scope

Included:
- server-side Reels collection;
- video downloading;
- backend API;
- offline video synchronization;
- vertical feed UI;
- local video storage;
- watched status tracking;
- storage management.

Not included:
- comments;
- likes;
- replies;
- publishing content;
- custom recommendation algorithm;
- social features.

## Architecture rules

- Frontend communicates only with our Backend API.
- Instagram credentials, cookies, and sessions must never be stored on the client.
- Instagram integration must be isolated from the core application logic.
- External integrations must be replaceable behind clear interfaces.
- Offline playback must work using locally stored files.
- Every external input must be validated.

## Engineering principles

- Prefer simple and explicit solutions.
- Avoid unnecessary abstractions.
- Do not add dependencies without explaining why.
- Keep modules isolated and maintainable.
- Use clear naming.
- Handle errors explicitly.
- Add tests for new functionality.
- Do not make unrelated changes during a task.

## Security rules

Never:
- commit passwords;
- commit tokens;
- commit Instagram cookies;
- commit session files;
- expose secrets in logs.

Never use real user credentials or production data in tests.

## Documentation maintenance

Documentation is part of the project and must stay synchronized with the code.

After completing a major task:

1. Update `docs/STATUS.md`.
2. Describe:
   - what was implemented;
   - what changed;
   - current project state;
   - next steps.

If architecture, data flow, or service boundaries change:
- update `docs/ARCHITECTURE.md`.

For important architectural decisions:
- create an ADR inside `docs/adr/`.

Do not change product scope without explicit confirmation.

## Git workflow

GitHub is the main source of project history, backup, and rollback.

After every major logical change:

1. Run relevant tests and checks.
2. Review Git diff.
3. Verify there are no secrets or temporary files.
4. Update documentation if needed.
5. Create a clear Git commit.
6. Push changes to GitHub.

Major changes include:
- new features;
- new services;
- database changes;
- API changes;
- architecture changes;
- completed milestones;
- large refactors.

Do not mix unrelated changes in one commit.

## Task workflow

Before implementing:
1. Read relevant documentation.
2. Understand existing architecture.
3. Explain the proposed approach.
4. List affected files.
5. Identify risks.

Before finishing:
1. Run tests/checks.
2. Review the diff.
3. Update documentation.
4. Report:
   - changed files;
   - executed commands;
   - remaining risks.