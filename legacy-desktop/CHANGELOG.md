# Changelog

All notable changes to Rosterm8. Newest first. Bump `version.py` and add an
entry here for every release.

## 0.1.0
- First standalone release. Rosterm8 is a staff-roster builder split out of
  the Guardian Discord bot into its own desktop app.
- Organizations: keep separate staff lists, shift types and rosters per org.
- Staff records with weekly availability and blackout dates.
- Named shift types with configurable headcounts.
- A deterministic fair-distribution scheduler that spreads shifts evenly
  across available staff.
- Clash rules to stop a staff member being rostered onto overlapping shifts.
- Roster history and export.
- Optional AI parsing of free-text availability, so staff can describe their
  hours in plain English instead of filling in a grid.
