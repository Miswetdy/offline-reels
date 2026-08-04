# Product

## Vision

Create a personal offline Reels experience.

The user should be able to:
- connect Instagram;
- prepare a personalized Reels feed;
- download videos;
- watch them offline through a vertical feed.

## MVP

The first version includes:

- collecting personalized Reels;
- downloading videos;
- storing videos;
- synchronizing with phone;
- offline playback;
- vertical swipe feed;
- watched status;
- storage management.

## Current Collector status

The production repository currently implements only the Collector architecture
foundation: states, integrity constraints and a migration. Users cannot connect
Instagram through the application yet, and no automatic collection or
normalization worker runs. The next planned step is an isolated Collector
service with fixture mode. The separate research spike is not product runtime.

## Out of scope

The first version does not include:

- comments;
- likes;
- replies;
- publishing;
- social features;
- custom recommendations.
